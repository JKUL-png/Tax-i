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
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from app import (
    checklist, configuracion, db, documentos, exportar, formulario, importar,
    lectura, rentai,
)
from app.escribir_210 import EscrituraBloqueada, VerificacionFallida

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


app = FastAPI(title="Tax-i", lifespan=ciclo_de_vida)

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


@app.get("/resumen")
def pagina_resumen():
    """Entrega el resumen para imprimir. El id va en la dirección: /resumen?id=3"""
    return FileResponse(CARPETA_STATIC / "resumen.html")


@app.get("/cuenta")
def pagina_cuenta():
    """Entrega la pantalla de la cuenta y los ajustes."""
    return FileResponse(CARPETA_STATIC / "cuenta.html")


@app.get("/api/configuracion")
def api_configuracion():
    """Cómo está configurado el programa ahora mismo.

    La pantalla lo usa para mostrarle al contador si la IA está apagada.
    Nunca incluye la llave.
    """
    return configuracion.CONFIG.como_diccionario()


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
    avances = db.contar_checklist()
    for cliente in clientes:
        cliente["documentos"] = conteos.get(cliente["id"], 0)
        avance = avances.get(cliente["id"], {"total": 0, "recibidos": 0})
        cliente["checklist_total"] = avance["total"]
        cliente["checklist_recibidos"] = avance["recibidos"]
    return clientes


@app.get("/api/clientes/{id_cliente}")
def api_obtener_cliente(id_cliente: int):
    cliente = db.obtener_cliente(id_cliente)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")
    return cliente


@app.post("/api/clientes", status_code=201)
def api_crear_cliente(datos: ClienteNuevo):
    cliente = db.crear_cliente(
        nombre=datos.nombre,
        dos_digitos=datos.dos_digitos,
        fecha_vencimiento=datos.fecha_vencimiento,
        notas=datos.notas,
    )
    # Se le arma el checklist sugerido para que no arranque en blanco.
    # Es un punto de partida: el contador lo ajusta como necesite.
    db.crear_renglones(cliente["id"], checklist.LISTA_BASE)
    return cliente


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
    # Y el archivo de Excel de ese cliente, que también es confidencial.
    formulario.eliminar_carpeta_cliente(id_cliente)


# ----------------------------------------------------------
# API de documentos
# ----------------------------------------------------------


def con_tipo(documento):
    """Le agrega al documento lo que la pantalla necesita para mostrarlo."""
    documento = dict(documento)
    documento["tipo"] = documentos.tipo_legible(documento["extension"])
    documento["vista"] = documentos.como_se_previsualiza(documento["extension"])
    return documento


def guardar_y_registrar(id_cliente, nombre_original, contenido,
                        huella, venia_en_zip=None):
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
        huella=huella,
        venia_en_zip=venia_en_zip,
    )
    return con_tipo(registro)


