"""
Lo que el programa puede leer de un documento SIN inteligencia artificial.

Regla del proyecto: el código maneja los datos, la IA maneja lo desordenado.
Todo lo que está aquí es código: es exacto, es gratis, funciona sin
internet y no manda nada a ninguna parte.

Tres cosas hace:

  1. **Leer el XML de una factura electrónica.** Ese formato (UBL 2.1)
     ya trae los campos separados y con nombre. Mandárselo a una IA
     sería más lento, más caro y menos confiable que leerlo.

  2. **Sugerir a qué renglón del checklist se parece un archivo**, por
     las palabras de su nombre. Es una sugerencia, no una decisión: se
     muestra marcada como tal y el contador confirma.

  3. **Sacar el texto de un PDF.** El PDF no sale del computador: el
     texto se extrae aquí y solo ese texto es lo que después se le puede
     mandar a la IA. Los PDF que son una foto escaneada no tienen texto
     adentro y de esos no se saca nada; eso se dice, no se inventa.
"""

import re
import unicodedata
from pathlib import Path
from xml.etree import ElementTree

# Palabras que no distinguen nada: aparecen en casi todos los renglones
# y en casi todos los nombres de archivo.
PALABRAS_VACIAS = {
    "de", "del", "la", "el", "los", "las", "y", "o", "a", "en", "por",
    "para", "con", "un", "una", "al", "certificado", "certificados",
    "soporte", "soportes", "documento", "documentos", "archivo", "copia",
    "scan", "escaneado", "img", "image", "foto", "whatsapp", "pdf",
}


def normalizar(texto):
    """Deja un texto en minúsculas, sin tildes y sin signos."""
    if not texto:
        return ""
    texto = str(texto).lower()
    texto = "".join(
        letra for letra in unicodedata.normalize("NFD", texto)
        if unicodedata.category(letra) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def raiz_de_palabra(palabra):
    """Quita el plural, para que 'vehiculos' y 'vehiculo' se reconozcan.

    Es un recorte muy sencillo, no un analizador de gramática: alcanza
    para comparar nombres de archivo con renglones de un checklist.
    """
    if len(palabra) > 4 and palabra.endswith("es"):
        return palabra[:-2]
    if len(palabra) > 3 and palabra.endswith("s"):
        return palabra[:-1]
    return palabra


# Las palabras de relleno se recortan igual que las demás, porque si no
# "soportes" se convierte en "soport" y deja de reconocerse como relleno.
RAICES_VACIAS = {raiz_de_palabra(palabra) for palabra in PALABRAS_VACIAS}


def palabras_utiles(texto):
    """Saca las palabras que sí distinguen, quitando las de relleno."""
    return {
        raiz_de_palabra(palabra)
        for palabra in normalizar(texto).split()
        if len(palabra) > 2 and raiz_de_palabra(palabra) not in RAICES_VACIAS
    }


# ----------------------------------------------------------
# Sugerir el renglón del checklist
# ----------------------------------------------------------


def sugerir_renglon(nombre_archivo, renglones):
    """Adivina a qué renglón del checklist se parece un archivo.

    Compara las palabras del nombre del archivo con las de cada renglón.
    Devuelve (id_del_renglon, palabras_que_coincidieron) o (None, []).

    Es a propósito conservador: si no hay al menos dos palabras en común,
    o si dos renglones empatan, no sugiere nada. Prefiere quedarse
    callado antes que mandar el certificado de pensión a la casilla de
    los vehículos.
    """
    del_archivo = palabras_utiles(nombre_archivo)
    if not del_archivo:
        return None, []

    puntajes = []
    for renglon in renglones:
        del_renglon = palabras_utiles(renglon["titulo"])
        if not del_renglon:
            continue
        comunes = del_archivo & del_renglon

        # Se acepta con dos palabras en común, o con una sola cuando esa
        # palabra es TODO lo que distingue al renglón. Sin la segunda
        # regla, un renglón corto como "Soportes de vehículos" nunca
        # alcanzaría a sugerirse.
        suficiente = len(comunes) >= 2 or (
            len(comunes) >= 1 and comunes == del_renglon
        )
        if suficiente:
            puntajes.append((len(comunes), renglon["id"], sorted(comunes)))

    if not puntajes:
        return None, []

    puntajes.sort(reverse=True)
    mejor = puntajes[0]

    # Si hay empate, no se sugiere: no hay forma de saber cuál es.
    if len(puntajes) > 1 and puntajes[1][0] == mejor[0]:
        return None, []

    return mejor[1], mejor[2]


# ----------------------------------------------------------
# Leer el XML de una factura electrónica (UBL 2.1)
# ----------------------------------------------------------

# El XML de la DIAN usa "espacios de nombres": cada etiqueta viene con un
# prefijo largo. Estos son los que hacen falta para encontrar los campos.
ESPACIOS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}


def _texto(nodo, camino):
    """Busca un campo dentro del XML y devuelve su texto, o vacío."""
    if nodo is None:
        return ""
    encontrado = nodo.find(camino, ESPACIOS)
    if encontrado is None or encontrado.text is None:
        return ""
    return encontrado.text.strip()


