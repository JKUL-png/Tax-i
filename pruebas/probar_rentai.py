"""
Prueba de Rentai, la asistente.

Se corre así, desde la carpeta del proyecto:

    .venv/bin/python pruebas/probar_rentai.py

No se conecta a internet ni gasta llamadas de la IA: se reemplaza la
función que habla con el servicio por una que devuelve lo que uno quiera.
Así se pueden probar las respuestas raras que un modelo de verdad manda de
vez en cuando —una casilla inventada, un texto donde va un número, un JSON
mal armado— sin tener que esperar a que pasen.

Lo que comprueba:

  A. Que lo que contesta el modelo se entienda bien, incluso mal armado.
  B. Que las propuestas malas se descarten antes de llegar a la pantalla:
     casillas inventadas, casillas con fórmula, valores que no son números.
  C. Que aceptar una propuesta anote el valor y quede marcado como lectura
     automática, con el documento de donde salió.
  D. Que con el modo sin IA no se hable con nadie.
  E. Que el texto de los PDF se saque aquí, en el computador.
"""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import db, formulario, lectura, rentai  # noqa: E402
from app.configuracion import CONFIG  # noqa: E402

resultados = []


def comprobar(descripcion, condicion, detalle=""):
    resultados.append(bool(condicion))
    linea = f"  {'OK  ' if condicion else 'FALLA'}  {descripcion}"
    if detalle:
        linea += f"  [{detalle}]"
    print(linea)


def pdf_de_prueba(texto):
    """Arma un PDF de verdad, con su tabla xref, para probar la lectura."""
    objetos = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
    ]
    flujo = b"BT /F1 12 Tf 72 700 Td (" + texto.encode("latin-1") + b") Tj ET"
    objetos.append(
        b"<</Length " + str(len(flujo)).encode() + b">>stream\n" + flujo
        + b"\nendstream"
    )
    objetos.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")

    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += str(numero).encode() + b" 0 obj" + cuerpo + b"endobj\n"
    inicio = len(salida)
    salida += b"xref\n0 " + str(len(objetos) + 1).encode() + b"\n"
    salida += b"0000000000 65535 f \n"
    for posicion in posiciones:
        salida += ("%010d 00000 n \n" % posicion).encode()
    salida += (b"trailer<</Size " + str(len(objetos) + 1).encode()
               + b"/Root 1 0 R>>\nstartxref\n" + str(inicio).encode()
               + b"\n%%EOF\n")
    return bytes(salida)