@app.get("/api/clientes/{id_cliente}/documentos")
def api_listar_documentos(id_cliente: int):
    if db.obtener_cliente(id_cliente) is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")

    renglones = db.listar_checklist(id_cliente)
    salida = []

    for documento in db.listar_documentos(id_cliente):
        documento = con_tipo(documento)

        # A los que todavía nadie asignó se les propone un renglón, mirando
        # las palabras del nombre del archivo. Es una sugerencia hecha con
        # código, no con IA, y la pantalla la muestra marcada como tal.
        documento["sugerencia"] = None
        if documento["renglon_id"] is None:
            sugerido, _ = lectura.sugerir_renglon(
                documento["nombre_original"], renglones
            )
            documento["sugerencia"] = sugerido

        salida.append(documento)

    return salida


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
                huella = documentos.huella_del_contenido(datos)
                repetido = db.buscar_documento_por_huella(id_cliente, huella)
                if repetido:
                    ignorados.append(
                        nombre_interno + " — ya estaba subido como \""
                        + repetido["nombre_original"] + "\"."
                    )
                    continue
                guardados.append(
                    guardar_y_registrar(
                        id_cliente, nombre_interno, datos, huella, nombre
                    )
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

        # ¿Este cliente ya mandó exactamente este mismo archivo?
        # Se compara el contenido, no el nombre.
        huella = documentos.huella_del_contenido(contenido)
        repetido = db.buscar_documento_por_huella(id_cliente, huella)
        if repetido:
            ignorados.append(
                nombre + " — ya estaba subido como \""
                + repetido["nombre_original"] + "\"."
            )
            continue

        guardados.append(
            guardar_y_registrar(id_cliente, nombre, contenido, huella)
        )

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
        cliente = db.crear_cliente(
            nombre=nombre,
            dos_digitos=dos_digitos,
            fecha_vencimiento=fecha,
            notas=notas,
        )
        db.crear_renglones(cliente["id"], checklist.LISTA_BASE)
        creados.append(cliente)

    return {"creados": len(creados), "errores": errores}


# ----------------------------------------------------------
# API del checklist
#
# El checklist es del contador: él decide qué necesita cada cliente.
# El programa solo lleva la cuenta, no opina sobre qué debe estar.
# ----------------------------------------------------------


class RenglonNuevo(BaseModel):
    titulo: str


class RenglonCambios(BaseModel):
    """Todos los campos son opcionales: se cambia solo lo que se manda."""

    titulo: Optional[str] = None
    estado: Optional[str] = None


@app.get("/api/clientes/{id_cliente}/checklist")
def api_listar_checklist(id_cliente: int):
    if db.obtener_cliente(id_cliente) is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")
    renglones = db.listar_checklist(id_cliente)
    conteos = db.contar_documentos_por_renglon(id_cliente)
    for renglon in renglones:
        renglon["documentos"] = conteos.get(renglon["id"], 0)
    return renglones


@app.post("/api/clientes/{id_cliente}/checklist", status_code=201)
def api_agregar_renglon(id_cliente: int, datos: RenglonNuevo):
    if db.obtener_cliente(id_cliente) is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")
    try:
        titulo = checklist.limpiar_titulo(datos.titulo)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return db.crear_renglon(id_cliente, titulo)


@app.post("/api/clientes/{id_cliente}/checklist/base", status_code=201)
def api_agregar_lista_base(id_cliente: int):
    """Agrega la lista sugerida al checklist del cliente.

    Sirve para los clientes que quedaron sin checklist (los creados con
    una versión anterior del programa) y para el contador que borró todo
    y quiere volver a empezar.
    """
    if db.obtener_cliente(id_cliente) is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")
    return db.crear_renglones(id_cliente, checklist.LISTA_BASE)


@app.patch("/api/checklist/{id_renglon}")
def api_actualizar_renglon(id_renglon: int, cambios: RenglonCambios):
    if db.obtener_renglon(id_renglon) is None:
        raise HTTPException(status_code=404, detail="Ese renglón no existe.")

    titulo = None
    estado = None
    try:
        if cambios.titulo is not None:
            titulo = checklist.limpiar_titulo(cambios.titulo)
        if cambios.estado is not None:
            estado = checklist.limpiar_estado(cambios.estado)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    return db.actualizar_renglon(id_renglon, titulo=titulo, estado=estado)


@app.delete("/api/checklist/{id_renglon}", status_code=204)
def api_eliminar_renglon(id_renglon: int):
    if db.obtener_renglon(id_renglon) is None:
        raise HTTPException(status_code=404, detail="Ese renglón no existe.")
    # Los documentos que estaban asignados a este renglón NO se borran:
    # quedan sueltos para que el contador los reasigne.
    db.desasignar_renglon(id_renglon)
    db.eliminar_renglon(id_renglon)


# ----------------------------------------------------------
# Exportar: el resumen y el mensaje para el cliente
# ----------------------------------------------------------


def datos_del_resumen(id_cliente):
    """Junta todo lo que hace falta para armar el resumen de un cliente."""
    cliente = db.obtener_cliente(id_cliente)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")

    renglones = db.listar_checklist(id_cliente)
    archivos = [con_tipo(d) for d in db.listar_documentos(id_cliente)]
    return cliente, renglones, archivos


@app.get("/api/clientes/{id_cliente}/resumen")
def api_resumen(id_cliente: int):
    """El resumen del cliente, como datos, para dibujarlo en pantalla."""
    cliente, renglones, archivos = datos_del_resumen(id_cliente)
    return exportar.armar_resumen(cliente, renglones, archivos)


@app.get("/api/clientes/{id_cliente}/resumen.txt")
def api_resumen_txt(id_cliente: int):
    """El mismo resumen como archivo de texto, para guardarlo o archivarlo."""
    cliente, renglones, archivos = datos_del_resumen(id_cliente)
    resumen = exportar.armar_resumen(cliente, renglones, archivos)
    texto = exportar.texto_del_resumen(resumen)

    # El nombre del archivo se limpia igual que los documentos, porque va a
    # terminar guardado en el disco de alguien (probablemente en Windows).
    nombre = documentos.sanitizar_nombre("Resumen - " + cliente["nombre"] + ".txt")

    return PlainTextResponse(
        texto,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(nombre)
        },
    )


