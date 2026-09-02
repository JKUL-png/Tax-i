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
    # timeout: el servidor atiende varias peticiones a la vez (hilos) y
    # generar el Formulario 210 puede tener la base ocupada un rato. Sin
    # esta espera, una subida que caiga en ese momento revienta con
    # "database is locked" en vez de esperar su turno.
    conexion = sqlite3.connect(ARCHIVO_BD, timeout=30)
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
                -- 1 si es un cliente INVENTADO, del modo demostración.
                -- Sirve para mostrarlo marcado en pantalla y para poder
                -- quitarlos todos de un golpe sin tocar a los de verdad.
                es_demo           INTEGER NOT NULL DEFAULT 0,
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
                -- En qué va la lectura de este documento: 'pendiente',
                -- 'leyendo', 'listo' o 'fallo'. Es lo que hace que un
                -- documento se lea UNA sola vez y no se vuelva a pagar.
                estado_lectura  TEXT NOT NULL DEFAULT 'pendiente',
                -- Si falló, por qué. Escrito para que lo lea el contador.
                motivo_lectura  TEXT,
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

        # Los valores que el contador captura para el Formulario 210 de
        # cada cliente. Cada cliente tiene los suyos: la plantilla es la
        # misma para todos, pero lo que se escribe en ella es de cada uno.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS valores_210 (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id     INTEGER NOT NULL,
                -- La celda de la hoja de captura: 'G32', 'H104'...
                celda          TEXT NOT NULL,
                valor          REAL NOT NULL,
                -- De dónde salió el dato: el nombre del documento que lo
                -- respalda, o una nota como 'digitado por el contador'.
                documento      TEXT NOT NULL DEFAULT '',
                actualizado_en TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        # Una sola fila por celda y por cliente: si se vuelve a capturar la
        # misma celda, se reemplaza el valor y no se acumulan duplicados.
        conexion.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_valores_210_celda"
            " ON valores_210 (cliente_id, celda)"
        )

        # El historial de esos valores. No se borra nunca: es lo que le
        # permite al contador ver qué se cambió, cuándo y de dónde salió.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS bitacora_210 (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id     INTEGER NOT NULL,
                celda          TEXT NOT NULL,
                valor_anterior REAL,
                valor_nuevo    REAL,
                documento      TEXT NOT NULL DEFAULT '',
                fecha_hora     TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_bitacora_210_cliente"
            " ON bitacora_210 (cliente_id)"
        )

        # La conversación con RentAI, por cliente. Se guarda para que el
        # contador pueda volver a leerla y para que la conversación siga
        # donde quedó cuando cierre y abra el programa.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_mensajes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                -- Quién habló: 'contador' o 'rentai'.
                papel      TEXT NOT NULL,
                texto      TEXT NOT NULL,
                -- Las propuestas de ese mensaje, en JSON. Vacío si no hubo.
                propuestas TEXT NOT NULL DEFAULT '[]',
                creado_en  TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_cliente"
            " ON chat_mensajes (cliente_id)"
        )

        # La bitácora general: qué pasó, cuándo y con qué cliente.
        #
        # Ojo: la de arriba (bitacora_210) es SOLO de los valores del
        # Formulario 210. Esta es de todo lo demás: subir, borrar, marcar
        # un renglón, generar un archivo. Se separan porque la del 210
        # guarda cifras (valor anterior y nuevo) y esta no guarda ninguna.
        #
        # Esto NO es el log del programa. El log no lleva ni nombres de
        # clientes ni nombres de archivos; esta tabla sí, y por eso vive
        # dentro de datos/base.db, que es la carpeta protegida donde ya
        # están los documentos. Al borrar un cliente se borra con él.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS bitacora (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                -- Qué pasó, en clave: 'documentos_subidos',
                -- 'documentos_borrados'... La lista está en app/bitacora.py.
                accion     TEXT NOT NULL,
                -- El nombre del archivo o del renglón al que le pasó.
                detalle    TEXT NOT NULL DEFAULT '',
                -- Cuántas cosas: 5 documentos borrados de un golpe es UNA
                -- anotación con cantidad 5, no cinco anotaciones.
                cantidad   INTEGER NOT NULL DEFAULT 1,
                fecha_hora TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_bitacora_cliente"
            " ON bitacora (cliente_id, id)"
        )

        # Ajustes del programa que el contador puede cambiar desde la
        # pantalla. Por ahora solo uno: cuál plantilla está en uso.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS ajustes (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
            """
        )

        # Lo que se le sacó a cada documento, guardado dato por dato.
        #
        # Por qué existe esta tabla
        # -------------------------
        # El modelo de IA no tiene memoria. Cada vez que se le pregunta
        # algo hay que volver a contarle todo, y antes eso significaba
        # remandarle el texto de los documentos en CADA pregunta: se
        # pagaba el mismo documento diez veces y cada respuesta se
        # demoraba lo que se demora leerlos.
        #
        # La memoria del sistema es esta tabla. Se lee cada documento UNA
        # vez, lo que se le sacó queda aquí, y a partir de ahí las
        # preguntas se contestan con estas filas. Tres cosas se ganan: se
        # paga una vez por documento, las respuestas son inmediatas, y lo
        # ya extraído se sigue viendo con IA_PROVEEDOR=ninguno, porque
        # ya está en el computador y no hay que preguntarle a nadie.
        #
        # 'origen' dice quién lo sacó, y no es un detalle: es la regla
        # del proyecto.
        #   'codigo'  lo leyó el programa de un XML. Es exacto.
        #   'ia'      lo leyó un modelo. Es LECTURA AUTOMÁTICA y se
        #             muestra marcada como tal, para verificar contra el
        #             documento original.
        #
        # 'documento_id' es lo que permite abrir el original al lado del
        # dato. Ningún dato vive suelto: todos dicen de dónde salieron.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS datos_extraidos (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id     INTEGER NOT NULL,
                documento_id   INTEGER NOT NULL,
                -- Qué es: "Salarios", "Retención practicada", "NIT del
                -- emisor". Tal como lo dice el documento.
                concepto       TEXT NOT NULL,
                -- La cifra, cuando el dato es una cifra. Se guarda como
                -- texto, tal como está escrita en el documento: el
                -- programa no convierte ni redondea ni suma.
                valor          TEXT,
                -- Lo que no es cifra: un nombre, un NIT, un periodo.
                detalle        TEXT,
                -- 'codigo' o 'ia'. Ver arriba.
                origen         TEXT NOT NULL,
                extraido_en    TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (documento_id) REFERENCES documentos(id)
                    ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_extraidos_cliente"
            " ON datos_extraidos (cliente_id)"
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_extraidos_documento"
            " ON datos_extraidos (documento_id)"
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
        # La marca del modo demostración. Los clientes que ya existían son
        # de verdad, así que el valor por defecto (0) es el correcto.
        if "es_demo" not in columnas:
            conexion.execute(
                "ALTER TABLE clientes ADD COLUMN es_demo INTEGER"
                " NOT NULL DEFAULT 0"
            )

        columnas_valores = {
            fila["name"]
            for fila in conexion.execute("PRAGMA table_info(valores_210)")
        }
        # Con qué plantilla se anotó cada valor. Sirve para avisar si el
        # contador cambia de plantilla: las casillas de una no tienen por
        # qué significar lo mismo en la otra.
        if columnas_valores and "plantilla" not in columnas_valores:
            conexion.execute(
                "ALTER TABLE valores_210 ADD COLUMN plantilla TEXT"
            )

        columnas_doc = {
            fila["name"]
            for fila in conexion.execute("PRAGMA table_info(documentos)")
        }
        if "hash" not in columnas_doc:
            conexion.execute("ALTER TABLE documentos ADD COLUMN hash TEXT")
        if "renglon_id" not in columnas_doc:
            conexion.execute("ALTER TABLE documentos ADD COLUMN renglon_id INTEGER")
        # En qué va la lectura de cada documento. Es lo que hace que se
        # lea UNA sola vez: si ya está 'listo', no se vuelve a leer ni a
        # pagar. Los cuatro valores posibles son 'pendiente', 'leyendo',
        # 'listo' y 'fallo'.
        if "estado_lectura" not in columnas_doc:
            conexion.execute(
                "ALTER TABLE documentos ADD COLUMN estado_lectura TEXT"
                " NOT NULL DEFAULT 'pendiente'"
            )
        # Si falló, por qué. Se le muestra al contador tal cual.
        if "motivo_lectura" not in columnas_doc:
            conexion.execute(
                "ALTER TABLE documentos ADD COLUMN motivo_lectura TEXT"
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
            SELECT id, nombre, dos_digitos, fecha_vencimiento, notas,
                   es_demo, creado_en
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
            "SELECT id, nombre, dos_digitos, fecha_vencimiento, notas,"
            " es_demo, creado_en FROM clientes WHERE id = ?",
            (id_cliente,),
        ).fetchone()
    return dict(fila) if fila else None


def crear_cliente(nombre, dos_digitos, fecha_vencimiento=None, notas=None,
                  es_demo=False):
    """Guarda un cliente nuevo y devuelve el registro completo.

    `es_demo` marca los clientes INVENTADOS del modo demostración. Solo
    lo pone app/demostracion.py: por la pantalla no entra nunca, para que
    nadie cree sin querer un cliente de verdad marcado como de mentira.
    """
    creado_en = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        cursor = conexion.execute(
            "INSERT INTO clientes"
            " (nombre, dos_digitos, fecha_vencimiento, notas, es_demo,"
            "  creado_en)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (nombre, dos_digitos, fecha_vencimiento, notas,
             1 if es_demo else 0, creado_en),
        )
        id_nuevo = cursor.lastrowid
    return obtener_cliente(id_nuevo)


def clientes_de_demostracion():
    """Los ids de los clientes inventados. Vacío si no hay demostración."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT id FROM clientes WHERE es_demo = 1 ORDER BY id"
        ).fetchall()
    return [fila["id"] for fila in filas]


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
                   extension, tamano, hash, renglon_id, venia_en_zip,
                   estado_lectura, motivo_lectura, subido_en
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
                   extension, tamano, hash, renglon_id, venia_en_zip,
                   estado_lectura, motivo_lectura, subido_en
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
# Lo que se le sacó a cada documento
#
# Esta es la memoria del programa. Ver el comentario de la tabla
# datos_extraidos, arriba, para el porqué.
# ----------------------------------------------------------


