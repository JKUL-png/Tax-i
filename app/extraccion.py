"""
Leerle los datos a un XML de factura electrónica, con código y gratis.

Qué quedó aquí y qué se fue
---------------------------
Antes este archivo hacía dos cosas: leía los XML con código y le mandaba
al modelo el texto de cada PDF, uno por uno, para que dijera qué decía.
Esa segunda parte se fue en septiembre de 2026.

Se fue porque se pagaba dos veces por lo mismo. La pasada
(`app/pasada.py`) le manda al modelo el texto de TODOS los documentos
del cliente de una sola vez, junto con la exógena, y de ahí salen tanto
las propuestas del formulario como los datos sueltos de cada documento.
Leerlos antes uno por uno era mandar el mismo texto dos veces y cobrarlo
dos veces — y encima peor, porque al leerlos por separado el modelo no
podía mirar la exógena al lado.

Lo que quedó es lo que **no cuesta nada**: un XML de factura electrónica
trae los campos ya separados y con nombre. Eso lo lee el programa, es
exacto, no sale del computador y no hay a quién preguntarle. Por eso
corre solo al confirmar una carga, sin pedir permiso: la regla de la
casa es que lo gratis pasa sin preguntar y lo que cuesta lo pide el
contador.

Y se fue también la fila de fondo (`app/cola.py`). Existía porque leer
con IA se demoraba segundos por documento y no se podía dejar al
contador esperando. Parsear un XML tarda milisegundos: una fila con su
hilo, su candado y su rescate al arrancar era maquinaria para un
problema que ya no existe.

Dónde vive la memoria del sistema
---------------------------------
En la base de datos, igual que antes: la tabla `datos_extraidos`. Ahí
entra lo que se lee de los XML (origen 'codigo') y lo que devuelve la
pasada (origen 'pasada'), y de ahí sale lo que RentAI usa para
contestar. Los documentos no se vuelven a leer nunca.
"""

from app import db, documentos, lectura

# Cómo se llama cada campo del XML cuando se le muestra al contador.
NOMBRES = {
    "numero": "Número del documento",
    "fecha": "Fecha de emisión",
    "cufe": "CUFE (código único ante la DIAN)",
    "emisor": "Emisor",
    "nit_emisor": "NIT del emisor",
    "receptor": "Receptor",
    "total": "Total del documento",
    "moneda": "Moneda",
}


def _datos_del_xml(documento):
    """Los datos de un XML de factura, leídos por el programa.

    Sin IA, sin internet y sin margen de error: el formato UBL 2.1 trae
    cada campo con su nombre. Devuelve None si no era un XML legible.
    """
    ruta = documentos.ruta_del_documento(
        documento["cliente_id"], documento["nombre_guardado"]
    )
    if ruta is None or not ruta.exists():
        return None

    campos = lectura.leer_xml(ruta.read_bytes())
    if not campos:
        return None

    datos = []
    for clave, valor in campos.items():
        # El total es la única cifra; lo demás son identificaciones.
        es_cifra = clave == "total"
        datos.append({
            "concepto": NOMBRES.get(clave, clave),
            "valor": valor if es_cifra else "",
            "detalle": "" if es_cifra else valor,
            # La cita de un XML es el propio campo: no hay frase de la
            # que dudar, porque no lo leyó un modelo.
            "cita": "",
        })
    return datos


def extraer(documento):
    """Lee un documento si es un XML. Devuelve un informe corto.

    Nunca lanza una excepción por que el documento sea ilegible: en ese
    caso queda marcado con el motivo y el programa sigue. Un documento
    malo no puede trabar el trabajo de los demás.

        {"documento_id": 12, "estado": "listo", "cuantos": 4,
         "origen": "codigo", "motivo": ""}

    Un PDF o una foto NO se leen aquí y eso no es un fallo: quedan
    'pendiente', y su texto se lee en la pasada, todo junto.
    """
    id_documento = documento["id"]
    informe = {
        "documento_id": id_documento,
        "nombre": documento["nombre_original"],
        "estado": "pendiente",
        "cuantos": 0,
        "origen": "",
        "motivo": "",
    }

    try:
        datos = _datos_del_xml(documento)
    except Exception:
        # El detalle técnico NO se guarda ni se muestra: podría traer
        # contenido del documento, y eso no puede quedar en un mensaje
        # de error ni en los registros.
        db.marcar_lectura(id_documento, "fallo", "No se pudo leer este XML.")
        informe.update(estado="fallo", motivo="No se pudo leer este XML.")
        return informe

    if datos is None:
        informe["motivo"] = (
            "Se lee con la propuesta del formulario, junto con los demás."
        )
        return informe

    db.guardar_datos_extraidos(
        documento["cliente_id"], id_documento, datos, "codigo"
    )
    db.marcar_lectura(id_documento, "listo")
    informe.update(estado="listo", cuantos=len(datos), origen="codigo")
    return informe


def leer_xml_pendientes(cliente_id=None):
    """Lee los XML que estén sin leer. Devuelve un informe por documento.

    Se llama de una, sin hilos: parsear un XML tarda milisegundos y
    quien la llama puede esperar sin que se note.
    """
    return [extraer(documento) for documento in db.documentos_sin_leer(cliente_id)]


def resumen(cliente_id):
    """En qué va la lectura de los documentos de un cliente."""
    conteo = {"pendiente": 0, "leyendo": 0, "listo": 0, "fallo": 0}
    for documento in db.listar_documentos(cliente_id):
        estado = documento.get("estado_lectura") or "pendiente"
        if estado in conteo:
            conteo[estado] += 1
    return {
        "estados": conteo,
        "sin_leer": conteo["pendiente"] + conteo["leyendo"],
        "datos_guardados": len(db.listar_datos_extraidos(cliente_id)),
    }
