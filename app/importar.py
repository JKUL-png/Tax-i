"""
Lectura de la lista de clientes desde un archivo de Excel o CSV.

Esto NO usa inteligencia artificial, a propósito. Un Excel con columnas
es información ordenada: leerla con código es exacto, gratis, instantáneo,
funciona sin internet y —lo más importante— las cédulas de los clientes
no salen del computador.

Lo que hace es proponer: lee el archivo y arma una lista de clientes
sugeridos. No guarda nada. El contador revisa, corrige lo que esté mal
y solo entonces se crean.

Nota de privacidad: la cédula completa se usa únicamente para sacar los
dos últimos dígitos. La cédula entera nunca se guarda en la base.
"""

import csv
import io
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

# Topes, para que un archivo enorme no deje el programa colgado.
LIMITE_ARCHIVO = 10 * 1024 * 1024   # 10 MB
LIMITE_FILAS = 2000


# ----------------------------------------------------------
# Reconocer los encabezados
#
# Cada contador arma su Excel a su manera. Aquí está la lista de las
# formas más comunes de escribir cada columna. Si el archivo trae un
# encabezado que no está en esta lista, la pantalla le deja al contador
# asignarlo a mano: no se adivina.
# ----------------------------------------------------------

SINONIMOS = {
    "nombre": [
        "nombre", "nombres", "nombre completo", "nombre del cliente",
        "cliente", "contribuyente", "razon social", "apellidos y nombres",
        "nombres y apellidos", "titular",
    ],
    "cedula": [
        "cedula", "cc", "c c", "documento", "no documento",
        "numero de documento", "num documento", "identificacion",
        "no identificacion", "numero de identificacion", "nit",
        "cedula de ciudadania", "doc", "id",
    ],
    "dos_digitos": [
        "dos digitos", "ultimos dos digitos", "ultimos digitos",
        "dos ultimos digitos", "digitos", "ultimos 2 digitos",
    ],
    "fecha_vencimiento": [
        "fecha", "fecha de vencimiento", "fecha vencimiento", "vencimiento",
        "vence", "plazo", "fecha limite", "fecha maxima", "fecha plazo",
        "fecha de presentacion",
    ],
}


def normalizar(texto):
    """Deja un encabezado en su forma más simple para poder compararlo.

    'Fecha de Vencimiento:' y 'FECHA DE VENCIMIENTO' quedan los dos como
    'fecha de vencimiento'. Quita tildes, mayúsculas y puntuación.
    """
    if texto is None:
        return ""
    texto = str(texto).strip().lower()
    # Quita las tildes: 'cédula' -> 'cedula'
    texto = "".join(
        letra for letra in unicodedata.normalize("NFD", texto)
        if unicodedata.category(letra) != "Mn"
    )
    # Cambia cualquier signo por un espacio y junta los espacios repetidos.
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return " ".join(texto.split())


def reconocer_columnas(encabezados):
    """Dice qué columna es cuál. Devuelve {campo: número de columna}.

    Solo asigna cuando el encabezado coincide exactamente con uno de los
    sinónimos conocidos. Prefiere no adivinar y dejar que el contador
    escoja, antes que meter la cédula en la casilla equivocada.
    """
    encontradas = {}
    for numero, encabezado in enumerate(encabezados):
        limpio = normalizar(encabezado)
        if not limpio:
            continue
        for campo, opciones in SINONIMOS.items():
            if campo in encontradas:
                continue          # ya se encontró esta columna antes
            if limpio in opciones:
                encontradas[campo] = numero
                break
    return encontradas


# ----------------------------------------------------------
# Leer los valores de cada casilla
# ----------------------------------------------------------


def texto_de_casilla(valor):
    """Convierte lo que venga en la casilla en texto limpio.

    Excel a veces devuelve números donde uno esperaría texto: una cédula
    puede llegar como 1000000001.0 en vez de "1000000001".
    """
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%Y-%m-%d")
    return str(valor).strip()


