"""El resumen del cliente y el mensaje de lo que le falta."""

from urllib.parse import quote

from app import db, documentos, exportar
from app.api.base import app
from app.api.documentos import con_tipo
from app.servidor import ErrorHttp, Respuesta


# ----------------------------------------------------------
# Exportar: el resumen y el mensaje para el cliente
# ----------------------------------------------------------


def datos_del_resumen(id_cliente):
    """Junta todo lo que hace falta para armar el resumen de un cliente."""
    cliente = db.obtener_cliente(id_cliente)
    if cliente is None:
        raise ErrorHttp(404, "Ese cliente no existe.")

    renglones = db.listar_checklist(id_cliente)
    archivos = [con_tipo(d) for d in db.listar_documentos(id_cliente)]
    return cliente, renglones, archivos


@app.get("/api/clientes/{id_cliente}/resumen")
def api_resumen(peticion, id_cliente):
    """El resumen del cliente, como datos, para dibujarlo en pantalla."""
    cliente, renglones, archivos = datos_del_resumen(id_cliente)
    return exportar.armar_resumen(cliente, renglones, archivos)


@app.get("/api/clientes/{id_cliente}/resumen.txt")
def api_resumen_txt(peticion, id_cliente):
    """El mismo resumen como archivo de texto, para guardarlo o archivarlo."""
    cliente, renglones, archivos = datos_del_resumen(id_cliente)
    resumen = exportar.armar_resumen(cliente, renglones, archivos)
    texto = exportar.texto_del_resumen(resumen)

    # El nombre del archivo se limpia igual que los documentos, porque va a
    # terminar guardado en el disco de alguien (probablemente en Windows).
    nombre = documentos.sanitizar_nombre("Resumen - " + cliente["nombre"] + ".txt")

    # El nombre va codificado (filename*=UTF-8) para que las tildes y las
    # eñes lleguen bien al disco de quien lo descargue.
    return Respuesta.texto(
        texto,
        cabeceras={
            "Content-Disposition":
                "attachment; filename*=UTF-8''" + quote(nombre)
        },
    )


@app.get("/api/clientes/{id_cliente}/mensaje")
def api_mensaje(peticion, id_cliente):
    """El borrador del mensaje de 'esto es lo que me falta'.

    Es un borrador a propósito: la pantalla lo muestra en un campo
    editable para que el contador lo ajuste antes de mandarlo.
    """
    cliente = db.obtener_cliente(id_cliente)
    if cliente is None:
        raise ErrorHttp(404, "Ese cliente no existe.")

    renglones = db.listar_checklist(id_cliente)
    return {"texto": exportar.mensaje_de_faltantes(cliente, renglones)}
