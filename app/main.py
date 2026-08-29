"""
Servidor del asistente de organización documental para renta.

Corre en http://localhost:8000 y sirve dos cosas:
  - las páginas de la interfaz (carpeta static/)
  - una pequeña API para leer y guardar clientes y sus documentos

El servidor por dentro está en app/servidor.py, hecho solo con lo que
Python ya trae. Antes esto lo hacía FastAPI; se sacó porque arrastraba un
archivo compilado sin firmar (pydantic_core) que el Control inteligente de
aplicaciones de Windows 11 BLOQUEA, y el programa no arrancaba en el
computador de destino. Las direcciones, los códigos y el JSON quedaron
exactamente iguales: la pantalla no se enteró del cambio.

Nota: no se registra en los logs ningún nombre de cliente ni contenido de
documentos. Solo errores técnicos.
"""

import mimetypes
from datetime import date
from pathlib import Path
from urllib.parse import quote

from app import (
    checklist, configuracion, db, documentos, exportar, formulario, importar,
    lectura, rentai,
)
from app.escribir_210 import EscrituraBloqueada, VerificacionFallida
from app.servidor import Aplicacion, ErrorHttp, Respuesta

# Raíz del proyecto. Este archivo vive en app/, así que subimos un nivel.
# Se usa pathlib (y no texto pegado con / o \) para que las rutas funcionen
# igual en Mac y en Windows.
RAIZ = Path(__file__).resolve().parent.parent
CARPETA_STATIC = RAIZ / "static"

app = Aplicacion()

# Deja disponibles el CSS y el JavaScript en /static/...
app.carpeta_estatica("/static/", CARPETA_STATIC)


# ----------------------------------------------------------
# Páginas
# ----------------------------------------------------------


def _pagina(nombre):
    """Entrega uno de los archivos HTML de la carpeta static."""
    return Respuesta.archivo(CARPETA_STATIC / nombre, tipo="text/html; charset=utf-8")


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


# ----------------------------------------------------------
# Validación de los datos que llegan del navegador
#
# Todo lo que manda el navegador se revisa aquí antes de tocar la base.
#
# Antes esto lo hacían unas clases de pydantic. Ahora son funciones
# sueltas, que hacen lo mismo y se leen igual de fácil: mirar el valor,
# y si está mal, levantar un error con el texto que va a ver el contador.
# ----------------------------------------------------------

# Marca de "este campo no lo mandaron", distinta de "lo mandaron vacío".
# Sirve para saber si hay que borrar un dato o dejarlo como estaba.
NO_MANDADO = ...


def limpiar_nombre(valor):
    """Quita espacios sobrantes y verifica que quede algo."""
    if valor is None:
        return None
    limpio = " ".join(str(valor).split())
    if not limpio:
        raise ValueError("El nombre no puede estar vacío.")
    if len(limpio) > 120:
        raise ValueError("El nombre es demasiado largo.")
    return limpio


def limpiar_digitos(valor):
    """Verifica que sean dos dígitos. Acepta '5' y lo convierte en '05'."""
    if valor is None:
        return None
    limpio = str(valor).strip()
    if not limpio.isdigit() or len(limpio) > 2:
        raise ValueError(
            "Deben ser los dos últimos dígitos de la cédula, por ejemplo 07."
        )
    return limpio.zfill(2)


def limpiar_fecha(valor):
    """Acepta una fecha AAAA-MM-DD, o vacío si todavía no se sabe."""
    if valor is None:
        return None
    limpio = str(valor).strip()
    if not limpio:
        return None
    try:
        date.fromisoformat(limpio)
    except ValueError:
        raise ValueError("La fecha no es válida.")
    return limpio


def revisado(funcion, valor):
    """Aplica una de las funciones de arriba y convierte su queja en un 400.

    Los textos de ValueError están escritos para que los lea el contador,
    así que se le pasan tal cual a la pantalla.
    """
    try:
        return funcion(valor)
    except ValueError as error:
        raise ErrorHttp(400, str(error))


def campo(datos, nombre, por_defecto=None):
    """Saca un campo del JSON que mandó el navegador."""
    return datos.get(nombre, por_defecto)


