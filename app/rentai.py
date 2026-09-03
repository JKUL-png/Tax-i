"""
RentAI: la asistente que conversa sobre un cliente y propone qué anotar.

Qué hace y qué NO hace
----------------------
RentAI lee lo que ya está en el computador —los documentos del cliente, su
checklist, lo que ya se anotó en el formulario— y contesta preguntas sobre
eso. Cuando encuentra una cifra en un documento, **propone** anotarla en
una casilla de la plantilla. Propone: no escribe.

Nada de lo que dice RentAI entra al archivo solo. El contador ve cada
propuesta con el documento de donde salió y decide si la anota. Es la
regla del proyecto: todo dato que salga de una IA se muestra marcado como
lectura automática y con un enlace al original.

RentAI tampoco calcula impuestos, ni dice qué es deducible, ni sugiere
cómo declarar, ni afirma que alguien está obligado a declarar. Eso no es
prudencia: es la línea legal del proyecto, y está escrita en las
instrucciones que se le mandan al modelo y verificada aquí en el código.

Qué sale de este computador
---------------------------
Con IA_PROVEEDOR=ninguno (el valor por defecto) no sale nada y RentAI no
funciona. Con la IA encendida, al servicio que el contador haya elegido
le llega: el nombre del cliente, su checklist, la conversación y **los
datos que ya se le sacaron a sus documentos**, no los documentos.

Eso último cambió. Antes, cada pregunta remandaba el texto de los
documentos, así que el mismo certificado salía de aquí una y otra vez.
Ahora cada documento se lee UNA sola vez, al confirmarlo (eso lo hace
app/extraccion.py, y ahí sí sale su texto esa única vez), lo que se le
sacó queda guardado en la base, y a partir de entonces lo que sale son
esas filas: "Salarios = 45.000.000", no el certificado entero.

Sale menos, sale una vez, y lo ya leído se sigue viendo aunque después
se apague la IA. Los archivos NO se mandan nunca.

Con cuál servicio se habla lo decide el contador en la pantalla de
Cuenta, y con eso decide también a quién le está confiando esos textos.
Si elige Ollama, el modelo corre en este mismo computador y no sale
nada tampoco. Lo que cambia de un servicio a otro está en
app/proveedores.py; aquí no se sabe con cuál se está hablando.
"""

import json

from app import db, formulario, instrucciones, proveedores
from app.configuracion import CONFIG
from app.plantilla_210 import TIPO_CAPTURA

# Cómo se llama. Está en una constante porque se ve en toda la pantalla.
NOMBRE = "RentAI"

# Cuántos mensajes anteriores se le recuerdan. Más que esto no ayuda y
# hace la conversación cara y lenta.
MENSAJES_QUE_RECUERDA = 8

# Cuántos documentos del cliente se le mandan, y cuánto texto de cada uno.
#
# Estos números no son al azar: las capas gratis de estos servicios
# suelen dejar pasar unos 8.000 tokens por minuto, que son unas 32.000
# letras contando ida y vuelta. En ese presupuesto tienen que caber las
# instrucciones, el catálogo de casillas, los documentos y la
# conversación. Si se agranda esto, empieza a rebotar con "servicio
# ocupado" en el servicio más apretado.
DOCUMENTOS_QUE_SE_MANDAN = 6

# Cuántos datos de cada documento se le cuentan. Ya no se manda el texto
# del documento sino lo que se le sacó, que es mucho más corto: un
# certificado que ocupaba 1.000 letras cabe ahora en seis renglones.
DATOS_POR_DOCUMENTO = 12

# Lo mismo para el catálogo: cada casilla se manda en una línea corta.
LARGO_DE_LINEA_DEL_CATALOGO = 38


class RentaiApagada(Exception):
    """La IA está apagada o mal configurada. No es un error del programa."""


class RentaiFallo(Exception):
    """Se intentó hablar con el servicio y no se pudo."""


