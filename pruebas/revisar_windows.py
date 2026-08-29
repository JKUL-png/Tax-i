"""
Revisión del programa en un computador con Windows.

Para qué es
-----------
Tax-i se escribe en un Mac y se va a usar en un Windows. Hay errores que
NO aparecen en el Mac por más que uno pruebe: los nombres de archivo con
dos puntos, las tildes que se vuelven signos raros, los ZIP hechos con el
Explorador, el .bat que no arranca. Todos aparecen allá, con el contador
al frente y sin nadie que pueda depurarlos.

Este archivo va al computador con Windows junto con el resto del programa
y contesta una sola pregunta: **funciona o no funciona, y si no, qué**.

Cómo se corre
-------------
Primero haga doble clic en iniciar.bat una vez, para que arme el entorno
y baje las librerías. Apáguelo con Control + C. Después, en esa misma
carpeta, abra la terminal (escriba cmd en la barra de direcciones del
Explorador y dele Enter) y pegue esto:

    .venv\\Scripts\\python.exe pruebas\\revisar_windows.py

En el Mac también corre, para revisar antes de mandarlo:

    .venv/bin/python pruebas/revisar_windows.py

Las revisiones que solo tienen sentido en Windows se saltan solas en el
Mac y se anuncian como saltadas, no como aprobadas.

No toca nada
------------
No borra ni cambia ningún documento ni ningún cliente. Lo único que
escribe son archivos de prueba en una carpeta temporal del sistema y un
archivo suelto dentro de datos/, que borra al terminar.
"""

import os
import platform
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ES_WINDOWS = os.name == "nt"

# En la consola de Windows la salida sale en cp850 o cp1252 y una tilde
# la tumba con un error feo. Se pide UTF-8 y, si no se puede, se manda a
# reemplazar lo que no quepa en vez de reventar.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


resultados = []


def titulo(texto):
    print("\n" + texto)
    print("-" * len(texto))


def comprobar(descripcion, condicion, detalle=""):
    """Anota una revisión y la imprime."""
    condicion = bool(condicion)
    resultados.append(condicion)
    marca = "OK   " if condicion else "FALLA"
    print("  %s  %s" % (marca, descripcion))
    if detalle:
        print("           %s" % detalle)
    return condicion


def saltada(descripcion, motivo):
    """Una revisión que aquí no aplica. No cuenta ni a favor ni en contra."""
    print("  ----   %s" % descripcion)
    print("           %s" % motivo)


def aviso(texto):
    """Algo que conviene saber pero que no es una falla."""
    print("  AVISO  %s" % texto)


# ==========================================================
# A. El computador
# ==========================================================

def revisar_computador():
    titulo("A. El computador")

    version = sys.version_info
    comprobar(
        "Python es 3.9 o más nuevo",
        version >= (3, 9),
        "hay Python %d.%d.%d" % version[:3],
    )

    print("           sistema: %s %s" % (platform.system(), platform.release()))

    # Que la consola pueda escribir tildes y eñes. Si esto falla, cualquier
    # mensaje del programa con el nombre de un cliente colombiano revienta.
    prueba = "Ñoño Muñoz — cédula, declaración, año"
    try:
        codificacion = sys.stdout.encoding or "desconocida"
        prueba.encode(codificacion, errors="strict")
        pudo = True
    except (UnicodeEncodeError, LookupError):
        pudo = False
    comprobar(
        "la consola escribe tildes y eñes sin romperse",
        pudo,
        "la consola usa %s" % (sys.stdout.encoding or "desconocida"),
    )

    if ES_WINDOWS:
        largo = len(str(RAIZ))
        comprobar(
            "la carpeta del proyecto no está demasiado adentro",
            largo < 150,
            "la ruta mide %d caracteres; Windows corta las rutas en 260 y"
            " los documentos van varias carpetas más adentro" % largo,
        )
    else:
        saltada("el largo de la ruta", "solo importa en Windows")


# ==========================================================
# B. El proyecto llegó completo
# ==========================================================