def sacar_dos_digitos(valor):
    """Saca los dos últimos dígitos de una cédula.

    Devuelve (dos_digitos, aviso). El aviso es None si todo salió bien.
    La cédula completa se descarta aquí mismo: no se devuelve ni se guarda.
    """
    texto = texto_de_casilla(valor)
    if not texto:
        return "", None

    solo_numeros = re.sub(r"\D", "", texto)
    if len(solo_numeros) < 2:
        return "", "la cédula no tiene suficientes dígitos"

    return solo_numeros[-2:], None


# Una fecha suelta como 05/08/2026 es ambigua: puede ser el 5 de agosto
# (orden colombiano) o el 8 de mayo (orden gringo). Pero una COLUMNA entera
# casi nunca lo es: basta con que una sola fila diga 14/10/2026 para saber
# que ese archivo escribe día/mes, porque no existe el mes 14.
# Por eso primero se mira toda la columna y después se leen las fechas.

PATRON_FECHA_SUELTA = re.compile(r"^\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{2,4})\s*$")


def detectar_orden_de_fecha(valores):
    """Mira toda la columna de fechas y decide si es día/mes o mes/día.

    Devuelve ("DMA" o "AMD-invertido", seguro) donde `seguro` dice si se
    encontró una prueba en el archivo o si se está asumiendo.
    """
    primero_grande = False
    segundo_grande = False

    for valor in valores:
        # Las fechas que Excel guarda como fecha de verdad no son ambiguas.
        if isinstance(valor, (datetime, date)):
            continue
        coincidencia = PATRON_FECHA_SUELTA.match(texto_de_casilla(valor))
        if not coincidencia:
            continue
        primero = int(coincidencia.group(1))
        segundo = int(coincidencia.group(2))
        if primero > 12:
            primero_grande = True     # el primer número no puede ser un mes
        if segundo > 12:
            segundo_grande = True     # el segundo número no puede ser un mes

    if primero_grande and not segundo_grande:
        return "dia_primero", True
    if segundo_grande and not primero_grande:
        return "mes_primero", True

    # Sin pruebas en el archivo: se asume el orden colombiano y se avisa.
    return "dia_primero", False


def sacar_fecha(valor, orden="dia_primero"):
    """Convierte lo que haya en la casilla en una fecha AAAA-MM-DD.

    Devuelve (fecha, aviso). Si no se entiende, devuelve fecha vacía y el
    motivo: es preferible dejarla en blanco para que el contador la
    escriba, antes que inventar una fecha de vencimiento.
    """
    if valor is None or texto_de_casilla(valor) == "":
        return "", None

    # Excel guarda las fechas como fechas de verdad: ese es el caso fácil.
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%Y-%m-%d"), None

    texto = texto_de_casilla(valor)

    # Formato AAAA-MM-DD: no es ambiguo, se prueba primero.
    try:
        leida = datetime.strptime(texto, "%Y-%m-%d")
        return leida.strftime("%Y-%m-%d"), None
    except ValueError:
        pass

    coincidencia = PATRON_FECHA_SUELTA.match(texto)
    if coincidencia:
        primero = int(coincidencia.group(1))
        segundo = int(coincidencia.group(2))
        anio = int(coincidencia.group(3))
        if anio < 100:
            anio += 2000

        if orden == "dia_primero":
            dia, mes = primero, segundo
        else:
            mes, dia = primero, segundo

        try:
            return date(anio, mes, dia).strftime("%Y-%m-%d"), None
        except ValueError:
            return "", "la fecha no existe en el calendario"

    return "", "no se entendió la fecha, escríbala a mano"


# ----------------------------------------------------------
# Abrir el archivo
# ----------------------------------------------------------


