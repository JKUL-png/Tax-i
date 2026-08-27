"""
Manejo de los archivos que sube el contador.

Aquí vive todo lo que tiene que ver con el disco:
  - revisar que el archivo sea de un tipo que sirve
  - limpiar el nombre para que Windows lo acepte
  - guardarlo en datos/archivos/<id del cliente>/
  - abrir los ZIP y sacar lo que traen adentro

Nada de esto sale del computador. No se escribe en los logs ningún nombre
de archivo ni de cliente.
"""

import io
import re
import zipfile
from pathlib import Path

# Rutas relativas a la raíz del proyecto (este archivo vive en app/).
RAIZ = Path(__file__).resolve().parent.parent
CARPETA_ARCHIVOS = RAIZ / "datos" / "archivos"


# ----------------------------------------------------------
# Qué se acepta
# ----------------------------------------------------------

# Extensiones que el prototipo sabe recibir. Todo lo demás se rechaza
# con un mensaje claro, en vez de guardarlo y que estorbe después.
EXTENSIONES_DOCUMENTO = {".pdf", ".xml"}
EXTENSIONES_FOTO = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif"}
EXTENSIONES_PERMITIDAS = EXTENSIONES_DOCUMENTO | EXTENSIONES_FOTO

# Límites. Están para que un archivo enorme o un ZIP mal hecho no dejen
# el programa colgado ni llenen el disco.
LIMITE_ARCHIVO = 25 * 1024 * 1024        # 25 MB por archivo suelto
LIMITE_ZIP = 100 * 1024 * 1024           # 100 MB el ZIP comprimido
LIMITE_ZIP_EXPANDIDO = 200 * 1024 * 1024  # 200 MB ya descomprimido
LIMITE_ARCHIVOS_EN_ZIP = 300             # cuántos archivos saca de un ZIP


def tipo_legible(extension):
    """Nombre del tipo de archivo para mostrar en pantalla."""
    if extension == ".pdf":
        return "PDF"
    if extension == ".xml":
        return "XML"
    if extension in EXTENSIONES_FOTO:
        return "Foto"
    return extension.replace(".", "").upper()


# ----------------------------------------------------------
# Limpieza de nombres de archivo
#
# Windows es mucho más estricto que Mac con los nombres. Un archivo que
# se guarda bien en el Mac del desarrollador puede reventar en el Windows
# del contador. Por eso se limpia SIEMPRE antes de guardar.
# ----------------------------------------------------------

# Caracteres que Windows no permite en un nombre de archivo.
CARACTERES_PROHIBIDOS = r'[<>:"/\\|?*\x00-\x1f]'

# Nombres que Windows tiene reservados para dispositivos. Un archivo
# llamado "CON.pdf" no se puede crear en Windows, ni siquiera con extensión.
NOMBRES_RESERVADOS = (
    {"CON", "PRN", "AUX", "NUL"}
    | {"COM" + str(n) for n in range(1, 10)}
    | {"LPT" + str(n) for n in range(1, 10)}
)


def es_basura(nombre):
    """Dice si el archivo es basura del sistema y no un documento.

    macOS mete estos archivos en las carpetas y dentro de los ZIP sin que
    el usuario se entere. No son documentos del cliente.
    """
    partes = nombre.replace("\\", "/").split("/")
    for parte in partes:
        if parte == "__MACOSX":
            return True
    solo_nombre = partes[-1]
    if solo_nombre.startswith("._"):
        return True
    if solo_nombre in (".DS_Store", "Thumbs.db", "desktop.ini"):
        return True
    return False


def sanitizar_nombre(nombre):
    """Convierte cualquier nombre en uno que Windows y Mac acepten.

    Ejemplo: 'Certificado 2025: Bancolombia.pdf'
             -> 'Certificado 2025- Bancolombia.pdf'
    """
    # 1. Quedarse solo con el nombre, sin carpetas. Esto también evita que
    #    un ZIP con rutas como '../../algo.pdf' escriba fuera de su carpeta.
    solo_nombre = nombre.replace("\\", "/").split("/")[-1]

    # 2. Reemplazar los caracteres que Windows prohíbe.
    limpio = re.sub(CARACTERES_PROHIBIDOS, "-", solo_nombre)

    # 3. Separar el nombre de la extensión.
    ruta = Path(limpio)
    base = ruta.stem
    extension = ruta.suffix.lower()

    # 4. Windows no acepta nombres que terminen en punto o en espacio.
    base = base.strip().rstrip(". ")

    # 5. Si quedó vacío (por ejemplo el nombre era solo '...'), poner uno.
    if not base:
        base = "documento"

    # 6. Nombres reservados de Windows: se les pone un guion bajo adelante.
    if base.upper() in NOMBRES_RESERVADOS:
        base = "_" + base

    # 7. Recortar si es larguísimo. Windows tiene un tope de ruta total.
    if len(base) > 100:
        base = base[:100].rstrip(". ")

    return base + extension


def nombre_libre(carpeta, nombre):
    """Si ya existe un archivo con ese nombre, le agrega (2), (3), etc.

    Así el contador puede subir dos veces 'certificado.pdf' de dos bancos
    distintos sin que el segundo borre al primero.
    """
    destino = carpeta / nombre
    if not destino.exists():
        return nombre

    ruta = Path(nombre)
    base = ruta.stem
    extension = ruta.suffix
    numero = 2
    while True:
        intento = base + " (" + str(numero) + ")" + extension
        if not (carpeta / intento).exists():
            return intento
        numero += 1


# ----------------------------------------------------------
# Carpetas
# ----------------------------------------------------------


