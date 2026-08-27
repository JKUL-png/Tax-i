"""
Servidor del asistente de organización documental para renta.

Corre en http://localhost:8000 y sirve dos cosas:
  - las páginas de la interfaz (carpeta static/)
  - una pequeña API para leer y guardar clientes y sus documentos

Nota: no se registra en los logs ningún nombre de cliente ni contenido de
documentos. Solo errores técnicos.
"""

import mimetypes
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from app import db, documentos, importar

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
    """Entrega la página principal: la lista de clientes."""
    return FileResponse(CARPETA_STATIC / "index.html")


@app.get("/cliente")
def pagina_cliente():
    """Entrega la página de un cliente. El id va en la dirección: /cliente?id=3"""
    return FileResponse(CARPETA_STATIC / "cliente.html")


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
    notas: Optional[str] = None

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
    notas: Optional[str] = None

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
    """Lista los clientes, agregándole a cada uno cuántos documentos tiene."""
    clientes = db.listar_clientes()
    conteos = db.contar_documentos()
    for cliente in clientes:
        cliente["documentos"] = conteos.get(cliente["id"], 0)
    return clientes


@app.get("/api/clientes/{id_cliente}")
def api_obtener_cliente(id_cliente: int):
    cliente = db.obtener_cliente(id_cliente)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")
    return cliente


@app.post("/api/clientes", status_code=201)
def api_crear_cliente(datos: ClienteNuevo):
    return db.crear_cliente(
        nombre=datos.nombre,
        dos_digitos=datos.dos_digitos,
        fecha_vencimiento=datos.fecha_vencimiento,
        notas=datos.notas,
    )


@app.patch("/api/clientes/{id_cliente}")
def api_actualizar_cliente(id_cliente: int, cambios: ClienteCambios):
    if db.obtener_cliente(id_cliente) is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")

    # Se distingue "no mandaron el campo" de "lo mandaron vacío para borrarlo".
    enviados = cambios.model_dump(exclude_unset=True)
    fecha = enviados["fecha_vencimiento"] if "fecha_vencimiento" in enviados else ...
    notas = enviados["notas"] if "notas" in enviados else ...

    return db.actualizar_cliente(
        id_cliente,
        nombre=cambios.nombre,
        dos_digitos=cambios.dos_digitos,
        fecha_vencimiento=fecha,
        notas=notas,
    )


@app.delete("/api/clientes/{id_cliente}", status_code=204)
def api_eliminar_cliente(id_cliente: int):
    if not db.eliminar_cliente(id_cliente):
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")
    # Los documentos de la base se van solos (ON DELETE CASCADE), pero los
    # archivos del disco hay que borrarlos a mano. Son datos confidenciales:
    # no se pueden quedar ahí después de eliminar al cliente.
    documentos.eliminar_carpeta_cliente(id_cliente)


# ----------------------------------------------------------
# API de documentos
# ----------------------------------------------------------


def con_tipo(documento):
    """Le agrega al documento el nombre del tipo para mostrarlo en pantalla."""
    documento = dict(documento)
    documento["tipo"] = documentos.tipo_legible(documento["extension"])
    return documento


def guardar_y_registrar(id_cliente, nombre_original, contenido, venia_en_zip=None):
    """Escribe el archivo en el disco y lo anota en la base de datos."""
    nombre_guardado, tamano = documentos.guardar_contenido(
        id_cliente, nombre_original, contenido
    )
    registro = db.crear_documento(
        cliente_id=id_cliente,
        nombre_original=nombre_original,
        nombre_guardado=nombre_guardado,
        extension=Path(nombre_guardado).suffix.lower(),
        tamano=tamano,
        venia_en_zip=venia_en_zip,
    )
    return con_tipo(registro)


@app.get("/api/clientes/{id_cliente}/documentos")
def api_listar_documentos(id_cliente: int):
    if db.obtener_cliente(id_cliente) is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")
    return [con_tipo(documento) for documento in db.listar_documentos(id_cliente)]


@app.post("/api/clientes/{id_cliente}/documentos")
async def api_subir_documentos(
    id_cliente: int,
    archivos: List[UploadFile] = File(...),
):
    """Recibe uno o varios archivos y los guarda en la carpeta del cliente.

    Los ZIP se abren y se guarda lo que traen adentro, no el ZIP.
    Lo que no se pueda guardar se devuelve en la lista `ignorados`, con el
    motivo, para poder mostrárselo al contador en vez de fallar en silencio.
    """
    if db.obtener_cliente(id_cliente) is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")

    guardados = []
    ignorados = []

    for archivo in archivos:
        nombre_completo = archivo.filename or "documento"

        # Basura del sistema: se salta sin avisar, no es un documento.
        if documentos.es_basura(nombre_completo):
            continue

        # El navegador puede mandar la ruta de la carpeta cuando se arrastra
        # una carpeta completa. Aquí solo interesa el nombre del archivo.
        nombre = nombre_completo.replace("\\", "/").split("/")[-1]
        extension = Path(nombre).suffix.lower()

        # --- Caso ZIP: se abre y se guarda lo de adentro ---
        if extension == ".zip":
            contenido = await documentos.leer_con_limite(
                archivo, documentos.LIMITE_ZIP
            )
            if contenido is None:
                ignorados.append(nombre + " — el ZIP pesa más de 100 MB.")
                continue

            encontrados, motivos = documentos.abrir_zip(contenido)
            ignorados.extend(motivos)

            if not encontrados and not motivos:
                ignorados.append(nombre + " — el ZIP no traía documentos útiles.")

            for nombre_interno, datos in encontrados:
                guardados.append(
                    guardar_y_registrar(id_cliente, nombre_interno, datos, nombre)
                )
            continue

        # --- Caso archivo suelto ---
        if extension not in documentos.EXTENSIONES_PERMITIDAS:
            ignorados.append(nombre + " — tipo de archivo no admitido.")
            continue

        contenido = await documentos.leer_con_limite(
            archivo, documentos.LIMITE_ARCHIVO
        )
        if contenido is None:
            ignorados.append(nombre + " — pesa más de 25 MB.")
            continue
        if not contenido:
            ignorados.append(nombre + " — el archivo está vacío.")
            continue

        guardados.append(guardar_y_registrar(id_cliente, nombre, contenido))

    return {"guardados": guardados, "ignorados": ignorados}


