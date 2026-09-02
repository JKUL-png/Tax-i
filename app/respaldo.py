"""
El respaldo completo: llevarse todo, y traerlo de vuelta.

Para qué
--------
Si en octubre se le daña el disco al contador, sin esto pierde el trabajo
de toda la temporada: los clientes, los documentos que le mandaron, los
checklists y los valores capturados del Formulario 210. Nada de eso está
en ninguna nube — por diseño, porque son documentos tributarios de
terceros. Justamente por eso el respaldo tiene que ser fácil.

Qué se lleva
------------
Un solo archivo ZIP con:

    base.db                    la base entera
    documentos/<cliente>/...   los archivos, en una carpeta por cliente,
                               con el nombre del cliente en la carpeta
    formularios/<cliente>/...  los Excel generados
    RESPALDO.txt               qué trae y cómo devolverlo

Los documentos van en carpetas con el nombre del cliente y no con su
número, porque un respaldo también sirve para abrirlo y buscar un archivo
a mano sin el programa. Adentro de la base los documentos siguen
identificados por número, así que al restaurar no se depende del nombre.

Lo que NO va
------------
El `.env` no va. Ahí vive la llave del servicio de IA, y un respaldo se
copia a un disco externo, se manda por correo, se deja en un escritorio.
La llave se vuelve a escribir en la pantalla de Cuenta, que toma un
minuto; una llave filtrada no se puede recoger.

La papelera tampoco: es lo que el contador ya decidió borrar, y meterla
multiplicaría el tamaño del respaldo por lo que menos importa.

Devolverlo en otro computador
-----------------------------
`restaurar` toma ese mismo ZIP y deja el programa como estaba. Antes de
tocar nada guarda lo que hubiera, en `datos/antes-de-restaurar-<fecha>/`:
restaurar encima de una base con trabajo adentro sería el peor error
posible, y así siempre hay marcha atrás.
"""

import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from app import db, documentos

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = RAIZ / "datos"

# Cómo se llaman las cosas dentro del ZIP.
NOMBRE_BASE = "base.db"
CARPETA_DOCUMENTOS = "documentos"
CARPETA_FORMULARIOS = "formularios"
NOMBRE_LEEME = "RESPALDO.txt"

# Techo de lo que se acepta restaurar. Un respaldo de verdad no llega
# a esto ni de lejos; el límite es para que un ZIP preparado a mala fe
# no llene el disco al descomprimirlo.
LIMITE_DESCOMPRIMIDO = 4 * 1024 * 1024 * 1024   # 4 GB


class RespaldoInvalido(Exception):
    """El archivo que se dio no es un respaldo de este programa."""


def _nombre_de_carpeta(cliente):
    """La carpeta de un cliente dentro del ZIP: '3 - Juan Ejemplo'.

    Lleva el número adelante porque dos clientes se pueden llamar igual,
    y el nombre para que el ZIP se pueda abrir a mano y se entienda.
    Sanitizado, porque un nombre con ':' o '?' rompe el guardado en
    Windows al descomprimir.
    """
    limpio = documentos.sanitizar_nombre(cliente["nombre"] or "cliente")
    return "%d - %s" % (cliente["id"], limpio)


def _texto_del_leeme(clientes, cuantos_documentos):
    """El archivo que explica, adentro del ZIP, qué es esto y cómo devolverlo."""
    return (
        "RESPALDO DE TAX-I\n"
        "=================\n\n"
        "Hecho el %s\n\n"
        "Qué trae\n"
        "--------\n"
        "  %d cliente(s)\n"
        "  %d documento(s)\n"
        "  %s   la base de datos completa: clientes, checklists, valores\n"
        "        del Formulario 210, lo leído de cada documento y la bitácora\n"
        "  %s/   los documentos, en una carpeta por cliente\n"
        "  %s/  los archivos de Excel que se generaron\n\n"
        "Qué NO trae\n"
        "-----------\n"
        "  El archivo .env, donde vive la llave del servicio de IA. Se deja\n"
        "  afuera a propósito: un respaldo se copia y se mueve, y una llave\n"
        "  filtrada no se puede recoger. Se vuelve a escribir en la pantalla\n"
        "  de Cuenta.\n\n"
        "  La papelera, que es lo que ya se había decidido borrar.\n\n"
        "Cómo devolverlo en otro computador\n"
        "----------------------------------\n"
        "  1. Instale Tax-i en el computador nuevo y ábralo.\n"
        "  2. Entre a Historial y exportar.\n"
        "  3. En «Restaurar un respaldo», escoja este mismo archivo ZIP.\n\n"
        "  Lo que hubiera en el computador nuevo NO se pierde: antes de\n"
        "  restaurar se guarda una copia en la carpeta datos/, con la fecha\n"
        "  en el nombre.\n\n"
        "ESTE ARCHIVO CONTIENE INFORMACIÓN TRIBUTARIA DE TERCEROS.\n"
        "Guárdelo como guardaría los documentos en papel.\n"
        % (
            datetime.now().strftime("%d/%m/%Y a las %H:%M"),
            len(clientes), cuantos_documentos,
            NOMBRE_BASE, CARPETA_DOCUMENTOS, CARPETA_FORMULARIOS,
        )
    )


