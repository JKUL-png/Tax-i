"""
El cimiento común de todas las direcciones de la API.

Aquí vive UNA sola Aplicacion. Cada archivo de app/api/ la importa de
aquí y le cuelga sus direcciones; por eso importar un archivo de api/ es
lo que hace que sus rutas existan. De eso se encarga app/main.py, que
los importa todos.

Antes esto era un solo archivo de 1.175 líneas con once asuntos
distintos adentro. Se partió en agosto de 2026 porque cada función nueva
lo empeoraba. No cambió ni una dirección, ni un código de respuesta, ni
un texto: solo dónde está escrito cada pedazo.

Nota: no se registra en los logs ningún nombre de cliente ni contenido
de documentos. Solo errores técnicos.
"""

from datetime import date
from pathlib import Path

from app import db
from app.servidor import Aplicacion, ErrorHttp, Respuesta

# Raíz del proyecto. Este archivo vive en app/api/, así que subimos dos
# niveles. Se usa pathlib (y no texto pegado con / o \) para que las
# rutas funcionen igual en Mac y en Windows.
RAIZ = Path(__file__).resolve().parent.parent.parent
CARPETA_STATIC = RAIZ / "static"

app = Aplicacion()

# Deja disponibles el CSS y el JavaScript en /static/...
app.carpeta_estatica("/static/", CARPETA_STATIC)


def _pagina(nombre):
    """Entrega uno de los archivos HTML de la carpeta static."""
    return Respuesta.archivo(CARPETA_STATIC / nombre, tipo="text/html; charset=utf-8")


def cliente_o_404(id_cliente):
    """Devuelve el cliente, o corta la petición con un 404 si no existe."""
    cliente = db.obtener_cliente(id_cliente)
    if cliente is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    return cliente


# ----------------------------------------------------------
# Validación de los datos que llegan del navegador
#
# Todo lo que manda el navegador se revisa aquí antes de tocar la base.
#
# Antes esto lo hacían unas clases de pydantic. Ahora son funciones
# sueltas, que hacen lo mismo y se leen igual de fácil: mirar el valor,
# y si está mal, levantar un error con el texto que va a ver el contador.
# ----------------------------------------------------------

# Marca de "este campo no lo mandaron", distinta de "lo mandaron vacío".
# Sirve para saber si hay que borrar un dato o dejarlo como estaba.
NO_MANDADO = ...


def limpiar_nombre(valor):
    """Quita espacios sobrantes y verifica que quede algo."""
    if valor is None:
        return None
    limpio = " ".join(str(valor).split())
    if not limpio:
        raise ValueError("El nombre no puede estar vacío.")
    if len(limpio) > 120:
        raise ValueError("El nombre es demasiado largo.")
    return limpio


def limpiar_digitos(valor):
    """Verifica que sean dos dígitos. Acepta '5' y lo convierte en '05'."""
    if valor is None:
        return None
    limpio = str(valor).strip()
    if not limpio.isdigit() or len(limpio) > 2:
        raise ValueError(
            "Deben ser los dos últimos dígitos de la cédula, por ejemplo 07."
        )
    return limpio.zfill(2)


def limpiar_fecha(valor):
    """Acepta una fecha AAAA-MM-DD, o vacío si todavía no se sabe."""
    if valor is None:
        return None
    limpio = str(valor).strip()
    if not limpio:
        return None
    try:
        date.fromisoformat(limpio)
    except ValueError:
        raise ValueError("La fecha no es válida.")
    return limpio


def revisado(funcion, valor):
    """Aplica una de las funciones de arriba y convierte su queja en un 400.

    Los textos de ValueError están escritos para que los lea el contador,
    así que se le pasan tal cual a la pantalla.
    """
    try:
        return funcion(valor)
    except ValueError as error:
        raise ErrorHttp(400, str(error))


def campo(datos, nombre, por_defecto=None):
    """Saca un campo del JSON que mandó el navegador."""
    return datos.get(nombre, por_defecto)


def campo_texto(datos, nombre, por_defecto=""):
    """Saca un campo y comprueba que sea texto."""
    valor = datos.get(nombre, por_defecto)
    if valor is None:
        return por_defecto
    if not isinstance(valor, str):
        raise ErrorHttp(400, "El campo '%s' tiene que ser texto." % nombre)
    return valor


def campo_numero(datos, nombre):
    """Saca un campo y comprueba que sea un número."""
    valor = datos.get(nombre)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorHttp(400, "El campo '%s' tiene que ser un número." % nombre)
    return float(valor)


def campo_si_o_no(datos, nombre):
    """Saca un campo y comprueba que sea sí o no."""
    valor = datos.get(nombre)
    if not isinstance(valor, bool):
        raise ErrorHttp(400, "El campo '%s' tiene que ser sí o no." % nombre)
    return valor


def campo_lista_de_numeros(datos, nombre):
    """Saca una lista de números enteros. Se usa para las selecciones en lote.

    La pantalla manda, por ejemplo, {"ids": [3, 7, 12]}. Aquí se comprueba
    que sea de verdad una lista de números y no cualquier otra cosa, porque
    con esa lista se van a borrar archivos.
    """
    valor = datos.get(nombre)
    if not isinstance(valor, list):
        raise ErrorHttp(400, "El campo '%s' tiene que ser una lista." % nombre)
    numeros = []
    for elemento in valor:
        if isinstance(elemento, bool) or not isinstance(elemento, int):
            raise ErrorHttp(
                400, "El campo '%s' solo admite números enteros." % nombre
            )
        numeros.append(elemento)
    return numeros
