"""
La configuración del programa, leída del archivo .env.

Solo hay dos cosas configurables, y las dos tienen que ver con la IA:

  SIN_IA=true          Apaga por completo la inteligencia artificial.
                       Nada sale del computador. El programa funciona
                       completo: organiza, arma el checklist y exporta.

  GROQ_API_KEY=        La llave para usar la IA, cuando SIN_IA sea false.
                       Se saca gratis en console.groq.com, sin tarjeta.

  IA_MODELO=           Cuál modelo usar. Si no se pone, se usa uno bueno
                       por defecto.

**El valor por defecto es SIN_IA=true.** Si no hay archivo .env, o está
mal escrito, o alguien lo borró, el programa se queda en el modo en que
ningún dato de ningún cliente sale del equipo. Es la opción segura, y
tiene que ser la que pase cuando algo falla.

El .env NUNCA se sube a git. Está en .gitignore.

Desde agosto de 2026 estos tres valores también se pueden cambiar desde
la pantalla de Cuenta, sin abrir el archivo a mano. La pantalla llama a
`guardar_en_env()`, que reescribe el .env respetando los comentarios, y
después a `CONFIG.recargar()`, para que el cambio valga de una vez sin
tener que apagar y prender el programa.
"""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = RAIZ / ".env"

# Formas de escribir "sí" que se aceptan, para que no falle por una tilde
# o por una mayúscula.
VALORES_VERDADEROS = {"true", "1", "si", "sí", "yes", "y", "on"}
VALORES_FALSOS = {"false", "0", "no", "n", "off"}

# Con cuál servicio de IA se habla. Se eligió Groq porque su capa gratis
# es gratis de verdad (sin tarjeta) y porque se compromete a no entrenar
# modelos con lo que uno le manda ni a guardarlo. Eso importa: aquí se
# manejan documentos tributarios de terceros.
SERVICIO = "https://api.groq.com/openai/v1/chat/completions"

# El modelo por defecto. Se puede cambiar con IA_MODELO en el .env.
#
# Se probaron los cuatro modelos gratis que sirven para esto, con los
# documentos de un cliente de prueba. Este fue el único que encontró las
# tres cifras que se le pidieron de tres documentos distintos; los otros
# encontraron una o dos y dijeron que no había casilla.
#
# Su cupo gratis son 200.000 tokens al día, y cada mensaje gasta unos
# 5.000: alcanza para unas 40 preguntas diarias. Si se acaba, en el .env
# se puede poner IA_MODELO=qwen/qwen3.8-27b, que tiene 2 millones al día
# pero busca peor.
MODELO_POR_DEFECTO = "openai/gpt-oss-120b"


def leer_env(ruta=ARCHIVO_ENV):
    """Lee un archivo .env y devuelve sus valores como un diccionario.

    Se escribe a mano en vez de usar una librería porque son quince
    líneas y así es una dependencia menos que se puede romper al
    instalar en el computador del contador.

    Formato: una línea por valor, NOMBRE=valor. Las líneas vacías y las
    que empiezan con # se ignoran.
    """
    valores = {}
    if not ruta.exists():
        return valores

    # encoding explícito: sin esto, en Windows se lee en cp1252 y una
    # tilde en un comentario rompe la lectura del archivo entero.
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        if "=" not in linea:
            continue
        nombre, _, valor = linea.partition("=")
        valor = valor.strip()
        # Quitar las comillas si el valor viene entre comillas.
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        valores[nombre.strip().upper()] = valor

    return valores


def _es_verdadero(valor, por_defecto):
    """Interpreta un texto como sí o no. Si no se entiende, usa el defecto."""
    if valor is None:
        return por_defecto
    limpio = valor.strip().lower()
    if limpio in VALORES_VERDADEROS:
        return True
    if limpio in VALORES_FALSOS:
        return False
    return por_defecto


