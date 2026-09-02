"""
La revisión de arranque: ¿está todo en su sitio para trabajar?

Qué revisa
----------
Cinco cosas, y las contesta en español, no en jerga:

  1. ¿Se puede escribir en datos/?  Si no, no se puede guardar nada y hay
     que saberlo AHORA, no cuando el contador suba doce documentos y se
     pierdan.
  2. ¿Está la plantilla del Formulario 210 donde debe?
  3. ¿Cómo está la IA? Y si está apagada, decir que eso está bien.
  4. ¿Está LibreOffice? Si no, los totales se ven al abrir en Excel.
  5. ¿Quedaron documentos sin leer de la sesión anterior?

Cómo se escriben los avisos
---------------------------
Ninguno dice "Errno 13" ni "OSError". Cada uno dice qué pasa y qué hacer,
en una frase que el contador pueda leer y actuar. Si un aviso no le dice
qué hacer, está mal escrito.

Los tres niveles:
  'bien'     todo en orden
  'aviso'    se puede trabajar, pero hay algo que conviene saber
  'problema' esto impide trabajar y hay que arreglarlo
"""

from app import db, demostracion
from app.configuracion import CONFIG

RAIZ = db.RAIZ


def _punto(titulo, nivel, mensaje, que_hacer=""):
    return {
        "titulo": titulo,
        "nivel": nivel,
        "mensaje": mensaje,
        "que_hacer": que_hacer,
    }


def revisar_carpeta_datos():
    """¿Se puede escribir en datos/? Es lo primero, porque sin eso nada."""
    carpeta = db.CARPETA_DATOS
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        prueba = carpeta / ".prueba-de-escritura"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
    except OSError:
        return _punto(
            "Dónde se guarda el trabajo", "problema",
            "El programa NO puede escribir en su carpeta de datos, así que"
            " no va a poder guardar documentos ni clientes.",
            "Puede pasar si el programa quedó en una carpeta protegida"
            " (Archivos de programa) o en una memoria USB de solo lectura."
            " Mueva la carpeta del programa a su Escritorio o a Documentos"
            " y vuelva a abrirlo.",
        )

    return _punto(
        "Dónde se guarda el trabajo", "bien",
        "Todo se guarda en la carpeta datos/, aquí en este computador."
        " Nada se sube a internet.",
    )


def revisar_plantilla():
    """¿Está la plantilla del Formulario 210?"""
    # Se importa aquí y no arriba para no obligar a leer la plantilla
    # entera solo por arrancar el programa.
    from app import formulario

    try:
        ruta = formulario.ruta_plantilla()
    except Exception:
        ruta = None

    if ruta is None:
        return _punto(
            "La plantilla del Formulario 210", "aviso",
            "Todavía no hay ninguna plantilla puesta. Todo lo demás"
            " funciona: puede recibir documentos, armar el checklist y"
            " exportar. Lo único que no se puede todavía es generar el"
            " archivo de Excel.",
            "Entre a un cliente, a la pestaña «Formulario 210», y suba ahí"
            " su archivo de Excel. También puede dejarlo en la carpeta"
            " plantillas/ del programa.",
        )

    return _punto(
        "La plantilla del Formulario 210", "bien",
        "Puesta y lista: %s" % ruta.name,
    )


def revisar_ia(probar_conexion=False):
    """¿Cómo está la IA? Estar apagada NO es un problema.

    Con `probar_conexion=True` se le habla al servicio para ver si de
    verdad contesta. Eso tarda unos segundos y necesita internet, así que
    al arrancar NO se hace: el programa tiene que prender rápido. La
    pantalla sí lo pide cuando el contador la abre.
    """
    if CONFIG.sin_ia:
        return _punto(
            "El servicio de IA", "bien",
            "Está en modo sin IA, y así está bien: el programa funciona"
            " completo y ningún dato sale de este computador. La IA solo"
            " acelera la lectura de los documentos; no habilita nada.",
        )

    if not CONFIG.ia_disponible:
        return _punto(
            "El servicio de IA", "aviso",
            "Hay un servicio de IA elegido pero le falta algo: %s"
            % CONFIG.motivo,
            "Entre a «Cuenta y ajustes» y complete lo que falte. Mientras"
            " tanto el programa funciona igual, solo que sin la lectura"
            " automática de los documentos.",
        )

    if not probar_conexion:
        return _punto(
            "El servicio de IA", "bien",
            "Configurado: %s. En la pantalla de Cuenta puede probar que"
            " responda." % CONFIG.ficha.nombre,
        )

    from app import proveedores
    sirve, motivo = proveedores.probar(
        CONFIG.proveedor, CONFIG.llave, CONFIG.base_url
    )
    if sirve:
        return _punto(
            "El servicio de IA", "bien",
            "%s responde bien. %s" % (CONFIG.ficha.nombre, motivo),
        )
    return _punto(
        "El servicio de IA", "aviso",
        "El servicio de IA no está respondiendo: %s" % motivo,
        "Revise la llave y la dirección en «Cuenta y ajustes». El resto"
        " del programa funciona igual sin IA.",
    )


