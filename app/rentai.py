"""
Rentai: la asistente que conversa sobre un cliente y propone qué anotar.

Qué hace y qué NO hace
----------------------
Rentai lee lo que ya está en el computador —los documentos del cliente, su
checklist, lo que ya se anotó en el formulario— y contesta preguntas sobre
eso. Cuando encuentra una cifra en un documento, **propone** anotarla en
una casilla de la plantilla. Propone: no escribe.

Nada de lo que dice Rentai entra al archivo solo. El contador ve cada
propuesta con el documento de donde salió y decide si la anota. Es la
regla del proyecto: todo dato que salga de una IA se muestra marcado como
lectura automática y con un enlace al original.

Rentai tampoco calcula impuestos, ni dice qué es deducible, ni sugiere
cómo declarar, ni afirma que alguien está obligado a declarar. Eso no es
prudencia: es la línea legal del proyecto, y está escrita en las
instrucciones que se le mandan al modelo y verificada aquí en el código.

Qué sale de este computador
---------------------------
Con SIN_IA=true (el valor por defecto) no sale nada y Rentai no funciona.
Con la IA encendida, a Groq le llega: el nombre del cliente, el texto de
sus documentos, su checklist y la conversación. Los archivos NO se mandan:
de un PDF se manda el texto que se extrajo aquí, nunca el archivo.

Se eligió Groq porque su capa gratis no cobra ni pide tarjeta y porque se
compromete a no entrenar modelos con lo que uno le manda ni a guardarlo.
Se descartó la capa gratis de Gemini justamente por lo contrario.
"""

import json
import urllib.error
import urllib.request

from app import db, documentos, formulario, lectura
from app.configuracion import CONFIG, SERVICIO
from app.plantilla_210 import TIPO_CAPTURA

# Cómo se llama. Está en una constante porque se ve en toda la pantalla.
NOMBRE = "Rentai"

# Cuánto se espera a que conteste antes de darse por vencido.
SEGUNDOS_DE_ESPERA = 60

# Cuántos mensajes anteriores se le recuerdan. Más que esto no ayuda y
# hace la conversación cara y lenta.
MENSAJES_QUE_RECUERDA = 12

# Cuántos documentos del cliente se le mandan, y cuánto texto de cada uno.
DOCUMENTOS_QUE_SE_MANDAN = 10
LETRAS_POR_DOCUMENTO = 2500


class RentaiApagada(Exception):
    """La IA está apagada o mal configurada. No es un error del programa."""


class RentaiFallo(Exception):
    """Se intentó hablar con el servicio y no se pudo."""


# ---------------------------------------------------------------------------
# Las instrucciones del modelo
#
# Esto es lo que Rentai "es". Se escribe en español porque en español
# trabaja, y se le repiten las prohibiciones más de una vez a propósito:
# es lo que más importa que no se le olvide.
# ---------------------------------------------------------------------------