def carpeta_del_cliente(id_cliente):
    """Devuelve (y crea si hace falta) la carpeta de archivos del cliente."""
    carpeta = CARPETA_ARCHIVOS / str(int(id_cliente))
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def ruta_del_documento(id_cliente, nombre_guardado):
    """Ruta completa de un documento, verificando que no se salga de la carpeta.

    La verificación es por seguridad: aunque el nombre venga de la base de
    datos, se comprueba que el archivo esté realmente dentro de la carpeta
    del cliente y no en cualquier otro lugar del disco.
    """
    carpeta = carpeta_del_cliente(id_cliente).resolve()
    destino = (carpeta / nombre_guardado).resolve()
    if carpeta not in destino.parents:
        return None
    return destino


def eliminar_carpeta_cliente(id_cliente):
    """Borra la carpeta con todos los archivos de un cliente.

    Se usa cuando se elimina el cliente, para no dejar documentos
    confidenciales sueltos en el disco.
    """
    carpeta = CARPETA_ARCHIVOS / str(int(id_cliente))
    if not carpeta.exists():
        return
    for archivo in carpeta.iterdir():
        if archivo.is_file():
            archivo.unlink()
    carpeta.rmdir()


# ----------------------------------------------------------
# Guardar
# ----------------------------------------------------------


def guardar_contenido(id_cliente, nombre_original, contenido):
    """Escribe un archivo en la carpeta del cliente.

    Devuelve (nombre_guardado, tamaño). El nombre guardado puede ser
    distinto del original: se limpió para Windows y se le pudo agregar
    un número si ya existía.
    """
    carpeta = carpeta_del_cliente(id_cliente)
    nombre = nombre_libre(carpeta, sanitizar_nombre(nombre_original))
    # Modo "wb": bytes crudos. Aquí no aplica encoding porque no es texto.
    (carpeta / nombre).write_bytes(contenido)
    return nombre, len(contenido)


async def leer_con_limite(archivo, limite):
    """Lee una subida por pedazos y se detiene si pasa del límite.

    Se lee de a un pedazo y no todo de una para que un archivo gigante
    no se cargue entero en la memoria antes de darnos cuenta.
    Devuelve None si el archivo era demasiado grande.
    """
    pedazos = []
    total = 0
    while True:
        pedazo = await archivo.read(1024 * 1024)   # 1 MB cada vez
        if not pedazo:
            break
        total += len(pedazo)
        if total > limite:
            return None
        pedazos.append(pedazo)
    return b"".join(pedazos)


# ----------------------------------------------------------
# ZIP
# ----------------------------------------------------------


def nombre_dentro_del_zip(info):
    """Saca el nombre real de un archivo que viene dentro de un ZIP.

    Un ZIP puede guardar los nombres de dos maneras, y avisa cuál usó con
    una banderita (el bit 0x800):

      - Bandera puesta: los nombres van en UTF-8. Python los lee bien solo.
      - Bandera apagada: van en una codificación vieja de DOS (cp437).
        Python asume cp437, que es lo correcto para los ZIP hechos con el
        Explorador de Windows: ahí la ñ y las tildes salen bien.

    El problema son los ZIP que guardan los nombres en UTF-8 pero se les
    olvida poner la bandera (los hacen algunos celulares y programas de
    compresión). Python los lee como cp437 y 'Niño.pdf' aparece como
    'Ni├▒o.pdf'. Para esos se recuperan los bytes originales y se leen
    como UTF-8.
    """
    if info.flag_bits & 0x800:
        return info.filename

    try:
        # Deshace la lectura de Python para volver a los bytes tal como
        # están escritos dentro del ZIP.
        crudo = info.filename.encode("cp437")
    except UnicodeEncodeError:
        return info.filename

    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        # No era UTF-8: entonces sí era cp437 de verdad y Python ya lo
        # había leído bien.
        return info.filename


def abrir_zip(contenido):
    """Saca los archivos útiles de un ZIP, sin escribir nada todavía.

    Devuelve dos listas:
      - encontrados: pares (nombre, contenido) listos para guardar
      - ignorados:   textos explicando qué se dejó por fuera y por qué
    """
    encontrados = []
    ignorados = []

    try:
        paquete = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile:
        return [], ["El archivo ZIP está dañado o no se pudo abrir."]

    total_expandido = 0

    with paquete:
        for info in paquete.infolist():
            if len(encontrados) >= LIMITE_ARCHIVOS_EN_ZIP:
                ignorados.append(
                    "El ZIP traía más de " + str(LIMITE_ARCHIVOS_EN_ZIP)
                    + " archivos. Se tomaron los primeros."
                )
                break

            nombre = nombre_dentro_del_zip(info)

            # Las carpetas dentro del ZIP no son documentos.
            if info.is_dir():
                continue

            # Basura de macOS y de Windows.
            if es_basura(nombre):
                continue

            solo_nombre = nombre.replace("\\", "/").split("/")[-1]
            extension = Path(solo_nombre).suffix.lower()

            if extension == ".zip":
                ignorados.append(solo_nombre + " — es un ZIP dentro de otro ZIP.")
                continue

            if extension not in EXTENSIONES_PERMITIDAS:
                ignorados.append(solo_nombre + " — tipo de archivo no admitido.")
                continue

            if info.file_size > LIMITE_ARCHIVO:
                ignorados.append(solo_nombre + " — pesa más de 25 MB.")
                continue

            total_expandido += info.file_size
            if total_expandido > LIMITE_ZIP_EXPANDIDO:
                ignorados.append(
                    "El ZIP descomprimido pesa demasiado. Se cortó ahí."
                )
                break

            try:
                datos = paquete.read(info)
            except Exception:
                ignorados.append(solo_nombre + " — no se pudo leer del ZIP.")
                continue

            encontrados.append((solo_nombre, datos))

    return encontrados, ignorados