@app.get("/api/clientes/{id_cliente}/mensaje")
def api_mensaje(id_cliente: int):
    """El borrador del mensaje de 'esto es lo que me falta'.

    Es un borrador a propósito: la pantalla lo muestra en un campo
    editable para que el contador lo ajuste antes de mandarlo.
    """
    cliente = db.obtener_cliente(id_cliente)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")

    renglones = db.listar_checklist(id_cliente)
    return {"texto": exportar.mensaje_de_faltantes(cliente, renglones)}


# ----------------------------------------------------------
# Asignar un documento a un renglón del checklist
#
# Esto es lo que conecta las dos mitades del programa: el archivo que
# llegó y la casilla que lo estaba esperando. Por ahora lo hace el
# contador a mano; más adelante se le puede sugerir automáticamente.
# ----------------------------------------------------------


class DocumentoCambios(BaseModel):
    # Se usa el truco de `...` para distinguir "no me mandaron el campo"
    # de "me mandaron null para soltar el documento".
    renglon_id: Optional[int] = None


@app.patch("/api/documentos/{id_documento}")
def api_asignar_documento(id_documento: int, cambios: DocumentoCambios):
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise HTTPException(status_code=404, detail="Ese documento no existe.")

    renglon_id = cambios.renglon_id

    if renglon_id is not None:
        renglon = db.obtener_renglon(renglon_id)
        if renglon is None:
            raise HTTPException(status_code=404, detail="Ese renglón no existe.")
        if renglon["cliente_id"] != documento["cliente_id"]:
            raise HTTPException(
                status_code=400,
                detail="Ese renglón es de otro cliente.",
            )
        # Asignar un documento a un renglón es decir "esto ya llegó",
        # así que el renglón se marca recibido solo.
        db.actualizar_renglon(renglon_id, estado=checklist.RECIBIDO)

    return con_tipo(db.asignar_documento(id_documento, renglon_id))


# ----------------------------------------------------------
# Vista previa de un documento
#
# La idea es que el contador pueda mirar qué es un archivo sin tener
# que descargarlo y abrirlo en otro programa.
# ----------------------------------------------------------

# Cuánto se muestra de una hoja de cálculo o de un XML en la vista previa.
# Es una mirada rápida, no el archivo completo.
FILAS_EN_VISTA = 60
COLUMNAS_EN_VISTA = 15
LETRAS_EN_VISTA = 20000