def nombre_del_archivo():
    """Cómo se llama el respaldo que se descarga: con la fecha adentro."""
    return "Tax-i respaldo %s.zip" % datetime.now().strftime("%Y-%m-%d %H%M")


def armar(destino):
    """Escribe el respaldo completo en `destino`. Devuelve qué metió.

    Se escribe a un archivo y no a memoria: con doscientos documentos
    escaneados esto pesa cientos de megas, y armarlo entero en memoria
    dejaría el programa sin aire justo cuando más se necesita que
    funcione.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    clientes = db.listar_clientes()
    informe = {"clientes": len(clientes), "documentos": 0, "formularios": 0}

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as paquete:
        # 1. La base. Es lo único imprescindible: sin ella los archivos
        #    sueltos no dicen de quién son.
        if db.ARCHIVO_BD.exists():
            paquete.write(db.ARCHIVO_BD, NOMBRE_BASE)

        # 2. Los documentos, por cliente.
        for cliente in clientes:
            carpeta = documentos.carpeta_del_cliente(cliente["id"])
            if not carpeta.exists():
                continue
            nombre_carpeta = _nombre_de_carpeta(cliente)
            for archivo in sorted(carpeta.iterdir()):
                if not archivo.is_file() or documentos.es_basura(archivo.name):
                    continue
                paquete.write(
                    archivo,
                    "%s/%s/%s" % (CARPETA_DOCUMENTOS, nombre_carpeta,
                                  archivo.name),
                )
                informe["documentos"] += 1

        # 3. Los Excel generados. No son imprescindibles —se vuelven a
        #    armar desde la base— pero pesan poco y ahorran el paso.
        for cliente in clientes:
            carpeta = CARPETA_DATOS / "formularios" / ("cliente-%d" % cliente["id"])
            if not carpeta.exists():
                continue
            nombre_carpeta = _nombre_de_carpeta(cliente)
            for archivo in sorted(carpeta.iterdir()):
                if not archivo.is_file():
                    continue
                paquete.write(
                    archivo,
                    "%s/%s/%s" % (CARPETA_FORMULARIOS, nombre_carpeta,
                                  archivo.name),
                )
                informe["formularios"] += 1

        paquete.writestr(
            NOMBRE_LEEME,
            _texto_del_leeme(clientes, informe["documentos"]),
        )

    informe["tamano"] = destino.stat().st_size
    return informe


def revisar(ruta_zip):
    """Mira un ZIP y dice si es un respaldo de este programa y qué trae.

    Se hace ANTES de tocar nada, para poder decirle al contador qué va a
    pasar y que confirme. Levanta RespaldoInvalido si no sirve.
    """
    ruta_zip = Path(ruta_zip)
    try:
        with zipfile.ZipFile(ruta_zip) as paquete:
            nombres = paquete.namelist()
            descomprimido = sum(i.file_size for i in paquete.infolist())
    except (zipfile.BadZipFile, OSError):
        raise RespaldoInvalido(
            "Ese archivo no es un ZIP que se pueda abrir. Escoja el"
            " archivo de respaldo que generó Tax-i."
        )

    if NOMBRE_BASE not in nombres:
        raise RespaldoInvalido(
            "Ese ZIP no es un respaldo de Tax-i: no trae la base de datos"
            " adentro. Escoja el archivo que generó el botón «Exportar"
            " todo»."
        )

    if descomprimido > LIMITE_DESCOMPRIMIDO:
        raise RespaldoInvalido(
            "Ese respaldo ocupa demasiado al abrirlo y no se va a"
            " restaurar, por seguridad."
        )

    # Nadie escribe fuera de donde debe. Un ZIP puede traer rutas como
    # "../../algo" y eso escribiría en cualquier parte del disco.
    for nombre in nombres:
        if nombre.startswith("/") or ".." in Path(nombre).parts:
            raise RespaldoInvalido(
                "Ese respaldo trae rutas que se salen de su carpeta y no"
                " se va a restaurar."
            )

    return {
        "documentos": sum(
            1 for n in nombres
            if n.startswith(CARPETA_DOCUMENTOS + "/") and not n.endswith("/")
        ),
        "formularios": sum(
            1 for n in nombres
            if n.startswith(CARPETA_FORMULARIOS + "/") and not n.endswith("/")
        ),
        "tamano": ruta_zip.stat().st_size,
        "tamano_abierto": descomprimido,
    }


def _guardar_lo_que_habia():
    """Aparta lo que hay ahora, antes de restaurar encima.

    Devuelve la carpeta donde quedó, o None si no había nada que guardar.
    Esto no es opcional: restaurar sobre una base con trabajo adentro y
    sin marcha atrás sería el peor error que puede cometer este programa.
    """
    hay_base = db.ARCHIVO_BD.exists()
    hay_archivos = documentos.CARPETA_ARCHIVOS.exists()
    if not hay_base and not hay_archivos:
        return None

    marca = datetime.now().strftime("%Y-%m-%d %H%M%S")
    refugio = CARPETA_DATOS / ("antes-de-restaurar-" + marca)
    refugio.mkdir(parents=True, exist_ok=True)

    if hay_base:
        shutil.copy2(db.ARCHIVO_BD, refugio / NOMBRE_BASE)
    if hay_archivos:
        shutil.copytree(
            documentos.CARPETA_ARCHIVOS, refugio / CARPETA_DOCUMENTOS,
            dirs_exist_ok=True,
        )
    return refugio


def restaurar(ruta_zip):
    """Devuelve un respaldo a este computador. Devuelve un informe.

    Antes de tocar nada aparta lo que hubiera. Si algo falla a mitad, esa
    copia sigue ahí y no se perdió nada.
    """
    informacion = revisar(ruta_zip)
    refugio = _guardar_lo_que_habia()

    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    documentos.CARPETA_ARCHIVOS.mkdir(parents=True, exist_ok=True)

    puestos = 0
    with zipfile.ZipFile(ruta_zip) as paquete:
        # 1. La base, primero: es la que dice de quién es cada archivo.
        #    Se lee con paquete.read() y se escribe con write_bytes(),
        #    que es como el resto del programa saca cosas de un ZIP.
        db.ARCHIVO_BD.write_bytes(paquete.read(NOMBRE_BASE))

        # 2. Los documentos. En el ZIP están en carpetas con el nombre
        #    del cliente ("3 - Juan Ejemplo"), que es como se leen a mano.
        #    En el disco van en la carpeta numerada, que es la que usa el
        #    programa. El número está al principio del nombre.
        for nombre in paquete.namelist():
            if not nombre.startswith(CARPETA_DOCUMENTOS + "/"):
                continue
            if nombre.endswith("/"):
                continue

            partes = Path(nombre).parts
            if len(partes) < 3:
                continue
            numero = partes[1].split(" - ")[0].strip()
            if not numero.isdigit():
                continue

            carpeta = documentos.carpeta_del_cliente(int(numero), crear=True)
            (carpeta / partes[-1]).write_bytes(paquete.read(nombre))
            puestos += 1

        # 3. Los Excel generados.
        for nombre in paquete.namelist():
            if not nombre.startswith(CARPETA_FORMULARIOS + "/"):
                continue
            if nombre.endswith("/"):
                continue
            partes = Path(nombre).parts
            if len(partes) < 3:
                continue
            numero = partes[1].split(" - ")[0].strip()
            if not numero.isdigit():
                continue
            carpeta = CARPETA_DATOS / "formularios" / ("cliente-%s" % numero)
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / partes[-1]).write_bytes(paquete.read(nombre))

    # La base restaurada puede venir de una versión anterior del programa:
    # se le agregan las columnas que le falten.
    db.crear_tablas()

    return {
        "clientes": len(db.listar_clientes()),
        "documentos": puestos,
        "formularios": informacion["formularios"],
        "copia_de_seguridad": _para_mostrar(refugio),
    }


def _para_mostrar(carpeta):
    """La ruta de la copia, corta, para decírsela al contador.

    Se prefiere la ruta relativa al programa —'datos/antes-de-…'— que es
    más corta y se entiende. Si por lo que sea la carpeta no cuelga de
    ahí, se muestra completa en vez de reventar: esto se llama DESPUÉS de
    haber restaurado, y fallar aquí le diría al contador que algo salió
    mal cuando en realidad ya salió bien.
    """
    if carpeta is None:
        return ""
    try:
        return str(carpeta.relative_to(RAIZ))
    except ValueError:
        return str(carpeta)
