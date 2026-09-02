"""
La bitácora: qué pasó con cada cliente, cuándo, y con cuántas cosas.

Para qué sirve
--------------
En temporada el contador toca muchos expedientes en un día. Cuando algo
no cuadra —"yo juraría que subí ese certificado"— la bitácora es lo que
contesta. Y cuando se borra algo, deja constancia de qué se borró y
cuándo, que es la condición que se puso para permitir el borrado en lote.

Qué NO es
---------
No es el log del programa. El log (lo que sale por la terminal) no lleva
nombres de clientes ni nombres de archivos, y eso no cambia. Esta tabla
sí los lleva, y por eso vive dentro de datos/base.db, en la misma carpeta
protegida donde ya están los documentos. Al borrar un cliente se borra
con él.

Tampoco guarda cifras. Los valores del Formulario 210 tienen su propia
bitácora (bitacora_210), que sí guarda el valor anterior y el nuevo.
"""

from app import db

# ----------------------------------------------------------
# Las acciones que se anotan
#
# Se guardan en clave (texto corto, sin tildes ni espacios) y se
# traducen a español al mostrarlas. Así, si mañana se cambia la
# redacción, no hay que tocar lo que ya está guardado en la base.
# ----------------------------------------------------------

CLIENTE_CREADO = "cliente_creado"
CLIENTE_EDITADO = "cliente_editado"

DOCUMENTOS_SUBIDOS = "documentos_subidos"
DOCUMENTOS_BORRADOS = "documentos_borrados"
DOCUMENTO_ASIGNADO = "documento_asignado"
DOCUMENTOS_LEIDOS = "documentos_leidos"

RENGLON_AGREGADO = "renglon_agregado"
RENGLON_EDITADO = "renglon_editado"
RENGLON_QUITADO = "renglon_quitado"
RENGLON_RECIBIDO = "renglon_recibido"
RENGLON_FALTANTE = "renglon_faltante"
LISTA_BASE_AGREGADA = "lista_base_agregada"

FORMULARIO_GENERADO = "formulario_generado"

# Cómo se lee cada acción en pantalla. La primera forma es para una sola
# cosa, la segunda para varias. Se escoge según la cantidad.
TEXTOS = {
    CLIENTE_CREADO:       ("Se creó el cliente", "Se creó el cliente"),
    CLIENTE_EDITADO:      ("Se cambiaron los datos del cliente",
                           "Se cambiaron los datos del cliente"),
    DOCUMENTOS_SUBIDOS:   ("Se subió 1 documento", "Se subieron {n} documentos"),
    DOCUMENTOS_BORRADOS:  ("Se borró 1 documento", "Se borraron {n} documentos"),
    DOCUMENTO_ASIGNADO:   ("Se asignó un documento del checklist",
                           "Se asignaron {n} documentos del checklist"),
    DOCUMENTOS_LEIDOS:    ("Se leyeron los documentos pendientes",
                           "Se leyeron los documentos pendientes"),
    RENGLON_AGREGADO:     ("Se agregó un renglón al checklist",
                           "Se agregaron {n} renglones al checklist"),
    RENGLON_EDITADO:      ("Se cambió el texto de un renglón",
                           "Se cambiaron {n} renglones"),
    RENGLON_QUITADO:      ("Se quitó un renglón del checklist",
                           "Se quitaron {n} renglones del checklist"),
    RENGLON_RECIBIDO:     ("Se marcó como recibido", "Se marcaron {n} como recibidos"),
    RENGLON_FALTANTE:     ("Se volvió a marcar como faltante",
                           "Se volvieron a marcar {n} como faltantes"),
    LISTA_BASE_AGREGADA:  ("Se agregó la lista base del checklist",
                           "Se agregó la lista base del checklist ({n} renglones)"),
    FORMULARIO_GENERADO:  ("Se generó el archivo del Formulario 210",
                           "Se generó el archivo del Formulario 210"),
}

# Cómo se pinta cada acción en la pantalla: sirve para que el contador
# encuentre un borrado de un vistazo sin tener que leer todo.
TONOS = {
    DOCUMENTOS_BORRADOS: "peligro",
    RENGLON_QUITADO: "peligro",
    DOCUMENTOS_SUBIDOS: "entrada",
    DOCUMENTOS_LEIDOS: "entrada",
    LISTA_BASE_AGREGADA: "entrada",
    RENGLON_AGREGADO: "entrada",
    RENGLON_RECIBIDO: "logro",
    FORMULARIO_GENERADO: "logro",
}


def anotar(cliente_id, accion, detalle="", cantidad=1):
    """Anota que pasó algo. Se llama DESPUÉS de que ya pasó.

    `detalle` es el nombre del archivo o del renglón. Puede ir vacío.
    `cantidad` agrupa: cinco documentos borrados de un golpe son UNA
    anotación con cantidad 5, no cinco anotaciones seguidas.
    """
    if cliente_id is None:
        return
    db.anotar_en_bitacora(cliente_id, accion, detalle, cantidad)


def frase(accion, cantidad=1):
    """Convierte una acción guardada en una frase en español.

    Si la acción no está en la lista —porque la anotó una versión más
    nueva del programa— se devuelve la clave tal cual en vez de fallar.
    """
    formas = TEXTOS.get(accion)
    if formas is None:
        return accion.replace("_", " ")
    una, varias = formas
    if cantidad and cantidad > 1:
        return varias.format(n=cantidad)
    return una


def tono(accion):
    """Con qué color se muestra: 'peligro', 'entrada', 'logro' o ''."""
    return TONOS.get(accion, "")


def historial(cliente_id, limite=100):
    """La bitácora de un cliente, ya lista para mostrarla en pantalla."""
    salida = []
    for fila in db.listar_bitacora(cliente_id, limite):
        salida.append({
            "id": fila["id"],
            "accion": fila["accion"],
            "detalle": fila["detalle"],
            "cantidad": fila["cantidad"],
            "fecha_hora": fila["fecha_hora"],
            "frase": frase(fila["accion"], fila["cantidad"]),
            "tono": tono(fila["accion"]),
        })
    return salida