@app.get("/api/documentos/{id_documento}/vista")
def api_vista_documento(id_documento: int):
    """Prepara lo que hace falta para mostrar el documento en pantalla.

    Los PDF y las imágenes los sabe mostrar el navegador solo, así que
    para esos basta con devolver la dirección del archivo. El XML y las
    hojas de cálculo hay que leerlos aquí.
    """
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise HTTPException(status_code=404, detail="Ese documento no existe.")

    vista = documentos.como_se_previsualiza(documento["extension"])
    direccion = "/api/documentos/" + str(id_documento) + "/archivo"

    if vista in ("pdf", "imagen"):
        return {"vista": vista, "url": direccion}

    if vista == "sin_vista":
        return {
            "vista": "sin_vista",
            "url": direccion,
            "motivo": (
                "Las fotos de iPhone (.heic) no las muestra el navegador."
                if documento["extension"] in (".heic", ".heif")
                else "Este tipo de archivo no se puede ver aquí."
            ),
        }

    ruta = documentos.ruta_del_documento(
        documento["cliente_id"], documento["nombre_guardado"]
    )
    if ruta is None or not ruta.is_file():
        raise HTTPException(
            status_code=404, detail="El archivo ya no está en el disco."
        )

    contenido = ruta.read_bytes()

    # --- XML: se muestra el texto tal cual ---
    if vista == "texto":
        texto = None
        for codificacion in ("utf-8", "cp1252", "latin-1"):
            try:
                texto = contenido.decode(codificacion)
                break
            except UnicodeDecodeError:
                continue
        if texto is None:
            return {"vista": "sin_vista", "url": direccion,
                    "motivo": "No se pudo leer el texto del archivo."}

        recortado = len(texto) > LETRAS_EN_VISTA
        return {
            "vista": "texto",
            "url": direccion,
            "texto": texto[:LETRAS_EN_VISTA],
            "recortado": recortado,
            # Si es una factura electrónica, el código saca los campos
            # exactos del XML. Esto NO pasa por ninguna IA: el formato ya
            # trae cada dato con su nombre.
            "leido": lectura.leer_xml(contenido),
        }

    # --- Hojas de cálculo: se arma una tabla ---
    try:
        filas = importar.leer_archivo(documento["nombre_guardado"], contenido)
    except ValueError as error:
        return {"vista": "sin_vista", "url": direccion, "motivo": str(error)}

    recortado = len(filas) > FILAS_EN_VISTA
    filas_visibles = [
        [importar.texto_de_casilla(casilla) for casilla in fila[:COLUMNAS_EN_VISTA]]
        for fila in filas[:FILAS_EN_VISTA]
    ]

    return {
        "vista": "tabla",
        "url": direccion,
        "filas": filas_visibles,
        "total_filas": len(filas),
        "recortado": recortado,
    }


# ----------------------------------------------------------
# API del Formulario 210
#
# La plantilla es una sola para todos los clientes. Lo que se guarda por
# cliente son los valores; el archivo de Excel se arma cuando se pide,
# siempre partiendo de la plantilla limpia. Ver app/formulario.py.
# ----------------------------------------------------------


class ValorFormulario(BaseModel):
    """Un valor que se captura en una casilla de la plantilla."""

    celda: str
    valor: float
    # De dónde salió el dato. Queda en la bitácora.
    documento: str = ""

    @field_validator("celda")
    @classmethod
    def _revisar_celda(cls, valor):
        limpia = (valor or "").strip().upper()
        if not limpia:
            raise ValueError("Falta decir en qué casilla va el valor.")
        return limpia

    @field_validator("documento")
    @classmethod
    def _revisar_documento(cls, valor):
        return (valor or "").strip()[:200]


def _cliente_o_404(id_cliente):
    cliente = db.obtener_cliente(id_cliente)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Ese cliente no existe.")
    return cliente


@app.get("/api/plantilla")
def api_plantilla():
    """Qué plantilla hay puesta y si LibreOffice está disponible."""
    return formulario.resumen_plantilla()


class PlantillaElegida(BaseModel):
    """Cuál de las plantillas de la carpeta se va a usar."""

    nombre: str


@app.put("/api/plantilla/activa")
def api_elegir_plantilla(datos: PlantillaElegida):
    """Cambia la plantilla en uso a otra de las que ya están guardadas."""
    try:
        elegida = formulario.elegir_plantilla(datos.nombre)
    except formulario.SinPlantilla as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"archivo": elegida.name}


@app.post("/api/plantilla", status_code=201)
async def api_subir_plantilla(archivo: UploadFile = File(...)):
    """Guarda la plantilla que subió el contador y la deja en uso.

    El archivo se guarda tal como llegó. Es de él, con su licencia: el
    programa no le quita ni le cambia nada.
    """
    contenido = await archivo.read()
    try:
        guardada = formulario.guardar_plantilla_subida(
            archivo.filename, contenido
        )
    except formulario.SinPlantilla as error:
        raise HTTPException(status_code=400, detail=str(error))
    return formulario.resumen_plantilla() | {"guardada": guardada.name}