def revisar_proyecto():
    titulo("B. El proyecto llegó completo")

    necesarios = [
        "app/main.py", "app/db.py", "app/configuracion.py",
        "app/documentos.py", "app/rentai.py",
        "static/index.html", "static/cuenta.html", "static/estilos.css",
        "requirements.txt", "iniciar.bat",
    ]
    faltan = [n for n in necesarios if not (RAIZ / n).exists()]
    comprobar(
        "están todos los archivos del programa",
        not faltan,
        "faltan: " + ", ".join(faltan) if faltan else "",
    )

    # El .bat necesita saltos de línea de Windows. Con saltos de Mac,
    # cmd.exe puede no encontrar las etiquetas (:instalar, :arrancar) y
    # el lanzador se cierra sin decir por qué.
    bat = RAIZ / "iniciar.bat"
    if bat.exists():
        crudo = bat.read_bytes()
        comprobar(
            "iniciar.bat tiene saltos de línea de Windows (CRLF)",
            b"\r\n" in crudo,
            "si se abre con LF, cmd.exe puede no encontrar las etiquetas"
            " y cerrarse sin explicación",
        )

    # Que todo el código se pueda leer como UTF-8. Si un archivo se guardó
    # en otra codificación, en Windows falla al leerlo.
    malos = []
    for patron in ("app/*.py", "static/*.js", "static/*.html", "static/*.css",
                   "pruebas/*.py"):
        for archivo in RAIZ.glob(patron):
            try:
                archivo.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                malos.append(archivo.name)
    comprobar(
        "todos los archivos del programa se leen como UTF-8",
        not malos,
        "no se pudieron leer: " + ", ".join(malos) if malos else "",
    )


# ==========================================================
# C. Las librerías
# ==========================================================

def revisar_librerias():
    titulo("C. Las librerías")

    # (qué se importa, para qué sirve, cómo se llama al instalarlo)
    librerias = [
        ("fastapi", "el servidor", "fastapi"),
        ("uvicorn", "el que lo prende", "uvicorn[standard]"),
        ("multipart", "recibir los archivos que se suben", "python-multipart"),
        ("openpyxl", "leer y escribir el Excel del 210", "openpyxl"),
        ("pypdf", "sacar el texto de los PDF", "pypdf"),
    ]
    for modulo, para_que, nombre_pip in librerias:
        try:
            __import__(modulo)
            bien = True
        except ImportError:
            bien = False
        comprobar(
            "está instalado %s (%s)" % (nombre_pip, para_que),
            bien,
            "" if bien else "instálelo con: .venv\\Scripts\\python.exe -m pip"
                            " install %s" % nombre_pip,
        )


# ==========================================================
# D. Los nombres de archivo
#
# Este es el error más típico de todos: un cliente manda
# "Certificado 2025: Bancolombia.pdf" y en el Mac se guarda sin problema.
# En Windows los dos puntos están prohibidos y el guardado revienta.
# ==========================================================

def revisar_nombres():
    titulo("D. Los nombres de archivo")

    try:
        from app import documentos
    except ImportError as error:
        comprobar("se pudo cargar el módulo de documentos", False, str(error))
        return

    hostiles = [
        'Certificado 2025: Bancolombia.pdf',
        'Retencion <2025>.pdf',
        'Extracto | enero.pdf',
        'CON.pdf',
        'LPT1.pdf',
        'documento.pdf ',
        'documento..pdf',
        '../../fuera.pdf',
        'C:\\Users\\otro\\cosa.pdf',
        'Declaración año 2025 ñ.pdf',
        '?.pdf',
    ]

    prohibidos = set('<>:"/\\|?*')
    reservados = documentos.NOMBRES_RESERVADOS

    limpios = []
    problemas = []
    for nombre in hostiles:
        limpio = documentos.sanitizar_nombre(nombre)
        limpios.append(limpio)
        base = limpio.rsplit(".", 1)[0]
        if set(limpio) & prohibidos:
            problemas.append("%s -> %s (caracter prohibido)" % (nombre, limpio))
        elif base.upper() in reservados:
            problemas.append("%s -> %s (nombre reservado)" % (nombre, limpio))
        elif limpio != limpio.rstrip(". "):
            problemas.append("%s -> %s (termina en punto o espacio)"
                             % (nombre, limpio))
        elif not base:
            problemas.append("%s -> quedó sin nombre" % nombre)

    comprobar(
        "los nombres hostiles quedan legales para Windows",
        not problemas,
        " | ".join(problemas) if problemas else "se probaron %d nombres"
                                                % len(hostiles),
    )

    # Y ahora la prueba de verdad: crear los archivos. Que el nombre se vea
    # legal no basta; lo que importa es que el sistema lo acepte.
    with tempfile.TemporaryDirectory() as temporal:
        carpeta = Path(temporal)
        fallaron = []
        for limpio in limpios:
            try:
                (carpeta / limpio).write_bytes(b"prueba")
            except OSError as error:
                fallaron.append("%s (%s)" % (limpio, error.strerror or error))
        comprobar(
            "los archivos con esos nombres se crean de verdad",
            not fallaron,
            " | ".join(fallaron) if fallaron else "se crearon %d archivos"
                                                  % len(limpios),
        )

    # La basura de macOS no debe entrar como si fuera un documento.
    basura = ["__MACOSX/algo.pdf", "._certificado.pdf", ".DS_Store",
              "Thumbs.db"]
    coladas = [b for b in basura if not documentos.es_basura(b)]
    comprobar(
        "la basura del sistema se reconoce y no entra",
        not coladas,
        "se colaron: " + ", ".join(coladas) if coladas else "",
    )


