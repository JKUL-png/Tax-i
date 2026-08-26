"""
Servidor del asistente de organización documental para renta.

Corre en http://localhost:8000 y sirve dos cosas:
  - las páginas de la interfaz (carpeta static/)
  - una pequeña API para leer y guardar clientes

Nota: no se registra en los logs ningún nombre de cliente ni contenido de
documentos. Solo errores técnicos.
"""

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from app import db

# Raíz del proyecto. Este archivo vive en app/, así que subimos un nivel.
# Se usa pathlib (y no texto pegado con / o \) para que las rutas funcionen
# igual en Mac y en Windows.
RAIZ = Path(__file__).resolve().parent.parent
CARPETA_STATIC = RAIZ / "static"


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """Lo que pasa al prender y al apagar el servidor."""
    db.crear_tablas()   # prepara la base de datos si es la primera vez
    yield


app = FastAPI(title="Asistente de renta", lifespan=ciclo_de_vida)

# Deja disponibles el CSS y el JavaScript en /static/...
app.mount("/static", StaticFiles(directory=CARPETA_STATIC), name="static")


# ----------------------------------------------------------
# Páginas
# ----------------------------------------------------------


@app.get("/")
def inicio():
    """Entrega la página principal."""
    return FileResponse(CARPETA_STATIC / "index.html")


# ----------------------------------------------------------
# Validación de los datos que llegan del navegador
#
# Todo lo que manda el navegador se revisa aquí antes de tocar la base.
# ----------------------------------------------------------


def limpiar_nombre(valor):
    """Quita espacios sobrantes y verifica que quede algo."""
    if valor is None:
        return None
    limpio = " ".join(valor.split())
    if not limpio:
        raise ValueError("El nombre no puede estar vacío.")
    if len(limpio) > 120:
        raise ValueError("El nombre es demasiado largo.")
    return limpio


def limpiar_digitos(valor):
    """Verifica que sean dos dígitos. Acepta '5' y lo convierte en '05'."""
    if valor is None:
        return None
    limpio = valor.strip()
    if not limpio.isdigit() or len(limpio) > 2:
        raise ValueError(
            "Deben ser los dos últimos dígitos de la cédula, por ejemplo 07."
        )
    return limpio.zfill(2)


def limpiar_fecha(valor):
    """Acepta una fecha AAAA-MM-DD, o vacío si todavía no se sabe."""
    if valor is None:
        return None
    limpio = valor.strip()
    if not limpio:
        return None
    try:
        date.fromisoformat(limpio)
    except ValueError:
        raise ValueError("La fecha no es válida.")
    return limpio


class ClienteNuevo(BaseModel):
    nombre: str
    dos_digitos: str
    fecha_vencimiento: Optional[str] = None

    @field_validator("nombre")
    @classmethod
    def _revisar_nombre(cls, valor):
        return limpiar_nombre(valor)

    @field_validator("dos_digitos")
    @classmethod
    def _revisar_digitos(cls, valor):
        return limpiar_digitos(valor)

    @field_validator("fecha_vencimiento")
    @classmethod
    def _revisar_fecha(cls, valor):
        return limpiar_fecha(valor)


class ClienteCambios(BaseModel):
    """Todos los campos son opcionales: se cambia solo lo que se manda."""

    nombre: Optional[str] = None
    dos_digitos: Optional[str] = None
    fecha_vencimiento: Optional[str] = None

    @field_validator("nombre")
    @classmethod
    def _revisar_nombre(cls, valor):
        return limpiar_nombre(valor)

    @field_validator("dos_digitos")
    @classmethod
    def _revisar_digitos(cls, valor):
        return limpiar_digitos(valor)

    @field_validator("fecha_vencimiento")
    @classmethod
    def _revisar_fecha(cls, valor):
        return limpiar_fecha(valor)


# ----------------------------------------------------------
# API de clientes
# ----------------------------------------------------------


@app.get("/api/clientes")
def api_listar_clientes():
    return db.listar_clientes()


@app.post("/api/clientes", status_code=201)
def api_crear_cliente(datos: ClienteNuevo):
    return db.crear_cliente(
        nombre=datos.nombre,
        dos_digitos=datos.dos_digitos,
        fecha_vencimiento=datos.fecha_vencimiento,
    )


@app.patch("/api/clientes/{id_cliente}")
def api_actualizar_cliente(id_cliente: int, cambios: ClienteCambios):
    if db.obtener_cliente(id_cliente) is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")

    # Se distingue "no mandaron el campo" de "lo mandaron vacío para borrarlo".
    enviados = cambios.model_dump(exclude_unset=True)
    fecha = enviados["fecha_vencimiento"] if "fecha_vencimiento" in enviados else ...

    return db.actualizar_cliente(
        id_cliente,
        nombre=cambios.nombre,
        dos_digitos=cambios.dos_digitos,
        fecha_vencimiento=fecha,
    )


@app.delete("/api/clientes/{id_cliente}", status_code=204)
def api_eliminar_cliente(id_cliente: int):
    if not db.eliminar_cliente(id_cliente):
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")
