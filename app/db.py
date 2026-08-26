"""
Base de datos del asistente.

Usamos SQLite: la base entera es un solo archivo (datos/base.db).
No hay que instalar ni configurar nada, y el archivo se puede copiar
o respaldar como cualquier otro documento.

Ese archivo contiene datos confidenciales de terceros, por eso la
carpeta datos/ está excluida de git.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

# Rutas relativas a la raíz del proyecto (este archivo vive en app/).
# Con pathlib funcionan igual en Mac y en Windows.
RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = RAIZ / "datos"
ARCHIVO_BD = CARPETA_DATOS / "base.db"


def conectar():
    """Abre una conexión a la base. Crea la carpeta datos/ si no existe."""
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ARCHIVO_BD)
    # row_factory hace que los resultados se puedan leer por nombre de columna
    # (fila["nombre"]) en vez de por posición (fila[1]), que es ilegible.
    conexion.row_factory = sqlite3.Row
    return conexion


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