def marcar_lectura(id_documento, estado, motivo=""):
    """Anota en qué va la lectura de un documento.

    Los estados son 'pendiente', 'leyendo', 'listo' y 'fallo'. Devuelve
    True si el documento existía.
    """
    if estado not in ("pendiente", "leyendo", "listo", "fallo"):
        raise ValueError("Estado de lectura desconocido: %r" % (estado,))
    with conectar() as conexion:
        cursor = conexion.execute(
            "UPDATE documentos SET estado_lectura = ?, motivo_lectura = ?"
            " WHERE id = ?",
            (estado, motivo or None, id_documento),
        )
    return cursor.rowcount > 0


def documentos_sin_leer(cliente_id=None):
    """Los documentos a los que todavía no se les sacó nada.

    Sin `cliente_id` devuelve los de todos los clientes, que es como los
    pide la cola cuando arranca el programa.

    Van los que están 'pendiente' y también los que quedaron a medias en
    'leyendo' —porque se cerró el programa a mitad—, para que se puedan
    retomar. Los que fallaron NO vuelven solos: el contador decide si
    reintentarlos, para no gastar cupo repitiendo lo que ya falló.
    """
    consulta = (
        "SELECT * FROM documentos"
        " WHERE estado_lectura IN ('pendiente', 'leyendo')"
    )
    parametros = []
    if cliente_id is not None:
        consulta += " AND cliente_id = ?"
        parametros.append(cliente_id)
    consulta += " ORDER BY id"

    with conectar() as conexion:
        filas = conexion.execute(consulta, parametros).fetchall()
    return [dict(fila) for fila in filas]


