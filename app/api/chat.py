"""La conversación con Rentai, por cliente."""

from app import configuracion, db, formulario, rentai
from app.api.base import (
    app, campo_numero, campo_texto, cliente_o_404, revisado,
)
from app.api.formulario import limpiar_celda
from app.escribir_210 import EscrituraBloqueada
from app.servidor import ErrorHttp


# ----------------------------------------------------------
# Rentai, la asistente
# ----------------------------------------------------------


@app.get("/api/rentai")
def api_rentai(peticion):
    """Quién es Rentai y si está disponible ahora mismo."""
    return {
        "nombre": rentai.NOMBRE,
        "disponible": configuracion.CONFIG.ia_disponible,
        "motivo": configuracion.CONFIG.motivo,
    }


@app.get("/api/clientes/{id_cliente}/chat")
def api_leer_chat(peticion, id_cliente):
    """La conversación que va con este cliente."""
    cliente_o_404(id_cliente)
    return db.listar_mensajes(id_cliente)


@app.post("/api/clientes/{id_cliente}/chat")
def api_hablar(peticion, id_cliente):
    """Le manda un mensaje a Rentai sobre este cliente."""
    cliente = cliente_o_404(id_cliente)
    datos = peticion.diccionario()
    try:
        return rentai.hablar(cliente, campo_texto(datos, "mensaje"))
    except rentai.RentaiApagada as error:
        raise ErrorHttp(409, str(error))
    except rentai.RentaiFallo as error:
        raise ErrorHttp(502, str(error))
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))


@app.delete("/api/clientes/{id_cliente}/chat")
def api_borrar_chat(peticion, id_cliente):
    """Borra la conversación. Los valores ya anotados no se tocan."""
    cliente_o_404(id_cliente)
    db.borrar_mensajes(id_cliente)


@app.post("/api/clientes/{id_cliente}/chat/anotar")
def api_anotar_propuesta(peticion, id_cliente):
    """Anota una propuesta que el contador aceptó."""
    cliente_o_404(id_cliente)

    datos = peticion.diccionario()
    celda = revisado(limpiar_celda, campo_texto(datos, "celda"))
    valor = campo_numero(datos, "valor")
    documento = campo_texto(datos, "documento", "")

    try:
        return rentai.anotar_propuesta(id_cliente, celda, valor, documento)
    except EscrituraBloqueada as error:
        raise ErrorHttp(400, str(error))
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))
