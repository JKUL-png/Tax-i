"""
Revisa la capa que traduce de un servicio de IA a otro.

Lo importante que se comprueba aquí:

  - Cada proveedor arma su petición como la espera SU servicio. Anthropic
    no se autentica igual que OpenAI, y Ollama no pide el JSON igual que
    ninguno de los dos. Si esto se rompe, Rentai falla en silencio con
    la mitad de los servicios y el contador solo ve "no se entendió".

  - Un .env viejo (SIN_IA + GROQ_API_KEY) sigue funcionando y NO pierde
    la llave. Es el error fácil de cometer al renombrar una variable.

  - "ninguno" nunca queda disponible, pase lo que pase.

No se habla con ningún servicio de verdad: no hace falta internet ni
ninguna llave para correr esto.

    .venv/bin/python pruebas/probar_proveedores.py
"""

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import configuracion, proveedores  # noqa: E402

resultados = []


def comprobar(descripcion, condicion, detalle=""):
    resultados.append(bool(condicion))
    print(("  OK    " if condicion else "  FALLA ") + descripcion
          + (("  [" + str(detalle)[:90] + "]") if detalle else ""))


def titulo(texto):
    print("\n" + texto)


MENSAJES = [
    {"role": "system", "content": "eres una asistente"},
    {"role": "user", "content": "hola"},
]


# ----------------------------------------------------------
# El reintento cuando se acaba el cupo
#
# En las capas gratis el error 429 («no hay cupo») es rutina, no una
# avería. El programa espera y vuelve a intentar: 2 segundos, 4 y 8.
#
# Para probarlo se levanta un servidor de mentira que contesta lo que
# haga falta en cada caso. No se habla con ningún servicio de verdad y
# no se gasta ni un token.
# ----------------------------------------------------------

PUERTO_FALSO = 8231
GUION = {"respuestas": [], "recibidas": 0}


class _ServicioFalso(BaseHTTPRequestHandler):
    """Contesta lo que diga GUION, en orden."""

    protocol_version = "HTTP/1.1"

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        cual = GUION["recibidas"]
        GUION["recibidas"] += 1
        codigo, pide_esperar = GUION["respuestas"][
            min(cual, len(GUION["respuestas"]) - 1)
        ]

        if codigo == 200:
            cuerpo = json.dumps(
                {"choices": [{"message": {"content": "listo"}}]}
            ).encode("utf-8")
        else:
            cuerpo = json.dumps(
                {"error": {"message": "rate limit"}}
            ).encode("utf-8")

        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        if pide_esperar is not None:
            self.send_header("Retry-After", str(pide_esperar))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, formato, *argumentos):
        pass


class _ConfiguracionFalsa:
    proveedor = "openai_compatible"
    llave = "x" * 20
    base_url = "http://127.0.0.1:%d" % PUERTO_FALSO
    modelo = "modelo-de-prueba"


def probar_reintentos():
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO_FALSO), _ServicioFalso)
    servidor.daemon_threads = True
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    def conversar_con(respuestas):
        """Devuelve (funcionó, texto, segundos, cuántas peticiones hubo)."""
        GUION["respuestas"] = respuestas
        GUION["recibidas"] = 0
        comenzo = time.monotonic()
        try:
            salida = proveedores.conversar(_ConfiguracionFalsa(), MENSAJES)
            return True, salida, time.monotonic() - comenzo, GUION["recibidas"]
        except proveedores.ErrorDeProveedor as error:
            return False, str(error), time.monotonic() - comenzo, GUION["recibidas"]

    try:
        # Dos veces sin cupo y a la tercera pasa.
        bien, salida, tardo, veces = conversar_con(
            [(429, None), (429, None), (200, None)]
        )
        comprobar("insiste y termina funcionando", bien, salida)
        comprobar("fueron 3 peticiones: la primera y 2 reintentos", veces == 3)
        comprobar("esperó 2 s y luego 4 s", 5.5 < tardo < 8, "%.1f s" % tardo)

        # Nunca hay cupo: se rinde, pero avisando bien.
        bien, salida, tardo, veces = conversar_con([(429, None)])
        comprobar("si nunca hay cupo, no revienta", not bien)
        comprobar("fueron 4 peticiones: la primera y 3 reintentos", veces == 4)
        comprobar("esperó 2+4+8 segundos", 13 < tardo < 17, "%.1f s" % tardo)
        comprobar("el aviso explica que las capas gratis tienen límite",
                  "límite diario" in salida)
        comprobar("y dice que el programa ya reintentó",
                  "reintentó 3 veces" in salida)

        # Si el servicio dice cuánto esperar, manda él.
        bien, salida, tardo, veces = conversar_con([(429, 1), (200, None)])
        comprobar("hace caso a Retry-After en vez de a su propio cálculo",
                  bien and 0.7 < tardo < 2.5, "esperó %.1f s, no 2" % tardo)

        # Pero si pide una barbaridad, no se queda congelado.
        bien, salida, tardo, veces = conversar_con([(429, 600), (200, None)])
        comprobar("si le piden esperar 10 minutos, no espera",
                  not bien and tardo < 2, "%.1f s" % tardo)
        comprobar("y le dice al contador que puede seguir trabajando",
                  "seguir trabajando" in salida)

        # Una llave mala no se arregla esperando: no se reintenta.
        bien, salida, tardo, veces = conversar_con([(401, None)])
        comprobar("una llave mala NO se reintenta", not bien and veces == 1,
                  "%d petición" % veces)
        comprobar("se rinde de una vez, sin esperar", tardo < 1,
                  "%.2f s" % tardo)
        comprobar("y dice que revise la llave", "llave" in salida)
    finally:
        servidor.shutdown()
        servidor.server_close()