def leer_xml(contenido):
    """Saca los datos de un XML de factura electrónica.

    Devuelve un diccionario con lo que encontró, o None si el archivo no
    es un XML que se pueda leer. Todos los valores salen tal cual del
    archivo: no se calcula ni se interpreta nada.
    """
    try:
        raiz = ElementTree.fromstring(contenido)
    except ElementTree.ParseError:
        return None

    # Algunas facturas vienen envueltas en otro XML (AttachedDocument):
    # la factura de verdad va adentro, como texto.
    if raiz.tag.endswith("AttachedDocument"):
        adentro = raiz.find(".//cac:Attachment/cac:ExternalReference"
                            "/cbc:Description", ESPACIOS)
        if adentro is not None and adentro.text:
            try:
                raiz = ElementTree.fromstring(adentro.text.strip())
            except ElementTree.ParseError:
                pass

    datos = {}

    numero = _texto(raiz, "cbc:ID")
    if numero:
        datos["numero"] = numero

    fecha = _texto(raiz, "cbc:IssueDate")
    if fecha:
        datos["fecha"] = fecha

    # El CUFE: el código único que identifica la factura ante la DIAN.
    cufe = _texto(raiz, "cbc:UUID")
    if cufe:
        datos["cufe"] = cufe

    emisor = raiz.find("cac:AccountingSupplierParty", ESPACIOS)
    if emisor is not None:
        nombre = _texto(emisor, ".//cbc:RegistrationName")
        if nombre:
            datos["emisor"] = nombre
        nit = _texto(emisor, ".//cbc:CompanyID")
        if nit:
            datos["nit_emisor"] = nit

    receptor = raiz.find("cac:AccountingCustomerParty", ESPACIOS)
    if receptor is not None:
        nombre = _texto(receptor, ".//cbc:RegistrationName")
        if nombre:
            datos["receptor"] = nombre

    # El total se toma como texto, tal como está escrito en el archivo.
    # El programa NO suma, NO convierte y NO compara cifras.
    total = _texto(raiz, ".//cac:LegalMonetaryTotal/cbc:PayableAmount")
    if total:
        datos["total"] = total
        moneda = raiz.find(".//cac:LegalMonetaryTotal/cbc:PayableAmount",
                           ESPACIOS)
        if moneda is not None:
            unidad = moneda.attrib.get("currencyID")
            if unidad:
                datos["moneda"] = unidad

    return datos or None


# ----------------------------------------------------------
# Texto de un PDF
# ----------------------------------------------------------

# Hasta cuántas páginas se leen de un PDF. Un certificado tiene una o
# dos; si llega uno de doscientas, no vale la pena leerlo entero para
# después recortarlo.
PAGINAS_QUE_SE_LEEN = 12

# Cuántas letras se conservan por documento.
LETRAS_POR_DOCUMENTO = 6000


def leer_pdf(contenido):
    """Saca el texto de un PDF. Devuelve (texto, motivo).

    Si no se pudo sacar nada, el texto viene vacío y el motivo explica
    por qué, en palabras que se le puedan mostrar al contador.

    Todo pasa en este computador: pypdf no se conecta a ninguna parte.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", (
            "Falta la librería pypdf para leer PDF. Se instala con:"
            " pip install -r requirements.txt"
        )

    from io import BytesIO

    try:
        lector = PdfReader(BytesIO(contenido))
    except Exception:
        return "", "No se pudo abrir el PDF. Puede estar dañado o con clave."

    if getattr(lector, "is_encrypted", False):
        return "", "El PDF tiene contraseña, así que no se puede leer."

    partes = []
    for pagina in lector.pages[:PAGINAS_QUE_SE_LEEN]:
        try:
            partes.append(pagina.extract_text() or "")
        except Exception:
            # Una página ilegible no debe tumbar la lectura de las otras.
            continue

    texto = "\n".join(partes).strip()
    # Los espacios de más y los saltos triples solo gastan espacio.
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)

    if not texto:
        return "", (
            "Este PDF no tiene texto adentro: es una foto escaneada. Para"
            " leerlo haría falta reconocimiento de imágenes, que todavía no"
            " está."
        )

    if len(texto) > LETRAS_POR_DOCUMENTO:
        texto = texto[:LETRAS_POR_DOCUMENTO] + "\n[…recortado]"

    return texto, ""


def texto_del_documento(nombre_guardado, contenido):
    """El texto que se puede sacar de un documento, sea del tipo que sea.

    Devuelve (texto, motivo). Es la puerta única: quien necesite el
    contenido de un documento pregunta aquí y no le importa si por dentro
    era un PDF, un XML o un texto plano.
    """
    extension = Path(nombre_guardado).suffix.lower()

    if extension == ".pdf":
        return leer_pdf(contenido)

    if extension == ".xml":
        datos = leer_xml(contenido)
        if not datos:
            return "", "El XML no parece una factura electrónica."
        renglones = [f"{nombre}: {valor}" for nombre, valor in datos.items()]
        return "\n".join(renglones), ""

    if extension in (".txt", ".csv"):
        try:
            return contenido.decode("utf-8", errors="replace")[
                :LETRAS_POR_DOCUMENTO], ""
        except Exception:
            return "", "No se pudo leer el archivo."

    return "", (
        f"De un archivo {extension or 'sin extensión'} todavía no se puede"
        f" sacar texto."
    )