def campo_texto(datos, nombre, por_defecto=""):
    """Saca un campo y comprueba que sea texto."""
    valor = datos.get(nombre, por_defecto)
    if valor is None:
        return por_defecto
    if not isinstance(valor, str):
        raise ErrorHttp(400, "El campo '%s' tiene que ser texto." % nombre)
    return valor


def campo_numero(datos, nombre):
    """Saca un campo y comprueba que sea un número."""
    valor = datos.get(nombre)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorHttp(400, "El campo '%s' tiene que ser un número." % nombre)
    return float(valor)


def campo_si_o_no(datos, nombre):
    """Saca un campo y comprueba que sea sí o no."""
    valor = datos.get(nombre)
    if not isinstance(valor, bool):
        raise ErrorHttp(400, "El campo '%s' tiene que ser sí o no." % nombre)
    return valor


# ----------------------------------------------------------
# API de clientes
# ----------------------------------------------------------


@app.get("/api/clientes")
def api_listar_clientes(peticion):
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
def api_obtener_cliente(peticion, id_cliente):
    cliente = db.obtener_cliente(id_cliente)
    if cliente is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    return cliente


@app.post("/api/clientes", codigo=201)
def api_crear_cliente(peticion, **partes):
    datos = peticion.diccionario()

    nombre = revisado(limpiar_nombre, campo_texto(datos, "nombre"))
    dos_digitos = revisado(limpiar_digitos, campo_texto(datos, "dos_digitos"))
    fecha = revisado(limpiar_fecha, campo(datos, "fecha_vencimiento"))

    cliente = db.crear_cliente(
        nombre=nombre,
        dos_digitos=dos_digitos,
        fecha_vencimiento=fecha,
        notas=campo(datos, "notas"),
    )
    # Se le arma el checklist sugerido para que no arranque en blanco.
    # Es un punto de partida: el contador lo ajusta como necesite.
    db.crear_renglones(cliente["id"], checklist.LISTA_BASE)
    return cliente


@app.patch("/api/clientes/{id_cliente}")
def api_actualizar_cliente(peticion, id_cliente):
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")

    datos = peticion.diccionario()

    # Se distingue "no mandaron el campo" de "lo mandaron vacío para
    # borrarlo". Por eso se mira si la llave está en el JSON, no si su
    # valor es nulo.
    nombre = (revisado(limpiar_nombre, datos["nombre"])
              if "nombre" in datos else None)
    dos_digitos = (revisado(limpiar_digitos, datos["dos_digitos"])
                   if "dos_digitos" in datos else None)
    fecha = (revisado(limpiar_fecha, datos["fecha_vencimiento"])
             if "fecha_vencimiento" in datos else NO_MANDADO)
    notas = datos["notas"] if "notas" in datos else NO_MANDADO

    return db.actualizar_cliente(
        id_cliente,
        nombre=nombre,
        dos_digitos=dos_digitos,
        fecha_vencimiento=fecha,
        notas=notas,
    )


