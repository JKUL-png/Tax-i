"""El checklist de cada cliente: qué se le pidió y qué ya llegó."""

from app import bitacora, checklist, db
from app.api.base import (app, campo_lista_de_numeros, campo_texto,
                          revisado)
from app.servidor import ErrorHttp


# ----------------------------------------------------------
# API del checklist
#
# El checklist es del contador: él decide qué necesita cada cliente.
# El programa solo lleva la cuenta, no opina sobre qué debe estar.
# ----------------------------------------------------------


@app.get("/api/clientes/{id_cliente}/checklist")
def api_listar_checklist(peticion, id_cliente):
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    renglones = db.listar_checklist(id_cliente)
    conteos = db.contar_documentos_por_renglon(id_cliente)
    for renglon in renglones:
        renglon["documentos"] = conteos.get(renglon["id"], 0)
    return renglones


@app.post("/api/clientes/{id_cliente}/checklist", codigo=201)
def api_agregar_renglon(peticion, id_cliente):
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    datos = peticion.diccionario()
    titulo = revisado(checklist.limpiar_titulo, campo_texto(datos, "titulo"))
    renglon = db.crear_renglon(id_cliente, titulo)
    bitacora.anotar(id_cliente, bitacora.RENGLON_AGREGADO, titulo)
    return renglon


@app.post("/api/clientes/{id_cliente}/checklist/base", codigo=201)
def api_agregar_lista_base(peticion, id_cliente):
    """Agrega la lista sugerida al checklist del cliente.

    Sirve para los clientes que quedaron sin checklist (los creados con
    una versión anterior del programa) y para el contador que borró todo
    y quiere volver a empezar.
    """
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    renglones = db.crear_renglones(id_cliente, checklist.LISTA_BASE)
    bitacora.anotar(id_cliente, bitacora.LISTA_BASE_AGREGADA, "",
                    len(renglones))
    return renglones


@app.put("/api/clientes/{id_cliente}/checklist/orden")
def api_reordenar_checklist(peticion, id_cliente):
    """Reacomoda los renglones en el orden que el contador los dejó."""
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    ids = campo_lista_de_numeros(peticion.diccionario(), "ids")
    if not ids:
        raise ErrorHttp(400, "No llegó ningún renglón que reordenar.")
    return db.reordenar_checklist(id_cliente, ids)


@app.patch("/api/checklist/{id_renglon}")
def api_actualizar_renglon(peticion, id_renglon):
    antes = db.obtener_renglon(id_renglon)
    if antes is None:
        raise ErrorHttp(404, "Ese renglón no existe.")

    datos = peticion.diccionario()
    titulo = None
    estado = None
    if datos.get("titulo") is not None:
        titulo = revisado(checklist.limpiar_titulo, datos["titulo"])
    if datos.get("estado") is not None:
        estado = revisado(checklist.limpiar_estado, datos["estado"])

    renglon = db.actualizar_renglon(id_renglon, titulo=titulo, estado=estado)

    # Marcar recibido y cambiarle el texto son dos cosas distintas y se
    # anotan distinto: al contador le interesa mucho más la primera.
    if estado is not None and estado != antes["estado"]:
        cual = (bitacora.RENGLON_RECIBIDO if estado == checklist.RECIBIDO
                else bitacora.RENGLON_FALTANTE)
        bitacora.anotar(antes["cliente_id"], cual, renglon["titulo"])
    elif titulo is not None and titulo != antes["titulo"]:
        bitacora.anotar(antes["cliente_id"], bitacora.RENGLON_EDITADO,
                        renglon["titulo"])

    return renglon


@app.delete("/api/checklist/{id_renglon}")
def api_eliminar_renglon(peticion, id_renglon):
    renglon = db.obtener_renglon(id_renglon)
    if renglon is None:
        raise ErrorHttp(404, "Ese renglón no existe.")
    # Los documentos que estaban asignados a este renglón NO se borran:
    # quedan sueltos para que el contador los reasigne.
    db.desasignar_renglon(id_renglon)
    db.eliminar_renglon(id_renglon)
    bitacora.anotar(renglon["cliente_id"], bitacora.RENGLON_QUITADO,
                    renglon["titulo"])
