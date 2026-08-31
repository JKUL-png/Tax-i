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

import sys
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

    print()
    print("=" * 62)
    print(" %d de %d comprobaciones pasaron." % (sum(resultados), len(resultados)))
    print(" Todo bien." if all(resultados) else " HAY FALLAS.")
    print("=" * 62)
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