@app.get("/api/documentos/{id_documento}/archivo")
def api_abrir_documento(id_documento: int):
    """Entrega el archivo original para verlo en el navegador."""
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise HTTPException(status_code=404, detail="Ese documento no existe.")

    ruta = documentos.ruta_del_documento(
        documento["cliente_id"], documento["nombre_guardado"]
    )
    if ruta is None or not ruta.is_file():
        raise HTTPException(
            status_code=404,
            detail="El archivo ya no está en el disco.",
        )

    tipo, _ = mimetypes.guess_type(documento["nombre_guardado"])

    # "inline" pide que el navegador lo muestre en vez de descargarlo.
    # El nombre va codificado (filename*=UTF-8) para que las tildes y las
    # eñes no se dañen.
    disposicion = "inline; filename*=UTF-8''" + quote(documento["nombre_original"])

    return FileResponse(
        ruta,
        media_type=tipo or "application/octet-stream",
        headers={"Content-Disposition": disposicion},
    )


@app.delete("/api/documentos/{id_documento}", status_code=204)
def api_eliminar_documento(id_documento: int):
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise HTTPException(status_code=404, detail="Ese documento no existe.")

    # Primero el archivo del disco, después el registro de la base.
    ruta = documentos.ruta_del_documento(
        documento["cliente_id"], documento["nombre_guardado"]
    )
    if ruta is not None and ruta.is_file():
        ruta.unlink()

    db.eliminar_documento(id_documento)


# ----------------------------------------------------------
# Importar clientes desde un archivo de Excel o CSV
#
# Son dos pasos a propósito:
#   1. /analizar  lee el archivo y PROPONE una lista. No guarda nada.
#   2. /confirmar recibe la lista ya revisada por el contador y la guarda.
#
# Así el contador siempre ve y corrige antes de que algo entre a la base.
# ----------------------------------------------------------


class ClienteImportado(BaseModel):
    """Una fila ya revisada por el contador, lista para crearse.

    Aquí no se ponen validadores de pydantic a propósito: si una fila
    viene mal, se quiere avisar cuál fila fue y seguir con las demás,
    no rechazar el archivo entero.
    """

    nombre: str = ""
    dos_digitos: str = ""
    fecha_vencimiento: Optional[str] = None
    notas: Optional[str] = None


@app.post("/api/importar/analizar")
async def api_analizar_importacion(archivo: UploadFile = File(...)):
    """Lee el archivo y devuelve los clientes propuestos, sin guardar nada."""
    nombre = archivo.filename or "archivo"

    contenido = await documentos.leer_con_limite(archivo, importar.LIMITE_ARCHIVO)
    if contenido is None:
        raise HTTPException(
            status_code=400,
            detail="El archivo pesa más de 10 MB.",
        )
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

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
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/api/importar/confirmar")
def api_confirmar_importacion(clientes: List[ClienteImportado]):
    """Crea los clientes que el contador ya revisó.

    Cada fila se valida por separado: si una tiene un problema, se anota
    y se sigue con las demás en vez de perder todo el trabajo.
    """
    if not clientes:
        raise HTTPException(
            status_code=400,
            detail="No se seleccionó ningún cliente para crear.",
        )
    if len(clientes) > importar.LIMITE_FILAS:
        raise HTTPException(
            status_code=400,
            detail="Son demasiados clientes de una sola vez.",
        )

    creados = []
    errores = []

    for numero, fila in enumerate(clientes, start=1):
        try:
            nombre = limpiar_nombre(fila.nombre)
            dos_digitos = limpiar_digitos(fila.dos_digitos)
            fecha = limpiar_fecha(fila.fecha_vencimiento)
        except ValueError as error:
            errores.append("Fila " + str(numero) + ": " + str(error))
            continue

        notas = (fila.notas or "").strip() or None
        creados.append(
            db.crear_cliente(
                nombre=nombre,
                dos_digitos=dos_digitos,
                fecha_vencimiento=fecha,
                notas=notas,
            )
        )

    return {"creados": len(creados), "errores": errores}
