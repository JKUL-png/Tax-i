"""
Sacarle los datos a un documento UNA sola vez y guardarlos en la base.

El problema que resuelve
------------------------
El modelo de IA no tiene memoria. Cada vez que se le pregunta algo hay
que volver a contarle todo desde cero. Antes eso significaba remandarle
el texto de los documentos del cliente en CADA pregunta: se pagaba el
mismo certificado diez veces, y cada respuesta se demoraba lo que se
demora leerlos otra vez.

La memoria del sistema es la base de datos, no el modelo. Aquí se lee
cada documento una vez, lo que se le sacó queda en `datos_extraidos`, y
de ahí en adelante las preguntas se contestan con esas filas.

Tres cosas se ganan:

  1. Se paga una vez por documento, no una vez por pregunta.
  2. Las respuestas salen al instante: ya no hay que releer nada.
  3. Lo ya extraído se sigue viendo con IA_PROVEEDOR=ninguno. Está en
     este computador; no hay a quién preguntarle.

Quién lee qué
-------------
Es la regla del proyecto: **el código maneja los datos, la IA maneja lo
desordenado.**

  - Un **XML** de factura electrónica trae los campos ya separados y con
    nombre. Eso lo lee el programa, con `lectura.leer_xml`. Es exacto, es
    gratis, no sale del computador y no se le pregunta a nadie. Un XML
    NUNCA se le manda a la IA.

  - Un **PDF** o un texto suelto no tiene estructura. De ahí el texto se
    extrae aquí, en el computador, y solo ese texto —nunca el archivo—
    es lo que se le puede mandar al modelo para que diga qué encontró.

Lo que sale de aquí NO es una decisión
--------------------------------------
Todo lo que saca el modelo queda marcado con origen 'ia', y en pantalla
se muestra como LECTURA AUTOMÁTICA, junto a un enlace para abrir el
documento original. El contador verifica. Nada de esto entra solo al
Formulario 210: para eso está `formulario.guardar_valor`, y ahí lo pone
él.

Y no se le pide al modelo que sume, que compare cifras ni que decida
fechas. Se le pide una sola cosa: qué dice el documento.
"""

import json

from app import db, documentos, instrucciones, lectura, proveedores
from app.configuracion import CONFIG

# Cuánto texto de un documento se le manda al modelo. Un certificado de
# ingresos cabe de sobra; con más, se gasta cupo sin sacar más datos.
LETRAS_QUE_SE_MANDAN = 4000

# Techo de datos por documento. Si un modelo se entusiasma y devuelve
# cincuenta filas, algo entendió mal: se corta.
DATOS_MAXIMOS = 25


class SinIA(Exception):
    """Hacía falta la IA para leer este documento y está apagada."""


def _texto_del_archivo(documento):
    """El texto de un documento del disco. Devuelve (texto, motivo)."""
    ruta = documentos.ruta_del_documento(
        documento["cliente_id"], documento["nombre_guardado"]
    )
    if ruta is None or not ruta.exists():
        return "", "El archivo ya no está en el disco."
    return lectura.texto_del_documento(
        documento["nombre_guardado"], ruta.read_bytes()
    )


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

    datos = []
    for clave, valor in campos.items():
        # El total es la única cifra; lo demás son identificaciones.
        es_cifra = clave == "total"
        datos.append({
            "concepto": NOMBRES.get(clave, clave),
            "valor": valor if es_cifra else "",
            "detalle": "" if es_cifra else valor,
        })
    return datos


