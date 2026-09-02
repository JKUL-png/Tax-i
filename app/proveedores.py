"""
Con cuál servicio de IA se habla.

El programa no está casado con ninguna empresa. Aquí adentro está lo
único que cambia de un servicio a otro —la dirección, cómo se manda la
llave, cómo se arma la pregunta y dónde viene la respuesta— y afuera
todo el resto del programa habla con una sola forma.

Los cuatro que se pueden elegir
-------------------------------
  ninguno            No se usa IA. Nada sale del computador. El programa
                     funciona COMPLETO: recibe documentos, arma el
                     checklist, llena el Formulario 210 y exporta. Es el
                     valor de fábrica y el que queda si algo falla.

  anthropic          Claude, de Anthropic.

  openai_compatible  Casi todo lo demás. OpenAI, Groq, OpenRouter,
                     Together, DeepSeek, LM Studio... todos hablan el
                     mismo idioma, así que con este uno solo se cubren.
                     Hay que decirle la dirección (IA_BASE_URL).

  ollama             Modelos que corren en el propio computador. Ojo:
                     con este, ningún dato sale del equipo tampoco, y
                     no hace falta llave.

Por qué no se usa la librería de cada servicio
----------------------------------------------
Porque todas traen archivos compilados (.pyd o .so) y el Control
inteligente de aplicaciones de Windows 11 los bloquea cuando no vienen
firmados. Eso ya pasó una vez en este proyecto: fue lo que obligó a
sacar FastAPI. Aquí se usa urllib, que viene con Python.

La llave
--------
Nunca se escribe en el log, ni se manda a la pantalla, ni sale de este
computador para otra cosa que no sea autenticarse con el servicio que
el contador eligió. En pantalla solo se muestra un pedacito.
"""

import json
import time
import urllib.error
import urllib.request

# Cómo se presenta el programa. Sin esto, Python se identifica como
# "Python-urllib/3.x" y algunos servicios detrás de Cloudflare lo
# rechazan con un 403 (error 1010) creyendo que es un robot.
IDENTIFICACION = "asistente-renta/1.0"

# La versión de la API de Anthropic. Es obligatoria en cada petición.
VERSION_ANTHROPIC = "2023-06-01"

# Cuánto se espera antes de darse por vencido.
SEGUNDOS_DE_ESPERA = 60
SEGUNDOS_DE_PRUEBA = 20

# Reintentos cuando el servicio contesta "no hay cupo" (error 429).
#
# En las capas gratis —la de Groq, por ejemplo— el 429 no es una avería:
# es lo normal cuando se mandan varios documentos seguidos. Casi siempre
# se arregla esperando unos segundos, así que el programa espera y vuelve
# a intentar en vez de molestar al contador.
#
# Se espera 2 segundos, después 4 y después 8. Son tres intentos además
# del primero. Si el servicio dice cuánto esperar (cabecera Retry-After),
# se le hace caso a él en vez de calcular.
ESPERAS_POR_CUPO = (2, 4, 8)

# Si el servicio pide esperar más que esto, no se espera. Dejar el
# programa congelado dos minutos es peor que avisarle al contador y que
# él decida si reintenta o sigue con otra cosa.
ESPERA_MAXIMA_ACEPTADA = 30

# Techo de la respuesta. Aquí se piden cifras y frases cortas, no
# ensayos: con esto sobra y se gasta menos.
LARGO_MAXIMO_RESPUESTA = 2000


