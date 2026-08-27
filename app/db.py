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
                -- Huella del contenido (SHA-256). Sirve para darse cuenta
                -- de que un cliente mandó dos veces el mismo archivo,
                -- aunque le haya cambiado el nombre.
                hash            TEXT,
                -- A qué renglón del checklist pertenece este documento.
                -- Vacío mientras nadie lo haya asignado. No se pone llave
                -- foránea a propósito: la tabla checklist se crea después,
                -- y en las bases que ya existen ALTER TABLE no la puede
                -- agregar. Se maneja en el código, igual en los dos casos.
                renglon_id      INTEGER,
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

        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS checklist (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id     INTEGER NOT NULL,
                -- Lo que se le pidió al cliente, en palabras del contador.
                titulo         TEXT NOT NULL,
                -- Solo dos valores: 'faltante' o 'recibido'.
                estado         TEXT NOT NULL DEFAULT 'faltante',
                -- Para que los renglones se muestren siempre en el mismo
                -- orden, sin importar cuándo se agregaron.
                orden          INTEGER NOT NULL,
                actualizado_en TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_checklist_cliente"
            " ON checklist (cliente_id)"
        )

        # --- Cambios sobre bases que ya existían ---
        # Si la base se creó con una versión anterior del programa, le falta
        # la columna "notas". Se agrega aquí en vez de pedirle al contador
        # que borre su base y empiece de cero.
        columnas = {
            fila["name"]
            for fila in conexion.execute("PRAGMA table_info(clientes)")
        }
        if "notas" not in columnas:
            conexion.execute("ALTER TABLE clientes ADD COLUMN notas TEXT")

        columnas_doc = {
            fila["name"]
            for fila in conexion.execute("PRAGMA table_info(documentos)")
        }
        if "hash" not in columnas_doc:
            conexion.execute("ALTER TABLE documentos ADD COLUMN hash TEXT")
        if "renglon_id" not in columnas_doc:
            conexion.execute("ALTER TABLE documentos ADD COLUMN renglon_id INTEGER")


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
            SELECT id, nombre, dos_digitos, fecha_vencimiento, notas, creado_en
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
            "SELECT id, nombre, dos_digitos, fecha_vencimiento, notas, creado_en"
            " FROM clientes WHERE id = ?",
            (id_cliente,),
        ).fetchone()
    return dict(fila) if fila else None


def crear_cliente(nombre, dos_digitos, fecha_vencimiento=None, notas=None):
    """Guarda un cliente nuevo y devuelve el registro completo."""
    creado_en = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        cursor = conexion.execute(
            "INSERT INTO clientes"
            " (nombre, dos_digitos, fecha_vencimiento, notas, creado_en)"
            " VALUES (?, ?, ?, ?, ?)",
            (nombre, dos_digitos, fecha_vencimiento, notas, creado_en),
        )
        id_nuevo = cursor.lastrowid
    return obtener_cliente(id_nuevo)


def actualizar_cliente(id_cliente, nombre=None, dos_digitos=None,
                       fecha_vencimiento=..., notas=...):
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

    if notas is not ...:
        campos.append("notas = ?")
        valores.append(notas)

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
                   extension, tamano, hash, renglon_id, venia_en_zip, subido_en
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
                   extension, tamano, hash, renglon_id, venia_en_zip, subido_en
            FROM documentos WHERE id = ?
            """,
            (id_documento,),
        ).fetchone()
    return dict(fila) if fila else None


def crear_documento(cliente_id, nombre_original, nombre_guardado,
                    extension, tamano, huella=None, venia_en_zip=None):
    """Registra en la base un documento que ya se escribió en el disco."""
    subido_en = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        cursor = conexion.execute(
            """
            INSERT INTO documentos
                (cliente_id, nombre_original, nombre_guardado,
                 extension, tamano, hash, venia_en_zip, subido_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (cliente_id, nombre_original, nombre_guardado,
             extension, tamano, huella, venia_en_zip, subido_en),
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


# ----------------------------------------------------------
# Operaciones sobre el checklist
# ----------------------------------------------------------


def listar_checklist(id_cliente):
    """Devuelve los renglones del checklist de un cliente, en su orden."""
    with conectar() as conexion:
        filas = conexion.execute(
            """
            SELECT id, cliente_id, titulo, estado, orden, actualizado_en
            FROM checklist
            WHERE cliente_id = ?
            ORDER BY orden, id
            """,
            (id_cliente,),
        ).fetchall()
    return [dict(fila) for fila in filas]


def contar_checklist():
    """Cuántos renglones tiene cada cliente y cuántos ya llegaron.

    Devuelve {id_cliente: {"total": n, "recibidos": n}}. Sirve para
    mostrar "7 de 11" en la lista de clientes sin preguntar uno por uno.
    """
    with conectar() as conexion:
        filas = conexion.execute(
            """
            SELECT cliente_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN estado = 'recibido' THEN 1 ELSE 0 END)
                       AS recibidos
            FROM checklist
            GROUP BY cliente_id
            """
        ).fetchall()
    return {
        fila["cliente_id"]: {
            "total": fila["total"],
            "recibidos": fila["recibidos"] or 0,
        }
        for fila in filas
    }


def obtener_renglon(id_renglon):
    """Devuelve un renglón del checklist, o None si no existe."""
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT id, cliente_id, titulo, estado, orden, actualizado_en"
            " FROM checklist WHERE id = ?",
            (id_renglon,),
        ).fetchone()
    return dict(fila) if fila else None