class Configuracion:
    """Lo que el programa sabe sobre cómo debe comportarse."""

    def __init__(self, valores=None):
        if valores is None:
            valores = leer_env()

        # Por defecto True: sin .env, no sale nada del computador.
        self.sin_ia = _es_verdadero(valores.get("SIN_IA"), True)
        self.llave = (valores.get("GROQ_API_KEY") or "").strip()
        self.modelo = (valores.get("IA_MODELO") or MODELO_POR_DEFECTO).strip()

    @property
    def ia_disponible(self):
        """Dice si de verdad se puede usar la IA ahora mismo.

        Hacen falta las dos cosas: que no esté en modo sin IA, y que
        haya una llave. Tener una llave con SIN_IA=true NO alcanza:
        el modo sin IA manda.
        """
        return (not self.sin_ia) and bool(self.llave)

    @property
    def motivo(self):
        """Por qué la IA está apagada, en palabras que se puedan mostrar."""
        if self.sin_ia:
            return (
                "Modo sin IA activo. Ningún dato de ningún cliente sale de"
                " este computador."
            )
        if not self.llave:
            return (
                "La IA está permitida pero falta la llave (GROQ_API_KEY en el"
                " archivo .env). La llave es gratis y se saca en"
                " console.groq.com. Por ahora el programa funciona sin IA."
            )
        return "La IA está disponible."

    @property
    def pista_llave(self):
        """Un pedacito de la llave, para que el contador reconozca cuál es.

        Nunca se manda la llave completa a la pantalla. Se muestra el
        principio y los cuatro últimos caracteres, que es lo mismo que
        hace la consola de Groq: alcanza para saber si es la que uno
        cree, y no sirve para nada si alguien la ve por encima del
        hombro.
        """
        if not self.llave:
            return ""
        if len(self.llave) <= 12:
            return "•" * len(self.llave)
        return self.llave[:6] + "…" + self.llave[-4:]

    def recargar(self):
        """Vuelve a leer el .env y se actualiza a sí misma.

        Se cambia por dentro en vez de crear una Configuracion nueva
        porque otros módulos (rentai.py) guardaron una referencia a
        ESTE objeto al arrancar. Si se creara uno nuevo, ellos se
        quedarían hablando con el viejo y el cambio no serviría de nada.
        """
        valores = leer_env()
        self.sin_ia = _es_verdadero(valores.get("SIN_IA"), True)
        self.llave = (valores.get("GROQ_API_KEY") or "").strip()
        self.modelo = (valores.get("IA_MODELO") or MODELO_POR_DEFECTO).strip()
        return self

    def como_diccionario(self):
        """Lo que se le manda a la pantalla. Nunca incluye la llave."""
        return {
            "sin_ia": self.sin_ia,
            "ia_disponible": self.ia_disponible,
            "motivo": self.motivo,
            "modelo": self.modelo if self.ia_disponible else "",
            "tiene_llave": bool(self.llave),
            "pista_llave": self.pista_llave,
            "modelo_configurado": self.modelo,
            "modelo_por_defecto": MODELO_POR_DEFECTO,
        }


# ----------------------------------------------------------
# Escribir el .env desde la pantalla de Cuenta
# ----------------------------------------------------------

# El encabezado que se le pone al .env cuando hay que crearlo desde cero
# (por ejemplo, si el contador nunca copió el .env.ejemplo).
ENCABEZADO_ENV = """\
# Configuración de Tax-i.
# Este archivo es privado: NUNCA se sube a git y no sale de este computador.
# Se puede editar a mano o desde la pantalla de Cuenta del programa.
"""


def _valor_para_env(valor):
    """Deja un valor listo para escribirlo en una línea del .env.

    Un salto de línea partiría el archivo en dos y dejaría media llave
    suelta en una línea, así que se quitan. Si el valor trae espacios en
    las puntas o un # (que el lector tomaría por comentario), se guarda
    entre comillas.
    """
    limpio = str(valor).replace("\r", " ").replace("\n", " ").strip()
    if limpio and ("#" in limpio or limpio != limpio.strip()):
        return '"' + limpio.replace('"', "") + '"'
    return limpio


def guardar_en_env(cambios, ruta=ARCHIVO_ENV):
    """Escribe valores en el .env sin borrar lo que ya estaba.

    `cambios` es un diccionario, por ejemplo {"SIN_IA": "false"}. De cada
    nombre que ya exista en el archivo se reemplaza su línea en el sitio
    donde está; los que no existan se agregan al final. Los comentarios y
    el orden del archivo se respetan: el contador puede seguir abriéndolo
    con el bloc de notas y encontrarlo igual de explicado.

    Se escribe primero en un archivo temporal y después se reemplaza el
    bueno de un solo golpe. Así, si se va la luz a mitad de la escritura,
    el .env de siempre queda intacto en vez de quedar a medias.
    """
    cambios = {n.strip().upper(): _valor_para_env(v) for n, v in cambios.items()}

    if ruta.exists():
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    else:
        lineas = ENCABEZADO_ENV.splitlines()

    pendientes = dict(cambios)
    salida = []
    for linea in lineas:
        desnuda = linea.strip()
        if desnuda and not desnuda.startswith("#") and "=" in desnuda:
            nombre = desnuda.partition("=")[0].strip().upper()
            if nombre in pendientes:
                salida.append(nombre + "=" + pendientes.pop(nombre))
                continue
        salida.append(linea)

    # Lo que no estaba en el archivo se agrega al final.
    if pendientes:
        if salida and salida[-1].strip():
            salida.append("")
        for nombre, valor in pendientes.items():
            salida.append(nombre + "=" + valor)

    texto = "\n".join(salida).rstrip("\n") + "\n"

    temporal = ruta.with_name(ruta.name + ".nuevo")
    # encoding y newline explícitos: en Windows, sin newline="", Python
    # convierte cada \n en \r\n y el archivo termina con saltos dobles.
    with open(temporal, "w", encoding="utf-8", newline="\n") as archivo:
        archivo.write(texto)

    # En Mac y Linux se deja el archivo legible solo por su dueño: adentro
    # va una llave. En Windows no existe chmod y la llamada no hace nada.
    try:
        temporal.chmod(0o600)
    except (OSError, NotImplementedError):
        pass

    temporal.replace(ruta)
    return ruta


# Se lee una sola vez al arrancar. Después solo cambia si el contador la
# cambia desde la pantalla de Cuenta, que llama a CONFIG.recargar().
CONFIG = Configuracion()