# ==========================================================
# E. Los ZIP con tildes
#
# Los ZIP hechos con el Explorador de Windows guardan los nombres en una
# codificación vieja de DOS. Los hechos por otros programas los guardan en
# UTF-8 pero a veces se les olvida avisarlo. Si esto se lee mal, el
# contador ve "Ni├▒o.pdf" en la pantalla.
# ==========================================================

def revisar_zip():
    titulo("E. Los ZIP con tildes")

    try:
        from app import documentos
    except ImportError as error:
        comprobar("se pudo cargar el módulo de documentos", False, str(error))
        return

    nombre = "Certificado Niño año.pdf"

    class InfoFalsa:
        """Un archivo dentro de un ZIP, tal como lo entrega Python.

        Se arma a mano y no con un ZIP de verdad por un detalle de la
        librería: al escribir un nombre con tildes, Python le pone la
        bandera de UTF-8 sola y no deja armar el caso del ZIP que NO la
        trae, que es justamente el que hay que probar. Lo que decide el
        programa depende de estos dos datos y de nada más.
        """

        def __init__(self, filename, flag_bits):
            self.filename = filename
            self.flag_bits = flag_bits

    crudo_utf8 = nombre.encode("utf-8")
    crudo_dos = nombre.encode("cp437")

    casos = [
        # (cómo llegó el ZIP, lo que Python leyó, la bandera)
        ("con la bandera de UTF-8 puesta",
         InfoFalsa(nombre, 0x800)),

        # El Explorador de Windows: nombres en la codificación vieja de
        # DOS y sin bandera. Python ya los lee bien.
        ("hecho con el Explorador de Windows (cp437, sin bandera)",
         InfoFalsa(crudo_dos.decode("cp437"), 0)),

        # El caso torcido: los nombres van en UTF-8 pero se olvidó la
        # bandera. Python los lee como cp437 y salen "Ni├▒o.pdf".
        ("en UTF-8 pero sin la bandera puesta",
         InfoFalsa(crudo_utf8.decode("cp437"), 0)),
    ]

    for descripcion, info in casos:
        leido = documentos.nombre_dentro_del_zip(info)
        comprobar(
            "un ZIP %s conserva la ñ y las tildes" % descripcion,
            leido == nombre,
            "se leyó: %r" % leido,
        )


# ==========================================================
# F. Las carpetas y la base de datos
# ==========================================================

def revisar_almacenamiento():
    titulo("F. Las carpetas y la base de datos")

    # ¿Se puede escribir donde va a escribir el programa? En Windows, si el
    # proyecto quedó en "Archivos de programa" o en una carpeta sincronizada,
    # a veces no se puede.
    carpeta_datos = RAIZ / "datos"
    try:
        carpeta_datos.mkdir(exist_ok=True)
        prueba = carpeta_datos / "prueba-de-escritura.txt"
        prueba.write_text("prueba", encoding="utf-8")
        prueba.unlink()
        puede = True
        motivo = ""
    except OSError as error:
        puede = False
        motivo = str(error)
    comprobar("se puede escribir en la carpeta datos/", puede, motivo)

    # SQLite en un archivo temporal, no en la base del contador.
    with tempfile.TemporaryDirectory() as temporal:
        archivo = Path(temporal) / "prueba.db"
        try:
            conexion = sqlite3.connect(str(archivo))
            conexion.execute("CREATE TABLE prueba (nombre TEXT)")
            conexion.execute("INSERT INTO prueba VALUES (?)",
                             ("Declaración de María Ñáñez",))
            fila = conexion.execute("SELECT nombre FROM prueba").fetchone()
            conexion.close()
            bien = fila[0] == "Declaración de María Ñáñez"
            motivo = ""
        except sqlite3.Error as error:
            bien, motivo = False, str(error)
    comprobar("SQLite guarda y devuelve el texto con tildes intacto",
              bien, motivo)


# ==========================================================
# G. Cosas del código que solo se notan en Windows
#
# Esto no ejecuta el programa: lee el código y busca las dos costumbres
# que funcionan en el Mac y fallan allá.
# ==========================================================