def rescatar_lecturas_a_medias():
    """Devuelve a 'pendiente' los documentos que quedaron en 'leyendo'.

    Un documento queda en 'leyendo' si se cerró el programa —o se fue la
    luz— justo mientras se leía. Se llama al arrancar: así la cola retoma
    donde iba en vez de dejar documentos colgados para siempre.

    Devuelve cuántos rescató.
    """
    with conectar() as conexion:
        cursor = conexion.execute(
            "UPDATE documentos SET estado_lectura = 'pendiente'"
            " WHERE estado_lectura = 'leyendo'"
        )
    return cursor.rowcount


def guardar_datos_extraidos(cliente_id, documento_id, datos, origen):
    """Guarda lo que se le sacó a un documento. Reemplaza lo que hubiera.

    `datos` es una lista de diccionarios con 'concepto' y, opcionalmente,
    'valor' y 'detalle'. `origen` es 'codigo' (lo leyó el programa de un
    XML: es exacto) o 'ia' (lo leyó un modelo: es lectura automática y en
    pantalla se muestra marcada como tal).

    Se borra primero lo anterior de ese documento para que releer no
    deje datos duplicados ni datos viejos de una lectura anterior.
    """
    if origen not in ("codigo", "ia"):
        raise ValueError("Origen desconocido: %r" % (origen,))

    cuando = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        conexion.execute(
            "DELETE FROM datos_extraidos WHERE documento_id = ?",
            (documento_id,),
        )
        for dato in datos:
            concepto = str(dato.get("concepto", "")).strip()
            if not concepto:
                continue
            conexion.execute(
                """
                INSERT INTO datos_extraidos
                    (cliente_id, documento_id, concepto, valor, detalle,
                     origen, extraido_en)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (cliente_id, documento_id, concepto[:200],
                 _o_nada(dato.get("valor")), _o_nada(dato.get("detalle")),
                 origen, cuando),
            )
    return listar_datos_extraidos(cliente_id, documento_id=documento_id)


def _o_nada(valor):
    """Deja el valor como texto recortado, o None si está vacío."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto[:300] if texto else None


def listar_datos_extraidos(cliente_id, documento_id=None):
    """Lo que se le sacó a los documentos de un cliente.

    Cada fila trae el nombre del documento de donde salió, para que en
    pantalla se pueda abrir el original al lado del dato. Ningún dato se
    muestra suelto.
    """
    consulta = (
        "SELECT e.*, d.nombre_original, d.nombre_guardado"
        " FROM datos_extraidos e"
        " JOIN documentos d ON d.id = e.documento_id"
        " WHERE e.cliente_id = ?"
    )
    parametros = [cliente_id]
    if documento_id is not None:
        consulta += " AND e.documento_id = ?"
        parametros.append(documento_id)
    consulta += " ORDER BY e.documento_id, e.id"

    with conectar() as conexion:
        filas = conexion.execute(consulta, parametros).fetchall()
    return [dict(fila) for fila in filas]


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


# ----------------------------------------------------------
# Valores del Formulario 210, por cliente
# ----------------------------------------------------------


def _numero(valor):
    """SQLite devuelve los REAL como 1500000.0. Si es entero, se ve mejor así."""
    if valor is None:
        return None
    if float(valor).is_integer():
        return int(valor)
    return float(valor)


def listar_valores_210(cliente_id):
    """Los valores capturados de un cliente: {celda: {valor, documento, ...}}."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT celda, valor, documento, actualizado_en, plantilla"
            " FROM valores_210"
            " WHERE cliente_id = ? ORDER BY celda",
            (cliente_id,),
        ).fetchall()
    return {
        fila["celda"]: {
            "celda": fila["celda"],
            "valor": _numero(fila["valor"]),
            "documento": fila["documento"],
            "actualizado_en": fila["actualizado_en"],
            "plantilla": fila["plantilla"] or "",
        }
        for fila in filas
    }


def obtener_valor_210(cliente_id, celda):
    """El valor de una celda de un cliente, o None si no se ha capturado."""
    return listar_valores_210(cliente_id).get(celda)


def guardar_valor_210(cliente_id, celda, valor, documento="", plantilla=""):
    """Guarda (o reemplaza) el valor de una celda y lo anota en el historial.

    Devuelve el registro guardado.
    """
    anterior = obtener_valor_210(cliente_id, celda)
    ahora = datetime.now().isoformat(timespec="seconds")

    with conectar() as conexion:
        conexion.execute(
            "INSERT INTO valores_210"
            " (cliente_id, celda, valor, documento, actualizado_en, plantilla)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (cliente_id, celda) DO UPDATE SET"
            "   valor = excluded.valor,"
            "   documento = excluded.documento,"
            "   actualizado_en = excluded.actualizado_en,"
            "   plantilla = excluded.plantilla",
            (cliente_id, celda, float(valor), documento or "", ahora,
             plantilla or ""),
        )
        conexion.execute(
            "INSERT INTO bitacora_210"
            " (cliente_id, celda, valor_anterior, valor_nuevo, documento,"
            "  fecha_hora) VALUES (?, ?, ?, ?, ?, ?)",
            (
                cliente_id, celda,
                None if anterior is None else float(anterior["valor"]),
                float(valor), documento or "", ahora,
            ),
        )

    return {
        "celda": celda,
        "valor": _numero(valor),
        "documento": documento or "",
        "actualizado_en": ahora,
        "plantilla": plantilla or "",
    }


def borrar_valor_210(cliente_id, celda):
    """Quita un valor capturado. La celda vuelve a lo que trae la plantilla.

    El movimiento queda en el historial con valor_nuevo en blanco.
    """
    anterior = obtener_valor_210(cliente_id, celda)
    if anterior is None:
        return False

    ahora = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        conexion.execute(
            "DELETE FROM valores_210 WHERE cliente_id = ? AND celda = ?",
            (cliente_id, celda),
        )
        conexion.execute(
            "INSERT INTO bitacora_210"
            " (cliente_id, celda, valor_anterior, valor_nuevo, documento,"
            "  fecha_hora) VALUES (?, ?, ?, NULL, ?, ?)",
            (cliente_id, celda, float(anterior["valor"]),
             "se quitó el valor", ahora),
        )
    return True


def listar_bitacora_210(cliente_id, limite=200):
    """El historial de cambios de un cliente, del más reciente al más viejo."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT celda, valor_anterior, valor_nuevo, documento, fecha_hora"
            " FROM bitacora_210 WHERE cliente_id = ?"
            " ORDER BY id DESC LIMIT ?",
            (cliente_id, limite),
        ).fetchall()
    return [
        {
            "celda": fila["celda"],
            "valor_anterior": _numero(fila["valor_anterior"]),
            "valor_nuevo": _numero(fila["valor_nuevo"]),
            "documento": fila["documento"],
            "fecha_hora": fila["fecha_hora"],
        }
        for fila in filas
    ]