class ErrorDeProveedor(Exception):
    """Algo salió mal hablando con el servicio, con un texto para mostrar.

    Además del texto lleva dos datos que el resto del código necesita
    para decidir si vale la pena volver a intentar:

      codigo             el número del error HTTP (429, 401, 500…), o 0
                         si ni siquiera se pudo conectar.
      segundos_sugeridos cuánto pidió esperar el propio servicio en la
                         cabecera Retry-After, o None si no dijo nada.
    """

    def __init__(self, mensaje, codigo=0, segundos_sugeridos=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.segundos_sugeridos = segundos_sugeridos


def _sin_barra(texto):
    """Quita la barra del final para poder pegar la dirección sin dudas."""
    return (texto or "").strip().rstrip("/")


# ----------------------------------------------------------
# Cada proveedor
#
# Los cuatro exponen lo mismo, así que el resto del programa no tiene
# que saber cuál está en uso.
# ----------------------------------------------------------


class Proveedor:
    """Lo que todo proveedor sabe hacer."""

    clave = ""
    nombre = ""
    necesita_llave = True
    necesita_base_url = False
    base_url_por_defecto = ""
    modelo_sugerido = ""
    # Qué se le manda a este servicio cuando la IA está encendida.
    # Se muestra en la pantalla de Cuenta, para que el contador sepa.
    que_sale = ""
    # Cuánto cuesta usarlo: 'gratis', 'mixto' (tiene capa gratis y capa
    # de pago) o 'pago'. La pantalla ordena por esto y muestra primero
    # los que no cuestan, porque el objetivo del programa es que se pueda
    # usar completo sin pagar tokens.
    costo = "pago"

    def url_del_chat(self, base_url):
        raise NotImplementedError

    def url_de_prueba(self, base_url):
        raise NotImplementedError

    def cabeceras(self, llave):
        raise NotImplementedError

    def cuerpo(self, mensajes, modelo, pedir_json=True):
        raise NotImplementedError

    def leer_respuesta(self, datos):
        raise NotImplementedError

    def leer_prueba(self, datos):
        """Qué decir cuando la prueba de conexión salió bien."""
        return "La conexión sirve."


class Ninguno(Proveedor):
    """No hay IA. Es el valor de fábrica y el que queda si algo falla."""

    clave = "ninguno"
    nombre = "Sin IA"
    necesita_llave = False
    costo = "gratis"
    que_sale = "Nada. Ningún dato sale de este computador."

    def url_del_chat(self, base_url):
        raise ErrorDeProveedor("La IA está apagada.")

    def url_de_prueba(self, base_url):
        raise ErrorDeProveedor("La IA está apagada.")


class Anthropic(Proveedor):
    """Claude, de Anthropic."""

    clave = "anthropic"
    nombre = "Anthropic (Claude)"
    necesita_llave = True
    base_url_por_defecto = "https://api.anthropic.com"
    modelo_sugerido = "claude-opus-5"
    que_sale = ("El nombre del cliente, su checklist, la conversación y"
                " los datos que ya se le sacaron a sus documentos. Cada"
                " documento se lee UNA vez —ahí sí sale su texto— y de"
                " ahí en adelante solo salen esos datos. Los archivos"
                " nunca salen.")

    def url_del_chat(self, base_url):
        return _sin_barra(base_url or self.base_url_por_defecto) + "/v1/messages"

    def url_de_prueba(self, base_url):
        return _sin_barra(base_url or self.base_url_por_defecto) + "/v1/models"

    def cabeceras(self, llave):
        return {
            "Content-Type": "application/json",
            # Anthropic NO usa "Authorization: Bearer". Usa su propia
            # cabecera, y exige que se diga con cuál versión se habla.
            "x-api-key": llave,
            "anthropic-version": VERSION_ANTHROPIC,
            "User-Agent": IDENTIFICACION,
        }

    def cuerpo(self, mensajes, modelo, pedir_json=True):
        # Anthropic lleva las instrucciones aparte, en "system", no
        # mezcladas con la conversación como los demás.
        instrucciones = []
        conversacion = []
        for mensaje in mensajes:
            if mensaje["role"] == "system":
                instrucciones.append(mensaje["content"])
            else:
                conversacion.append(mensaje)

        cuerpo = {
            "model": modelo,
            # max_tokens es obligatorio aquí, a diferencia de los demás.
            "max_tokens": LARGO_MAXIMO_RESPUESTA,
            "messages": conversacion,
        }
        if instrucciones:
            cuerpo["system"] = "\n\n".join(instrucciones)
        # No lleva "response_format": aquí el JSON se pide en las
        # instrucciones, que ya lo hacen (ver app/rentai.py).
        return cuerpo

    def leer_respuesta(self, datos):
        # Puede negarse a contestar por sus reglas de seguridad. Cuando
        # pasa, contesta 200 con este motivo y sin texto: hay que
        # decirlo en vez de mostrar un error raro.
        if datos.get("stop_reason") == "refusal":
            raise ErrorDeProveedor(
                "El modelo se negó a contestar esta petición. Pruebe a"
                " preguntarlo de otra manera."
            )
        try:
            for bloque in datos["content"]:
                if bloque.get("type") == "text":
                    return bloque["text"]
        except (KeyError, TypeError):
            pass
        raise ErrorDeProveedor("El servicio contestó algo que no se entendió.")

    def leer_prueba(self, datos):
        cuantos = len(datos.get("data") or [])
        return "La llave sirve. El servicio ofrece %d modelos." % cuantos


class CompatibleConOpenAI(Proveedor):
    """OpenAI y todos los que hablan igual que OpenAI.

    Son casi todos: Groq, OpenRouter, Together, DeepSeek, LM Studio,
    vLLM... Por eso con este solo proveedor se cubre casi todo el mundo.
    """

    clave = "openai_compatible"
    nombre = "Compatible con OpenAI"
    necesita_llave = True
    necesita_base_url = True
    # 'mixto': con este se puede apuntar tanto a un servicio con capa
    # gratis (Groq) como a uno de pago (OpenAI). Cuál, lo elige el
    # contador con la lista de SERVICIOS_COMPATIBLES.
    costo = "mixto"
    base_url_por_defecto = "https://api.openai.com/v1"
    modelo_sugerido = "gpt-4o-mini"
    que_sale = ("El nombre del cliente, su checklist, la conversación y"
                " los datos que ya se le sacaron a sus documentos. Cada"
                " documento se lee UNA vez —ahí sí sale su texto— y de"
                " ahí en adelante solo salen esos datos. Los archivos"
                " nunca salen.")

    def url_del_chat(self, base_url):
        return _sin_barra(base_url or self.base_url_por_defecto) + "/chat/completions"

    def url_de_prueba(self, base_url):
        return _sin_barra(base_url or self.base_url_por_defecto) + "/models"

    def cabeceras(self, llave):
        return {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + llave,
            "User-Agent": IDENTIFICACION,
        }

    def cuerpo(self, mensajes, modelo, pedir_json=True):
        cuerpo = {
            "model": modelo,
            "messages": mensajes,
            # Temperatura baja: aquí no se quiere creatividad, se quiere
            # que copie bien una cifra de un papel.
            "temperature": 0.1,
        }
        if pedir_json:
            # Que conteste JSON y no un párrafo con el JSON adentro.
            # No todos los servidores compatibles lo admiten; si uno lo
            # rechaza, quien llama vuelve a intentar sin esta línea.
            cuerpo["response_format"] = {"type": "json_object"}
        return cuerpo

    def leer_respuesta(self, datos):
        try:
            return datos["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ErrorDeProveedor("El servicio contestó algo que no se entendió.")

    def leer_prueba(self, datos):
        cuantos = len(datos.get("data") or [])
        return "La conexión sirve. El servicio ofrece %d modelos." % cuantos


class Ollama(Proveedor):
    """Un modelo corriendo en este mismo computador, con Ollama.

    Con este, igual que con "ninguno", ningún dato sale del equipo: el
    modelo está aquí. No hace falta llave.
    """

    clave = "ollama"
    nombre = "Ollama (en este computador)"
    necesita_llave = False
    costo = "gratis"
    base_url_por_defecto = "http://localhost:11434"
    modelo_sugerido = "llama3.1"
    que_sale = ("Nada sale de este computador: el modelo corre aquí"
                " mismo.")

    def url_del_chat(self, base_url):
        return _sin_barra(base_url or self.base_url_por_defecto) + "/api/chat"

    def url_de_prueba(self, base_url):
        return _sin_barra(base_url or self.base_url_por_defecto) + "/api/tags"

    def cabeceras(self, llave):
        return {
            "Content-Type": "application/json",
            "User-Agent": IDENTIFICACION,
        }

    def cuerpo(self, mensajes, modelo, pedir_json=True):
        cuerpo = {
            "model": modelo,
            "messages": mensajes,
            # Sin esto contesta en pedacitos y hay que irlos pegando.
            "stream": False,
            "options": {"temperature": 0.1},
        }
        if pedir_json:
            # Ollama no dice "response_format": dice "format".
            cuerpo["format"] = "json"
        return cuerpo

    def leer_respuesta(self, datos):
        try:
            return datos["message"]["content"]
        except (KeyError, TypeError):
            raise ErrorDeProveedor("El servicio contestó algo que no se entendió.")

    def leer_prueba(self, datos):
        modelos = datos.get("models") or []
        if not modelos:
            return ("Ollama está corriendo, pero no tiene ningún modelo"
                    " descargado. Baje uno con: ollama pull llama3.1")
        nombres = ", ".join(m.get("name", "") for m in modelos[:3])
        return "Ollama contesta. Modelos descargados: %s" % nombres


PROVEEDORES = {
    p.clave: p for p in (Ninguno(), Anthropic(), CompatibleConOpenAI(), Ollama())
}

# Si en el .env dice cualquier otra cosa, se usa este. Es el seguro:
# ante la duda, no sale nada del computador.
POR_DEFECTO = "ninguno"


def obtener(clave):
    """El proveedor que se llame así, o 'ninguno' si no existe."""
    return PROVEEDORES.get((clave or "").strip().lower(), PROVEEDORES[POR_DEFECTO])


# ----------------------------------------------------------
# Los servicios que hablan como OpenAI, listos de un clic
#
# "Compatible con OpenAI" no es un servicio: es un idioma que hablan
# muchos. El contador no tiene por qué saberse la dirección de cada uno,
# así que aquí están las de los que sirven, y al elegir uno la dirección
# se llena sola y solo queda pedir la llave.
#
# Van primero los que tienen capa gratis. El objetivo del programa es que
# un contador pueda usarlo completo sin pagar tokens.
# ----------------------------------------------------------

SERVICIOS_COMPATIBLES = (
    {
        "clave": "groq",
        "nombre": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "costo": "gratis",
        "resumen": ("Tiene capa gratis sin tarjeta. Es el camino"
                    " recomendado para empezar."),
        # Verificado en la documentación de Groq.
        "privacidad": (
            "Groq NO usa los datos para entrenar modelos, y esa política"
            " es la misma en la capa gratis y en la de pago: Groq corre"
            " modelos de otros, no desarrolla los suyos, así que no tiene"
            " para qué entrenar con lo que uno le manda. Por defecto"
            " tampoco guarda los datos de las consultas; puede registrarlos"
            " temporalmente hasta 30 días para resolver problemas, y ese"
            " registro se puede APAGAR en Data Controls, dentro de los"
            " ajustes de la consola de Groq. Vale la pena apagarlo: aquí"
            " se manda información tributaria de terceros."
        ),
        "enlace": "https://console.groq.com/settings",
        "enlace_texto": "Consola de Groq → Ajustes → Data Controls",
    },
    {
        "clave": "openai",
        "nombre": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "costo": "pago",
        "resumen": "Se paga por uso. No tiene capa gratis.",
        "privacidad": (
            "Revise en su cuenta de OpenAI qué hace con los datos de la"
            " API antes de mandarle documentos de clientes."
        ),
        "enlace": "",
        "enlace_texto": "",
    },
    {
        "clave": "otro",
        "nombre": "Otro (escribo la dirección)",
        "base_url": "",
        "costo": "",
        "resumen": ("Cualquier otro que hable como OpenAI: OpenRouter,"
                    " Together, DeepSeek, LM Studio, vLLM…"),
        "privacidad": (
            "Antes de elegir un servicio, mire qué hace con lo que uno le"
            " manda. Hay capas gratis que entrenan con eso y donde"
            " revisores humanos pueden leerlo. Aquí van documentos"
            " tributarios de terceros: eso pesa más que el precio."
        ),
        "enlace": "",
        "enlace_texto": "",
    },
)

# Lo que hay que saber de las capas gratis, y por qué existe la fila.
AVISO_CAPA_GRATIS = (
    "Las capas gratis tienen un límite de uso diario. Cuando se acaba, el"
    " servicio contesta «no hay cupo»: el programa espera y reintenta"
    " solo, y si aun así no alcanza, lo que quede sin leer se queda"
    " pendiente en la fila para más tarde. Por eso los documentos se leen"
    " en una fila y no todos de golpe — así usted decide cuándo se gasta"
    " el cupo del día, y nada se pierde si se acaba."
)


def lista_para_pantalla():
    """Los proveedores, listos para dibujar el selector de la pantalla.

    El orden importa: primero los que NO cuestan. El objetivo del
    proyecto es que un contador pueda usar el programa completo sin
    pagar tokens, y la pantalla tiene que reflejar eso — si lo primero
    que se ve es un servicio de pago, parece que hay que pagar.

        1. Sin IA          nada sale del computador, y todo funciona
        2. Ollama          el modelo corre aquí; tampoco sale nada
        3. Compatible      apuntando a Groq, que tiene capa gratis
        4. Anthropic       de pago
    """
    return [
        {
            "clave": p.clave,
            "nombre": p.nombre,
            "necesita_llave": p.necesita_llave,
            "necesita_base_url": p.necesita_base_url,
            "base_url_por_defecto": p.base_url_por_defecto,
            "modelo_sugerido": p.modelo_sugerido,
            "que_sale": p.que_sale,
            "costo": p.costo,
        }
        for p in (PROVEEDORES["ninguno"], PROVEEDORES["ollama"],
                  PROVEEDORES["openai_compatible"], PROVEEDORES["anthropic"])
    ]


# ----------------------------------------------------------
# Hablar con el servicio
# ----------------------------------------------------------


def _segundos_que_pide(error):
    """Cuánto pidió esperar el servicio en la cabecera Retry-After.

    Devuelve el número de segundos, o None si no mandó la cabecera o si
    mandó algo que no se entiende. La norma permite mandar una fecha en
    vez de un número; eso casi no se usa para los cupos y aquí se ignora
    en vez de adivinar mal.
    """
    try:
        crudo = error.headers.get("Retry-After")
    except Exception:
        return None
    if not crudo:
        return None
    try:
        segundos = float(str(crudo).strip())
    except ValueError:
        return None
    return segundos if segundos >= 0 else None


def _una_peticion(url, cabeceras, cuerpo, metodo, segundos):
    """Una sola petición HTTP. Devuelve el JSON, o levanta ErrorDeProveedor.

    Los mensajes de error están escritos para que los lea el contador,
    no para depurar. Y en ninguno de ellos aparece la llave.
    """
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    peticion = urllib.request.Request(
        url, data=datos, headers=cabeceras, method=metodo
    )

    try:
        with urllib.request.urlopen(peticion, timeout=segundos) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        cuerpo_error = ""
        try:
            cuerpo_error = error.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        raise _error_legible(error.code, cuerpo_error,
                             _segundos_que_pide(error))
    except urllib.error.URLError as error:
        raise ErrorDeProveedor(
            "No se pudo conectar con el servicio de IA. Revise la"
            " dirección y la conexión a internet. Todo lo demás del"
            " programa funciona igual sin IA."
        ) from error
    except TimeoutError:
        raise ErrorDeProveedor(
            "El servicio de IA se demoró más de %d segundos y se canceló."
            % segundos
        )
    except ValueError:
        raise ErrorDeProveedor("El servicio contestó algo que no era JSON.")


def _pedir(url, cabeceras, cuerpo, metodo, segundos, reintentar_cupo=False):
    """Como `_una_peticion`, pero insistiendo cuando no hay cupo.

    Con `reintentar_cupo=True`, si el servicio contesta 429 («no hay
    cupo»), se espera y se vuelve a intentar: 2 segundos, después 4 y
    después 8. En las capas gratis el 429 es rutina, no una avería, y
    esperar unos segundos lo resuelve casi siempre.

    Solo se reintenta el 429. Una llave mala o un modelo que no existe
    no se arreglan esperando: esos se avisan de una vez.

    Si el servicio manda la cabecera Retry-After, se le hace caso a él en
    vez de calcular — él sabe cuándo se le libera el cupo. Pero si pide
    más de ESPERA_MAXIMA_ACEPTADA segundos no se espera: se corta y se le
    dice al contador, que es mejor que dejarle el programa congelado.
    """
    if not reintentar_cupo:
        return _una_peticion(url, cabeceras, cuerpo, metodo, segundos)

    for espera_calculada in ESPERAS_POR_CUPO:
        try:
            return _una_peticion(url, cabeceras, cuerpo, metodo, segundos)
        except ErrorDeProveedor as error:
            if error.codigo != 429:
                raise

            espera = error.segundos_sugeridos
            if espera is None:
                espera = espera_calculada
            if espera > ESPERA_MAXIMA_ACEPTADA:
                raise ErrorDeProveedor(
                    "Se acabó el cupo del servicio de IA y pide esperar"
                    " %d segundos, que es demasiado para dejarlo esperando."
                    " Puede seguir trabajando: lo que quedó pendiente se"
                    " puede procesar más tarde." % round(espera),
                    codigo=429, segundos_sugeridos=espera,
                )
            time.sleep(espera)

    # Se acabaron los intentos. Se prueba una última vez y, si vuelve a
    # ser falta de cupo, se le dice al contador que ya se insistió — para
    # que no se ponga a reintentar a mano lo que el programa acaba de
    # hacer tres veces.
    try:
        return _una_peticion(url, cabeceras, cuerpo, metodo, segundos)
    except ErrorDeProveedor as error:
        if error.codigo != 429:
            raise
        raise ErrorDeProveedor(
            str(error) + " El programa ya esperó y reintentó %d veces."
            % len(ESPERAS_POR_CUPO),
            codigo=429, segundos_sugeridos=error.segundos_sugeridos,
        ) from error


def _error_legible(codigo, detalle="", segundos_sugeridos=None):
    """Convierte un número de error HTTP en algo que se pueda leer."""
    if codigo in (401, 403):
        return ErrorDeProveedor(
            "La llave de la IA no sirve o no tiene permiso. Revísela en"
            " la pantalla de Cuenta.",
            codigo=codigo,
        )
    if codigo == 404:
        return ErrorDeProveedor(
            "La dirección del servicio no existe, o el modelo que puso no"
            " está en ese servicio. Revise los dos en la pantalla de Cuenta.",
            codigo=codigo,
        )
    if codigo == 429:
        # Este es el único que se reintenta solo. Si el contador llega a
        # ver este texto es porque ya se intentó tres veces esperando, y
        # el cupo sigue agotado: no tiene sentido decirle que espere y
        # reintente él, que es lo que el programa acaba de hacer.
        return ErrorDeProveedor(
            "Se acabó el cupo del servicio de IA por ahora. Las capas"
            " gratis tienen un límite diario; puede seguir trabajando sin"
            " IA y procesar lo pendiente más tarde.",
            codigo=codigo, segundos_sugeridos=segundos_sugeridos,
        )
    if codigo >= 500:
        return ErrorDeProveedor(
            "El servicio de IA está caído en este momento (error %d)."
            % codigo,
            codigo=codigo,
        )
    return ErrorDeProveedor(
        "El servicio de IA rechazó la petición (error %d). %s"
        % (codigo, _resumen_del_detalle(detalle)),
        codigo=codigo,
    )


def _resumen_del_detalle(detalle):
    """Saca el mensaje que mandó el servicio, si se entiende.

    Nunca devuelve la petición completa: adentro va el texto de los
    documentos del cliente y eso no se muestra en un error.
    """
    if not detalle:
        return ""
    try:
        datos = json.loads(detalle)
    except ValueError:
        return ""
    error = datos.get("error")
    if isinstance(error, dict):
        return str(error.get("message", ""))[:200]
    if isinstance(error, str):
        return error[:200]
    return str(datos.get("message", ""))[:200]


def conversar(config, mensajes):
    """Le manda la conversación al servicio elegido y devuelve el texto.

    `config` es el objeto Configuracion: de ahí salen el proveedor, la
    dirección, la llave y el modelo.
    """
    proveedor = obtener(config.proveedor)

    if proveedor.clave == "ninguno":
        raise ErrorDeProveedor("La IA está apagada.")
    if proveedor.necesita_llave and not config.llave:
        raise ErrorDeProveedor(
            "Falta la llave del servicio de IA. Se pone en la pantalla"
            " de Cuenta."
        )

    url = proveedor.url_del_chat(config.base_url)
    cabeceras = proveedor.cabeceras(config.llave)

    try:
        datos = _pedir(
            url, cabeceras,
            proveedor.cuerpo(mensajes, config.modelo, pedir_json=True),
            "POST", SEGUNDOS_DE_ESPERA, reintentar_cupo=True,
        )
    except ErrorDeProveedor as error:
        # Hay servidores compatibles con OpenAI que no admiten que se les
        # pida JSON con response_format y rechazan la petición entera. En
        # ese caso se reintenta sin pedirlo: las instrucciones ya piden
        # JSON de todos modos, y así funciona con LM Studio, con vLLM y
        # con los servidores caseros.
        if "rechazó la petición" not in str(error):
            raise
        datos = _pedir(
            url, cabeceras,
            proveedor.cuerpo(mensajes, config.modelo, pedir_json=False),
            "POST", SEGUNDOS_DE_ESPERA, reintentar_cupo=True,
        )

    return proveedor.leer_respuesta(datos)


def probar(clave_proveedor, llave, base_url):
    """Pregunta si la configuración sirve. Devuelve (sirve, motivo).

    Se pregunta por la lista de modelos, que es una petición de solo
    lectura: NO se manda ni un dato de ningún cliente. Sirve para que el
    contador sepa en el momento si quedó bien configurado, en vez de
    descubrirlo cuando le escriba a RentAI.
    """
    proveedor = obtener(clave_proveedor)

    if proveedor.clave == "ninguno":
        return True, ("Está en modo sin IA. No hay nada que probar y"
                      " ningún dato sale de este computador.")

    llave = (llave or "").strip()
    if proveedor.necesita_llave and not llave:
        return False, "Falta la llave de este servicio."

    if proveedor.necesita_base_url and not (base_url or "").strip():
        return False, "Falta la dirección del servicio (IA_BASE_URL)."

    try:
        datos = _pedir(
            proveedor.url_de_prueba(base_url),
            proveedor.cabeceras(llave),
            None, "GET", SEGUNDOS_DE_PRUEBA,
        )
    except ErrorDeProveedor as error:
        return False, str(error)

    return True, proveedor.leer_prueba(datos)
