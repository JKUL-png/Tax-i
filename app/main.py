"""
Servidor del asistente de organización documental para renta.

Corre en http://localhost:8000 y sirve dos cosas:
  - las páginas de la interfaz (carpeta static/)
  - una pequeña API para leer y guardar clientes y sus documentos

Este archivo ya no tiene direcciones adentro: solo enciende las que
están en app/api/. Importar cada uno de esos archivos es lo que hace que
sus direcciones existan, porque los decoradores @app.get y @app.post se
ejecutan al importar. Por eso los imports de abajo parecen no usarse: sí
se usan, y sacarlos apagaría media aplicación.

El servidor por dentro está en app/servidor.py, hecho solo con lo que
Python ya trae. Antes esto lo hacía FastAPI; se sacó porque arrastraba un
archivo compilado sin firmar (pydantic_core) que el Control inteligente de
aplicaciones de Windows 11 BLOQUEA, y el programa no arrancaba en el
computador de destino.

Nota: no se registra en los logs ningún nombre de cliente ni contenido de
documentos. Solo errores técnicos.
"""

from app import db
from app.api.base import app

# Cada uno de estos imports registra sus direcciones sobre `app`.
# El orden no importa: las direcciones no se pisan entre sí.
from app.api import (
    checklist, chat, clientes, cuenta, documentos, formulario, importar,
    paginas, resumen,
)

# Esta tupla no se usa para nada más que dejar constancia de que los
# imports de arriba SÍ hacen algo: cada uno registra sus direcciones al
# importarse. Sin ella parecen imports olvidados y alguien los borraría.
MODULOS = (
    paginas, clientes, documentos, importar, checklist, resumen,
    formulario, chat, cuenta,
)


# ----------------------------------------------------------
# Arrancar el programa
# ----------------------------------------------------------


def arrancar():
    """Prende el servidor. Es lo que llaman iniciar.sh e iniciar.bat."""
    import argparse

    opciones = argparse.ArgumentParser(description="Servidor de Tax-i")
    opciones.add_argument("--puerto", type=int, default=8000)
    opciones.add_argument("--maquina", default="127.0.0.1")
    elegidas = opciones.parse_args()

    app.arrancar(
        maquina=elegidas.maquina,
        puerto=elegidas.puerto,
        # Prepara la base de datos si es la primera vez.
        al_arrancar=db.crear_tablas,
    )


if __name__ == "__main__":
    arrancar()
