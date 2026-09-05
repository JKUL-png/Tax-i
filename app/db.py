"""
Base de datos del asistente.

Usamos SQLite: la base entera es un solo archivo (datos/base.db).
No hay que instalar ni configurar nada, y el archivo se puede copiar
o respaldar como cualquier otro documento.

Ese archivo contiene datos confidenciales de terceros, por eso la
carpeta datos/ está excluida de git.
"""

import json
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
                -- El número del renglón del 210 cuando el renglón salió
                -- de la exógena: '32' para R32. Vacío en los que
                -- escribió el contador.
                codigo_renglon TEXT NOT NULL DEFAULT '',
                -- 'contador' o 'dian'. Los de la DIAN se crean solos al
                -- cargar la exógena; los del contador los escribe él.
                origen         TEXT NOT NULL DEFAULT 'contador',
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

        # La información exógena de cada cliente: lo que los terceros le
        # reportaron a la DIAN. Una carga por cliente y por año gravable.
        #
        # Se guardan los avisos legales de la DIAN TEXTUALES y la fecha
        # de corte, porque el propio primer aviso dice que la
        # información puede cambiar si un tercero la modifica después.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS exogena_cargas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id      INTEGER NOT NULL,
                anio            TEXT NOT NULL,
                -- Lo que dice la cabecera del archivo sobre el titular.
                identificacion  TEXT NOT NULL DEFAULT '',
                tipo_documento  TEXT NOT NULL DEFAULT '',
                nombre          TEXT NOT NULL DEFAULT '',
                -- Hasta cuándo alcanzaron a llegar los datos, y cuándo
                -- se generó el archivo. No son lo mismo.
                fecha_corte     TEXT NOT NULL DEFAULT '',
                fecha_reporte   TEXT NOT NULL DEFAULT '',
                -- Los tres avisos de la DIAN, en JSON, palabra por
                -- palabra. No se resumen ni se reescriben.
                avisos          TEXT NOT NULL DEFAULT '[]',
                -- Los cinco topes, en JSON. Son resumen, no renglones.
                topes           TEXT NOT NULL DEFAULT '[]',
                archivo         TEXT NOT NULL DEFAULT '',
                cargado_en      TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        # Una sola carga por cliente y año: volver a cargar el archivo
        # reemplaza la anterior, no la acumula.
        conexion.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_exogena_cliente_anio"
            " ON exogena_cargas (cliente_id, anio)"
        )

        # Cada cosa que un tercero reportó. Una fila del archivo, una
        # fila aquí.
        #
        # 'requiere_decision' se marca cuando la DIAN propone más de un
        # renglón para la misma cifra. El programa NUNCA elige: guarda
        # las opciones tal como ella las escribió y espera al contador.
        # 'renglon_elegido' es lo que él decidió, y arranca vacío.
        #
        # 'posible_duplicado' se marca cuando dos filas pueden ser el
        # mismo hecho económico. Solo se marca: no se unen, no se
        # descartan y no se elige cuál vale.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS exogena_filas (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                carga_id          INTEGER NOT NULL,
                cliente_id        INTEGER NOT NULL,
                -- En qué fila del Excel estaba. Es lo que le permite al
                -- contador volver al archivo y verlo con sus ojos.
                fila_excel        INTEGER NOT NULL,
                nit_reporta       TEXT NOT NULL DEFAULT '',
                nombre_reporta    TEXT NOT NULL DEFAULT '',
                detalle           TEXT NOT NULL DEFAULT '',
                -- El código que viene dentro del detalle: (Concepto: 2276)
                concepto          TEXT NOT NULL DEFAULT '',
                valor             REAL,
                -- El texto completo de la columna de uso sugerido, sin
                -- recortar ni reescribir. Es de la DIAN.
                uso_sugerido      TEXT NOT NULL DEFAULT '',
                nota              TEXT NOT NULL DEFAULT '',
                -- Los renglones, los topes citados, las opciones y la
                -- información adicional, en JSON.
                renglones         TEXT NOT NULL DEFAULT '[]',
                topes             TEXT NOT NULL DEFAULT '[]',
                opciones          TEXT NOT NULL DEFAULT '[]',
                adicional         TEXT NOT NULL DEFAULT '{}',
                requiere_decision INTEGER NOT NULL DEFAULT 0,
                renglon_elegido   TEXT NOT NULL DEFAULT '',
                posible_duplicado INTEGER NOT NULL DEFAULT 0,
                duplicado_de      TEXT NOT NULL DEFAULT '[]',
                -- El soporte que el contador enlazó a esta fila. Lo
                -- enlaza él: el programa a lo sumo propone uno.
                documento_id      INTEGER,
                FOREIGN KEY (carga_id) REFERENCES exogena_cargas(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_exogena_filas_cliente"
            " ON exogena_filas (cliente_id)"
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_exogena_filas_carga"
            " ON exogena_filas (carga_id)"
        )

        # Lo que el programa cree que es cada documento.
        #
        # Se guardan en vez de calcularse cada vez que se abre la
        # pantalla porque leer cuarenta PDF para pintar una lista la
        # dejaría en blanco varios segundos, y porque la capa 2 —cuando
        # llegue— cuesta plata: recalcularla al abrir la pantalla sería
        # pagar el mismo documento diez veces.
        #
        # SUGERENCIAS, no asignaciones. La columna renglon_id de
        # documentos sigue siendo la única verdad sobre dónde está cada
        # documento, y ahí solo escribe el contador.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS sugerencias (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                documento_id INTEGER NOT NULL,
                cliente_id   INTEGER NOT NULL,
                renglon_id   INTEGER NOT NULL,
                -- De dónde salió: 'exogena', 'xml', 'texto' o 'nombre'.
                -- Se muestra en pantalla: una sugerencia sin origen
                -- visible es una en la que no se puede confiar.
                origen       TEXT NOT NULL,
                -- 'alta' o 'media'. Con 'baja' no se guarda ninguna.
                certeza      TEXT NOT NULL,
                -- La frase que explica por qué, en palabras del contador.
                porque       TEXT NOT NULL DEFAULT '',
                -- La mejor de todas, que es la que se propone.
                principal    INTEGER NOT NULL DEFAULT 0,
                creada_en    TEXT NOT NULL,
                FOREIGN KEY (documento_id) REFERENCES documentos(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_sugerencias_documento"
            " ON sugerencias (documento_id)"
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_sugerencias_cliente"
            " ON sugerencias (cliente_id)"
        )

        # A qué renglones va un documento. Son VARIOS a propósito: un
        # certificado de ingresos y retenciones soporta el ingreso en un
        # renglón y la retención en otro, y obligar a elegir uno solo
        # sería obligar a subir el mismo papel dos veces.
        #
        # documentos.renglon_id se queda como EL PRINCIPAL. No es otra
        # verdad: es la misma, guardada donde el resto del programa ya
        # sabe buscarla (el conteo del checklist, la columna «Soporte
        # cargado» de la exógena). Esta capa las mantiene iguales.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS documento_renglones (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                documento_id INTEGER NOT NULL,
                cliente_id   INTEGER NOT NULL,
                renglon_id   INTEGER NOT NULL,
                principal    INTEGER NOT NULL DEFAULT 0,
                asignado_en  TEXT NOT NULL,
                FOREIGN KEY (documento_id) REFERENCES documentos(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (renglon_id) REFERENCES checklist(id)
                    ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_doc_renglon"
            " ON documento_renglones (documento_id, renglon_id)"
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_doc_renglon_cliente"
            " ON documento_renglones (cliente_id)"
        )

        # Lo que el contador corrigió, para no volver a proponerle lo
        # mismo mal.
        #
        # Se guarda por CÓDIGO de renglón del 210 y por título, nunca por
        # id: los ids son de cada cliente y los códigos no. Eso es lo que
        # hace que una corrección hecha en un cliente sirva en todos los
        # demás, que es de lo que se trata: el contador arregla una vez y
        # el programa aprende para siempre.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS reglas_aprendidas (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                -- Quién emite el documento: su NIT si se pudo leer, y
                -- si no, las palabras con que se le reconoce.
                tercero        TEXT NOT NULL,
                tercero_nombre TEXT NOT NULL DEFAULT '',
                -- Qué clase de papel es: 'cesantias', 'predial'... Vacío
                -- cuando no se pudo saber, y entonces la regla vale para
                -- cualquier documento de ese tercero.
                tipo           TEXT NOT NULL DEFAULT '',
                codigo_renglon TEXT NOT NULL DEFAULT '',
                titulo         TEXT NOT NULL DEFAULT '',
                -- Cuántas veces la ha confirmado. Una regla que él
                -- repitió cinco veces pesa más que una de una sola vez.
                veces          INTEGER NOT NULL DEFAULT 1,
                creada_en      TEXT NOT NULL,
                actualizada_en TEXT NOT NULL
            )
            """
        )
        conexion.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_regla_llave"
            " ON reglas_aprendidas (tercero, tipo)"
        )

        # Cada vez que se le pide al modelo el formulario de un cliente.
        #
        # Una fila por pasada, con lo que gastó. Es lo que contesta
        # «¿cuánto me está costando esto?» en la pantalla de Cuenta, y
        # también lo que deja rastro de con cuál modelo se propuso cada
        # cifra cuando algo no cuadre en marzo.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS pasadas (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id     INTEGER NOT NULL,
                corrida_en     TEXT NOT NULL,
                proveedor      TEXT NOT NULL DEFAULT '',
                modelo         TEXT NOT NULL DEFAULT '',
                -- Con cuáles instrucciones se corrió. Ver
                -- instrucciones.VERSION.
                version        TEXT NOT NULL DEFAULT '',
                -- En cuántos pedazos hubo que partirla. 1 es lo normal.
                bloques        INTEGER NOT NULL DEFAULT 1,
                documentos     INTEGER NOT NULL DEFAULT 0,
                filas_exogena  INTEGER NOT NULL DEFAULT 0,
                tokens_entrada INTEGER NOT NULL DEFAULT 0,
                tokens_salida  INTEGER NOT NULL DEFAULT 0,
                tokens_cache_lectura   INTEGER NOT NULL DEFAULT 0,
                tokens_cache_escritura INTEGER NOT NULL DEFAULT 0,
                -- Aproximado, y en pantalla se dice que es aproximado:
                -- sale de una lista de precios que tiene fecha.
                costo_usd      REAL NOT NULL DEFAULT 0,
                -- 'lista', 'parcial' (algún bloque falló) o 'fallo'.
                estado         TEXT NOT NULL DEFAULT 'lista',
                motivo         TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_pasadas_cliente"
            " ON pasadas (cliente_id)"
        )

        # Lo que propuso la pasada, un renglón puede tener varias filas.
        #
        # Esto NO es el formulario: es una PROPUESTA. El formulario del
        # cliente sigue siendo valores_210, y de aquí a allá solo se pasa
        # cuando el contador aprueba. Tenerlo en dos tablas separadas es
        # lo que hace que una pasada fallida no le deje el formulario a
        # medio llenar.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS pasada_valores (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                pasada_id      INTEGER NOT NULL,
                cliente_id     INTEGER NOT NULL,
                -- "R32". El código del renglón del 210, nunca un id.
                renglon        TEXT NOT NULL,
                renglon_nombre TEXT NOT NULL DEFAULT '',
                -- La cifra como la copió el modelo, con sus puntos, y
                -- al lado la misma ya convertida por el código. Las dos,
                -- porque la primera es lo que se puede cotejar con el
                -- papel y la segunda es con la que se suma.
                valor          TEXT NOT NULL DEFAULT '',
                numero         REAL,
                -- 'exogena' o 'documento', y de cuál.
                fuente         TEXT NOT NULL DEFAULT '',
                referencia     TEXT NOT NULL DEFAULT '',
                documento_id   INTEGER,
                fila_exogena_id INTEGER,
                cita           TEXT NOT NULL DEFAULT '',
                -- 1 si la cita se encontró en el original. Lo que no se
                -- verifica no se puede aprobar.
                verificada     INTEGER NOT NULL DEFAULT 0,
                -- 'A', 'B' o 'C', ya comprobado contra la fuente.
                nivel          TEXT NOT NULL DEFAULT 'C',
                -- El que había dicho el modelo, antes de comprobarlo.
                nivel_pedido   TEXT NOT NULL DEFAULT '',
                condicion      TEXT NOT NULL DEFAULT '',
                nota           TEXT NOT NULL DEFAULT '',
                -- Por qué se bajó el nivel o por qué se descartó.
                motivo         TEXT NOT NULL DEFAULT '',
                -- En cuál casilla de la plantilla va, y por qué esa.
                -- Vacío cuando el renglón tiene varias y empatan: ahí
                -- escoge el contador. Escoger la casilla DENTRO de un
                -- renglón no es una decisión tributaria —el renglón ya
                -- está decidido—, por eso el programa sí la puede tomar.
                celda          TEXT NOT NULL DEFAULT '',
                celda_motivo   TEXT NOT NULL DEFAULT '',
                -- 'propuesto', 'aprobado', 'descartado' o 'revision'.
                estado         TEXT NOT NULL DEFAULT 'propuesto',
                bloque         INTEGER NOT NULL DEFAULT 1,
                -- 1 cuando dos bloques propusieron cosas distintas para
                -- el mismo renglón. No se resuelve solo: se avisa.
                conflicto      INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (pasada_id) REFERENCES pasadas(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_pasada_valores_pasada"
            " ON pasada_valores (pasada_id)"
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_pasada_valores_cliente"
            " ON pasada_valores (cliente_id)"
        )

        # El modo comparación: el 210 que el contador llenó a mano contra
        # el que propuso Tax-i. Es la medición que dice si esto sirve.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS comparaciones (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id    INTEGER NOT NULL,
                pasada_id     INTEGER,
                hecha_en      TEXT NOT NULL,
                archivo       TEXT NOT NULL DEFAULT '',
                coinciden     INTEGER NOT NULL DEFAULT 0,
                difieren      INTEGER NOT NULL DEFAULT 0,
                solo_taxi     INTEGER NOT NULL DEFAULT 0,
                solo_contador INTEGER NOT NULL DEFAULT 0,
                -- El detalle renglón por renglón y el desglose por
                -- nivel, en JSON. Es un informe, no una tabla que se
                -- consulte por partes.
                detalle       TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
                    ON DELETE CASCADE
            )
            """
        )
        conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_comparaciones_cliente"
            " ON comparaciones (cliente_id)"
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

        # Los renglones que salen de la exógena traen el código del
        # formulario 210 ("32") y quedan marcados con su origen. Los que
        # ya existían los escribió el contador, así que 'contador' es el
        # valor correcto por defecto.
        # Las asignaciones que ya existían pasan a la tabla nueva. Sin
        # esto, un contador que actualiza el programa vería el checklist
        # en ceros: los conteos ahora se sacan de documento_renglones.
        ya_hay = conexion.execute(
            "SELECT COUNT(*) AS cuantos FROM documento_renglones"
        ).fetchone()["cuantos"]
        if not ya_hay:
            conexion.execute(
                "INSERT OR IGNORE INTO documento_renglones (documento_id,"
                " cliente_id, renglon_id, principal, asignado_en)"
                " SELECT id, cliente_id, renglon_id, 1, subido_en"
                " FROM documentos WHERE renglon_id IS NOT NULL"
            )

        columnas_checklist = {
            fila["name"]
            for fila in conexion.execute("PRAGMA table_info(checklist)")
        }
        if columnas_checklist and "codigo_renglon" not in columnas_checklist:
            conexion.execute(
                "ALTER TABLE checklist ADD COLUMN codigo_renglon TEXT"
                " NOT NULL DEFAULT ''"
            )
        if columnas_checklist and "origen" not in columnas_checklist:
            conexion.execute(
                "ALTER TABLE checklist ADD COLUMN origen TEXT"
                " NOT NULL DEFAULT 'contador'"
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
        # En qué va la clasificación. Es distinta de estado_lectura:
        # clasificar es gratis y local, leer con IA cuesta. Por eso
        # clasificar arranca solo al subir y leer lo pide el contador.
        if "estado_clasificacion" not in columnas_doc:
            conexion.execute(
                "ALTER TABLE documentos ADD COLUMN estado_clasificacion TEXT"
                " NOT NULL DEFAULT 'pendiente'"
            )
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

        # La frase del documento de donde salió cada dato. Antes se
        # verificaba y se botaba; ahora se guarda, para que el contador
        # pueda ver de dónde salió sin volver a abrir el PDF.
        columnas_extraidos = {
            fila["name"]
            for fila in conexion.execute("PRAGMA table_info(datos_extraidos)")
        }
        if "cita" not in columnas_extraidos:
            conexion.execute(
                "ALTER TABLE datos_extraidos ADD COLUMN cita TEXT"
                " NOT NULL DEFAULT ''"
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

    Sin `cliente_id` devuelve los de todos los clientes.

    Van los que están 'pendiente' y también los que quedaron a medias en
    'leyendo' —de una versión anterior, cuando los PDF se leían uno por
    uno en otro hilo—. Los que fallaron NO vuelven solos: el contador
    decide si reintentarlos.
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

    Un documento quedaba en 'leyendo' si se cerraba el programa —o se
    iba la luz— justo mientras la vieja fila lo leía. Se llama al
    arrancar para que ninguno se quede colgado para siempre.

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
    'valor', 'detalle' y 'cita'. `origen` dice quién lo leyó:

      'codigo'  lo leyó el programa de un XML. Es exacto.
      'pasada'  salió de la pasada del formulario. Es lectura automática
                y en pantalla se muestra marcada como tal, con su cita
                ya verificada contra el texto del documento.
      'ia'      lo leyó un modelo, en las versiones anteriores del
                programa. Ya no se escribe, pero se sigue leyendo: lo
                que un contador ya tiene guardado no se le borra.

    Se borra primero lo anterior de ese documento para que releer no
    deje datos duplicados ni datos viejos de una lectura anterior.
    """
    if origen not in ("codigo", "pasada", "ia"):
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
                     origen, extraido_en, cita)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (cliente_id, documento_id, concepto[:200],
                 _o_nada(dato.get("valor")), _o_nada(dato.get("detalle")),
                 origen, cuando, str(dato.get("cita") or "")[:500]),
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
            SELECT id, cliente_id, titulo, estado, orden, actualizado_en,
                   codigo_renglon, origen
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
            "SELECT id, cliente_id, titulo, estado, orden, actualizado_en,"
            " codigo_renglon, origen FROM checklist WHERE id = ?",
            (id_renglon,),
        ).fetchone()
    return dict(fila) if fila else None


def crear_renglon(cliente_id, titulo, estado="faltante",
                  codigo_renglon="", origen="contador"):
    """Agrega un renglón al final del checklist de un cliente.

    'origen' dice quién lo puso: 'contador' si lo escribió él, 'dian' si
    salió de la exógena. 'codigo_renglon' es el número del 210 ('32'),
    y es lo que después permite llevar el valor a su casilla.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        # El siguiente número de orden: uno más que el último que haya.
        fila = conexion.execute(
            "SELECT MAX(orden) AS ultimo FROM checklist WHERE cliente_id = ?",
            (cliente_id,),
        ).fetchone()
        orden = (fila["ultimo"] or 0) + 1

        cursor = conexion.execute(
            "INSERT INTO checklist (cliente_id, titulo, estado, orden,"
            " actualizado_en, codigo_renglon, origen)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cliente_id, titulo, estado, orden, ahora, codigo_renglon, origen),
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


def actualizar_renglon(id_renglon, titulo=None, estado=None, orden=None):
    """Cambia el nombre, el estado o el lugar de un renglón.

    El contador puede renombrar hasta los renglones que salieron de la
    exógena: son suyos. Renombrar uno de la DIAN no le quita el código
    del 210, así que el valor sigue sabiendo a qué casilla va.
    """
    campos = []
    valores = []

    if titulo is not None:
        campos.append("titulo = ?")
        valores.append(titulo)

    if estado is not None:
        campos.append("estado = ?")
        valores.append(estado)

    if orden is not None:
        campos.append("orden = ?")
        valores.append(orden)

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


def reordenar_checklist(cliente_id, ids_en_orden):
    """Reacomoda los renglones de un cliente en el orden que se le pase.

    Solo mueve los que sean de ese cliente: un id de otro se ignora en
    vez de mover algo que no era.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        for posicion, id_renglon in enumerate(ids_en_orden, start=1):
            conexion.execute(
                "UPDATE checklist SET orden = ?, actualizado_en = ?"
                " WHERE id = ? AND cliente_id = ?",
                (posicion, ahora, id_renglon, cliente_id),
            )
    return listar_checklist(cliente_id)


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
        # Y la tabla de varios renglones queda igual: asignar por esta
        # puerta significa «este es EL renglón», así que reemplaza lo que
        # hubiera. Para sumar uno sin quitar los otros está
        # agregar_renglon_a_documento.
        conexion.execute(
            "DELETE FROM documento_renglones WHERE documento_id = ?",
            (id_documento,),
        )
        if renglon_id is not None:
            fila = conexion.execute(
                "SELECT cliente_id FROM documentos WHERE id = ?",
                (id_documento,),
            ).fetchone()
            if fila is not None:
                conexion.execute(
                    "INSERT OR IGNORE INTO documento_renglones (documento_id,"
                    " cliente_id, renglon_id, principal, asignado_en)"
                    " VALUES (?, ?, ?, 1, ?)",
                    (id_documento, fila["cliente_id"], renglon_id,
                     datetime.now().isoformat(timespec="seconds")),
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
        conexion.execute(
            "DELETE FROM documento_renglones WHERE renglon_id = ?",
            (renglon_id,),
        )


def contar_documentos_por_renglon(cliente_id):
    """Cuántos documentos tiene asignado cada renglón: {renglon_id: cantidad}."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT renglon_id, COUNT(*) AS cantidad"
            " FROM documento_renglones"
            " WHERE cliente_id = ? GROUP BY renglon_id",
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


# ----------------------------------------------------------
# Operaciones sobre la información exógena
# ----------------------------------------------------------
#
# Los campos que son listas o diccionarios se guardan en JSON: son cosas
# que se leen y se muestran enteras, nunca se buscan por adentro, y así
# no hacen falta cinco tablas más para lo mismo.


def _desde_json(texto, por_defecto):
    """Devuelve lo que había en un campo JSON, sin reventar si está dañado."""
    if not texto:
        return por_defecto
    try:
        return json.loads(texto)
    except (ValueError, TypeError):
        return por_defecto


def obtener_carga_exogena(cliente_id, anio=None):
    """La exógena cargada de un cliente. La del año pedido, o la última."""
    consulta = "SELECT * FROM exogena_cargas WHERE cliente_id = ?"
    parametros = [cliente_id]
    if anio:
        consulta += " AND anio = ?"
        parametros.append(anio)
    consulta += " ORDER BY anio DESC, id DESC LIMIT 1"

    with conectar() as conexion:
        fila = conexion.execute(consulta, parametros).fetchone()
    if not fila:
        return None

    carga = dict(fila)
    carga["avisos"] = _desde_json(carga["avisos"], [])
    carga["topes"] = _desde_json(carga["topes"], [])
    return carga


def listar_cargas_exogena(cliente_id):
    """Los años de los que hay exógena cargada, del más nuevo al más viejo."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT id, anio, fecha_corte, cargado_en FROM exogena_cargas"
            " WHERE cliente_id = ? ORDER BY anio DESC",
            (cliente_id,),
        ).fetchall()
    return [dict(fila) for fila in filas]


def listar_filas_exogena(carga_id):
    """Todo lo que le reportaron al cliente, en el orden del archivo.

    Cada fila trae el nombre del documento que el contador le enlazó, si
    le enlazó alguno, para poder abrir el original desde la tabla.
    """
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT f.*, d.nombre_original, d.nombre_guardado"
            " FROM exogena_filas f"
            " LEFT JOIN documentos d ON d.id = f.documento_id"
            " WHERE f.carga_id = ? ORDER BY f.fila_excel",
            (carga_id,),
        ).fetchall()

    resultado = []
    for fila in filas:
        dato = dict(fila)
        dato["renglones"] = _desde_json(dato["renglones"], [])
        dato["topes"] = _desde_json(dato["topes"], [])
        dato["opciones"] = _desde_json(dato["opciones"], [])
        dato["adicional"] = _desde_json(dato["adicional"], {})
        dato["duplicado_de"] = _desde_json(dato["duplicado_de"], [])
        dato["requiere_decision"] = bool(dato["requiere_decision"])
        dato["posible_duplicado"] = bool(dato["posible_duplicado"])
        resultado.append(dato)
    return resultado


def obtener_fila_exogena(id_fila):
    """Una sola fila de la exógena, o None."""
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT * FROM exogena_filas WHERE id = ?", (id_fila,)
        ).fetchone()
    if not fila:
        return None
    dato = dict(fila)
    dato["renglones"] = _desde_json(dato["renglones"], [])
    dato["topes"] = _desde_json(dato["topes"], [])
    dato["opciones"] = _desde_json(dato["opciones"], [])
    dato["adicional"] = _desde_json(dato["adicional"], {})
    dato["duplicado_de"] = _desde_json(dato["duplicado_de"], [])
    dato["requiere_decision"] = bool(dato["requiere_decision"])
    dato["posible_duplicado"] = bool(dato["posible_duplicado"])
    return dato


def guardar_exogena(cliente_id, lectura, archivo=""):
    """Guarda una exógena leída, reemplazando la que hubiera de ese año.

    Volver a cargar el archivo del mismo año reemplaza los registros: la
    DIAN misma advierte que la información cambia cuando un tercero la
    modifica, así que la carga nueva manda.

    Lo que NO se toca son los renglones del checklist. Eso se decide
    aparte (ver app/exogena_cliente.py) justamente para no borrarle al
    contador un renglón que ya tenga documentos encima.
    """
    cabecera = lectura["cabecera"]
    anio = cabecera.get("anio") or ""
    ahora = datetime.now().isoformat(timespec="seconds")

    with conectar() as conexion:
        # Fuera la carga anterior del mismo año, si la había. Sus filas
        # se van con ella por el ON DELETE CASCADE.
        conexion.execute(
            "DELETE FROM exogena_cargas WHERE cliente_id = ? AND anio = ?",
            (cliente_id, anio),
        )
        cursor = conexion.execute(
            "INSERT INTO exogena_cargas"
            " (cliente_id, anio, identificacion, tipo_documento, nombre,"
            "  fecha_corte, fecha_reporte, avisos, topes, archivo, cargado_en)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cliente_id, anio,
                cabecera.get("identificacion", ""),
                cabecera.get("tipo_documento", ""),
                cabecera.get("nombre", ""),
                cabecera.get("fecha_corte", ""),
                cabecera.get("fecha_reporte", ""),
                json.dumps(lectura["avisos"], ensure_ascii=False),
                json.dumps(lectura["topes"], ensure_ascii=False),
                archivo, ahora,
            ),
        )
        carga_id = cursor.lastrowid

        for fila in lectura["filas"]:
            conexion.execute(
                "INSERT INTO exogena_filas"
                " (carga_id, cliente_id, fila_excel, nit_reporta,"
                "  nombre_reporta, detalle, concepto, valor, uso_sugerido,"
                "  nota, renglones, topes, opciones, adicional,"
                "  requiere_decision, posible_duplicado, duplicado_de)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    carga_id, cliente_id, fila["fila_excel"],
                    fila["nit_reporta"], fila["nombre_reporta"],
                    fila["detalle"], fila["concepto"], fila["valor"],
                    fila["uso_sugerido"], fila["nota"],
                    json.dumps(fila["renglones"], ensure_ascii=False),
                    json.dumps(fila["topes"], ensure_ascii=False),
                    json.dumps(fila["opciones"], ensure_ascii=False),
                    json.dumps(fila["informacion_adicional"], ensure_ascii=False),
                    1 if fila["requiere_decision"] else 0,
                    1 if fila["posible_duplicado"] else 0,
                    json.dumps(fila["duplicado_de"], ensure_ascii=False),
                ),
            )

    return obtener_carga_exogena(cliente_id, anio)


def enlazar_soporte_exogena(id_fila, documento_id):
    """Enlaza (o desenlaza, con None) el documento que respalda una fila."""
    with conectar() as conexion:
        conexion.execute(
            "UPDATE exogena_filas SET documento_id = ? WHERE id = ?",
            (documento_id, id_fila),
        )
    return obtener_fila_exogena(id_fila)


def elegir_renglon_exogena(id_fila, codigo):
    """Guarda el renglón que el contador eligió para una fila.

    Con codigo = "" se vuelve atrás y la fila queda otra vez esperando
    decisión. El programa nunca escribe aquí por su cuenta.
    """
    with conectar() as conexion:
        conexion.execute(
            "UPDATE exogena_filas SET renglon_elegido = ? WHERE id = ?",
            (codigo or "", id_fila),
        )
    return obtener_fila_exogena(id_fila)


def borrar_exogena(cliente_id, anio):
    """Quita la exógena de un año. No toca los renglones del checklist."""
    with conectar() as conexion:
        cursor = conexion.execute(
            "DELETE FROM exogena_cargas WHERE cliente_id = ? AND anio = ?",
            (cliente_id, anio),
        )
    return cursor.rowcount > 0


# ----------------------------------------------------------
# Operaciones sobre las sugerencias
# ----------------------------------------------------------
#
# Son propuestas, no asignaciones: dónde está de verdad cada documento lo
# dice documentos.renglon_id, y ahí solo escribe el contador.


def guardar_sugerencias(cliente_id, documento_id, sugerencias):
    """Reemplaza las sugerencias de un documento por estas.

    Reemplaza y no acumula: si se vuelve a clasificar —porque se cargó
    la exógena y ahora hay con qué cruzar— las de antes ya no valen.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        conexion.execute(
            "DELETE FROM sugerencias WHERE documento_id = ?", (documento_id,)
        )
        for posicion, sugerencia in enumerate(sugerencias):
            conexion.execute(
                "INSERT INTO sugerencias (documento_id, cliente_id,"
                " renglon_id, origen, certeza, porque, principal, creada_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (documento_id, cliente_id, sugerencia["renglon_id"],
                 sugerencia["origen"], sugerencia["certeza"],
                 sugerencia.get("porque", ""), 1 if posicion == 0 else 0,
                 ahora),
            )
        conexion.execute(
            "UPDATE documentos SET estado_clasificacion = 'listo'"
            " WHERE id = ?", (documento_id,)
        )


def sugerencias_del_cliente(cliente_id):
    """Las sugerencias de todos sus documentos: {documento_id: [...]}."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT * FROM sugerencias WHERE cliente_id = ?"
            " ORDER BY documento_id, principal DESC, id",
            (cliente_id,),
        ).fetchall()
    agrupadas = {}
    for fila in filas:
        dato = dict(fila)
        dato["principal"] = bool(dato["principal"])
        agrupadas.setdefault(dato["documento_id"], []).append(dato)
    return agrupadas


def documentos_sin_clasificar(cliente_id=None):
    """Los documentos a los que todavía no se les ha propuesto nada."""
    consulta = ("SELECT * FROM documentos WHERE estado_clasificacion ="
                " 'pendiente'")
    parametros = []
    if cliente_id is not None:
        consulta += " AND cliente_id = ?"
        parametros.append(cliente_id)
    consulta += " ORDER BY id"
    with conectar() as conexion:
        filas = conexion.execute(consulta, parametros).fetchall()
    return [dict(fila) for fila in filas]


def marcar_para_clasificar(cliente_id):
    """Vuelve a poner en la fila todos los documentos de un cliente.

    Se llama al cargar la exógena: hasta ese momento no había terceros
    con qué cruzar, y ahora sí. Los que el contador ya asignó a mano no
    se tocan: su decisión manda sobre cualquier sugerencia.
    """
    with conectar() as conexion:
        cursor = conexion.execute(
            "UPDATE documentos SET estado_clasificacion = 'pendiente'"
            " WHERE cliente_id = ? AND renglon_id IS NULL",
            (cliente_id,),
        )
    return cursor.rowcount


# ----------------------------------------------------------
# A qué renglones va un documento
# ----------------------------------------------------------
#
# Un documento puede ir a varios: el certificado de ingresos y
# retenciones soporta el ingreso en uno y la retención en otro.
#
# documentos.renglon_id guarda EL PRINCIPAL, y estas funciones lo
# mantienen igual a lo que dice la tabla. No son dos verdades: es la
# misma, en el sitio donde el resto del programa ya sabe buscarla.


def _rehacer_principal(conexion, documento_id):
    """Deja documentos.renglon_id igual a lo que diga la tabla."""
    fila = conexion.execute(
        "SELECT renglon_id FROM documento_renglones WHERE documento_id = ?"
        " ORDER BY principal DESC, id LIMIT 1",
        (documento_id,),
    ).fetchone()
    conexion.execute(
        "UPDATE documentos SET renglon_id = ? WHERE id = ?",
        (fila["renglon_id"] if fila else None, documento_id),
    )


def renglones_del_documento(documento_id):
    """Todos los renglones de un documento, el principal primero."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT r.*, c.titulo, c.codigo_renglon"
            " FROM documento_renglones r"
            " JOIN checklist c ON c.id = r.renglon_id"
            " WHERE r.documento_id = ? ORDER BY r.principal DESC, r.id",
            (documento_id,),
        ).fetchall()
    salida = []
    for fila in filas:
        dato = dict(fila)
        dato["principal"] = bool(dato["principal"])
        salida.append(dato)
    return salida


def renglones_por_documento(cliente_id):
    """Lo mismo para todos los documentos de un cliente, de un viaje."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT r.*, c.titulo, c.codigo_renglon"
            " FROM documento_renglones r"
            " JOIN checklist c ON c.id = r.renglon_id"
            " WHERE r.cliente_id = ? ORDER BY r.documento_id,"
            " r.principal DESC, r.id",
            (cliente_id,),
        ).fetchall()
    agrupados = {}
    for fila in filas:
        dato = dict(fila)
        dato["principal"] = bool(dato["principal"])
        agrupados.setdefault(dato["documento_id"], []).append(dato)
    return agrupados


def agregar_renglon_a_documento(documento_id, renglon_id, principal=False):
    """Le suma un renglón a un documento sin quitarle los que ya tenía."""
    ahora = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        documento = conexion.execute(
            "SELECT cliente_id FROM documentos WHERE id = ?", (documento_id,)
        ).fetchone()
        if documento is None:
            return None
        if principal:
            conexion.execute(
                "UPDATE documento_renglones SET principal = 0"
                " WHERE documento_id = ?", (documento_id,)
            )
        conexion.execute(
            "INSERT OR IGNORE INTO documento_renglones"
            " (documento_id, cliente_id, renglon_id, principal, asignado_en)"
            " VALUES (?, ?, ?, ?, ?)",
            (documento_id, documento["cliente_id"], renglon_id,
             1 if principal else 0, ahora),
        )
        if principal:
            conexion.execute(
                "UPDATE documento_renglones SET principal = 1"
                " WHERE documento_id = ? AND renglon_id = ?",
                (documento_id, renglon_id),
            )
        _rehacer_principal(conexion, documento_id)
    return renglones_del_documento(documento_id)


def quitar_renglon_de_documento(documento_id, renglon_id):
    """Le quita UN renglón. Los otros se quedan."""
    with conectar() as conexion:
        conexion.execute(
            "DELETE FROM documento_renglones WHERE documento_id = ?"
            " AND renglon_id = ?", (documento_id, renglon_id)
        )
        _rehacer_principal(conexion, documento_id)
    return renglones_del_documento(documento_id)


# ----------------------------------------------------------
# Las reglas que el contador enseñó
# ----------------------------------------------------------


def guardar_regla(tercero, tipo, codigo_renglon, titulo, tercero_nombre=""):
    """Aprende una corrección, o le suma una vez a la que ya existía."""
    if not tercero or (not codigo_renglon and not titulo):
        return None
    ahora = datetime.now().isoformat(timespec="seconds")
    with conectar() as conexion:
        existente = conexion.execute(
            "SELECT * FROM reglas_aprendidas WHERE tercero = ? AND tipo = ?",
            (tercero, tipo or ""),
        ).fetchone()
        if existente:
            # Si volvió a mandar el mismo documento al mismo renglón, la
            # regla se refuerza. Si lo mandó a otro, manda lo último: la
            # última palabra del contador es la que vale.
            mismo = (existente["codigo_renglon"] == codigo_renglon
                     and existente["titulo"] == titulo)
            conexion.execute(
                "UPDATE reglas_aprendidas SET codigo_renglon = ?, titulo = ?,"
                " tercero_nombre = ?, veces = ?, actualizada_en = ?"
                " WHERE id = ?",
                (codigo_renglon, titulo, tercero_nombre or
                 existente["tercero_nombre"],
                 existente["veces"] + 1 if mismo else 1, ahora,
                 existente["id"]),
            )
            id_regla = existente["id"]
        else:
            cursor = conexion.execute(
                "INSERT INTO reglas_aprendidas (tercero, tercero_nombre,"
                " tipo, codigo_renglon, titulo, veces, creada_en,"
                " actualizada_en) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                (tercero, tercero_nombre, tipo or "", codigo_renglon, titulo,
                 ahora, ahora),
            )
            id_regla = cursor.lastrowid
    return obtener_regla(id_regla)


def obtener_regla(id_regla):
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT * FROM reglas_aprendidas WHERE id = ?", (id_regla,)
        ).fetchone()
    return dict(fila) if fila else None


def listar_reglas():
    """Todas las reglas aprendidas, las más usadas primero.

    No llevan cliente: una corrección hecha en un cliente sirve en
    todos. Y no guardan nada del documento, solo quién lo emite y a qué
    renglón va.
    """
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT * FROM reglas_aprendidas"
            " ORDER BY veces DESC, actualizada_en DESC"
        ).fetchall()
    return [dict(fila) for fila in filas]


def eliminar_regla(id_regla):
    """Borra una regla. Son del contador: él las quita cuando quiera."""
    with conectar() as conexion:
        cursor = conexion.execute(
            "DELETE FROM reglas_aprendidas WHERE id = ?", (id_regla,)
        )
    return cursor.rowcount > 0


# ----------------------------------------------------------
# La pasada del formulario
# ----------------------------------------------------------
#
# Dos tablas y una regla: lo que propone la pasada vive en
# `pasada_valores` y NO es el formulario. El formulario del cliente
# sigue siendo `valores_210`, y solo pasa de una tabla a la otra cuando
# el contador aprueba. Por eso una pasada que se cae a la mitad no le
# deja el formulario a medio llenar: no lo tocó nunca.


def crear_pasada(cliente_id, proveedor="", modelo="", version="",
                 documentos=0, filas_exogena=0, bloques=1):
    """Abre una pasada y devuelve su id. Se cierra con `cerrar_pasada`."""
    with conectar() as conexion:
        cursor = conexion.execute(
            """
            INSERT INTO pasadas
                (cliente_id, corrida_en, proveedor, modelo, version,
                 bloques, documentos, filas_exogena, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'corriendo')
            """,
            (cliente_id, datetime.now().isoformat(timespec="seconds"),
             proveedor, modelo, version, bloques, documentos, filas_exogena),
        )
        return cursor.lastrowid


def cerrar_pasada(pasada_id, estado, uso=None, costo=0.0, motivo="",
                  bloques=None):
    """Anota cómo terminó una pasada y lo que gastó."""
    uso = uso or {}
    campos = {
        "estado": estado,
        "motivo": motivo,
        "tokens_entrada": int(uso.get("entrada") or 0),
        "tokens_salida": int(uso.get("salida") or 0),
        "tokens_cache_lectura": int(uso.get("cache_lectura") or 0),
        "tokens_cache_escritura": int(uso.get("cache_escritura") or 0),
        "costo_usd": float(costo or 0),
    }
    if bloques is not None:
        campos["bloques"] = int(bloques)

    asignaciones = ", ".join("%s = ?" % clave for clave in campos)
    with conectar() as conexion:
        conexion.execute(
            "UPDATE pasadas SET %s WHERE id = ?" % asignaciones,
            list(campos.values()) + [pasada_id],
        )
    return obtener_pasada(pasada_id)


def obtener_pasada(pasada_id):
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT * FROM pasadas WHERE id = ?", (pasada_id,)
        ).fetchone()
    return dict(fila) if fila else None


def pasada_corriendo(cliente_id):
    """La pasada que este cliente tiene abierta ahora mismo. O None.

    Es lo contrario de `ultima_pasada`: aquella busca la propuesta ya
    terminada, para dibujarla; esta busca la que todavía está en el aire,
    para NO arrancar otra encima.

    Aquí solo se hace la consulta. Decidir si una pasada abierta sigue
    viva o se quedó colgada es cosa de `pasada.pasada_en_curso`, que es
    quien conoce los tiempos de espera del servicio.
    """
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT * FROM pasadas WHERE cliente_id = ?"
            " AND estado = 'corriendo'"
            " ORDER BY id DESC LIMIT 1",
            (cliente_id,),
        ).fetchone()
    return dict(fila) if fila else None


def ultima_pasada(cliente_id):
    """La última pasada de un cliente que haya dejado algo. O None.

    Se saltan las que fallaron y las que están corriendo, y eso es
    deliberado: una pasada que se cayó NO puede tapar la propuesta buena
    que el contador ya tenía en pantalla. Que falló se le dice en el
    momento, con el error; lo que no se hace es borrarle el trabajo
    anterior por un servicio que se cayó dos minutos.

    Las fallidas se quedan en la tabla igual, porque también gastaron
    tokens y eso tiene que aparecer en el gasto.
    """
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT * FROM pasadas WHERE cliente_id = ?"
            " AND estado IN ('lista', 'parcial')"
            " ORDER BY id DESC LIMIT 1",
            (cliente_id,),
        ).fetchone()
    return dict(fila) if fila else None


def guardar_valores_de_pasada(pasada_id, cliente_id, valores):
    """Guarda lo que propuso una pasada. Reemplaza lo de esa pasada."""
    with conectar() as conexion:
        conexion.execute(
            "DELETE FROM pasada_valores WHERE pasada_id = ?", (pasada_id,)
        )
        for valor in valores:
            conexion.execute(
                """
                INSERT INTO pasada_valores
                    (pasada_id, cliente_id, renglon, renglon_nombre, valor,
                     numero, fuente, referencia, documento_id,
                     fila_exogena_id, cita, verificada, nivel, nivel_pedido,
                     condicion, nota, motivo, celda, celda_motivo, estado,
                     bloque, conflicto)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?)
                """,
                (pasada_id, cliente_id,
                 str(valor.get("renglon") or ""),
                 str(valor.get("renglon_nombre") or "")[:200],
                 str(valor.get("valor") or "")[:100],
                 valor.get("numero"),
                 str(valor.get("fuente") or ""),
                 str(valor.get("referencia") or "")[:20],
                 valor.get("documento_id"),
                 valor.get("fila_exogena_id"),
                 str(valor.get("cita") or "")[:500],
                 1 if valor.get("verificada") else 0,
                 str(valor.get("nivel") or "C"),
                 str(valor.get("nivel_pedido") or ""),
                 str(valor.get("condicion") or "")[:300],
                 str(valor.get("nota") or "")[:600],
                 str(valor.get("motivo") or "")[:400],
                 str(valor.get("celda") or "")[:10],
                 str(valor.get("celda_motivo") or "")[:200],
                 str(valor.get("estado") or "propuesto"),
                 int(valor.get("bloque") or 1),
                 1 if valor.get("conflicto") else 0),
            )
    return listar_valores_de_pasada(pasada_id)


def listar_valores_de_pasada(pasada_id):
    """Lo propuesto por una pasada, con el nombre del documento al lado."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT p.*, d.nombre_original, d.nombre_guardado"
            " FROM pasada_valores p"
            " LEFT JOIN documentos d ON d.id = p.documento_id"
            " WHERE p.pasada_id = ?"
            " ORDER BY CAST(REPLACE(p.renglon, 'R', '') AS INTEGER), p.id",
            (pasada_id,),
        ).fetchall()
    return [dict(fila) for fila in filas]


