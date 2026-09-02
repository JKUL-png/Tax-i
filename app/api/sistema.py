"""La revisión de arranque y el modo demostración.

Las dos son de todo el programa, no de un cliente. Ver app/revision.py y
app/demostracion.py.
"""

from app import demostracion, revision
from app.api.base import app


@app.get("/api/revision")
def api_revision(peticion, **partes):
    """¿Está todo en su sitio para trabajar?

    Con ?probar_ia=si además se le habla al servicio de IA para ver si
    responde. Eso tarda unos segundos, así que no se hace siempre: la
    pantalla lo pide cuando el contador quiere comprobarlo.
    """
    return revision.revisar_todo(
        probar_conexion=peticion.si_o_no("probar_ia", False)
    )


@app.get("/api/demostracion")
def api_estado_demostracion(peticion, **partes):
    """¿Está prendido el modo demostración?"""
    return demostracion.estado()


@app.put("/api/demostracion")
def api_cambiar_demostracion(peticion, **partes):
    """Prende o apaga el modo demostración.

    Al apagarlo se borran los clientes inventados con sus documentos.
    Solo se borra lo que lleva la marca de demostración: los clientes de
    verdad no se tocan nunca.
    """
    datos = peticion.diccionario()
    if datos.get("prendido"):
        return demostracion.prender()
    return demostracion.apagar()