def leer_xlsx(contenido):
    """Saca las filas de un archivo de Excel. Devuelve una lista de listas."""
    # Se importa aquí adentro y no arriba para que, si openpyxl no está
    # instalado, el resto del programa siga funcionando y el error salga
    # solo cuando alguien intente subir un Excel.
    try:
        import openpyxl
    except ImportError:
        raise ValueError(
            "Falta la librería para leer Excel. Cierre el programa y"
            " vuelva a abrirlo con iniciar.sh (o iniciar.bat en Windows)."
        )

    try:
        libro = openpyxl.load_workbook(
            io.BytesIO(contenido), read_only=True, data_only=True
        )
    except Exception:
        raise ValueError("No se pudo abrir el archivo de Excel. ¿Está dañado?")

    hoja = libro.worksheets[0]     # la primera hoja
    filas = []
    for fila in hoja.iter_rows(values_only=True):
        filas.append(list(fila))
        if len(filas) > LIMITE_FILAS + 20:
            break
    libro.close()
    return filas


def leer_csv(contenido):
    """Saca las filas de un archivo CSV.

    Dos problemas típicos que se resuelven aquí:
      - El Excel de Windows en español guarda los CSV con punto y coma
        en vez de coma.
      - Y los guarda en cp1252, no en UTF-8, así que las tildes se dañan
        si uno no lo tiene en cuenta.
    """
    texto = None
    for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = contenido.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ValueError("No se pudo leer el archivo CSV.")

    # Detectar si separa con coma o con punto y coma.
    primera_linea = texto.split("\n", 1)[0]
    separador = ";" if primera_linea.count(";") > primera_linea.count(",") else ","

    filas = []
    for fila in csv.reader(io.StringIO(texto), delimiter=separador):
        filas.append(fila)
        if len(filas) > LIMITE_FILAS + 20:
            break
    return filas


def leer_archivo(nombre, contenido):
    """Abre el archivo según su extensión y devuelve sus filas."""
    extension = Path(nombre).suffix.lower()
    if extension == ".xlsx":
        return leer_xlsx(contenido)
    if extension == ".csv":
        return leer_csv(contenido)
    if extension == ".xls":
        raise ValueError(
            "El formato .xls es muy antiguo. Ábralo en Excel y guárdelo"
            " como .xlsx, o como CSV."
        )
    raise ValueError("Solo se pueden leer archivos .xlsx y .csv.")


# ----------------------------------------------------------
# Armar la propuesta
# ----------------------------------------------------------


def buscar_encabezados(filas):
    """Busca en qué fila están los títulos de las columnas.

    No siempre es la primera: muchos Excel traen arriba un título o
    renglones vacíos. Se toma la primera fila que tenga al menos una
    columna reconocible.
    """
    for numero, fila in enumerate(filas[:15]):
        columnas = reconocer_columnas(fila)
        if columnas:
            return numero, columnas
    return None, {}


