"""
Servidor del asistente de organización documental para renta.

Tax-i — un archivador de documentos para la temporada de renta.
Copyright (C) 2026 JKUL

Este programa es software libre: usted puede redistribuirlo y/o
modificarlo bajo los términos de la Licencia Pública General Affero de
GNU, publicada por la Free Software Foundation, en su versión 3.

Se distribuye con la esperanza de que sea útil, pero SIN NINGUNA
GARANTÍA; ni siquiera la garantía implícita de COMERCIABILIDAD o
IDONEIDAD PARA UN PROPÓSITO PARTICULAR. Vea la Licencia Pública General
Affero de GNU para más detalles. El texto completo está en el archivo
LICENSE, y en <https://www.gnu.org/licenses/agpl-3.0.html>.

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

from app import db, revision
from app.api.base import app

# Cada uno de estos imports registra sus direcciones sobre `app`.
# El orden no importa: las direcciones no se pisan entre sí.
from app.api import (
    checklist, chat, clientes, cuenta, documentos, exogena, formulario,
    importar, paginas, pasada, reglas, respaldo, resumen, sistema,
)

# Esta tupla no se usa para nada más que dejar constancia de que los
# imports de arriba SÍ hacen algo: cada uno registra sus direcciones al
# importarse. Sin ella parecen imports olvidados y alguien los borraría.
MODULOS = (
    paginas, clientes, documentos, importar, checklist, resumen,
    formulario, exogena, pasada, reglas, chat, cuenta, respaldo,
    sistema,
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
        al_arrancar=preparar,
    )


def preparar():
    """Lo que hay que dejar listo antes de empezar a atender.

    Se llama una sola vez, al prender el programa.
    """
    # Prepara la base de datos si es la primera vez, y le agrega las
    # columnas nuevas si viene de una versión anterior.
    db.crear_tablas()

    # Los documentos que quedaron marcados como 'leyendo' —de una versión
    # anterior del programa, cuando los PDF se leían uno por uno en otro
    # hilo— vuelven a 'pendiente'. Hoy ya no queda nada a medias: los XML
    # se leen de una al confirmar la carga, y el texto de los PDF lo lee
    # la pasada del formulario cuando el contador la pide.
    rescatados = db.rescatar_lecturas_a_medias()
    if rescatados:
        print("  %d documento(s) habían quedado a medio leer y vuelven"
              " a quedar pendientes." % rescatados)

    # Y se revisa que todo esté en su sitio, contándolo en español. Solo
    # se escribe lo que hay que saber: si está todo bien, una línea.
    revision.imprimir_al_arrancar()


if __name__ == "__main__":
    arrancar()