def revisar_libreoffice():
    """¿Está LibreOffice? No tenerlo no impide nada."""
    from app.recalcular import buscar_libreoffice

    if buscar_libreoffice():
        return _punto(
            "LibreOffice", "bien",
            "Instalado. Sirve para ver los totales del Formulario 210"
            " dentro del programa.",
        )

    return _punto(
        "LibreOffice", "aviso",
        "No está instalado, y no hace falta para trabajar. El archivo de"
        " Excel se genera completo igual; los totales se calculan solos"
        " al abrirlo en Excel.",
        "Solo si quiere ver los totales sin salir del programa, instale"
        " LibreOffice (es gratis) y vuelva a abrir Tax-i.",
    )


def revisar_cola():
    """¿Quedaron documentos sin leer de la sesión anterior?"""
    pendientes = len(db.documentos_sin_leer())
    if not pendientes:
        return _punto(
            "Documentos por leer", "bien",
            "No quedó ningún documento sin leer.",
        )

    return _punto(
        "Documentos por leer", "aviso",
        "Quedaron %d documento(s) sin leer de la vez pasada. No se perdió"
        " nada: siguen en la fila, tal como estaban." % pendientes,
        "Entre al cliente y apriete «Procesar pendientes» cuando quiera"
        " leerlos. Usted decide cuándo se gasta el cupo del día.",
    )


def revisar_demostracion():
    """¿Está prendido el modo demostración? Hay que decirlo siempre."""
    if not demostracion.activo():
        return None

    return _punto(
        "Modo demostración", "aviso",
        "El modo demostración está PRENDIDO. Hay clientes inventados"
        " cargados, marcados con «%s»." % demostracion.MARCA,
        "Apáguelo desde «Cuenta y ajustes» cuando termine de mostrar el"
        " programa. Al apagarlo se borran solo los inventados; sus"
        " clientes de verdad no se tocan.",
    )


def revisar_todo(probar_conexion=False):
    """La revisión completa. Devuelve los puntos y un resumen."""
    puntos = [
        revisar_carpeta_datos(),
        revisar_plantilla(),
        revisar_ia(probar_conexion),
        revisar_libreoffice(),
        revisar_cola(),
    ]
    aviso_demo = revisar_demostracion()
    if aviso_demo:
        puntos.append(aviso_demo)

    problemas = sum(1 for p in puntos if p["nivel"] == "problema")
    avisos = sum(1 for p in puntos if p["nivel"] == "aviso")

    if problemas:
        resumen = ("Hay algo que impide trabajar. Lea abajo qué es y qué"
                   " hacer.")
    elif avisos:
        resumen = "Se puede trabajar. Hay cosas que conviene saber."
    else:
        resumen = "Todo en orden."

    return {
        "puntos": puntos,
        "problemas": problemas,
        "avisos": avisos,
        "resumen": resumen,
    }


def imprimir_al_arrancar():
    """Escribe la revisión en la ventana negra, al prender el programa.

    Solo se escriben los avisos y los problemas. Si está todo bien se dice
    en una línea: llenar la pantalla de «OK» al arrancar hace que el día
    que salga un problema de verdad nadie lo lea.

    NO se prueba la conexión con la IA: eso tarda y necesita internet, y
    el programa tiene que prender rápido.
    """
    informe = revisar_todo(probar_conexion=False)

    for punto in informe["puntos"]:
        if punto["nivel"] == "bien":
            continue
        marca = "  !!" if punto["nivel"] == "problema" else "  --"
        print("%s %s: %s" % (marca, punto["titulo"], punto["mensaje"]))
        if punto["que_hacer"]:
            print("     %s" % punto["que_hacer"])

    if not informe["problemas"] and not informe["avisos"]:
        print("  Todo revisado y en orden.")

    return informe