@app.get("/api/clientes/{id_cliente}/formulario/hoja")
def api_hoja_formulario(id_cliente: int):
    """La hoja de captura como se ve para este cliente, para el editor."""
    _cliente_o_404(id_cliente)
    try:
        return formulario.hoja_del_cliente(id_cliente)
    except formulario.SinPlantilla as error:
        raise HTTPException(status_code=409, detail=str(error))


@app.get("/api/plantilla/celdas")
def api_buscar_celdas(buscar: str = "", todas: bool = False):
    """Busca casillas de la plantilla por palabra, renglón o celda."""
    try:
        return formulario.buscar_celdas(buscar, solo_esperadas=not todas)
    except formulario.SinPlantilla as error:
        raise HTTPException(status_code=409, detail=str(error))


@app.get("/api/clientes/{id_cliente}/formulario")
def api_formulario(id_cliente: int):
    """Los valores capturados de un cliente y el estado de su archivo."""
    _cliente_o_404(id_cliente)
    try:
        valores = formulario.listar_valores(id_cliente)
    except formulario.SinPlantilla as error:
        raise HTTPException(status_code=409, detail=str(error))
    return {"estado": formulario.estado(id_cliente), "valores": valores}


@app.put("/api/clientes/{id_cliente}/formulario/valores")
def api_guardar_valor(id_cliente: int, datos: ValorFormulario):
    """Guarda el valor de una casilla para este cliente."""
    _cliente_o_404(id_cliente)
    try:
        return formulario.guardar_valor(
            id_cliente, datos.celda, datos.valor, datos.documento
        )
    except formulario.SinPlantilla as error:
        raise HTTPException(status_code=409, detail=str(error))
    except EscrituraBloqueada as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.delete("/api/clientes/{id_cliente}/formulario/valores/{celda}",
            status_code=204)
def api_borrar_valor(id_cliente: int, celda: str):
    """Quita un valor capturado. La casilla vuelve a lo que trae la plantilla."""
    _cliente_o_404(id_cliente)
    if not db.borrar_valor_210(id_cliente, celda.upper().strip()):
        raise HTTPException(
            status_code=404, detail="Esa casilla no tenía ningún valor."
        )


@app.get("/api/clientes/{id_cliente}/formulario/bitacora")
def api_bitacora_formulario(id_cliente: int):
    """El historial de cambios del formulario de este cliente."""
    _cliente_o_404(id_cliente)
    return db.listar_bitacora_210(id_cliente)


@app.post("/api/clientes/{id_cliente}/formulario/generar")
def api_generar_formulario(id_cliente: int):
    """Arma el archivo de Excel de este cliente y devuelve cómo salió."""
    cliente = _cliente_o_404(id_cliente)
    try:
        return formulario.generar(cliente)
    except formulario.SinPlantilla as error:
        raise HTTPException(status_code=409, detail=str(error))
    except EscrituraBloqueada as error:
        raise HTTPException(status_code=400, detail=str(error))
    except VerificacionFallida as error:
        # El archivo se descartó. Es un error grave y hay que decirlo tal
        # cual, sin suavizarlo: el contador no debe usar ese archivo.
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/api/clientes/{id_cliente}/formulario/archivo")
def api_descargar_formulario(id_cliente: int):
    """Descarga el archivo de Excel ya generado de este cliente."""
    cliente = _cliente_o_404(id_cliente)
    archivo = formulario.archivo_cliente(id_cliente)
    if not archivo.exists():
        raise HTTPException(
            status_code=404,
            detail="Todavía no se ha generado el archivo de este cliente.",
        )
    return FileResponse(
        archivo,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        filename=formulario.nombre_para_descargar(cliente),
    )


# ----------------------------------------------------------
# API de Rentai, la asistente
#
# Rentai propone; nunca escribe sola. Cada propuesta la confirma el
# contador desde la pantalla. Ver app/rentai.py.
# ----------------------------------------------------------


class MensajeChat(BaseModel):
    """Lo que el contador le escribe a Rentai."""

    mensaje: str