@app.delete("/api/clientes/{id_cliente}")
def api_eliminar_cliente(peticion, id_cliente):
    if not db.eliminar_cliente(id_cliente):
        raise ErrorHttp(404, "Ese cliente no existe.")
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
def api_listar_documentos(peticion, id_cliente):
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")

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
def api_subir_documentos(peticion, id_cliente):
    """Recibe uno o varios archivos y los guarda en la carpeta del cliente.

    Los ZIP se abren y se guarda lo que traen adentro, no el ZIP.
    Lo que no se pueda guardar se devuelve en la lista `ignorados`, con el
    motivo, para poder mostrárselo al contador en vez de fallar en silencio.
    """
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")

    guardados = []
    ignorados = []

    for nombre_completo, contenido in peticion.archivos("archivos"):
        nombre_completo = nombre_completo or "documento"

        # Basura del sistema: se salta sin avisar, no es un documento.
        if documentos.es_basura(nombre_completo):
            continue

        # El navegador puede mandar la ruta de la carpeta cuando se arrastra
        # una carpeta completa. Aquí solo interesa el nombre del archivo.
        nombre = nombre_completo.replace("\\", "/").split("/")[-1]
        extension = Path(nombre).suffix.lower()

        # --- Caso ZIP: se abre y se guarda lo de adentro ---
        if extension == ".zip":
            if documentos.dentro_del_limite(contenido,
                                            documentos.LIMITE_ZIP) is None:
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

        if documentos.dentro_del_limite(contenido,
                                        documentos.LIMITE_ARCHIVO) is None:
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
def api_abrir_documento(peticion, id_documento):
    """Entrega el archivo original para verlo en el navegador."""
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise ErrorHttp(404, "Ese documento no existe.")

    ruta = documentos.ruta_del_documento(
        documento["cliente_id"], documento["nombre_guardado"]
    )
    if ruta is None or not ruta.is_file():
        raise ErrorHttp(404, "El archivo ya no está en el disco.")

    tipo, _ = mimetypes.guess_type(documento["nombre_guardado"])

    # Se manda "inline" para que el navegador lo muestre en vez de
    # descargarlo, y el nombre codificado para que las tildes y las eñes
    # no se dañen. De eso se encarga Respuesta.archivo.
    return Respuesta.archivo(
        ruta,
        tipo=tipo or "application/octet-stream",
        nombre_visible=documento["nombre_original"],
        descargar=False,
    )


@app.delete("/api/documentos/{id_documento}")
def api_eliminar_documento(peticion, id_documento):
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise ErrorHttp(404, "Ese documento no existe.")

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


@app.post("/api/importar/analizar")
def api_analizar_importacion(peticion, **partes):
    """Lee el archivo y devuelve los clientes propuestos, sin guardar nada."""
    nombre, contenido = peticion.archivos("archivo")[0]
    nombre = nombre or "archivo"

    if documentos.dentro_del_limite(contenido,
                                    importar.LIMITE_ARCHIVO) is None:
        raise ErrorHttp(400, "El archivo pesa más de 10 MB.")
    if not contenido:
        raise ErrorHttp(400, "El archivo está vacío.")

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
        raise ErrorHttp(400, str(error))


@app.post("/api/importar/confirmar")
def api_confirmar_importacion(peticion, **partes):
    """Crea los clientes que el contador ya revisó.

    Cada fila se valida por separado: si una tiene un problema, se anota
    y se sigue con las demás en vez de perder todo el trabajo.
    """
    clientes = peticion.lista()

    if not clientes:
        raise ErrorHttp(400, "No se seleccionó ningún cliente para crear.")
    if len(clientes) > importar.LIMITE_FILAS:
        raise ErrorHttp(400, "Son demasiados clientes de una sola vez.")

    creados = []
    errores = []

    for numero, fila in enumerate(clientes, start=1):
        if not isinstance(fila, dict):
            errores.append("Fila " + str(numero) + ": llegó mal armada.")
            continue
        try:
            nombre = limpiar_nombre(fila.get("nombre", ""))
            dos_digitos = limpiar_digitos(fila.get("dos_digitos", ""))
            fecha = limpiar_fecha(fila.get("fecha_vencimiento"))
        except ValueError as error:
            errores.append("Fila " + str(numero) + ": " + str(error))
            continue

        notas = (fila.get("notas") or "").strip() or None
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


@app.get("/api/clientes/{id_cliente}/checklist")
def api_listar_checklist(peticion, id_cliente):
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    renglones = db.listar_checklist(id_cliente)
    conteos = db.contar_documentos_por_renglon(id_cliente)
    for renglon in renglones:
        renglon["documentos"] = conteos.get(renglon["id"], 0)
    return renglones


@app.post("/api/clientes/{id_cliente}/checklist", codigo=201)
def api_agregar_renglon(peticion, id_cliente):
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    datos = peticion.diccionario()
    titulo = revisado(checklist.limpiar_titulo, campo_texto(datos, "titulo"))
    return db.crear_renglon(id_cliente, titulo)