def _pedirle_al_modelo(texto):
    """Una llamada al modelo. Devuelve la lista de datos crudos, o None.

    None significa «contestó algo que no era el JSON que se le pidió».
    Es distinto de [], que significa «leyó el documento y no encontró
    nada», y esa diferencia importa: lo primero se reintenta, lo
    segundo no.
    """
    contenido = proveedores.conversar(CONFIG, [
        {"role": "system", "content": instrucciones.EXTRAER},
        {"role": "user",
         "content": "Documento:\n\n" + texto[:LETRAS_QUE_SE_MANDAN]},
    ])

    # El modelo a veces envuelve el JSON en ```json ... ```. Se le quita.
    limpio = (contenido or "").strip()
    if limpio.startswith("```"):
        limpio = limpio.split("```")[1] if "```" in limpio[3:] else limpio[3:]
        if limpio.lstrip().lower().startswith("json"):
            limpio = limpio.lstrip()[4:]

    try:
        entendido = json.loads(limpio.strip())
    except ValueError:
        return None

    crudos = entendido.get("datos") if isinstance(entendido, dict) else entendido
    if not isinstance(crudos, list):
        return None

    limpios = []
    for dato in crudos[:DATOS_MAXIMOS]:
        if not isinstance(dato, dict):
            continue
        concepto = str(dato.get("concepto", "")).strip()
        if not concepto:
            continue
        limpios.append({
            "concepto": concepto,
            "valor": str(dato.get("valor", "") or "").strip(),
            "detalle": str(dato.get("detalle", "") or "").strip(),
            # La frase del documento de donde salió. Es lo que después
            # se busca en el texto para saber si el dato es de verdad.
            "cita": str(dato.get("cita", "") or "").strip(),
        })
    return limpios


def _datos_con_ia(texto):
    """Le pregunta al modelo qué dice el texto y VERIFICA lo que conteste.

    Devuelve (verificados, sin_verificar, hubo_respuesta).

    Dos cosas pasan aquí, y las dos son defensas:

    1. Si contesta algo que no es el JSON pedido, se reintenta UNA vez.
       Una respuesta a medias no se acepta nunca: o sale bien, o el
       documento queda para que lo revise el contador.

    2. De cada dato se exige la frase exacta del documento de donde
       salió, y esa frase se busca en el texto. La que no aparece, no se
       guarda. El modelo puede inventarse un número; no puede
       inventarse una frase y que además esté en el papel.
    """
    if not CONFIG.ia_disponible:
        raise SinIA(CONFIG.motivo)

    crudos = _pedirle_al_modelo(texto)
    if crudos is None:
        # Segundo y último intento. Si vuelve a contestar cualquier
        # cosa, no se insiste: se gastaría cupo sin ganar nada.
        crudos = _pedirle_al_modelo(texto)
    if crudos is None:
        return [], [], False

    verificados, sin_verificar = instrucciones.revisar_datos(crudos, texto)
    return verificados, sin_verificar, True


