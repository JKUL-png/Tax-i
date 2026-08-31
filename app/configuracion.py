"""
La configuración del programa, leída del archivo .env.

Todo lo configurable tiene que ver con la IA:

  IA_PROVEEDOR=  Con cuál servicio se habla. Cuatro opciones:
                   ninguno            no se usa IA (el de fábrica)
                   anthropic          Claude
                   openai_compatible  OpenAI, Groq, OpenRouter, Together,
                                      LM Studio... casi todos
                   ollama             un modelo en este mismo computador

  IA_BASE_URL=   La dirección del servicio. Solo hace falta con
                 openai_compatible; los otros traen la suya.

  IA_API_KEY=    La llave. No hace falta con ollama ni con ninguno.

  IA_MODELO=     Cuál modelo usar.

**El valor por defecto es IA_PROVEEDOR=ninguno.** Si no hay archivo
.env, o está mal escrito, o alguien lo borró, el programa se queda en el
modo en que ningún dato de ningún cliente sale del equipo. Es la opción
segura, y tiene que ser la que pase cuando algo falla.

Antes solo se podía usar Groq, y la configuración era otra: SIN_IA y
GROQ_API_KEY. Los .env viejos SIGUEN FUNCIONANDO —abajo está la
traducción— para que nadie pierda su llave al actualizar el programa.

El .env NUNCA se sube a git. Está en .gitignore.

Los cuatro valores también se cambian desde la pantalla de Cuenta, sin
abrir el archivo a mano. La pantalla llama a `guardar_en_env()`, que
reescribe el .env respetando los comentarios, y después a
`CONFIG.recargar()`, para que el cambio valga de una vez sin tener que
apagar y prender el programa.
"""

from pathlib import Path

from app import proveedores

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = RAIZ / ".env"

# Formas de escribir "sí" que se aceptan, para que no falle por una tilde
# o por una mayúscula.
VALORES_VERDADEROS = {"true", "1", "si", "sí", "yes", "y", "on"}
VALORES_FALSOS = {"false", "0", "no", "n", "off"}

# La dirección de Groq. Se usa solo para traducir los .env viejos, que
# tenían GROQ_API_KEY y ninguna dirección porque no hacía falta.
BASE_URL_DE_GROQ = "https://api.groq.com/openai/v1"
MODELO_VIEJO_DE_GROQ = "openai/gpt-oss-120b"


def leer_env(ruta=ARCHIVO_ENV):
    """Lee el archivo .env y devuelve un diccionario.

    No usa ninguna librería: son líneas "NOMBRE=valor". Las líneas
    vacías y las que empiezan por # se saltan. Si el archivo no existe,
    devuelve un diccionario vacío y el programa se va al modo seguro.
    """
    valores = {}
    if not ruta.exists():
        return valores

    # encoding explícito: en Windows, sin esto, Python usa cp1252 y un
    # comentario con tilde rompe la lectura del archivo entero.
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        nombre, _, valor = linea.partition("=")
        valor = valor.strip()
        # Se admiten comillas alrededor del valor, que es como las
        # escriben muchos ejemplos de internet.
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        valores[nombre.strip().upper()] = valor
    return valores


def _es_verdadero(valor, por_defecto):
    if valor is None:
        return por_defecto
    limpio = str(valor).strip().lower()
    if limpio in VALORES_VERDADEROS:
        return True
    if limpio in VALORES_FALSOS:
        return False
    return por_defecto


def _traducir(valores):
    """Entiende la configuración, sea vieja o nueva.

    Devuelve (proveedor, base_url, llave, modelo).

    La regla: si hay configuración nueva, manda la nueva. Si no la hay,
    se traduce la vieja. Así, quien actualice el programa con su .env de
    antes NO pierde su llave ni se queda sin IA de un día para otro,
    que era justo el error fácil de cometer aquí.
    """
    proveedor = (valores.get("IA_PROVEEDOR") or "").strip().lower()
    base_url = (valores.get("IA_BASE_URL") or "").strip()
    llave = (valores.get("IA_API_KEY") or "").strip()
    modelo = (valores.get("IA_MODELO") or "").strip()

    # --- La llave: si no está la nueva, se usa la vieja de Groq ---
    if not llave:
        llave = (valores.get("GROQ_API_KEY") or "").strip()

    # --- El proveedor ---
    if not proveedor:
        # No hay configuración nueva: se mira la vieja.
        # SIN_IA=true (o no hay .env) manda sobre todo lo demás.
        if _es_verdadero(valores.get("SIN_IA"), True):
            proveedor = "ninguno"
        elif llave:
            # Tenía una llave de Groq y la IA encendida: Groq habla el
            # idioma de OpenAI, así que sigue funcionando igual.
            proveedor = "openai_compatible"
            if not base_url:
                base_url = BASE_URL_DE_GROQ
            if not modelo:
                modelo = MODELO_VIEJO_DE_GROQ
        else:
            proveedor = "ninguno"

    elif _es_verdadero(valores.get("SIN_IA"), False):
        # Configuración nueva pero con el interruptor viejo en "apagado".
        # Gana el apagado: ante la duda, no sale nada del computador.
        proveedor = "ninguno"

    ficha = proveedores.obtener(proveedor)
    if not base_url:
        base_url = ficha.base_url_por_defecto
    if not modelo:
        modelo = ficha.modelo_sugerido

    return ficha.clave, base_url, llave, modelo