# ---------------------------------------------------------------------------
# Las instrucciones del modelo
#
# Esto es lo que RentAI "es". Se escribe en español porque en español
# trabaja, y se le repiten las prohibiciones más de una vez a propósito:
# es lo que más importa que no se le olvide.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Lo que RentAI sabe del cliente
# ---------------------------------------------------------------------------

def resumen_de_documentos(cliente_id):
    """Lo que ya se le sacó a los documentos, sacado de la BASE DE DATOS.

    Antes esta función volvía a abrir los PDF y le remandaba su texto al
    modelo en cada pregunta. Eso significaba pagar el mismo certificado
    otra vez en cada mensaje, y esperar a que se releyera.

    Ahora los documentos se leen UNA vez, al confirmarlos (ver
    app/extraccion.py), y lo que se les sacó vive en la base. Aquí solo
    se consultan esas filas. Los documentos ya no se vuelven a mandar
    nunca: lo que sale son los datos, que son mucho más cortos.

    Eso también es lo que hace que lo ya leído se siga viendo con
    IA_PROVEEDOR=ninguno: está en este computador.

    Cada dato dice de qué documento salió y quién lo leyó. Los que leyó
    un modelo van marcados como lectura automática, porque el contador
    tiene que poder distinguir eso de lo que leyó el programa de un XML.
    """
    filas = db.listar_datos_extraidos(cliente_id)
    documentos_del_cliente = db.listar_documentos(cliente_id)

    if not documentos_del_cliente:
        return "Este cliente todavía no tiene documentos subidos."

    # Los datos, agrupados por el documento del que salieron.
    por_documento = {}
    for fila in filas:
        por_documento.setdefault(fila["documento_id"], []).append(fila)

    bloques = []
    sin_leer = []

    for documento in documentos_del_cliente[:DOCUMENTOS_QUE_SE_MANDAN]:
        suyos = por_documento.get(documento["id"])
        if not suyos:
            sin_leer.append(documento["nombre_original"])
            continue

        # 'ia' es lectura automática; 'codigo' lo leyó el programa de un
        # XML y es exacto. Se le dice al modelo, para que no presente lo
        # uno como si fuera lo otro.
        como = ("leído por el programa del XML: exacto"
                if suyos[0]["origen"] == "codigo"
                else "LECTURA AUTOMÁTICA: hay que verificarla")
        lineas = [f"--- {documento['nombre_original']} ({como}) ---"]
        for dato in suyos[:DATOS_POR_DOCUMENTO]:
            partes = [dato["concepto"]]
            if dato["valor"]:
                partes.append(f"= {dato['valor']}")
            if dato["detalle"]:
                partes.append(f"({dato['detalle']})")
            lineas.append("  " + " ".join(partes))
        bloques.append("\n".join(lineas))

    if sin_leer:
        bloques.append(
            "DOCUMENTOS QUE TODAVÍA NO SE HAN LEÍDO (%d): %s\n"
            "  No sabes qué dicen. No adivines su contenido: dile al"
            " contador que los procese primero."
            % (len(sin_leer), ", ".join(sin_leer[:8]))
        )

    if not bloques:
        return ("Este cliente tiene documentos, pero todavía no se ha"
                " leído ninguno. No sabes qué dicen.")
    return "\n\n".join(bloques)


def catalogo_de_casillas():
    """Las casillas que se pueden llenar, en una lista corta y legible.

    Solo van las que la plantilla trae con un 0 puesto: son las que el
    archivo espera que alguien diligencie. Mandarle las 1.317 escribibles
    sería más ruido que ayuda, y muchas son filas de rótulo.

    Cada línea va apretada a propósito —"G32|Alimentación>Empresa xxx"—
    porque el catálogo entero tiene que caber en el presupuesto de tokens
    junto con los documentos. Escrito largo se come él solo la mitad.
    """
    lineas = []
    seccion_anterior = ""

    for celda in formulario.mapa()["celdas"]:
        if celda["tipo"] != TIPO_CAPTURA or not celda["cero_precargado"]:
            continue

        if celda["seccion"] != seccion_anterior:
            seccion_anterior = celda["seccion"]
            lineas.append(f"[{seccion_anterior[:28]}]")

        # El concepto padre más cercano, cortito: es lo que distingue una
        # casilla "Empresa xxx, NIT…" de las otras diecinueve iguales.
        contexto = celda.get("contexto") or []
        padre = contexto[-1] if contexto else ""
        for signo in ("(", ";", ":", ","):
            if signo in padre:
                antes = padre.split(signo)[0].strip()
                if len(antes) >= 8:
                    padre = antes
                    break

        nombre = f"{padre[:18]}>{celda['descripcion']}" if padre \
            else celda["descripcion"]
        nombre = nombre[:LARGO_DE_LINEA_DEL_CATALOGO]

        renglon = f" r{celda['renglon']}" if celda["renglon"] else ""
        lineas.append(f"{celda['celda']}|{nombre}{renglon}")

    return "\n".join(lineas)


