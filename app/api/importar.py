"""Importar una lista de clientes desde un Excel o un CSV, en dos pasos."""

from app import bitacora, checklist, db, documentos, importar
from app.api.base import (
    app, limpiar_digitos, limpiar_fecha, limpiar_nombre,
)
from app.servidor import ErrorHttp


# ----------------------------------------------------------
# Importar clientes desde un archivo de Excel o CSV
#
# Son dos pasos a propósito:
#   1. /analizar  lee el archivo y PROPONE una lista. No guarda nada.
#   2. /confirmar recibe la lista ya revisada por el contador y la guarda.
#
# Así el contador siempre ve y corrige antes de que algo entre a la base.
# ----------------------------------------------------------


@app.post("/api/importar/analizar")
def api_analizar_importacion(peticion, **partes):
    """Lee el archivo y devuelve los clientes propuestos, sin guardar nada."""
    nombre, contenido = peticion.archivos("archivo")[0]
    nombre = nombre or "archivo"

    if documentos.dentro_del_limite(contenido,
                                    importar.LIMITE_ARCHIVO) is None:
        raise ErrorHttp(400, "El archivo pesa más de 10 MB.")
    if not contenido:
        raise ErrorHttp(400, "El archivo está vacío.")

    # Los nombres que ya existen, para poder avisar de los repetidos.
    existentes = {
        importar.normalizar(cliente["nombre"])
        for cliente in db.listar_clientes()
    }

    try:
        return importar.analizar(nombre, contenido, existentes)
    except ValueError as error:
        # Los mensajes de ValueError están escritos para que los lea el
        # contador, así que se le pasan tal cual.
        raise ErrorHttp(400, str(error))


@app.post("/api/importar/confirmar")
def api_confirmar_importacion(peticion, **partes):
    """Crea los clientes que el contador ya revisó.

    Cada fila se valida por separado: si una tiene un problema, se anota
    y se sigue con las demás en vez de perder todo el trabajo.
    """
    clientes = peticion.lista()

    if not clientes:
        raise ErrorHttp(400, "No se seleccionó ningún cliente para crear.")
    if len(clientes) > importar.LIMITE_FILAS:
        raise ErrorHttp(400, "Son demasiados clientes de una sola vez.")

    creados = []
    errores = []

    for numero, fila in enumerate(clientes, start=1):
        if not isinstance(fila, dict):
            errores.append("Fila " + str(numero) + ": llegó mal armada.")
            continue
        try:
            nombre = limpiar_nombre(fila.get("nombre", ""))
            dos_digitos = limpiar_digitos(fila.get("dos_digitos", ""))
            fecha = limpiar_fecha(fila.get("fecha_vencimiento"))
        except ValueError as error:
            errores.append("Fila " + str(numero) + ": " + str(error))
            continue

        notas = (fila.get("notas") or "").strip() or None
        cliente = db.crear_cliente(
            nombre=nombre,
            dos_digitos=dos_digitos,
            fecha_vencimiento=fecha,
            notas=notas,
        )
        db.crear_renglones(cliente["id"], checklist.LISTA_BASE)
        bitacora.anotar(cliente["id"], bitacora.CLIENTE_CREADO,
                        cliente["nombre"])
        creados.append(cliente)

    return {"creados": len(creados), "errores": errores}