class PropuestaAceptada(BaseModel):
    """Una propuesta de Rentai que el contador decidió anotar."""

    celda: str
    valor: float
    documento: str = ""


@app.get("/api/rentai")
def api_rentai():
    """Quién es Rentai y si está disponible ahora mismo."""
    return {
        "nombre": rentai.NOMBRE,
        "disponible": configuracion.CONFIG.ia_disponible,
        "motivo": configuracion.CONFIG.motivo,
    }


@app.get("/api/clientes/{id_cliente}/chat")
def api_leer_chat(id_cliente: int):
    """La conversación que va con este cliente."""
    _cliente_o_404(id_cliente)
    return db.listar_mensajes(id_cliente)


@app.post("/api/clientes/{id_cliente}/chat")
def api_hablar(id_cliente: int, datos: MensajeChat):
    """Le manda un mensaje a Rentai sobre este cliente."""
    cliente = _cliente_o_404(id_cliente)
    try:
        return rentai.hablar(cliente, datos.mensaje)
    except rentai.RentaiApagada as error:
        raise HTTPException(status_code=409, detail=str(error))
    except rentai.RentaiFallo as error:
        raise HTTPException(status_code=502, detail=str(error))
    except formulario.SinPlantilla as error:
        raise HTTPException(status_code=409, detail=str(error))


@app.delete("/api/clientes/{id_cliente}/chat", status_code=204)
def api_borrar_chat(id_cliente: int):
    """Borra la conversación. Los valores ya anotados no se tocan."""
    _cliente_o_404(id_cliente)
    db.borrar_mensajes(id_cliente)


@app.post("/api/clientes/{id_cliente}/chat/anotar")
def api_anotar_propuesta(id_cliente: int, datos: PropuestaAceptada):
    """Anota una propuesta que el contador aceptó."""
    _cliente_o_404(id_cliente)
    try:
        return rentai.anotar_propuesta(
            id_cliente, datos.celda, datos.valor, datos.documento
        )
    except EscrituraBloqueada as error:
        raise HTTPException(status_code=400, detail=str(error))
    except formulario.SinPlantilla as error:
        raise HTTPException(status_code=409, detail=str(error))



# ----------------------------------------------------------
# La cuenta
#
# Hoy no hay cuentas de verdad: el programa corre en un computador y lo
# usa una persona. Esta pantalla existe por dos motivos.
#
# El primero es práctico y es el de ahora: que el contador pueda cambiar
# su llave de la IA sin tener que abrir el archivo .env con el bloc de
# notas. Las llaves se vencen, se cambian y se revocan; pedirle que edite
# un archivo escondido cada vez era pedirle demasiado.
#
# El segundo es que el día que haya login, ya hay un lugar donde ponerlo:
# los datos de quién es se guardan en la tabla "ajustes" con el prefijo
# "cuenta_", y las direcciones son /api/cuenta. No se inventó nada de
# usuarios ni de contraseñas todavía — eso está fuera del alcance de la
# versión 1 — pero el sitio ya está hecho.
# ----------------------------------------------------------

# Cómo se llama esta versión del programa cuando alguien pregunta.
VERSION = "prototipo"

# Los ajustes de la cuenta que se guardan en la base, con el prefijo que
# los agrupa. El día que haya varias cuentas, esto es lo que se muda.
AJUSTE_NOMBRE = "cuenta_nombre"
AJUSTE_CORREO = "cuenta_correo"


class CuentaCambios(BaseModel):
    """Los datos de quién usa el programa."""

    nombre: str = ""
    correo: str = ""

    @field_validator("nombre", "correo")
    @classmethod
    def _limpiar(cls, valor):
        # Se recorta a algo razonable: esto es un rótulo, no un campo libre.
        return (valor or "").strip()[:120]