def analizar(nombre_archivo, contenido, nombres_existentes):
    """Lee el archivo y arma la lista de clientes propuestos.

    `nombres_existentes` son los clientes que ya están en la base, para
    poder avisar de los repetidos.

    Devuelve un diccionario con las columnas reconocidas, los encabezados
    tal como venían, y las filas propuestas. NO guarda nada.
    """
    filas = leer_archivo(nombre_archivo, contenido)

    if not filas:
        raise ValueError("El archivo está vacío.")

    numero_encabezado, columnas = buscar_encabezados(filas)

    if numero_encabezado is None:
        raise ValueError(
            "No se reconoció ninguna columna. El archivo debe tener una fila"
            " de títulos con al menos 'Nombre' y 'Cédula'."
        )

    if "nombre" not in columnas:
        raise ValueError(
            "No se encontró la columna del nombre del cliente."
            " Revise que el título diga 'Nombre' o 'Cliente'."
        )

    encabezados = [texto_de_casilla(c) for c in filas[numero_encabezado]]

    # Columnas que no se reconocieron: su contenido se guarda como notas,
    # para no perder información que el contador puso ahí a propósito.
    usadas = set(columnas.values())
    otras = [
        (numero, encabezados[numero])
        for numero in range(len(encabezados))
        if numero not in usadas and encabezados[numero]
    ]

    # Antes de leer fila por fila, se mira la columna de fechas completa
    # para saber si el archivo escribe día/mes o mes/día.
    columna_fecha = columnas.get("fecha_vencimiento")
    valores_fecha = []
    if columna_fecha is not None:
        for fila in filas[numero_encabezado + 1:]:
            if columna_fecha < len(fila):
                valores_fecha.append(fila[columna_fecha])
    orden_fecha, orden_seguro = detectar_orden_de_fecha(valores_fecha)

    propuestas = []
    vistos_en_el_archivo = set()

    for fila in filas[numero_encabezado + 1:]:
        if len(propuestas) >= LIMITE_FILAS:
            break

        def casilla(campo):
            numero = columnas.get(campo)
            if numero is None or numero >= len(fila):
                return None
            return fila[numero]

        nombre = texto_de_casilla(casilla("nombre"))
        nombre = " ".join(nombre.split())

        # Fila completamente vacía: se salta en silencio.
        if not nombre and not texto_de_casilla(casilla("cedula")):
            continue

        avisos = []

        # --- Dos dígitos: de la columna directa, o sacados de la cédula ---
        dos_digitos = ""
        if "dos_digitos" in columnas:
            crudo = re.sub(r"\D", "", texto_de_casilla(casilla("dos_digitos")))
            if crudo:
                dos_digitos = crudo[-2:].zfill(2)
        if not dos_digitos:
            dos_digitos, aviso = sacar_dos_digitos(casilla("cedula"))
            if aviso:
                avisos.append(aviso)
            if dos_digitos:
                dos_digitos = dos_digitos.zfill(2)

        # --- Fecha ---
        fecha, aviso = sacar_fecha(casilla("fecha_vencimiento"), orden_fecha)
        if aviso:
            avisos.append(aviso)

        # --- Notas: lo que traían las columnas que no se reconocieron ---
        renglones_nota = []
        for numero, titulo in otras:
            if numero < len(fila):
                valor = texto_de_casilla(fila[numero])
                if valor:
                    renglones_nota.append(titulo + ": " + valor)
        notas = "\n".join(renglones_nota)

        # --- Revisiones ---
        if not nombre:
            avisos.append("falta el nombre")
        if not dos_digitos:
            avisos.append("faltan los dos dígitos de la cédula")
        if not fecha:
            avisos.append("sin fecha de vencimiento")

        clave = normalizar(nombre)
        repetido = False
        if clave and clave in nombres_existentes:
            avisos.append("ya hay un cliente con este nombre")
            repetido = True
        elif clave and clave in vistos_en_el_archivo:
            avisos.append("este nombre está repetido en el archivo")
            repetido = True
        if clave:
            vistos_en_el_archivo.add(clave)

        propuestas.append({
            "nombre": nombre,
            "dos_digitos": dos_digitos,
            "fecha_vencimiento": fecha,
            "notas": notas,
            "avisos": avisos,
            # Se marca para crear solo lo que está completo y no está
            # repetido. Un repetido se deja desmarcado para no crear dos
            # veces el mismo cliente sin querer; si de verdad son dos
            # personas distintas con el mismo nombre, el contador lo marca.
            "incluir": bool(nombre and dos_digitos and not repetido),
        })

    if not propuestas:
        raise ValueError("El archivo no tenía ninguna fila con datos.")

    # Si en todo el archivo no hubo forma de saber el orden de las fechas,
    # se avisa una sola vez arriba en vez de repetirlo en cada fila.
    aviso_fechas = None
    if valores_fecha and not orden_seguro:
        aviso_fechas = (
            "Las fechas se leyeron como día/mes/año. En este archivo no había"
            " forma de confirmarlo, así que verifíquelas antes de crear."
        )

    return {
        "encabezados": encabezados,
        "columnas_reconocidas": columnas,
        "columnas_ignoradas": [titulo for _, titulo in otras],
        "aviso_fechas": aviso_fechas,
        "propuestas": propuestas,
    }