def cambiar_estado_de_valores(ids, estado):
    """Marca varias propuestas de golpe: aprobadas, descartadas…"""
    if not ids:
        return 0
    huecos = ", ".join("?" for _ in ids)
    with conectar() as conexion:
        cursor = conexion.execute(
            "UPDATE pasada_valores SET estado = ? WHERE id IN (%s)" % huecos,
            [estado] + list(ids),
        )
        return cursor.rowcount


def gasto_de_pasadas(cliente_id=None):
    """Cuánto se ha gastado en pasadas, por cliente o en total.

    Es lo que muestra la pantalla de Cuenta. El costo es aproximado y
    ahí se dice: sale de una lista de precios con fecha.
    """
    consulta = (
        "SELECT COUNT(*) AS pasadas,"
        " COALESCE(SUM(tokens_entrada), 0) AS entrada,"
        " COALESCE(SUM(tokens_salida), 0) AS salida,"
        " COALESCE(SUM(tokens_cache_lectura), 0) AS cache_lectura,"
        " COALESCE(SUM(tokens_cache_escritura), 0) AS cache_escritura,"
        " COALESCE(SUM(costo_usd), 0) AS costo"
        " FROM pasadas WHERE estado != 'corriendo'"
    )
    parametros = []
    if cliente_id is not None:
        consulta += " AND cliente_id = ?"
        parametros.append(cliente_id)
    with conectar() as conexion:
        return dict(conexion.execute(consulta, parametros).fetchone())