class Configuracion:
    """Lo que el programa sabe sobre cómo debe comportarse."""

    def __init__(self, valores=None):
        self._aplicar(leer_env() if valores is None else valores)

    def _aplicar(self, valores):
        self.proveedor, self.base_url, self.llave, self.modelo = _traducir(valores)

    @property
    def ficha(self):
        """El proveedor elegido, con lo que sabe hacer."""
        return proveedores.obtener(self.proveedor)

    @property
    def sin_ia(self):
        """True cuando no se va a usar IA de ninguna clase."""
        return self.proveedor == "ninguno"

    @property
    def ia_disponible(self):
        """Dice si de verdad se puede usar la IA ahora mismo.

        Hacen falta las dos cosas: un proveedor que no sea "ninguno" y,
        si ese proveedor pide llave, una llave. Ollama no pide llave
        porque el modelo corre en este mismo computador.
        """
        if self.sin_ia:
            return False
        if self.ficha.necesita_llave and not self.llave:
            return False
        if self.ficha.necesita_base_url and not self.base_url:
            return False
        return True

    @property
    def motivo(self):
        """Por qué la IA está como está, en palabras que se puedan mostrar."""
        if self.sin_ia:
            return (
                "Modo sin IA activo. Ningún dato de ningún cliente sale de"
                " este computador."
            )
        if self.ficha.necesita_llave and not self.llave:
            return (
                "La IA está configurada con %s pero falta la llave. Se pone"
                " en la pantalla de Cuenta. Por ahora el programa funciona"
                " sin IA." % self.ficha.nombre
            )
        if self.ficha.necesita_base_url and not self.base_url:
            return (
                "Falta decir en qué dirección está el servicio. Se pone en"
                " la pantalla de Cuenta."
            )
        return "La IA está disponible (%s)." % self.ficha.nombre

    @property
    def pista_llave(self):
        """Un pedacito de la llave, para que el contador reconozca cuál es.

        Nunca se manda la llave completa a la pantalla. Se muestra el
        principio y los cuatro últimos caracteres, que es lo mismo que
        hacen las consolas de estos servicios: alcanza para saber si es
        la que uno cree, y no sirve para nada si alguien la ve por
        encima del hombro.
        """
        if not self.llave:
            return ""
        if len(self.llave) <= 12:
            return "•" * len(self.llave)
        return self.llave[:6] + "…" + self.llave[-4:]

    def recargar(self):
        """Vuelve a leer el .env y se actualiza a sí misma.

        Se cambia por dentro en vez de crear una Configuracion nueva
        porque otros módulos guardaron una referencia a ESTE objeto al
        arrancar. Si se creara uno nuevo, ellos se quedarían hablando
        con el viejo y el cambio no serviría de nada.
        """
        self._aplicar(leer_env())
        return self

    def como_diccionario(self):
        """Lo que se le manda a la pantalla. NUNCA incluye la llave."""
        return {
            "proveedor": self.proveedor,
            "proveedor_nombre": self.ficha.nombre,
            "base_url": self.base_url,
            "sin_ia": self.sin_ia,
            "ia_disponible": self.ia_disponible,
            "motivo": self.motivo,
            "que_sale": self.ficha.que_sale,
            "modelo": self.modelo if self.ia_disponible else "",
            "modelo_configurado": self.modelo,
            "tiene_llave": bool(self.llave),
            "pista_llave": self.pista_llave,
            "necesita_llave": self.ficha.necesita_llave,
            "necesita_base_url": self.ficha.necesita_base_url,
            "proveedores": proveedores.lista_para_pantalla(),
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

    `cambios` es un diccionario, por ejemplo {"IA_PROVEEDOR": "ollama"}.
    De cada nombre que ya exista en el archivo se reemplaza su línea en
    el sitio donde está; los que no existan se agregan al final. Los
    comentarios y el orden del archivo se respetan: el contador puede
    seguir abriéndolo con el bloc de notas y encontrarlo igual de
    explicado.

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
