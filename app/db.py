"""
Base de datos del asistente.

Usamos SQLite: la base entera es un solo archivo (datos/base.db).
No hay que instalar ni configurar nada, y el archivo se puede copiar
o respaldar como cualquier otro documento.

Ese archivo contiene datos confidenciales de terceros, por eso la
carpeta datos/ está excluida de git.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# Rutas relativas a la raíz del proyecto (este archivo vive en app/).
# Con pathlib funcionan igual en Mac y en Windows.
RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = RAIZ / "datos"
ARCHIVO_BD = CARPETA_DATOS / "base.db"


@contextmanager
def conectar():
    """Abre una conexión a la base y la cierra sola al terminar.

    Se usa siempre así:

        with conectar() as conexion:
            conexion.execute(...)

    Al salir del bloque guarda los cambios y cierra. Si algo falla adentro,
    deshace los cambios en vez de dejar la base a medias.
    """
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ARCHIVO_BD)
    # row_factory hace que los resultados se puedan leer por nombre de columna
    # (fila["nombre"]) en vez de por posición (fila[1]), que es ilegible.
    conexion.row_factory = sqlite3.Row
    # SQLite ignora las llaves foráneas si no se le pide expresamente que las
    # respete. Sin esta línea, borrar un cliente dejaría sus documentos
    # sueltos en la base apuntando a un cliente que ya no existe.
    conexion.execute("PRAGMA foreign_keys = ON")
    try:
        yield conexion
        conexion.commit()
    finally:
        conexion.close()


def crear_tablas():
    """Crea las tablas si todavía no existen. Se llama al arrancar el servidor."""
    with conectar() as conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS clientes (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre            TEXT NOT NULL,
                -- Se guardan como texto, no como número, para no perder
                -- el cero de adelante: "05" debe seguir siendo "05".
                dos_digitos       TEXT NOT NULL,
                -- Formato AAAA-MM-DD. Por ahora la escribe el contador a mano.
                fecha_vencimiento TEXT,
                creado_en         TEXT NOT NULL
            )
            """
        )
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS documentos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id      INTEGER NOT NULL,
                -- El nombre tal como lo mandó el cliente. Es el que se
                -- muestra en pantalla.
                nombre_original TEXT NOT NULL,
                -- El nombre con el que quedó en el disco: limpio de
                -- caracteres que Windows no acepta.
                nombre_guardado TEXT NOT NULL,
                extension       TEXT NOT NULL,
                tamano          INTEGER NOT NULL,
                -- Si salió de un ZIP, aquí queda el nombre del ZIP.
                venia_en_zip    TEXT,
                subido_en       TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        # Un índice: hace rápido buscar los documentos de un cliente.
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_documentos_cliente"
            " ON documentos (cliente_id)"
        )


# ----------------------------------------------------------
# Operaciones sobre clientes
# ----------------------------------------------------------


def listar_clientes():
    """Devuelve todos los clientes, ordenados por fecha de vencimiento.

    Los que no tienen fecha van al final: lo urgente primero.
    """
    with conectar() as conexion:
        filas = conexion.execute(
            """
            SELECT id, nombre, dos_digitos, fecha_vencimiento, creado_en
            FROM clientes
            ORDER BY
                CASE WHEN fecha_vencimiento IS NULL OR fecha_vencimiento = ''
                     THEN 1 ELSE 0 END,
                fecha_vencimiento,
                nombre COLLATE NOCASE
            """
        ).fetchall()
    return [dict(fila) for fila in filas]


def obtener_cliente(id_cliente):
    """Devuelve un cliente por su id, o None si no existe."""
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT id, nombre, dos_digitos, fecha_vencimiento, creado_en"
            " FROM clientes WHERE id = ?",
            (id_cliente,),
        ).fetchone()
    return dict(fila) if fila else None