# ----------------------------------------------------------
# Ajustes del programa
# ----------------------------------------------------------


def leer_ajuste(clave, por_defecto=""):
    """Un ajuste guardado, o el valor por defecto si nunca se guardó."""
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT valor FROM ajustes WHERE clave = ?", (clave,)
        ).fetchone()
    return fila["valor"] if fila else por_defecto


def guardar_ajuste(clave, valor):
    """Guarda un ajuste. Si ya existía, lo reemplaza."""
    with conectar() as conexion:
        conexion.execute(
            "INSERT INTO ajustes (clave, valor) VALUES (?, ?)"
            " ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
            (clave, str(valor)),
        )
    return valor


# ----------------------------------------------------------
# La conversación con RentAI
# ----------------------------------------------------------


def guardar_mensaje(cliente_id, papel, texto, propuestas=None):
    """Guarda un mensaje de la conversación de un cliente."""
    import json

    ahora = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        cursor = conexion.execute(
            "INSERT INTO chat_mensajes"
            " (cliente_id, papel, texto, propuestas, creado_en)"
            " VALUES (?, ?, ?, ?, ?)",
            (cliente_id, papel, texto,
             json.dumps(propuestas or [], ensure_ascii=False), ahora),
        )
        id_mensaje = cursor.lastrowid

    return {
        "id": id_mensaje,
        "papel": papel,
        "texto": texto,
        "propuestas": propuestas or [],
        "creado_en": ahora,
    }


