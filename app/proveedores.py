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

# Techo de la respuesta. Aquí se piden cifras y frases cortas, no
# ensayos: con esto sobra y se gasta menos.
LARGO_MAXIMO_RESPUESTA = 2000


class ErrorDeProveedor(Exception):
    """Algo salió mal hablando con el servicio, con un texto para mostrar."""


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
    que_sale = ("El nombre del cliente, el texto de sus documentos, su"
                " checklist y la conversación. Los archivos nunca.")

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
    base_url_por_defecto = "https://api.openai.com/v1"
    modelo_sugerido = "gpt-4o-mini"
    que_sale = ("El nombre del cliente, el texto de sus documentos, su"
                " checklist y la conversación. Los archivos nunca.")

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


def lista_para_pantalla():
    """Los proveedores, listos para dibujar el selector de la pantalla."""
    return [
        {
            "clave": p.clave,
            "nombre": p.nombre,
            "necesita_llave": p.necesita_llave,
            "necesita_base_url": p.necesita_base_url,
            "base_url_por_defecto": p.base_url_por_defecto,
            "modelo_sugerido": p.modelo_sugerido,
            "que_sale": p.que_sale,
        }
        for p in (PROVEEDORES["ninguno"], PROVEEDORES["anthropic"],
                  PROVEEDORES["openai_compatible"], PROVEEDORES["ollama"])
    ]


# ----------------------------------------------------------
# Hablar con el servicio
# ----------------------------------------------------------


def _pedir(url, cabeceras, cuerpo, metodo, segundos):
    """Una petición HTTP. Devuelve el JSON, o levanta ErrorDeProveedor.

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
        raise _error_legible(error.code, cuerpo_error)
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


def _error_legible(codigo, detalle=""):
    """Convierte un número de error HTTP en algo que se pueda leer."""
    if codigo in (401, 403):
        return ErrorDeProveedor(
            "La llave de la IA no sirve o no tiene permiso. Revísela en"
            " la pantalla de Cuenta."
        )
    if codigo == 404:
        return ErrorDeProveedor(
            "La dirección del servicio no existe, o el modelo que puso no"
            " está en ese servicio. Revise los dos en la pantalla de Cuenta."
        )
    if codigo == 429:
        return ErrorDeProveedor(
            "Se acabó el cupo del servicio, o está ocupado. Espere un"
            " minuto y vuelva a intentar."
        )
    if codigo >= 500:
        return ErrorDeProveedor(
            "El servicio de IA está caído en este momento (error %d)."
            % codigo
        )
    return ErrorDeProveedor(
        "El servicio de IA rechazó la petición (error %d). %s"
        % (codigo, _resumen_del_detalle(detalle))
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
            "POST", SEGUNDOS_DE_ESPERA,
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
            "POST", SEGUNDOS_DE_ESPERA,
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