@app.post("/api/clientes/{id_cliente}/checklist/base", codigo=201)
def api_agregar_lista_base(peticion, id_cliente):
    """Agrega la lista sugerida al checklist del cliente.

    Sirve para los clientes que quedaron sin checklist (los creados con
    una versión anterior del programa) y para el contador que borró todo
    y quiere volver a empezar.
    """
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    return db.crear_renglones(id_cliente, checklist.LISTA_BASE)


@app.patch("/api/checklist/{id_renglon}")
def api_actualizar_renglon(peticion, id_renglon):
    if db.obtener_renglon(id_renglon) is None:
        raise ErrorHttp(404, "Ese renglón no existe.")

    datos = peticion.diccionario()
    titulo = None
    estado = None
    if datos.get("titulo") is not None:
        titulo = revisado(checklist.limpiar_titulo, datos["titulo"])
    if datos.get("estado") is not None:
        estado = revisado(checklist.limpiar_estado, datos["estado"])

    return db.actualizar_renglon(id_renglon, titulo=titulo, estado=estado)


@app.delete("/api/checklist/{id_renglon}")
def api_eliminar_renglon(peticion, id_renglon):
    if db.obtener_renglon(id_renglon) is None:
        raise ErrorHttp(404, "Ese renglón no existe.")
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


# ----------------------------------------------------------
# Asignar un documento a un renglón del checklist
#
# Esto es lo que conecta las dos mitades del programa: el archivo que
# llegó y la casilla que lo estaba esperando. Por ahora lo hace el
# contador a mano; más adelante se le puede sugerir automáticamente.
# ----------------------------------------------------------


@app.patch("/api/documentos/{id_documento}")
def api_asignar_documento(peticion, id_documento):
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise ErrorHttp(404, "Ese documento no existe.")

    datos = peticion.diccionario()
    renglon_id = datos.get("renglon_id")

    if renglon_id is not None:
        if not isinstance(renglon_id, int) or isinstance(renglon_id, bool):
            raise ErrorHttp(400, "El renglón tiene que ser un número.")

        renglon = db.obtener_renglon(renglon_id)
        if renglon is None:
            raise ErrorHttp(404, "Ese renglón no existe.")
        if renglon["cliente_id"] != documento["cliente_id"]:
            raise ErrorHttp(400, "Ese renglón es de otro cliente.")
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
def api_vista_documento(peticion, id_documento):
    """Prepara lo que hace falta para mostrar el documento en pantalla.

    Los PDF y las imágenes los sabe mostrar el navegador solo, así que
    para esos basta con devolver la dirección del archivo. El XML y las
    hojas de cálculo hay que leerlos aquí.
    """
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise ErrorHttp(404, "Ese documento no existe.")

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
        raise ErrorHttp(404, "El archivo ya no está en el disco.")

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


def limpiar_celda(valor):
    """El nombre de una casilla de la plantilla, en mayúsculas: G115."""
    limpia = (valor or "").strip().upper()
    if not limpia:
        raise ValueError("Falta decir en qué casilla va el valor.")
    return limpia


def _cliente_o_404(id_cliente):
    cliente = db.obtener_cliente(id_cliente)
    if cliente is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    return cliente


@app.get("/api/plantilla")
def api_plantilla(peticion):
    """Qué plantilla hay puesta y si LibreOffice está disponible."""
    return formulario.resumen_plantilla()


@app.put("/api/plantilla/activa")
def api_elegir_plantilla(peticion, **partes):
    """Cambia la plantilla en uso a otra de las que ya están guardadas."""
    datos = peticion.diccionario()
    try:
        elegida = formulario.elegir_plantilla(campo_texto(datos, "nombre"))
    except formulario.SinPlantilla as error:
        raise ErrorHttp(400, str(error))
    return {"archivo": elegida.name}


@app.post("/api/plantilla", codigo=201)
def api_subir_plantilla(peticion, **partes):
    """Guarda la plantilla que subió el contador y la deja en uso.

    El archivo se guarda tal como llegó. Es de él, con su licencia: el
    programa no le quita ni le cambia nada.
    """
    nombre, contenido = peticion.archivos("archivo")[0]
    try:
        guardada = formulario.guardar_plantilla_subida(nombre, contenido)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(400, str(error))

    resumen = formulario.resumen_plantilla()
    resumen["guardada"] = guardada.name
    return resumen