def listar_mensajes(cliente_id, limite=50):
    """La conversación de un cliente, del más viejo al más nuevo.

    Se piden los últimos y se voltean: así el límite recorta lo viejo y no
    lo reciente, que es lo que hace falta para seguir hablando.
    """
    import json

    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT id, papel, texto, propuestas, creado_en FROM chat_mensajes"
            " WHERE cliente_id = ? ORDER BY id DESC LIMIT ?",
            (cliente_id, limite),
        ).fetchall()

    mensajes = []
    for fila in reversed(filas):
        try:
            propuestas = json.loads(fila["propuestas"])
        except (ValueError, TypeError):
            propuestas = []
        mensajes.append({
            "id": fila["id"],
            "papel": fila["papel"],
            "texto": fila["texto"],
            "propuestas": propuestas,
            "creado_en": fila["creado_en"],
        })
    return mensajes


def borrar_mensajes(cliente_id):
    """Borra la conversación de un cliente. No toca sus valores anotados."""
    with conectar() as conexion:
        conexion.execute(
            "DELETE FROM chat_mensajes WHERE cliente_id = ?", (cliente_id,)
        )


# ----------------------------------------------------------
# La bitácora general
#
# Qué pasó con los documentos y el checklist de cada cliente. La del
# Formulario 210 es aparte (bitacora_210), porque esa sí guarda cifras.
# ----------------------------------------------------------