def crear_renglon(cliente_id, titulo, estado="faltante"):
    """Agrega un renglón al final del checklist de un cliente."""
    ahora = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        # El siguiente número de orden: uno más que el último que haya.
        fila = conexion.execute(
            "SELECT MAX(orden) AS ultimo FROM checklist WHERE cliente_id = ?",
            (cliente_id,),
        ).fetchone()
        orden = (fila["ultimo"] or 0) + 1

        cursor = conexion.execute(
            "INSERT INTO checklist (cliente_id, titulo, estado, orden, actualizado_en)"
            " VALUES (?, ?, ?, ?, ?)",
            (cliente_id, titulo, estado, orden, ahora),
        )
        id_nuevo = cursor.lastrowid
    return obtener_renglon(id_nuevo)


def crear_renglones(cliente_id, titulos):
    """Agrega varios renglones de una vez. Se usa para la lista base."""
    ahora = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT MAX(orden) AS ultimo FROM checklist WHERE cliente_id = ?",
            (cliente_id,),
        ).fetchone()
        orden = (fila["ultimo"] or 0) + 1

        for titulo in titulos:
            conexion.execute(
                "INSERT INTO checklist"
                " (cliente_id, titulo, estado, orden, actualizado_en)"
                " VALUES (?, ?, 'faltante', ?, ?)",
                (cliente_id, titulo, orden, ahora),
            )
            orden += 1
    return listar_checklist(cliente_id)


def actualizar_renglon(id_renglon, titulo=None, estado=None):
    """Cambia el nombre o el estado de un renglón."""
    campos = []
    valores = []

    if titulo is not None:
        campos.append("titulo = ?")
        valores.append(titulo)

    if estado is not None:
        campos.append("estado = ?")
        valores.append(estado)

    if campos:
        campos.append("actualizado_en = ?")
        valores.append(datetime.now().isoformat(timespec="seconds"))
        valores.append(id_renglon)
        with conectar() as conexion:
            conexion.execute(
                f"UPDATE checklist SET {', '.join(campos)} WHERE id = ?",
                valores,
            )

    return obtener_renglon(id_renglon)


def eliminar_renglon(id_renglon):
    """Quita un renglón del checklist. Devuelve True si existía."""
    with conectar() as conexion:
        cursor = conexion.execute(
            "DELETE FROM checklist WHERE id = ?", (id_renglon,)
        )
    return cursor.rowcount > 0


def buscar_documento_por_huella(cliente_id, huella):
    """Busca si este cliente ya tiene un archivo con el mismo contenido.

    Compara la huella (SHA-256) y no el nombre, así que detecta el
    duplicado aunque el archivo haya llegado con otro nombre.
    """
    if not huella:
        return None
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT id, nombre_original FROM documentos"
            " WHERE cliente_id = ? AND hash = ? LIMIT 1",
            (cliente_id, huella),
        ).fetchone()
    return dict(fila) if fila else None


def asignar_documento(id_documento, renglon_id):
    """Asigna un documento a un renglón del checklist.

    Con renglon_id = None se le quita la asignación.
    """
    with conectar() as conexion:
        conexion.execute(
            "UPDATE documentos SET renglon_id = ? WHERE id = ?",
            (renglon_id, id_documento),
        )
    return obtener_documento(id_documento)


def desasignar_renglon(renglon_id):
    """Deja sin asignar los documentos que apuntaban a un renglón.

    Se llama antes de borrar un renglón del checklist: los documentos
    NO se borran, solo quedan sueltos para reasignarlos.
    """
    with conectar() as conexion:
        conexion.execute(
            "UPDATE documentos SET renglon_id = NULL WHERE renglon_id = ?",
            (renglon_id,),
        )


def contar_documentos_por_renglon(cliente_id):
    """Cuántos documentos tiene asignado cada renglón: {renglon_id: cantidad}."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT renglon_id, COUNT(*) AS cantidad FROM documentos"
            " WHERE cliente_id = ? AND renglon_id IS NOT NULL"
            " GROUP BY renglon_id",
            (cliente_id,),
        ).fetchall()
    return {fila["renglon_id"]: fila["cantidad"] for fila in filas}