def crear_cliente(nombre, dos_digitos, fecha_vencimiento=None):
    """Guarda un cliente nuevo y devuelve el registro completo."""
    creado_en = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        cursor = conexion.execute(
            "INSERT INTO clientes (nombre, dos_digitos, fecha_vencimiento, creado_en)"
            " VALUES (?, ?, ?, ?)",
            (nombre, dos_digitos, fecha_vencimiento, creado_en),
        )
        id_nuevo = cursor.lastrowid
    return obtener_cliente(id_nuevo)


def actualizar_cliente(id_cliente, nombre=None, dos_digitos=None, fecha_vencimiento=...):
    """Modifica los campos que se pasen. Devuelve el cliente actualizado.

    Ojo con fecha_vencimiento: su valor por defecto es `...` (y no None)
    para poder distinguir "no me mandaron este campo" de "me mandaron
    este campo vacío, borra la fecha".
    """
    campos = []
    valores = []

    if nombre is not None:
        campos.append("nombre = ?")
        valores.append(nombre)

    if dos_digitos is not None:
        campos.append("dos_digitos = ?")
        valores.append(dos_digitos)

    if fecha_vencimiento is not ...:
        campos.append("fecha_vencimiento = ?")
        valores.append(fecha_vencimiento)

    if campos:
        valores.append(id_cliente)
        with conectar() as conexion:
            conexion.execute(
                f"UPDATE clientes SET {', '.join(campos)} WHERE id = ?",
                valores,
            )

    return obtener_cliente(id_cliente)


def eliminar_cliente(id_cliente):
    """Borra un cliente. Devuelve True si existía."""
    with conectar() as conexion:
        cursor = conexion.execute("DELETE FROM clientes WHERE id = ?", (id_cliente,))
    return cursor.rowcount > 0


# ----------------------------------------------------------
# Operaciones sobre documentos
# ----------------------------------------------------------


def listar_documentos(id_cliente):
    """Devuelve los documentos de un cliente, el más reciente primero."""
    with conectar() as conexion:
        filas = conexion.execute(
            """
            SELECT id, cliente_id, nombre_original, nombre_guardado,
                   extension, tamano, venia_en_zip, subido_en
            FROM documentos
            WHERE cliente_id = ?
            ORDER BY subido_en DESC, id DESC
            """,
            (id_cliente,),
        ).fetchall()
    return [dict(fila) for fila in filas]


def contar_documentos():
    """Devuelve cuántos documentos tiene cada cliente: {id_cliente: cantidad}.

    Sirve para mostrar el número en la lista de clientes sin tener que
    preguntar cliente por cliente.
    """
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT cliente_id, COUNT(*) AS cantidad"
            " FROM documentos GROUP BY cliente_id"
        ).fetchall()
    return {fila["cliente_id"]: fila["cantidad"] for fila in filas}


def obtener_documento(id_documento):
    """Devuelve un documento por su id, o None si no existe."""
    with conectar() as conexion:
        fila = conexion.execute(
            """
            SELECT id, cliente_id, nombre_original, nombre_guardado,
                   extension, tamano, venia_en_zip, subido_en
            FROM documentos WHERE id = ?
            """,
            (id_documento,),
        ).fetchone()
    return dict(fila) if fila else None


def crear_documento(cliente_id, nombre_original, nombre_guardado,
                    extension, tamano, venia_en_zip=None):
    """Registra en la base un documento que ya se escribió en el disco."""
    subido_en = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        cursor = conexion.execute(
            """
            INSERT INTO documentos
                (cliente_id, nombre_original, nombre_guardado,
                 extension, tamano, venia_en_zip, subido_en)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cliente_id, nombre_original, nombre_guardado,
             extension, tamano, venia_en_zip, subido_en),
        )
        id_nuevo = cursor.lastrowid
    return obtener_documento(id_nuevo)


def eliminar_documento(id_documento):
    """Borra el registro del documento. Devuelve True si existía.

    Ojo: esto borra la fila de la base, no el archivo del disco.
    De borrar el archivo se encarga main.py.
    """
    with conectar() as conexion:
        cursor = conexion.execute(
            "DELETE FROM documentos WHERE id = ?", (id_documento,)
        )
    return cursor.rowcount > 0
