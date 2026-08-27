"""
Lo que el programa puede leer de un documento SIN inteligencia artificial.

Regla del proyecto: el código maneja los datos, la IA maneja lo desordenado.
Todo lo que está aquí es código: es exacto, es gratis, funciona sin
internet y no manda nada a ninguna parte.

Dos cosas hace:

  1. **Leer el XML de una factura electrónica.** Ese formato (UBL 2.1)
     ya trae los campos separados y con nombre. Mandárselo a una IA
     sería más lento, más caro y menos confiable que leerlo.

  2. **Sugerir a qué renglón del checklist se parece un archivo**, por
     las palabras de su nombre. Es una sugerencia, no una decisión: se
     muestra marcada como tal y el contador confirma.
"""

import re
import unicodedata
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