def main():
    if formulario.ruta_plantilla() is None:
        print("No hay plantilla en plantillas/. No se puede probar.")
        return 1

    cliente = db.crear_cliente("Cliente de prueba Rentai", "66")
    print(f"Cliente de prueba: {cliente['id']}")

    # Se guarda cómo estaba la configuración para dejarla igual al final.
    # Ojo: sin_ia ya no se guarda, se deduce del proveedor elegido.
    config_antes = (CONFIG.proveedor, CONFIG.base_url, CONFIG.llave)
    hablar_de_verdad = rentai._llamar_al_servicio

    try:
        # --------------------------------------------------------------
        print("\nA. Se entiende lo que contesta el modelo")
        # --------------------------------------------------------------
        respuesta, propuestas = rentai._entender_respuesta(json.dumps({
            "respuesta": "Encontré los salarios.",
            "propuestas": [{"celda": "G115", "valor": 45000000,
                            "documento": "certificado.pdf",
                            "por_que": "dice total devengado"}],
        }))
        comprobar("una respuesta bien armada se entiende",
                  respuesta == "Encontré los salarios." and len(propuestas) == 1)

        respuesta, propuestas = rentai._entender_respuesta("no soy JSON")
        comprobar("si no manda JSON, se muestra el texto y no hay propuestas",
                  respuesta == "no soy JSON" and propuestas == [])

        respuesta, propuestas = rentai._entender_respuesta('{"respuesta": 3}')
        comprobar("si manda algo raro, no se cae", propuestas == [])

        # --------------------------------------------------------------
        print("\nB. Las propuestas malas no llegan a la pantalla")
        # --------------------------------------------------------------
        revisadas = rentai.revisar_propuestas([
            {"celda": "G115", "valor": 45000000, "documento": "a.pdf"},
            {"celda": "I42", "valor": 1, "documento": "b.pdf"},
            {"celda": "ZZ9999", "valor": 1, "documento": "c.pdf"},
            {"celda": "G44", "valor": "mucha plata", "documento": "d.pdf"},
            {"celda": "G44", "valor": "3.500.000", "documento": "e.pdf"},
            "esto no es ni un diccionario",
        ])
        celdas = [p["celda"] for p in revisadas]
        comprobar("pasa la casilla buena", "G115" in celdas)
        comprobar("se descarta la casilla con fórmula (I42)", "I42" not in celdas)
        comprobar("se descarta la casilla inventada (ZZ9999)",
                  "ZZ9999" not in celdas)
        comprobar("se descarta el valor que no es número", len(celdas) == 2,
                  str(celdas))
        comprobar("un número escrito como '3.500.000' se entiende",
                  any(p["valor"] == 3500000 for p in revisadas))
        comprobar("las propuestas traen la descripción de la plantilla",
                  revisadas[0]["descripcion"] == "Salarios",
                  revisadas[0]["descripcion"])

        # --------------------------------------------------------------
        print("\nC. Aceptar una propuesta")
        # --------------------------------------------------------------
        rentai.anotar_propuesta(cliente["id"], "G115", 45000000,
                                "certificado_laboral.pdf")
        anotados = formulario.listar_valores(cliente["id"])
        comprobar("el valor quedó anotado", len(anotados) == 1
                  and anotados[0]["valor"] == 45000000)
        comprobar("queda marcado como lectura automática y con su documento",
                  "lectura automática" in anotados[0]["documento"]
                  and "certificado_laboral.pdf" in anotados[0]["documento"],
                  anotados[0]["documento"])

        # --------------------------------------------------------------
        print("\nD. Con la IA apagada no se habla con nadie")
        # --------------------------------------------------------------
        llamadas = []

        def servicio_falso(mensajes, config=None):
            llamadas.append(mensajes)
            return json.dumps({
                "respuesta": "Los salarios son 45 millones.",
                "propuestas": [{"celda": "G115", "valor": 45000000,
                                "documento": "certificado.pdf",
                                "por_que": "dice total devengado"}],
            })

        rentai._llamar_al_servicio = servicio_falso

        CONFIG.proveedor, CONFIG.llave = "ninguno", "llave-de-prueba"
        try:
            rentai.hablar(cliente, "hola")
            comprobar("con IA_PROVEEDOR=ninguno no contesta", False,
                      "contestó igual")
        except rentai.RentaiApagada:
            comprobar("con IA_PROVEEDOR=ninguno no contesta", True)
        comprobar("y no se llamó al servicio", llamadas == [])

        # Un proveedor elegido pero sin llave: tampoco se habla con nadie.
        CONFIG.proveedor, CONFIG.llave = "anthropic", ""
        try:
            rentai.hablar(cliente, "hola")
            comprobar("sin llave tampoco contesta", False, "contestó igual")
        except rentai.RentaiApagada:
            comprobar("sin llave tampoco contesta", True)
        comprobar("y tampoco se llamó al servicio", llamadas == [])

        # Ollama no pide llave, pero "ninguno" manda sobre todo.
        CONFIG.proveedor, CONFIG.llave = "ollama", ""
        comprobar("ollama sí queda disponible sin llave", CONFIG.ia_disponible)
        CONFIG.proveedor = "ninguno"
        comprobar("y ninguno nunca queda disponible", not CONFIG.ia_disponible)

        # --------------------------------------------------------------
        print("\nE. Una conversación completa")
        # --------------------------------------------------------------
        CONFIG.proveedor, CONFIG.llave = "anthropic", "llave-de-prueba"
        salida = rentai.hablar(cliente, "¿cuánto ganó de salarios?")

        comprobar("contesta", salida["respuesta"].startswith("Los salarios"))
        comprobar("propone una casilla", len(salida["propuestas"]) == 1,
                  str([p["celda"] for p in salida["propuestas"]]))
        comprobar("la conversación queda guardada",
                  len(db.listar_mensajes(cliente["id"])) == 2)

        mandado = llamadas[-1]
        comprobar("al modelo se le mandan sus instrucciones",
                  mandado[0]["role"] == "system"
                  and "no calculas el impuesto" in mandado[0]["content"].lower())
        comprobar("y el contexto del cliente",
                  "CATÁLOGO DE CASILLAS" in mandado[1]["content"])
        comprobar("el catálogo trae casillas de verdad",
                  "G115" in mandado[1]["content"])
        contexto = mandado[1]["content"]
        comprobar("el contexto NO trae la llave ni rutas del computador",
                  "llave-de-prueba" not in contexto
                  and str(RAIZ) not in contexto)

        db.borrar_mensajes(cliente["id"])
        comprobar("se puede borrar la charla",
                  db.listar_mensajes(cliente["id"]) == [])
        comprobar("y los valores anotados NO se borran con ella",
                  len(formulario.listar_valores(cliente["id"])) == 1)

        # --------------------------------------------------------------
        print("\nF. Leer un PDF, aquí en el computador")
        # --------------------------------------------------------------
        texto, motivo = lectura.leer_pdf(
            pdf_de_prueba("Total devengado 45.000.000")
        )
        comprobar("de un PDF con texto se saca el texto",
                  "45.000.000" in texto, repr(texto[:50]))

        from pypdf import PdfWriter
        from io import BytesIO
        escritor = PdfWriter()
        escritor.add_blank_page(width=200, height=200)
        memoria = BytesIO()
        escritor.write(memoria)
        texto, motivo = lectura.leer_pdf(memoria.getvalue())
        comprobar("de un PDF escaneado se dice que no se pudo, no se inventa",
                  texto == "" and "escaneada" in motivo, motivo[:45])

        texto, motivo = lectura.leer_pdf(b"esto no es un PDF")
        comprobar("un archivo que no es PDF no tumba nada",
                  texto == "" and motivo != "")

    finally:
        rentai._llamar_al_servicio = hablar_de_verdad
        CONFIG.proveedor, CONFIG.base_url, CONFIG.llave = config_antes
        db.eliminar_cliente(cliente["id"])
        formulario.eliminar_carpeta_cliente(cliente["id"])
        print("\nCliente de prueba eliminado.")

    total = len(resultados)
    buenas = sum(resultados)
    print(f"\n{buenas} de {total} comprobaciones pasaron.")
    if buenas != total:
        print("HAY FALLAS.")
        return 1
    print("Todo bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