def revisar_codigo():
    titulo("G. Cosas del código que solo se notan en Windows")

    archivos = sorted((RAIZ / "app").glob("*.py"))

    # 1. open() sin encoding. En Windows toma cp1252 y una tilde rompe la
    #    lectura del archivo entero.
    sin_encoding = []
    for archivo in archivos:
        for numero, linea in enumerate(
                archivo.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bopen\s*\(", linea) and "encoding" not in linea:
                # Los archivos binarios no llevan encoding, y así se escriben.
                if '"rb"' in linea or "'rb'" in linea or '"wb"' in linea \
                        or "'wb'" in linea:
                    continue
                sin_encoding.append("%s:%d" % (archivo.name, numero))
    comprobar(
        "ningún open() de texto se dejó sin encoding",
        not sin_encoding,
        " | ".join(sin_encoding) if sin_encoding else
        "se revisaron %d archivos" % len(archivos),
    )

    # 2. Rutas absolutas escritas a mano. Una ruta del Mac no existe allá.
    absolutas = []
    for archivo in archivos:
        for numero, linea in enumerate(
                archivo.read_text(encoding="utf-8").splitlines(), 1):
            if linea.lstrip().startswith("#"):
                continue
            if '"/Users/' in linea or "'/Users/" in linea:
                absolutas.append("%s:%d" % (archivo.name, numero))
    comprobar(
        "no hay rutas del Mac escritas a mano en el código",
        not absolutas,
        " | ".join(absolutas) if absolutas else "",
    )


# ==========================================================
# H. Los programas de afuera y el puerto
# ==========================================================

def revisar_alrededores():
    titulo("H. Los programas de afuera y el puerto")

    try:
        from app import recalcular
        ruta = recalcular.buscar_libreoffice()
    except ImportError:
        ruta = None

    if ruta:
        comprobar("LibreOffice está instalado", True, str(ruta))
    else:
        # No es una falla: el programa avisa y sigue. Pero sin él, los
        # totales del Formulario 210 no se calculan solos.
        aviso("LibreOffice no está instalado. El programa funciona igual,"
              " pero los totales del Formulario 210 no se recalculan solos."
              " Se baja gratis de libreoffice.org.")

    libre = puerto_libre(8000)
    if libre:
        comprobar("el puerto 8000 está libre", True)
    else:
        aviso("el puerto 8000 está ocupado. Puede ser el mismo Tax-i ya"
              " prendido en otra ventana; si no, ciérrelo antes de arrancar.")


def puerto_libre(numero):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", numero)) != 0


def buscar_puerto_libre():
    """Le pide al sistema un puerto que nadie esté usando."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ==========================================================
# I. La prueba de verdad: que el programa prenda y conteste
#
# Todo lo de arriba revisa las piezas. Esto arranca el programa completo
# en un puerto aparte, le pregunta algo, y lo apaga. Si esto pasa, el
# programa sirve en este computador.
# ==========================================================

def revisar_arranque():
    titulo("I. El programa prende y contesta")

    puerto = buscar_puerto_libre()
    servidor = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(puerto)],
        cwd=str(RAIZ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    direccion = "http://127.0.0.1:%d" % puerto
    prendio = False
    try:
        # Hasta 30 segundos: la primera vez, Windows Defender revisa cada
        # librería que se carga y el arranque se vuelve lento.
        for _ in range(60):
            if servidor.poll() is not None:
                break
            try:
                with urllib.request.urlopen(direccion + "/api/configuracion",
                                            timeout=2) as r:
                    prendio = r.status == 200
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)

        detalle = ""
        if not prendio and servidor.poll() is not None:
            salida = servidor.stdout.read().decode("utf-8", errors="replace")
            detalle = salida.strip().splitlines()[-1] if salida.strip() else ""
        comprobar("el servidor arranca y contesta", prendio, detalle)

        if prendio:
            paginas = [("la lista de clientes", "/"),
                       ("la pantalla del cliente", "/cliente"),
                       ("la pantalla de la cuenta", "/cuenta"),
                       ("la hoja de estilos", "/static/estilos.css")]
            for descripcion, camino in paginas:
                try:
                    with urllib.request.urlopen(direccion + camino,
                                                timeout=10) as r:
                        bien = r.status == 200
                        motivo = ""
                except (urllib.error.URLError, OSError) as error:
                    bien, motivo = False, str(error)
                comprobar("abre %s" % descripcion, bien, motivo)
    finally:
        servidor.terminate()
        try:
            servidor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            servidor.kill()


# ==========================================================

def main():
    print("=" * 62)
    print(" Revisión de Tax-i en este computador")
    print(" Carpeta: %s" % RAIZ)
    print("=" * 62)

    revisar_computador()
    revisar_proyecto()
    revisar_librerias()
    revisar_nombres()
    revisar_zip()
    revisar_almacenamiento()
    revisar_codigo()
    revisar_alrededores()
    revisar_arranque()

    total = len(resultados)
    buenas = sum(resultados)

    print("\n" + "=" * 62)
    print(" %d de %d revisiones pasaron." % (buenas, total))
    if buenas == total:
        print(" Todo bien. El programa funciona en este computador.")
        print("=" * 62)
        return 0

    print(" HAY FALLAS. Arriba, cada línea que dice FALLA explica cuál es.")
    print(" Mándele esta pantalla completa a quien hizo el programa.")
    print("=" * 62)
    return 1


if __name__ == "__main__":
    sys.exit(main())