def contexto_del_cliente(cliente):
    """Todo lo que RentAI necesita saber para contestar sobre este cliente."""
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


def _llamar_al_servicio(mensajes, config=CONFIG):
    """Le manda la conversación al servicio elegido y devuelve su texto.

    De con CUÁL servicio se habla, y de cómo se le habla, se encarga
    app/proveedores.py. Aquí solo se traducen sus errores al error que
    la pantalla ya sabe mostrar.
    """
    try:
        return proveedores.conversar(config, mensajes)
    except proveedores.ErrorDeProveedor as error:
        raise RentaiFallo(str(error))


def probar_llave(llave, proveedor=None, base_url=None):
    """Pregunta si la configuración de la IA sirve. Devuelve (sirve, motivo).

    Se pregunta por la lista de modelos, no por una conversación: es una
    petición de solo lectura que no manda ni un dato de ningún cliente.
    Sirve para que el contador pegue su llave nueva y sepa en el momento
    si quedó bien, en vez de descubrirlo cuando le escriba a RentAI.
    """
    return proveedores.probar(
        proveedor if proveedor is not None else CONFIG.proveedor,
        llave,
        base_url if base_url is not None else CONFIG.base_url,
    )


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


def revisar_propuestas(crudas, contexto=""):
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

        # La frase de donde dice haber sacado la cifra. Si se le pasó
        # el contexto que se le mandó, se comprueba que esa frase esté
        # de verdad ahí. La propuesta igual se muestra —el contador
        # puede querer verla— pero marcada como sin verificar, y eso se
        # ve en pantalla.
        cita = str(cruda.get("cita") or cruda.get("por_que") or "").strip()[:300]
        verificada = None
        if contexto:
            verificada = instrucciones.verificar_cita(cita, contexto)

        buenas.append({
            "celda": celda,
            "valor": int(valor) if float(valor).is_integer() else float(valor),
            "documento": str(cruda.get("documento") or "").strip()[:200],
            "por_que": cita,
            "cita": cita,
            "verificada": verificada,
            "descripcion": informacion["descripcion"],
            "renglon": informacion["renglon"],
            "contexto": formulario._rastro(informacion.get("contexto")),
        })

    return buenas


def hablar(cliente, mensaje):
    """Le manda un mensaje a RentAI y devuelve lo que contestó.

    Guarda los dos mensajes (el del contador y el de RentAI) en el
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

    # El contexto es lo ÚNICO que RentAI sabe del cliente: son las filas
    # de la base de datos, no los documentos. Se guarda aparte porque
    # después se usa para comprobar que las citas que devuelva estén
    # de verdad ahí y no salgan de su imaginación.
    contexto = contexto_del_cliente(cliente)

    conversacion = [{"role": "system", "content": instrucciones.CONVERSAR}]
    conversacion.append({"role": "system", "content": contexto})
    for anterior in db.listar_mensajes(cliente_id, MENSAJES_QUE_RECUERDA):
        conversacion.append({
            "role": "user" if anterior["papel"] == "contador" else "assistant",
            "content": anterior["texto"],
        })

    contenido = _llamar_al_servicio(conversacion)
    respuesta, crudas = _entender_respuesta(contenido)
    propuestas = revisar_propuestas(crudas, contexto)

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