@app.get("/api/clientes/{id_cliente}/formulario/hoja")
def api_hoja_formulario(peticion, id_cliente):
    """La hoja de captura como se ve para este cliente, para el editor."""
    _cliente_o_404(id_cliente)
    try:
        return formulario.hoja_del_cliente(id_cliente)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))


@app.get("/api/plantilla/celdas")
def api_buscar_celdas(peticion, **partes):
    """Busca casillas de la plantilla por palabra, renglón o celda."""
    buscar = peticion.texto_de("buscar", "")
    todas = peticion.si_o_no("todas", False)
    try:
        return formulario.buscar_celdas(buscar, solo_esperadas=not todas)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))


@app.get("/api/clientes/{id_cliente}/formulario")
def api_formulario(peticion, id_cliente):
    """Los valores capturados de un cliente y el estado de su archivo."""
    _cliente_o_404(id_cliente)
    try:
        valores = formulario.listar_valores(id_cliente)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))
    return {"estado": formulario.estado(id_cliente), "valores": valores}


@app.put("/api/clientes/{id_cliente}/formulario/valores")
def api_guardar_valor(peticion, id_cliente):
    """Guarda el valor de una casilla para este cliente."""
    _cliente_o_404(id_cliente)

    datos = peticion.diccionario()
    celda = revisado(limpiar_celda, campo_texto(datos, "celda"))
    valor = campo_numero(datos, "valor")
    documento = campo_texto(datos, "documento", "").strip()[:200]

    try:
        return formulario.guardar_valor(id_cliente, celda, valor, documento)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))
    except EscrituraBloqueada as error:
        raise ErrorHttp(400, str(error))


@app.delete("/api/clientes/{id_cliente}/formulario/valores/{celda}")
def api_borrar_valor(peticion, id_cliente, celda):
    """Quita un valor capturado. La casilla vuelve a lo que trae la plantilla."""
    _cliente_o_404(id_cliente)
    if not db.borrar_valor_210(id_cliente, celda.upper().strip()):
        raise ErrorHttp(404, "Esa casilla no tenía ningún valor.")


@app.get("/api/clientes/{id_cliente}/formulario/bitacora")
def api_bitacora_formulario(peticion, id_cliente):
    """El historial de cambios del formulario de este cliente."""
    _cliente_o_404(id_cliente)
    return db.listar_bitacora_210(id_cliente)


@app.post("/api/clientes/{id_cliente}/formulario/generar")
def api_generar_formulario(peticion, id_cliente):
    """Arma el archivo de Excel de este cliente y devuelve cómo salió."""
    cliente = _cliente_o_404(id_cliente)
    try:
        return formulario.generar(cliente)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))
    except EscrituraBloqueada as error:
        raise ErrorHttp(400, str(error))
    except VerificacionFallida as error:
        # El archivo se descartó. Es un error grave y hay que decirlo tal
        # cual, sin suavizarlo: el contador no debe usar ese archivo.
        raise ErrorHttp(500, str(error))


@app.get("/api/clientes/{id_cliente}/formulario/archivo")
def api_descargar_formulario(peticion, id_cliente):
    """Descarga el archivo de Excel ya generado de este cliente."""
    cliente = _cliente_o_404(id_cliente)
    archivo = formulario.archivo_cliente(id_cliente)
    if not archivo.exists():
        raise ErrorHttp(
            404, "Todavía no se ha generado el archivo de este cliente."
        )
    return Respuesta.archivo(
        archivo,
        tipo=("application/vnd.openxmlformats-officedocument"
              ".spreadsheetml.sheet"),
        nombre_visible=formulario.nombre_para_descargar(cliente),
        descargar=True,
    )


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
    _cliente_o_404(id_cliente)
    return db.listar_mensajes(id_cliente)


