"""
Las páginas que se ven en el navegador, y la configuración que necesitan.

Cada archivo de app/api/ registra sus direcciones sobre la MISMA
Aplicacion, la que vive en app/api/base.py. Importar este archivo es lo
que hace que sus rutas existan; de eso se encarga app/main.py.
"""

from app import configuracion
from app.api.base import app, _pagina


# ----------------------------------------------------------
# Páginas
# ----------------------------------------------------------


@app.get("/")
def inicio(peticion):
    """Entrega la página principal: la lista de clientes."""
    return _pagina("index.html")


@app.get("/cliente")
def pagina_cliente(peticion):
    """Entrega la página de un cliente. El id va en la dirección: /cliente?id=3"""
    return _pagina("cliente.html")


@app.get("/resumen")
def pagina_resumen(peticion):
    """Entrega el resumen para imprimir. El id va en la dirección: /resumen?id=3"""
    return _pagina("resumen.html")


@app.get("/cuenta")
def pagina_cuenta(peticion):
    """Entrega la pantalla de la cuenta y los ajustes."""
    return _pagina("cuenta.html")


@app.get("/api/configuracion")
def api_configuracion(peticion):
    """Cómo está configurado el programa ahora mismo.

    La pantalla lo usa para mostrarle al contador si la IA está apagada.
    Nunca incluye la llave.
    """
    return configuracion.CONFIG.como_diccionario()