def anotar_en_bitacora(cliente_id, accion, detalle="", cantidad=1):
    """Deja constancia de algo que pasó. Nunca falla hacia afuera.

    Se llama después de que la cosa ya pasó. Si anotar fallara y eso
    tumbara la petición, el contador vería un error rojo por un borrado
    que sí se hizo. Prefiero una anotación perdida a un susto.
    """
    try:
        with conectar() as conexion:
            conexion.execute(
                "INSERT INTO bitacora"
                " (cliente_id, accion, detalle, cantidad, fecha_hora)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    cliente_id,
                    accion,
                    detalle or "",
                    int(cantidad),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
    except sqlite3.Error:
        pass


def listar_bitacora(cliente_id, limite=100):
    """Lo último que pasó con este cliente, lo más reciente primero."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT id, accion, detalle, cantidad, fecha_hora"
            " FROM bitacora WHERE cliente_id = ?"
            " ORDER BY id DESC LIMIT ?",
            (cliente_id, limite),
        ).fetchall()
    return [dict(fila) for fila in filas]


# ----------------------------------------------------------
# Documentos en lote
# ----------------------------------------------------------


def documentos_de(cliente_id, ids):
    """Devuelve los documentos de esa lista que SÍ son de ese cliente.

    Es la comprobación que hace que un borrado en lote no pueda tocar los
    archivos de otro cliente aunque le manden ids de otro. Se hace aquí,
    en el servidor, y no en la pantalla: la pantalla se puede engañar.
    """
    ids = [int(uno) for uno in ids]
    if not ids:
        return []
    huecos = ",".join("?" for _ in ids)
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT id, cliente_id, nombre_original, nombre_guardado,"
            " extension, tamano, hash, renglon_id, venia_en_zip, subido_en"
            " FROM documentos"
            " WHERE cliente_id = ? AND id IN (%s)" % huecos,
            [cliente_id] + ids,
        ).fetchall()
    return [dict(fila) for fila in filas]


def eliminar_documentos(cliente_id, ids):
    """Borra de la base varios documentos de un cliente. Devuelve cuántos.

    Solo borra los que son de ese cliente: el cliente_id va en el WHERE,
    no se da por supuesto. Los archivos del disco los mueve a la papelera
    quien llama, antes de esto.
    """
    ids = [int(uno) for uno in ids]
    if not ids:
        return 0
    huecos = ",".join("?" for _ in ids)
    with conectar() as conexion:
        cursor = conexion.execute(
            "DELETE FROM documentos WHERE cliente_id = ? AND id IN (%s)" % huecos,
            [cliente_id] + ids,
        )
    return cursor.rowcount
