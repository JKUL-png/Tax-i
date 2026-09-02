"""Llevarse todo el trabajo en un archivo, y traerlo de vuelta.

Es lo que salva la temporada si se daña el disco. Ver app/respaldo.py.
"""

import tempfile
from pathlib import Path

from app import respaldo
from app.api.base import app
from app.servidor import ErrorHttp, Respuesta


@app.get("/api/respaldo")
def api_descargar_respaldo(peticion, **partes):
    """Arma el respaldo completo y lo entrega para descargar.

    Se escribe primero a un archivo temporal y después se manda. Con
    doscientos documentos escaneados esto pesa cientos de megas, y
    armarlo en memoria dejaría al programa sin aire.
    """
    with tempfile.TemporaryDirectory() as temporal:
        destino = Path(temporal) / "respaldo.zip"
        respaldo.armar(destino)
        return Respuesta.archivo(
            destino,
            tipo="application/zip",
            nombre_visible=respaldo.nombre_del_archivo(),
            descargar=True,
        )


@app.post("/api/respaldo/revisar")
def api_revisar_respaldo(peticion, **partes):
    """Mira el ZIP y dice qué trae, SIN tocar nada todavía.

    Es el primer paso de los dos: el contador ve qué va a entrar y qué va
    a pasar con lo que ya tiene, y después confirma. Restaurar encima del
    trabajo de una temporada no puede ser un solo clic.
    """
    nombre, contenido = peticion.archivos("archivo")[0]

    with tempfile.TemporaryDirectory() as temporal:
        ruta = Path(temporal) / "revisar.zip"
        ruta.write_bytes(contenido)
        try:
            informacion = respaldo.revisar(ruta)
        except respaldo.RespaldoInvalido as error:
            raise ErrorHttp(400, str(error))

    informacion["archivo"] = nombre or "respaldo.zip"
    return informacion


@app.post("/api/respaldo/restaurar")
def api_restaurar_respaldo(peticion, **partes):
    """Devuelve el respaldo a este computador.

    Antes de tocar nada aparta lo que hubiera en `datos/`, con la fecha
    en el nombre de la carpeta. Si el contador se equivocó de archivo, su
    trabajo sigue ahí.
    """
    nombre, contenido = peticion.archivos("archivo")[0]

    with tempfile.TemporaryDirectory() as temporal:
        ruta = Path(temporal) / "restaurar.zip"
        ruta.write_bytes(contenido)
        try:
            return respaldo.restaurar(ruta)
        except respaldo.RespaldoInvalido as error:
            raise ErrorHttp(400, str(error))
