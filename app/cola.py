"""
La fila de documentos por leer, trabajada en segundo plano.

Para qué
--------
Leer un documento con IA se demora unos segundos. Con doce documentos son
minutos. Si eso pasara mientras el contador espera, subir una carpeta se
sentiría como si el programa se hubiera colgado.

Entonces no espera: subir y confirmar es instantáneo, los documentos
quedan anotados como pendientes, y un hilo aparte los va leyendo mientras
el contador sigue trabajando. La pantalla muestra en qué va cada uno.

Dónde vive la fila
------------------
**En SQLite, no en memoria.** La fila no es una lista de Python: es la
columna `estado_lectura` de la tabla `documentos`. Eso es a propósito.

Si la fila viviera en memoria, cerrar el programa a mitad de una tanda
perdería el trabajo, y al volver a abrirlo el contador no tendría cómo
saber cuáles quedaron sin leer. Estando en la base, al arrancar se
retoma donde iba: los que quedaron a medias vuelven a 'pendiente' y la
fila sigue.

Un solo trabajador
------------------
Hay un hilo, no varios. Dos razones: las capas gratis limitan cuántas
peticiones por minuto se pueden hacer —mandarlas todas a la vez es la
forma más rápida de agotar el cupo— y así el orden en pantalla es el
mismo que el orden real de la fila.

Cuándo trabaja
--------------
Solo cuando se le dice. De fábrica no procesa nada solo: el contador
aprieta «Procesar pendientes» y decide cuándo gastar cupo. Si prende el
interruptor de «procesar automáticamente al confirmar», la fila arranca
sola cada vez que confirma una carga.
"""

import threading

from app import db, extraccion

# El ajuste que decide si la fila arranca sola al confirmar una carga.
# Guardado en la base, no en el .env: es una preferencia de trabajo del
# contador, no configuración del programa.
CLAVE_AUTOMATICO = "procesar_al_confirmar"


# El hilo que trabaja, y el candado que garantiza que solo haya uno.
_trabajador = None
_candado = threading.Lock()
# Se levanta para pedirle al hilo que pare en el próximo documento.
_pedido_de_parar = threading.Event()
# Lo último que hizo, para poder contarlo en pantalla.
_ultimo = {"leidos": 0, "fallidos": 0, "terminó": None}


def procesar_automaticamente():
    """¿Está prendido el interruptor de procesar al confirmar?

    Viene APAGADO de fábrica. Leer documentos gasta cupo, y esa decisión
    es del contador, no del programa.
    """
    return db.leer_ajuste(CLAVE_AUTOMATICO, "no") == "si"


def cambiar_automatico(prendido):
    """Prende o apaga el procesar al confirmar. Devuelve cómo quedó."""
    db.guardar_ajuste(CLAVE_AUTOMATICO, "si" if prendido else "no")
    return procesar_automaticamente()


def trabajando():
    """¿Hay un hilo leyendo documentos en este momento?"""
    return _trabajador is not None and _trabajador.is_alive()


def _seguir():
    """Se le pregunta antes de cada documento: ¿sigo o paro?"""
    return not _pedido_de_parar.is_set()


def _trabajar(cliente_id):
    """Lee los pendientes, uno por uno. Es lo que corre en el hilo."""
    global _trabajador
    try:
        informes = extraccion.extraer_pendientes(cliente_id, seguir=_seguir)
        _ultimo["leidos"] = sum(
            1 for i in informes if i["estado"] == "listo"
        )
        _ultimo["fallidos"] = sum(
            1 for i in informes if i["estado"] == "fallo"
        )
        _ultimo["terminó"] = True
    finally:
        # Pase lo que pase, el puesto queda libre para la próxima tanda.
        # Sin esto, un error inesperado dejaría la fila trabada para
        # siempre y solo se arreglaría reiniciando el programa.
        with _candado:
            _trabajador = None


def arrancar(cliente_id=None):
    """Pone a trabajar la fila, si no está trabajando ya.

    Con `cliente_id` lee solo los de ese cliente, que es lo que hace el
    botón «Procesar pendientes» de su pantalla. Sin él, los de todos.

    Devuelve True si arrancó una tanda nueva, False si ya había una en
    curso o si no había nada pendiente. Volver a llamarla mientras
    trabaja no hace nada: no se amontonan hilos ni se lee dos veces el
    mismo documento.
    """
    global _trabajador
    with _candado:
        if _trabajador is not None and _trabajador.is_alive():
            return False
        if not db.documentos_sin_leer(cliente_id):
            return False

        _pedido_de_parar.clear()
        _ultimo.update(leidos=0, fallidos=0, terminó=False)
        # daemon=True: si el contador cierra el programa, no se queda
        # esperando a que la fila termine. Lo que faltaba queda como
        # pendiente en la base y se retoma al volver a abrirlo.
        _trabajador = threading.Thread(
            target=_trabajar, args=(cliente_id,),
            name="cola-de-lectura", daemon=True,
        )
        _trabajador.start()
        return True


def parar():
    """Le pide a la fila que pare después del documento que va leyendo.

    No la corta en seco: el documento en curso se termina, para no dejar
    uno a medias. Lo que falte queda pendiente.
    """
    _pedido_de_parar.set()


def al_arrancar_el_programa():
    """Deja la fila lista cuando el programa se prende.

    Los documentos que quedaron en 'leyendo' —porque se cerró el programa
    a mitad de una lectura— vuelven a 'pendiente'. Así no quedan colgados
    y la fila los retoma.

    NO se pone a trabajar sola. Solo deja las cosas en su sitio y cuenta
    qué encontró, para que la pantalla de arranque lo diga.
    """
    rescatados = db.rescatar_lecturas_a_medias()
    pendientes = len(db.documentos_sin_leer())
    return {"rescatados": rescatados, "pendientes": pendientes}


def estado(cliente_id=None):
    """En qué va la fila, para contárselo a la pantalla."""
    return {
        "trabajando": trabajando(),
        "pendientes": len(db.documentos_sin_leer(cliente_id)),
        "automatico": procesar_automaticamente(),
        "ultima_tanda": dict(_ultimo),
    }