INSTRUCCIONES = """\
Eres Rentai, la asistente de un contador colombiano. Trabajas dentro de un
programa que vive en el computador de él y que organiza los documentos de
sus clientes para la declaración de renta de personas naturales (Formulario
210, año gravable 2025).

TU TRABAJO
Leer lo que dicen los documentos del cliente y proponerle al contador qué
cifra anotar en cuál casilla de su plantilla de Excel. También contestarle
preguntas sobre qué llegó, qué falta y qué dice cada documento.

LO QUE NUNCA HACES
- No calculas el impuesto a cargo, ni el anticipo, ni el saldo a pagar, ni
  el saldo a favor. Esos los calcula la plantilla del contador, no tú.
- No dices qué es deducible y qué no.
- No sugieres cómo declarar ni cómo pagar menos.
- No afirmas que alguien está o no está obligado a declarar.
- No sumas, restas ni promedias cifras para inventar un total. Si el
  documento dice una cifra, propones esa cifra tal cual. Si hay que sumar
  varias, lo hace la plantilla con sus fórmulas.
- No escribes nada en el archivo. Solo propones; el contador decide.

Si te preguntan algo de eso, dices con naturalidad que no es lo tuyo y que
eso lo decide él. No te disculpas cinco veces ni das sermones: una frase.

CÓMO PROPONES
Cada propuesta lleva:
- celda: el código exacto de una casilla del catálogo que te dieron. Si la
  casilla que necesitas no está en el catálogo, NO te la inventes: dilo en
  la respuesta y no propongas nada.
- valor: un número entero en pesos, sin puntos, sin comas y sin el signo
  $. Ejemplo: 45000000.
- documento: el nombre exacto del documento de donde sacaste la cifra, tal
  como aparece en la lista. Si la cifra te la dictó el contador en el chat,
  escribe "dictado por el contador".
- por_que: una línea corta diciendo dónde lo viste. Ejemplo: "el
  certificado dice 'total ingresos laborales 45.000.000'".

Nunca propongas una cifra que no viste. Si el documento está borroso, si
es una foto sin texto o si dice algo distinto de lo que se necesita, dilo.
Es mejor decir "no lo encontré" que adivinar: el contador confía en que lo
que le muestras está en el papel.

CÓMO HABLAS
En español, corto y directo, sin jerga y sin adornos. Tuteas o ustedeas
según como te hablen. Si el contador te dice "anota 3 millones en caja",
propones esa anotación sin pedirle que lo repita de otra forma.

FORMATO DE RESPUESTA
Contestas SIEMPRE con un objeto JSON, sin texto por fuera:

{"respuesta": "lo que le dices al contador",
 "propuestas": [{"celda": "G115", "valor": 45000000,
                 "documento": "certificado_laboral.pdf",
                 "por_que": "dice 'total devengado 45.000.000'"}]}

Si no hay nada que proponer, "propuestas" va vacío: [].
"""


# ---------------------------------------------------------------------------
# Lo que Rentai sabe del cliente
# ---------------------------------------------------------------------------

# El texto de un documento no cambia, así que se recuerda en memoria y no
# se vuelve a sacar del PDF en cada mensaje.
_texto_recordado = {}


def texto_de_documento(documento):
    """El texto de un documento del cliente, o el motivo por el que no hay."""
    llave = (documento["id"], documento["tamano"])
    if llave in _texto_recordado:
        return _texto_recordado[llave]

    ruta = documentos.ruta_del_documento(
        documento["cliente_id"], documento["nombre_guardado"]
    )
    if not ruta.exists():
        resultado = ("", "El archivo ya no está en el disco.")
    else:
        resultado = lectura.texto_del_documento(
            documento["nombre_guardado"], ruta.read_bytes()
        )

    if len(_texto_recordado) > 60:
        _texto_recordado.clear()
    _texto_recordado[llave] = resultado
    return resultado


def resumen_de_documentos(cliente_id):
    """Los documentos del cliente con su texto, listos para contárselos."""
    lineas = []
    for documento in db.listar_documentos(cliente_id)[:DOCUMENTOS_QUE_SE_MANDAN]:
        texto, motivo = texto_de_documento(documento)
        encabezado = f"--- {documento['nombre_original']} ---"
        if texto:
            lineas.append(f"{encabezado}\n{texto[:LETRAS_POR_DOCUMENTO]}")
        else:
            lineas.append(f"{encabezado}\n(no se pudo leer: {motivo})")

    if not lineas:
        return "Este cliente todavía no tiene documentos subidos."
    return "\n\n".join(lineas)