def main():
    print("=" * 62)
    print(" Revisión de la capa de proveedores de IA")
    print("=" * 62)

    # ----------------------------------------------------------
    titulo("A. Anthropic habla como Anthropic")
    # ----------------------------------------------------------
    anthropic = proveedores.obtener("anthropic")

    cabeceras = anthropic.cabeceras("llave-de-prueba")
    comprobar("usa x-api-key y no Authorization",
              cabeceras.get("x-api-key") == "llave-de-prueba"
              and "Authorization" not in cabeceras)
    comprobar("manda la versión de la API, que es obligatoria",
              "anthropic-version" in cabeceras)

    cuerpo = anthropic.cuerpo(MENSAJES, "claude-opus-5")
    comprobar("saca las instrucciones a 'system', fuera de los mensajes",
              cuerpo.get("system") == "eres una asistente"
              and all(m["role"] != "system" for m in cuerpo["messages"]))
    comprobar("manda max_tokens, que aquí es obligatorio",
              isinstance(cuerpo.get("max_tokens"), int))
    comprobar("NO manda response_format, que no existe en esta API",
              "response_format" not in cuerpo)

    comprobar("lee la respuesta de su lista de bloques",
              anthropic.leer_respuesta(
                  {"content": [{"type": "text", "text": "hola"}]}) == "hola")

    # Puede negarse por sus reglas de seguridad: contesta 200 sin texto.
    try:
        anthropic.leer_respuesta({"stop_reason": "refusal", "content": []})
        comprobar("avisa cuando el modelo se niega a contestar", False)
    except proveedores.ErrorDeProveedor:
        comprobar("avisa cuando el modelo se niega a contestar", True)

    comprobar("arma bien sus dos direcciones",
              anthropic.url_del_chat("") .endswith("/v1/messages")
              and anthropic.url_de_prueba("").endswith("/v1/models"))

    # ----------------------------------------------------------
    titulo("B. Los compatibles con OpenAI")
    # ----------------------------------------------------------
    openai = proveedores.obtener("openai_compatible")

    comprobar("se autentica con Authorization: Bearer",
              openai.cabeceras("abc").get("Authorization") == "Bearer abc")

    cuerpo = openai.cuerpo(MENSAJES, "gpt-4o-mini", pedir_json=True)
    comprobar("deja las instrucciones dentro de los mensajes",
              cuerpo["messages"][0]["role"] == "system")
    comprobar("pide JSON con response_format",
              cuerpo.get("response_format") == {"type": "json_object"})

    sin_json = openai.cuerpo(MENSAJES, "gpt-4o-mini", pedir_json=False)
    comprobar("y puede no pedirlo, para los servidores que no lo admiten",
              "response_format" not in sin_json)

    comprobar("respeta la dirección que le den",
              openai.url_del_chat("https://api.groq.com/openai/v1")
              == "https://api.groq.com/openai/v1/chat/completions")
    comprobar("y aguanta que venga con barra al final",
              openai.url_del_chat("https://api.groq.com/openai/v1/")
              == "https://api.groq.com/openai/v1/chat/completions")

    comprobar("lee la respuesta de choices",
              openai.leer_respuesta(
                  {"choices": [{"message": {"content": "hola"}}]}) == "hola")

    # ----------------------------------------------------------
    titulo("C. Ollama, que corre aquí mismo")
    # ----------------------------------------------------------
    ollama = proveedores.obtener("ollama")

    comprobar("no necesita llave", not ollama.necesita_llave)
    comprobar("no manda ninguna cabecera de autenticación",
              "Authorization" not in ollama.cabeceras("")
              and "x-api-key" not in ollama.cabeceras(""))

    cuerpo = ollama.cuerpo(MENSAJES, "llama3.1", pedir_json=True)
    comprobar("pide el JSON con 'format', no con 'response_format'",
              cuerpo.get("format") == "json"
              and "response_format" not in cuerpo)
    comprobar("apaga el streaming, o contestaría en pedacitos",
              cuerpo.get("stream") is False)
    comprobar("lee la respuesta de 'message'",
              ollama.leer_respuesta(
                  {"message": {"content": "hola"}}) == "hola")

    # ----------------------------------------------------------
    titulo("D. Una respuesta rara no tumba nada")
    # ----------------------------------------------------------
    for nombre in ("anthropic", "openai_compatible", "ollama"):
        proveedor = proveedores.obtener(nombre)
        try:
            proveedor.leer_respuesta({"algo": "que no es lo que se espera"})
            comprobar("%s avisa en vez de reventar" % nombre, False)
        except proveedores.ErrorDeProveedor:
            comprobar("%s avisa en vez de reventar" % nombre, True)

    # ----------------------------------------------------------
    titulo("E. Un nombre inventado cae en el lado seguro")
    # ----------------------------------------------------------
    comprobar("un proveedor que no existe se trata como 'ninguno'",
              proveedores.obtener("lo-que-sea").clave == "ninguno")
    comprobar("vacío también", proveedores.obtener("").clave == "ninguno")
    comprobar("y None también", proveedores.obtener(None).clave == "ninguno")

    sirve, motivo = proveedores.probar("ninguno", "", "")
    comprobar("probar 'ninguno' no habla con nadie", sirve, motivo)

    # ----------------------------------------------------------
    titulo("F. Un .env viejo sigue funcionando y NO pierde la llave")
    # ----------------------------------------------------------
    vieja = configuracion.Configuracion({
        "SIN_IA": "false",
        "GROQ_API_KEY": "gsk_llave_vieja_de_prueba_1234",
        "IA_MODELO": "openai/gpt-oss-120b",
    })
    comprobar("la llave de Groq no se pierde",
              vieja.llave == "gsk_llave_vieja_de_prueba_1234")
    comprobar("se entiende como compatible con OpenAI",
              vieja.proveedor == "openai_compatible", vieja.proveedor)
    comprobar("y con la dirección de Groq puesta sola",
              vieja.base_url == configuracion.BASE_URL_DE_GROQ, vieja.base_url)
    comprobar("la IA queda disponible, como estaba antes",
              vieja.ia_disponible, vieja.motivo)

    apagada = configuracion.Configuracion({
        "SIN_IA": "true",
        "GROQ_API_KEY": "gsk_llave_vieja_de_prueba_1234",
    })
    comprobar("con SIN_IA=true queda apagada aunque haya llave",
              apagada.sin_ia and not apagada.ia_disponible)

    # El interruptor viejo gana también sobre la configuración nueva: es
    # el lado seguro, y así un .env a medio migrar no manda datos afuera
    # sin querer.
    mezclada = configuracion.Configuracion({
        "SIN_IA": "true",
        "IA_PROVEEDOR": "anthropic",
        "IA_API_KEY": "sk-ant-de-prueba-1234567890",
    })
    comprobar("SIN_IA=true manda incluso sobre un proveedor nuevo",
              mezclada.sin_ia and not mezclada.ia_disponible)

    # ----------------------------------------------------------
    titulo("G. Sin .env, no sale nada del computador")
    # ----------------------------------------------------------
    vacia = configuracion.Configuracion({})
    comprobar("sin configuración queda en 'ninguno'",
              vacia.proveedor == "ninguno")
    comprobar("y la IA no está disponible", not vacia.ia_disponible)

    rota = configuracion.Configuracion({"IA_PROVEEDOR": "$$$ basura $$$"})
    comprobar("con el .env dañado también queda en 'ninguno'",
              rota.proveedor == "ninguno")

    # ----------------------------------------------------------
    titulo("H. La llave nunca se muestra entera")
    # ----------------------------------------------------------
    con_llave = configuracion.Configuracion({
        "IA_PROVEEDOR": "anthropic",
        "IA_API_KEY": "sk-ant-api03-secretisimo-no-mostrar",
    })
    pista = con_llave.pista_llave
    comprobar("la pista no es la llave", pista != con_llave.llave, pista)
    comprobar("la pista es corta", len(pista) < 20, pista)

    import json
    texto = json.dumps(con_llave.como_diccionario())
    comprobar("lo que se manda a la pantalla NO trae la llave",
              con_llave.llave not in texto)
    comprobar("ni el pedazo del medio de la llave",
              con_llave.llave[6:-4] not in texto)

    titulo("I. Cuando no hay cupo (error 429), insiste antes de rendirse")
    probar_reintentos()

    print()
    print("=" * 62)
    print(" %d de %d comprobaciones pasaron." % (sum(resultados), len(resultados)))
    print(" Todo bien." if all(resultados) else " HAY FALLAS.")
    print("=" * 62)
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