@app.post("/api/clientes/{id_cliente}/chat")
def api_hablar(peticion, id_cliente):
    """Le manda un mensaje a Rentai sobre este cliente."""
    cliente = _cliente_o_404(id_cliente)
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
    _cliente_o_404(id_cliente)
    db.borrar_mensajes(id_cliente)


@app.post("/api/clientes/{id_cliente}/chat/anotar")
def api_anotar_propuesta(peticion, id_cliente):
    """Anota una propuesta que el contador aceptó."""
    _cliente_o_404(id_cliente)

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
def api_cuenta(peticion):
    """Quién usa el programa, cómo está configurado y dónde están los datos."""
    return _cuenta_como_diccionario()


@app.put("/api/cuenta")
def api_guardar_cuenta(peticion, **partes):
    """Guarda el nombre y el correo de quien usa el programa.

    No se usan para nada todavía: salen en el resumen impreso el día que
    se quiera y sirven de sitio para el login cuando lo haya.
    """
    datos = peticion.diccionario()
    # Se recorta a algo razonable: esto es un rótulo, no un campo libre.
    db.guardar_ajuste(AJUSTE_NOMBRE, campo_texto(datos, "nombre", "").strip()[:120])
    db.guardar_ajuste(AJUSTE_CORREO, campo_texto(datos, "correo", "").strip()[:120])
    return _cuenta_como_diccionario()


def limpiar_llave(valor):
    """Revisa una llave de la IA antes de escribirla en el .env."""
    limpia = valor.strip()
    if not limpia:
        return ""
    # Una llave no tiene espacios ni saltos de línea. Si los trae, casi
    # siempre es porque se copió de más y así no va a funcionar.
    if any(c.isspace() for c in limpia):
        raise ValueError("La llave no puede tener espacios. Cópiela completa y sola.")
    if len(limpia) < 20 or len(limpia) > 200:
        raise ValueError("Esa llave no tiene la forma de una llave de Groq.")
    return limpia


def limpiar_modelo(valor):
    """Revisa el nombre del modelo de IA."""
    limpio = (valor or "").strip()[:100]
    if limpio and any(c.isspace() for c in limpio):
        raise ValueError("El nombre del modelo no lleva espacios.")
    return limpio


@app.put("/api/cuenta/ia")
def api_guardar_ia(peticion, **partes):
    """Cambia el modo de la IA, la llave y el modelo. Escribe el .env.

    Después de escribir se recarga la configuración en caliente, así el
    cambio vale de una vez. La llave se guarda en el .env y nunca en la
    base de datos ni en los logs.
    """
    datos = peticion.diccionario()

    sin_ia = campo_si_o_no(datos, "sin_ia")
    modelo = revisado(limpiar_modelo, campo_texto(datos, "modelo", ""))

    cambios = {"SIN_IA": "true" if sin_ia else "false"}

    # llave sin mandar = "no la toque". Mandada vacía = "bórrela".
    if "llave" in datos and datos["llave"] is not None:
        cambios["GROQ_API_KEY"] = revisado(
            limpiar_llave, campo_texto(datos, "llave", "")
        )

    if modelo:
        cambios["IA_MODELO"] = modelo

    try:
        configuracion.guardar_en_env(cambios)
    except OSError:
        # No se dice cuál archivo falló con detalle del sistema: eso se
        # queda en el servidor. Al contador se le dice qué hacer.
        raise ErrorHttp(
            500,
            "No se pudo escribir el archivo de configuración (.env)."
            " Revise que la carpeta del programa no esté protegida"
            " contra escritura.",
        )

    configuracion.CONFIG.recargar()
    return _cuenta_como_diccionario()


@app.post("/api/cuenta/ia/probar")
def api_probar_llave(peticion, **partes):
    """Prueba una llave contra el servicio, sin guardarla ni mandar datos.

    Si viene vacía se prueba la que ya está guardada. Lo único que sale
    del computador es la llave misma, para preguntar si sirve.
    """
    datos = peticion.diccionario()
    llave = campo_texto(datos, "llave", "").strip() or configuracion.CONFIG.llave
    sirve, motivo = rentai.probar_llave(llave)
    return {"sirve": sirve, "motivo": motivo}


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