def catalogo_de_casillas():
    """Las casillas que se pueden llenar, en una lista corta y legible.

    Solo van las que la plantilla trae con un 0 puesto: son las que el
    archivo espera que alguien diligencie. Mandarle las 1.317 escribibles
    sería más ruido que ayuda, y muchas son filas de rótulo.
    """
    lineas = []
    seccion_anterior = ""
    for celda in formulario.mapa()["celdas"]:
        if celda["tipo"] != TIPO_CAPTURA or not celda["cero_precargado"]:
            continue
        if celda["seccion"] != seccion_anterior:
            seccion_anterior = celda["seccion"]
            lineas.append(f"\n[{seccion_anterior}]")
        rastro = formulario._rastro(celda.get("contexto"))
        renglon = f" (renglón {celda['renglon']})" if celda["renglon"] else ""
        descripcion = f"{rastro} > {celda['descripcion']}" if rastro \
            else celda["descripcion"]
        lineas.append(f"{celda['celda']}: {descripcion[:110]}{renglon}")
    return "\n".join(lineas)


def contexto_del_cliente(cliente):
    """Todo lo que Rentai necesita saber para contestar sobre este cliente."""
    cliente_id = cliente["id"]

    renglones = db.listar_checklist(cliente_id)
    if renglones:
        checklist = "\n".join(
            f"- {r['titulo']}: {'recibido' if r['estado'] == 'recibido' else 'FALTA'}"
            for r in renglones
        )
    else:
        checklist = "Este cliente todavía no tiene checklist."

    anotados = formulario.listar_valores(cliente_id)
    if anotados:
        ya_anotado = "\n".join(
            f"- {v['celda']} = {v['valor']} ({v['descripcion'][:60]})"
            for v in anotados
        )
    else:
        ya_anotado = "Todavía no se ha anotado ningún valor."

    return f"""\
CLIENTE
Nombre: {cliente['nombre']}
Cédula termina en: {cliente['dos_digitos']}

CHECKLIST (lo que el contador le pidió)
{checklist}

VALORES YA ANOTADOS EN EL FORMULARIO
{ya_anotado}

DOCUMENTOS DEL CLIENTE (con el texto que se les pudo sacar)
{resumen_de_documentos(cliente_id)}

CATÁLOGO DE CASILLAS QUE SE PUEDEN LLENAR
Solo puedes proponer casillas de esta lista, con el código exacto.
{catalogo_de_casillas()}
"""


# ---------------------------------------------------------------------------
# Hablar con el servicio
# ---------------------------------------------------------------------------