def extraer(documento):
    """Le saca los datos a un documento y los guarda. Devuelve un informe.

    Nunca lanza una excepción por que el documento sea ilegible o por que
    el servicio de IA falle: en esos casos el documento queda marcado
    como 'fallo' con el motivo, y el programa sigue. Un documento malo no
    puede trabar el trabajo de los demás.

        {"documento_id": 12, "estado": "listo",
         "cuantos": 4, "origen": "codigo", "motivo": ""}
    """
    id_documento = documento["id"]
    informe = {
        "documento_id": id_documento,
        "nombre": documento["nombre_original"],
        "estado": "fallo",
        "cuantos": 0,
        "origen": "",
        "motivo": "",
    }

    db.marcar_lectura(id_documento, "leyendo")

    try:
        # 1. Si es un XML, lo lee el programa. No se le pregunta a nadie.
        datos = _datos_del_xml(documento)
        if datos is not None:
            db.guardar_datos_extraidos(
                documento["cliente_id"], id_documento, datos, "codigo"
            )
            db.marcar_lectura(id_documento, "listo")
            informe.update(estado="listo", cuantos=len(datos), origen="codigo")
            return informe

        # 2. Si no, se saca el texto aquí y solo el texto puede salir.
        texto, motivo = _texto_del_archivo(documento)
        if not texto.strip():
            db.marcar_lectura(id_documento, "fallo", motivo)
            informe["motivo"] = motivo or "No se pudo sacar texto del archivo."
            return informe

        verificados, sin_verificar, contesto = _datos_con_ia(texto)

        if not contesto:
            # Contestó dos veces algo que no era lo que se le pidió. No
            # se acepta a medias: queda para revisión manual.
            motivo = ("El modelo contestó algo que no se pudo entender, dos"
                      " veces. Revise este documento a mano.")
            db.marcar_lectura(id_documento, "fallo", motivo)
            informe["motivo"] = motivo
            return informe

        if sin_verificar and not verificados:
            # Todo lo que dijo que leyó, lo dijo sin poder mostrar dónde
            # lo vio. Eso NO se guarda: es exactamente el caso que la
            # cita textual existe para atrapar.
            motivo = ("Lo que el modelo dijo haber leído no aparece en el"
                      " documento, así que no se guardó nada. Revíselo a"
                      " mano.")
            db.marcar_lectura(id_documento, "fallo", motivo)
            informe["motivo"] = motivo
            informe["sin_verificar"] = len(sin_verificar)
            return informe

        db.guardar_datos_extraidos(
            documento["cliente_id"], id_documento, verificados, "ia"
        )
        aviso = ""
        if sin_verificar:
            aviso = ("%d dato(s) no se pudieron verificar contra el"
                     " documento y no se guardaron." % len(sin_verificar))
        db.marcar_lectura(id_documento, "listo", aviso)
        informe.update(estado="listo", cuantos=len(verificados), origen="ia",
                       motivo=aviso, sin_verificar=len(sin_verificar))
        return informe

    except SinIA as error:
        # La IA está apagada y este documento la necesitaba. No es un
        # fallo del documento: queda pendiente, para cuando se prenda.
        db.marcar_lectura(id_documento, "pendiente", str(error))
        informe.update(estado="pendiente", motivo=str(error))
        return informe

    except proveedores.ErrorDeProveedor as error:
        db.marcar_lectura(id_documento, "fallo", str(error))
        informe["motivo"] = str(error)
        return informe

    except Exception:
        # Cualquier otra cosa. El detalle técnico NO se guarda ni se
        # muestra: podría traer texto del documento, y eso no puede
        # quedar en un mensaje de error ni en los registros.
        motivo = "No se pudo leer este documento."
        db.marcar_lectura(id_documento, "fallo", motivo)
        informe["motivo"] = motivo
        return informe


def extraer_con_reintento(documento):
    """Como `extraer`, pero dándole una segunda oportunidad si falla.

    Un fallo casi siempre es pasajero: el servicio estaba ocupado, se cayó
    la conexión un segundo. Por eso se intenta otra vez antes de darlo por
    perdido.

    Solo se reintenta lo que puede cambiar. Un archivo del que no se puede
    sacar texto —una foto escaneada, un .zzz— va a fallar igual la segunda
    vez: eso no se reintenta, porque sería gastar cupo para nada.

    Si vuelve a fallar queda marcado y ya. La cola sigue con los demás:
    un documento malo no puede trabar la fila.
    """
    informe = extraer(documento)
    if informe["estado"] != "fallo":
        return informe

    # Lo que no cambia por reintentar: el archivo no está, o de ese tipo
    # de archivo no se puede sacar texto.
    motivo = (informe["motivo"] or "").lower()
    if "no se puede sacar texto" in motivo or "ya no está en el disco" in motivo:
        return informe

    segundo = extraer(documento)
    segundo["reintentado"] = True
    return segundo


def extraer_pendientes(cliente_id=None, seguir=None):
    """Lee los documentos que estén sin leer, uno por uno.

    Sin `cliente_id` lee los de todos los clientes, que es lo que hace la
    cola de fondo. `seguir` es una función que se pregunta antes de cada
    documento: si devuelve False, se para ahí y lo que falta queda
    pendiente para después. Sirve para poder apagar el programa sin
    esperar a que termine toda la fila.

    Si uno falla, se anota y se sigue con los demás. Devuelve un informe
    por documento.
    """
    informes = []
    for documento in db.documentos_sin_leer(cliente_id):
        if seguir is not None and not seguir():
            break
        informes.append(extraer_con_reintento(documento))
    return informes


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