def gasto_por_cliente():
    """El gasto de cada cliente que haya tenido al menos una pasada."""
    with conectar() as conexion:
        filas = conexion.execute(
            "SELECT p.cliente_id, c.nombre, COUNT(*) AS pasadas,"
            " COALESCE(SUM(p.tokens_entrada + p.tokens_salida), 0) AS tokens,"
            " COALESCE(SUM(p.costo_usd), 0) AS costo"
            " FROM pasadas p JOIN clientes c ON c.id = p.cliente_id"
            " WHERE p.estado != 'corriendo'"
            " GROUP BY p.cliente_id, c.nombre"
            " ORDER BY costo DESC"
        ).fetchall()
    return [dict(fila) for fila in filas]


def guardar_comparacion(cliente_id, pasada_id, archivo, resumen, detalle):
    """Guarda el resultado de comparar contra el 210 que él llenó."""
    with conectar() as conexion:
        cursor = conexion.execute(
            """
            INSERT INTO comparaciones
                (cliente_id, pasada_id, hecha_en, archivo, coinciden,
                 difieren, solo_taxi, solo_contador, detalle)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (cliente_id, pasada_id,
             datetime.now().isoformat(timespec="seconds"), archivo,
             int(resumen.get("coinciden", 0)),
             int(resumen.get("difieren", 0)),
             int(resumen.get("solo_taxi", 0)),
             int(resumen.get("solo_contador", 0)),
             json.dumps(detalle, ensure_ascii=False)),
        )
        return cursor.lastrowid


def ultima_comparacion(cliente_id):
    """La última comparación de un cliente, con su detalle ya entendido."""
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT * FROM comparaciones WHERE cliente_id = ?"
            " ORDER BY id DESC LIMIT 1",
            (cliente_id,),
        ).fetchone()
    if not fila:
        return None
    comparacion = dict(fila)
    comparacion["detalle"] = _desde_json(comparacion["detalle"], {})
    return comparacion