def _llamar_al_servicio(mensajes, modelo, llave):
    """Le manda la conversación al servicio y devuelve el texto que contestó.

    Se usa urllib, que viene con Python: una dependencia menos que se
    puede romper al instalar en el computador del contador.
    """
    cuerpo = json.dumps({
        "model": modelo,
        "messages": mensajes,
        # Que conteste JSON y no un párrafo con el JSON adentro.
        "response_format": {"type": "json_object"},
        # Temperatura baja: aquí no se quiere creatividad, se quiere que
        # copie bien una cifra de un papel.
        "temperature": 0.1,
    }).encode("utf-8")

    peticion = urllib.request.Request(
        SERVICIO,
        data=cuerpo,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {llave}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(peticion, timeout=SEGUNDOS_DE_ESPERA) as r:
            respuesta = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise RentaiFallo(
                "La llave de la IA no sirve. Revísela en el archivo .env"
                " (GROQ_API_KEY)."
            )
        if error.code == 429:
            raise RentaiFallo(
                "El servicio gratis está ocupado en este momento. Espere un"
                " minuto y vuelva a intentar."
            )
        raise RentaiFallo(
            f"El servicio de IA contestó con un error ({error.code})."
        )
    except urllib.error.URLError:
        raise RentaiFallo(
            "No hay conexión a internet, o el servicio no responde. Todo lo"
            " demás del programa funciona igual sin IA."
        )
    except TimeoutError:
        raise RentaiFallo(
            f"La IA se demoró más de {SEGUNDOS_DE_ESPERA} segundos y se"
            f" canceló."
        )

    try:
        return respuesta["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise RentaiFallo("El servicio de IA contestó algo que no se entendió.")


def _entender_respuesta(texto):
    """Convierte lo que contestó el modelo en respuesta y propuestas.

    El modelo puede contestar mal formado; eso no debe tumbar nada. Si el
    JSON no se entiende, se muestra el texto tal cual y no hay propuestas.
    """
    try:
        datos = json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        return (texto or "").strip(), []

    if not isinstance(datos, dict):
        return (texto or "").strip(), []

    respuesta = str(datos.get("respuesta") or "").strip()
    crudas = datos.get("propuestas")
    if not isinstance(crudas, list):
        crudas = []

    return respuesta, crudas


def revisar_propuestas(crudas):
    """Se queda solo con las propuestas que se pueden anotar de verdad.

    El modelo puede inventarse una casilla, mandar un texto donde va un
    número o apuntar a una celda con fórmula. Nada de eso llega a la
    pantalla: se revisa aquí contra el mapa de la plantilla, que es la
    misma revisión que se hace al escribir.
    """
    catalogo = formulario.indice()
    buenas = []

    for cruda in crudas:
        if not isinstance(cruda, dict):
            continue

        celda = str(cruda.get("celda") or "").strip().upper()
        informacion = catalogo.get(celda)
        if informacion is None or informacion["tipo"] != TIPO_CAPTURA:
            continue

        valor = cruda.get("valor")
        if isinstance(valor, str):
            # "45.000.000" o "$45,000,000" -> 45000000
            limpio = valor.replace("$", "").replace(" ", "").replace(".", "")
            limpio = limpio.replace(",", ".")
            try:
                valor = float(limpio)
            except ValueError:
                continue
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            continue
        if valor != valor:   # NaN
            continue

        buenas.append({
            "celda": celda,
            "valor": int(valor) if float(valor).is_integer() else float(valor),
            "documento": str(cruda.get("documento") or "").strip()[:200],
            "por_que": str(cruda.get("por_que") or "").strip()[:300],
            "descripcion": informacion["descripcion"],
            "renglon": informacion["renglon"],
            "contexto": formulario._rastro(informacion.get("contexto")),
        })

    return buenas


def hablar(cliente, mensaje):
    """Le manda un mensaje a Rentai y devuelve lo que contestó.

    Guarda los dos mensajes (el del contador y el de Rentai) en el
    historial de ese cliente, para que la conversación siga donde quedó.
    """
    if not CONFIG.ia_disponible:
        raise RentaiApagada(CONFIG.motivo)

    cliente_id = cliente["id"]
    mensaje = (mensaje or "").strip()
    if not mensaje:
        raise RentaiFallo("Escriba algo primero.")

    # Se guarda lo que dijo el contador antes de llamar al servicio: si la
    # llamada falla, su mensaje no se pierde.
    db.guardar_mensaje(cliente_id, "contador", mensaje)

    conversacion = [{"role": "system", "content": INSTRUCCIONES}]
    conversacion.append({
        "role": "system",
        "content": contexto_del_cliente(cliente),
    })
    for anterior in db.listar_mensajes(cliente_id, MENSAJES_QUE_RECUERDA):
        conversacion.append({
            "role": "user" if anterior["papel"] == "contador" else "assistant",
            "content": anterior["texto"],
        })

    contenido = _llamar_al_servicio(conversacion, CONFIG.modelo, CONFIG.llave)
    respuesta, crudas = _entender_respuesta(contenido)
    propuestas = revisar_propuestas(crudas)

    if not respuesta:
        respuesta = ("Listo." if propuestas
                     else "No encontré nada que proponer.")

    db.guardar_mensaje(cliente_id, "rentai", respuesta, propuestas)

    return {
        "respuesta": respuesta,
        "propuestas": propuestas,
        "descartadas": len(crudas) - len(propuestas),
    }


def anotar_propuesta(cliente_id, celda, valor, documento):
    """Anota una propuesta que el contador aceptó.

    Queda marcada en la bitácora como lectura automática, con el documento
    de donde salió. Pasa por la misma puerta y las mismas revisiones que
    cualquier valor escrito a mano.
    """
    origen = f"lectura automática de {documento}" if documento \
        else f"lectura automática de {NOMBRE}"
    return formulario.guardar_valor(cliente_id, celda, valor, origen)