class AjustesIA(BaseModel):
    """Cómo queda configurada la IA.

    `llave` en None significa "no la toque". En "" significa "bórrela".
    """

    sin_ia: bool
    llave: Optional[str] = None
    modelo: str = ""

    @field_validator("llave")
    @classmethod
    def _revisar_llave(cls, valor):
        if valor is None:
            return None
        limpia = valor.strip()
        if not limpia:
            return ""
        # Una llave no tiene espacios ni saltos de línea. Si los trae, casi
        # siempre es porque se copió de más y así no va a funcionar.
        if any(c.isspace() for c in limpia):
            raise ValueError(
                "La llave no puede tener espacios. Cópiela completa y sola."
            )
        if len(limpia) < 20 or len(limpia) > 200:
            raise ValueError("Esa llave no tiene la forma de una llave de Groq.")
        return limpia

    @field_validator("modelo")
    @classmethod
    def _revisar_modelo(cls, valor):
        limpio = (valor or "").strip()[:100]
        if limpio and any(c.isspace() for c in limpio):
            raise ValueError("El nombre del modelo no lleva espacios.")
        return limpio


class LlavePorProbar(BaseModel):
    """Una llave que el contador quiere probar antes de guardarla."""

    llave: str = ""


def _cuenta_como_diccionario():
    """Todo lo que la pantalla de Cuenta necesita saber. Sin la llave."""
    datos = configuracion.CONFIG.como_diccionario()
    datos.update({
        "version": VERSION,
        "nombre": db.leer_ajuste(AJUSTE_NOMBRE, ""),
        "correo": db.leer_ajuste(AJUSTE_CORREO, ""),
        "clientes": len(db.listar_clientes()),
        # contar_documentos() devuelve cuántos tiene cada cliente;
        # aquí solo interesa el total.
        "documentos": sum(db.contar_documentos().values()),
        # Dónde quedaron las cosas, por si hay que respaldarlas o mudarlas.
        "carpeta_datos": str(RAIZ / "datos"),
        "archivo_env": str(configuracion.ARCHIVO_ENV),
        "hay_env": configuracion.ARCHIVO_ENV.exists(),
    })
    return datos


@app.get("/api/cuenta")
def api_cuenta():
    """Quién usa el programa, cómo está configurado y dónde están los datos."""
    return _cuenta_como_diccionario()


@app.put("/api/cuenta")
def api_guardar_cuenta(cambios: CuentaCambios):
    """Guarda el nombre y el correo de quien usa el programa.

    No se usan para nada todavía: salen en el resumen impreso el día que
    se quiera y sirven de sitio para el login cuando lo haya.
    """
    db.guardar_ajuste(AJUSTE_NOMBRE, cambios.nombre)
    db.guardar_ajuste(AJUSTE_CORREO, cambios.correo)
    return _cuenta_como_diccionario()


@app.put("/api/cuenta/ia")
def api_guardar_ia(ajustes: AjustesIA):
    """Cambia el modo de la IA, la llave y el modelo. Escribe el .env.

    Después de escribir se recarga la configuración en caliente, así el
    cambio vale de una vez. La llave se guarda en el .env y nunca en la
    base de datos ni en los logs.
    """
    cambios = {"SIN_IA": "true" if ajustes.sin_ia else "false"}

    if ajustes.llave is not None:
        cambios["GROQ_API_KEY"] = ajustes.llave

    if ajustes.modelo:
        cambios["IA_MODELO"] = ajustes.modelo

    try:
        configuracion.guardar_en_env(cambios)
    except OSError:
        # No se dice cuál archivo falló con detalle del sistema: eso se
        # queda en el servidor. Al contador se le dice qué hacer.
        raise HTTPException(
            status_code=500,
            detail=(
                "No se pudo escribir el archivo de configuración (.env)."
                " Revise que la carpeta del programa no esté protegida"
                " contra escritura."
            ),
        )

    configuracion.CONFIG.recargar()
    return _cuenta_como_diccionario()


@app.post("/api/cuenta/ia/probar")
def api_probar_llave(datos: LlavePorProbar):
    """Prueba una llave contra el servicio, sin guardarla ni mandar datos.

    Si viene vacía se prueba la que ya está guardada. Lo único que sale
    del computador es la llave misma, para preguntar si sirve.
    """
    llave = datos.llave.strip() or configuracion.CONFIG.llave
    sirve, motivo = rentai.probar_llave(llave)
    return {"sirve": sirve, "motivo": motivo}
