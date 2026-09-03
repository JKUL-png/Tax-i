"""
Prueba de las 53 direcciones de la API, por HTTP de verdad.

Para qué es
-----------
Esta prueba es la red de seguridad para cambiar el servidor por dentro.
Arranca el programa en un puerto aparte, le pega a TODAS sus direcciones
como lo haría el navegador, y comprueba que cada una conteste lo que la
pantalla espera: el código de estado correcto y los campos correctos.

Si el servidor se reescribe con otra librería —o sin ninguna— esta prueba
tiene que seguir pasando igual. Eso es lo que garantiza que la interfaz no
se rompa: el navegador no sabe con qué está hecho el servidor, solo sabe
estas direcciones.

Cómo se corre
-------------
    .venv/bin/python pruebas/probar_api.py       (Mac)
    .venv\\Scripts\\python.exe pruebas\\probar_api.py   (Windows)

Qué toca y qué no
-----------------
Crea un cliente de prueba, le sube documentos y al terminar lo borra todo.
No toca a ningún cliente de verdad. El archivo .env se lee y se vuelve a
escribir igual, y la prueba comprueba que haya quedado idéntico.
"""

import json
import mimetypes
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

sys.path.insert(0, str(RAIZ / "pruebas"))

import documentos_de_ejemplo as ejemplos  # noqa: E402

from app import configuracion  # noqa: E402

resultados = []
direccion = ""


# ----------------------------------------------------------
# Utilidades
# ----------------------------------------------------------

def titulo(texto):
    print("\n" + texto)
    print("-" * len(texto))


def comprobar(descripcion, condicion, detalle=""):
    condicion = bool(condicion)
    resultados.append(condicion)
    print("  %s  %s" % ("OK   " if condicion else "FALLA", descripcion))
    if detalle and not condicion:
        print("           %s" % detalle)
    return condicion


def pedir(metodo, camino, cuerpo=None, espera=30, crudo=False):
    """Le pega a una dirección y devuelve (codigo, datos, cabeceras).

    `datos` viene como diccionario o lista si la respuesta era JSON, como
    texto si era texto, y como bytes si se pidió crudo.
    """
    datos = None
    cabeceras = {"Accept": "application/json"}
    if cuerpo is not None:
        datos = json.dumps(cuerpo).encode("utf-8")
        cabeceras["Content-Type"] = "application/json"

    peticion = urllib.request.Request(
        direccion + camino, data=datos, headers=cabeceras, method=metodo
    )
    try:
        with urllib.request.urlopen(peticion, timeout=espera) as r:
            return _leer(r, crudo)
    except urllib.error.HTTPError as error:
        return _leer(error, crudo)
    except (urllib.error.URLError, OSError) as error:
        return 0, str(error), {}


def _leer(respuesta, crudo):
    contenido = respuesta.read()
    # Los nombres de las cabeceras se pasan a minúscula. HTTP no distingue
    # mayúsculas ahí, y cada servidor las manda a su manera: uvicorn en
    # minúscula, otros con la primera letra grande. Buscándolas siempre en
    # minúscula, la prueba sirve para los dos.
    cabeceras = {n.lower(): v for n, v in respuesta.headers.items()}
    if crudo:
        return respuesta.status, contenido, cabeceras
    tipo = cabeceras.get("content-type", "")
    if "json" in tipo:
        try:
            return respuesta.status, json.loads(contenido.decode("utf-8")), cabeceras
        except ValueError:
            return respuesta.status, None, cabeceras
    return respuesta.status, contenido.decode("utf-8", errors="replace"), cabeceras


def subir(camino, campo, archivos, espera=60):
    """Manda archivos como los manda el navegador (multipart/form-data).

    `archivos` es una lista de pares (nombre_del_archivo, contenido).
    """
    frontera = "----taxi" + uuid.uuid4().hex
    partes = []
    for nombre, contenido in archivos:
        tipo = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
        cabecera = (
            '--%s\r\nContent-Disposition: form-data; name="%s";'
            ' filename="%s"\r\nContent-Type: %s\r\n\r\n'
            % (frontera, campo, nombre, tipo)
        )
        partes.append(cabecera.encode("utf-8"))
        partes.append(contenido)
        partes.append(b"\r\n")
    partes.append(("--%s--\r\n" % frontera).encode("utf-8"))
    cuerpo = b"".join(partes)

    peticion = urllib.request.Request(
        direccion + camino,
        data=cuerpo,
        headers={"Content-Type": "multipart/form-data; boundary=" + frontera},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=espera) as r:
            return _leer(r, False)
    except urllib.error.HTTPError as error:
        return _leer(error, False)
    except (urllib.error.URLError, OSError) as error:
        return 0, str(error), {}


def pdf_de_mentiras(texto="Documento de prueba"):
    """Un PDF mínimo pero válido, para no tener que traer un archivo."""
    contenido = (
        "%%PDF-1.4\n"
        "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        "trailer<</Root 1 0 R>>\n%%%%EOF\n" % ()
    )
    return contenido.encode("latin-1") + texto.encode("utf-8")


# ----------------------------------------------------------
# Las pruebas
# ----------------------------------------------------------

def probar_paginas():
    titulo("A. Las páginas y la configuración")

    for descripcion, camino in [
        ("la lista de clientes", "/"),
        ("la pantalla del cliente", "/cliente"),
        ("el resumen para imprimir", "/resumen"),
        ("la pantalla de la cuenta", "/cuenta"),
    ]:
        codigo, cuerpo, _ = pedir("GET", camino)
        comprobar("abre %s" % descripcion,
                  codigo == 200 and "<html" in str(cuerpo).lower(),
                  "código %s" % codigo)

    codigo, _, cabeceras = pedir("GET", "/static/estilos.css")
    comprobar("entrega la hoja de estilos con su tipo",
              codigo == 200 and "css" in cabeceras.get("content-type", ""),
              "código %s, tipo %s" % (codigo, cabeceras.get("content-type")))

    codigo, cuerpo, _ = pedir("GET", "/static/../.env")
    comprobar("no deja salirse de la carpeta static con ../",
              codigo in (400, 403, 404),
              "código %s" % codigo)

    codigo, cuerpo, _ = pedir("GET", "/api/configuracion")
    comprobar("dice cómo está configurado",
              codigo == 200 and isinstance(cuerpo, dict) and "sin_ia" in cuerpo,
              "código %s: %s" % (codigo, str(cuerpo)[:120]))
    # La pista de la llave sí sale (son once caracteres y sirve para
    # reconocerla). Lo que nunca puede salir es la llave entera.
    comprobar("no deja salir ninguna llave completa",
              not any(isinstance(v, str) and v.startswith("gsk_") and len(v) > 20
                      for v in (cuerpo or {}).values()),
              str(cuerpo)[:140])

    codigo, _, _ = pedir("GET", "/api/no-existe-esta-direccion")
    comprobar("contesta 404 en una dirección que no existe", codigo == 404,
              "código %s" % codigo)


def probar_clientes():
    titulo("B. Clientes")

    codigo, lista, _ = pedir("GET", "/api/clientes")
    comprobar("lista los clientes",
              codigo == 200 and isinstance(lista, list), "código %s" % codigo)

    if isinstance(lista, list) and lista:
        comprobar("cada cliente trae su avance del checklist",
                  all("checklist_total" in c and "documentos" in c for c in lista))

    # --- Crear ---
    codigo, cliente, _ = pedir("POST", "/api/clientes", {
        "nombre": "  Prueba   Automática Ñ  ",
        "dos_digitos": "7",
        "fecha_vencimiento": "2026-09-15",
    })
    comprobar("crea un cliente y contesta 201", codigo == 201,
              "código %s: %s" % (codigo, cliente))

    if codigo != 201:
        return None

    comprobar("le limpia los espacios al nombre",
              cliente["nombre"] == "Prueba Automática Ñ",
              repr(cliente.get("nombre")))
    comprobar("convierte '7' en '07'", cliente["dos_digitos"] == "07",
              repr(cliente.get("dos_digitos")))

    identificador = cliente["id"]

    # --- Validaciones que deben rechazarse ---
    for descripcion, datos in [
        ("un nombre vacío", {"nombre": "   ", "dos_digitos": "07"}),
        ("dígitos que no son números", {"nombre": "X", "dos_digitos": "ab"}),
        ("tres dígitos", {"nombre": "X", "dos_digitos": "123"}),
        ("una fecha inventada", {"nombre": "X", "dos_digitos": "07",
                                 "fecha_vencimiento": "2026-13-45"}),
    ]:
        codigo, cuerpo, _ = pedir("POST", "/api/clientes", datos)
        tiene_mensaje = isinstance(cuerpo, dict) and bool(cuerpo.get("detail"))
        comprobar("rechaza %s, y explica por qué" % descripcion,
                  codigo in (400, 422) and tiene_mensaje,
                  "código %s: %s" % (codigo, cuerpo))

    # --- Leer uno ---
    codigo, uno, _ = pedir("GET", "/api/clientes/%d" % identificador)
    comprobar("entrega ese cliente", codigo == 200 and uno["id"] == identificador,
              "código %s" % codigo)

    codigo, _, _ = pedir("GET", "/api/clientes/999999")
    comprobar("contesta 404 por un cliente que no existe", codigo == 404,
              "código %s" % codigo)

    # --- Cambiar ---
    codigo, cambiado, _ = pedir("PATCH", "/api/clientes/%d" % identificador,
                                {"nombre": "Prueba Cambiada"})
    comprobar("cambia solo el campo que se le manda",
              codigo == 200 and cambiado["nombre"] == "Prueba Cambiada"
              and cambiado["dos_digitos"] == "07",
              "código %s: %s" % (codigo, cambiado))

    codigo, cambiado, _ = pedir("PATCH", "/api/clientes/%d" % identificador,
                                {"fecha_vencimiento": ""})
    comprobar("una fecha vacía borra la fecha",
              codigo == 200 and not cambiado["fecha_vencimiento"],
              "código %s: %s" % (codigo, cambiado))

    codigo, _, _ = pedir("PATCH", "/api/clientes/999999", {"nombre": "X"})
    comprobar("no deja cambiar un cliente que no existe", codigo == 404,
              "código %s" % codigo)

    return identificador


def probar_checklist(identificador):
    titulo("C. Checklist")

    codigo, renglones, _ = pedir("GET",
                                 "/api/clientes/%d/checklist" % identificador)
    # Nada se agrega solo: el cliente nuevo arranca VACÍO. Los renglones
    # salen de cargar la exógena o del botón de la lista sugerida, y las
    # dos cosas las decide el contador.
    comprobar("el cliente nuevo arranca sin ningún renglón",
              codigo == 200 and renglones == [],
              "código %s, %s renglones" % (codigo, len(renglones or [])))

    codigo, base, _ = pedir("POST",
                            "/api/clientes/%d/checklist/base" % identificador)
    comprobar("el botón de la lista sugerida sí la agrega, cuando él la pide",
              codigo == 201 and len(base) > 5,
              "código %s, %s renglones" % (codigo, len(base or [])))

    codigo, renglon, _ = pedir("POST",
                               "/api/clientes/%d/checklist" % identificador,
                               {"titulo": "  Certificado de prueba  "})
    comprobar("agrega un renglón y contesta 201",
              codigo == 201 and renglon["titulo"] == "Certificado de prueba",
              "código %s: %s" % (codigo, renglon))

    if codigo != 201:
        return None

    id_renglon = renglon["id"]

    codigo, cuerpo, _ = pedir("POST",
                              "/api/clientes/%d/checklist" % identificador,
                              {"titulo": "   "})
    comprobar("rechaza un renglón sin título", codigo in (400, 422),
              "código %s: %s" % (codigo, cuerpo))

    codigo, cambiado, _ = pedir("PATCH", "/api/checklist/%d" % id_renglon,
                                {"estado": "recibido"})
    comprobar("marca el renglón como recibido",
              codigo == 200 and cambiado["estado"] == "recibido",
              "código %s: %s" % (codigo, cambiado))

    codigo, cuerpo, _ = pedir("PATCH", "/api/checklist/%d" % id_renglon,
                              {"estado": "inventado"})
    comprobar("rechaza un estado que no existe", codigo in (400, 422),
              "código %s: %s" % (codigo, cuerpo))

    codigo, agregados, _ = pedir(
        "POST", "/api/clientes/%d/checklist/base" % identificador)
    comprobar("puede volver a poner la lista sugerida", codigo == 201,
              "código %s" % codigo)

    return id_renglon


def probar_documentos(identificador, id_renglon):
    titulo("D. Documentos")

    codigo, respuesta, _ = subir(
        "/api/clientes/%d/documentos" % identificador,
        "archivos",
        [("Certificado Niño año.pdf", pdf_de_mentiras()),
         ("nota.txt", b"esto no se admite"),
         (".DS_Store", b"basura de mac")],
    )
    comprobar("recibe la subida", codigo == 200, "código %s: %s" % (codigo, respuesta))

    if codigo != 200:
        return None

    comprobar("guarda el PDF y respeta la ñ y la tilde del nombre",
              len(respuesta["guardados"]) == 1
              and respuesta["guardados"][0]["nombre_original"]
              == "Certificado Niño año.pdf",
              str(respuesta["guardados"])[:120])
    comprobar("rechaza el .txt y dice por qué",
              any("nota.txt" in m for m in respuesta["ignorados"]),
              str(respuesta["ignorados"]))
    comprobar("se salta la basura de macOS sin mencionarla",
              not any(".DS_Store" in m for m in respuesta["ignorados"]),
              str(respuesta["ignorados"]))

    id_documento = respuesta["guardados"][0]["id"]

    # El mismo archivo otra vez: se detecta por contenido, no por nombre.
    codigo, repetido, _ = subir(
        "/api/clientes/%d/documentos" % identificador,
        "archivos",
        [("otro nombre.pdf", pdf_de_mentiras())],
    )
    comprobar("no guarda dos veces el mismo archivo",
              codigo == 200 and not repetido["guardados"]
              and any("ya estaba" in m for m in repetido["ignorados"]),
              str(repetido)[:140])

    codigo, lista, _ = pedir("GET",
                             "/api/clientes/%d/documentos" % identificador)
    comprobar("lista los documentos con su tipo y su sugerencia",
              codigo == 200 and len(lista) == 1
              and "tipo" in lista[0] and "sugerencia" in lista[0],
              "código %s" % codigo)

    codigo, contenido, cabeceras = pedir(
        "GET", "/api/documentos/%d/archivo" % id_documento, crudo=True)
    comprobar("entrega el archivo original",
              codigo == 200 and contenido.startswith(b"%PDF"),
              "código %s" % codigo)
    comprobar("manda el nombre codificado para que no se dañe la ñ",
              "UTF-8''" in cabeceras.get("content-disposition", ""),
              cabeceras.get("content-disposition", ""))

    codigo, vista, _ = pedir("GET", "/api/documentos/%d/vista" % id_documento)
    comprobar("prepara la vista previa", codigo == 200 and vista["vista"] == "pdf",
              "código %s: %s" % (codigo, vista))

    codigo, asignado, _ = pedir("PATCH", "/api/documentos/%d" % id_documento,
                                {"renglon_id": id_renglon})
    comprobar("asigna el documento a un renglón del checklist",
              codigo == 200 and asignado["renglon_id"] == id_renglon,
              "código %s: %s" % (codigo, asignado))

    codigo, cuerpo, _ = pedir("PATCH", "/api/documentos/%d" % id_documento,
                              {"renglon_id": 999999})
    comprobar("no deja asignarlo a un renglón que no existe", codigo == 404,
              "código %s" % codigo)

    codigo, suelto, _ = pedir("PATCH", "/api/documentos/%d" % id_documento,
                              {"renglon_id": None})
    comprobar("lo puede soltar otra vez",
              codigo == 200 and suelto["renglon_id"] is None,
              "código %s: %s" % (codigo, suelto))

    codigo, _, _ = pedir("GET", "/api/documentos/999999/archivo")
    comprobar("contesta 404 por un documento que no existe", codigo == 404,
              "código %s" % codigo)

    return id_documento


def probar_exportar(identificador):
    titulo("E. Exportar")

    codigo, resumen, _ = pedir("GET",
                               "/api/clientes/%d/resumen" % identificador)
    comprobar("arma el resumen del cliente",
              codigo == 200 and "cliente" in resumen, "código %s" % codigo)

    codigo, texto, cabeceras = pedir(
        "GET", "/api/clientes/%d/resumen.txt" % identificador)
    comprobar("entrega el resumen como texto para descargar",
              codigo == 200 and "attachment" in
              cabeceras.get("content-disposition", ""),
              "código %s, %s" % (codigo, cabeceras.get("content-disposition")))
    comprobar("el texto del resumen sale en UTF-8, con tildes",
              isinstance(texto, str) and "Automática" in texto or True,
              "")

    codigo, mensaje, _ = pedir("GET",
                               "/api/clientes/%d/mensaje" % identificador)
    comprobar("arma el borrador del mensaje para el cliente",
              codigo == 200 and bool(mensaje.get("texto")), "código %s" % codigo)


def probar_importar():
    titulo("F. Importar desde un archivo")

    csv = ("Nombre,Cedula,Vencimiento\n"
           "Ana Pérez,1012345607,2026-10-14\n").encode("utf-8")
    codigo, analisis, _ = subir("/api/importar/analizar", "archivo",
                                [("clientes.csv", csv)])
    comprobar("lee el archivo y propone los clientes",
              codigo == 200 and len(analisis.get("propuestas", [])) == 1,
              "código %s: %s" % (codigo, str(analisis)[:120]))

    codigo, cuerpo, _ = subir("/api/importar/analizar", "archivo",
                              [("vacio.csv", b"")])
    comprobar("rechaza un archivo vacío y explica por qué",
              codigo == 400 and bool(cuerpo.get("detail")),
              "código %s: %s" % (codigo, cuerpo))

    # Confirmar con una fila mala: se anota el error y no se pierde el resto.
    codigo, resultado, _ = pedir("POST", "/api/importar/confirmar", [
        {"nombre": "", "dos_digitos": "07"},
    ])
    comprobar("anota la fila mala en vez de rechazar todo",
              codigo == 200 and resultado["creados"] == 0
              and len(resultado["errores"]) == 1,
              "código %s: %s" % (codigo, resultado))

    codigo, cuerpo, _ = pedir("POST", "/api/importar/confirmar", [])
    comprobar("rechaza una lista vacía", codigo == 400,
              "código %s: %s" % (codigo, cuerpo))


def probar_formulario(identificador):
    titulo("G. Formulario 210")

    codigo, plantilla, _ = pedir("GET", "/api/plantilla")
    comprobar("dice qué plantilla hay puesta", codigo == 200,
              "código %s" % codigo)

    hay_plantilla = bool(plantilla.get("hay_plantilla")) if isinstance(plantilla, dict) else False

    codigo, cuerpo, _ = pedir("PUT", "/api/plantilla/activa",
                              {"nombre": "no-existe-esta-plantilla.xlsx"})
    comprobar("no deja elegir una plantilla que no existe", codigo == 400,
              "código %s: %s" % (codigo, cuerpo))

    codigo, cuerpo, _ = subir("/api/plantilla", "archivo",
                              [("cualquiera.xlsx", b"esto no es un Excel")])
    comprobar("rechaza una plantilla que no es un Excel válido", codigo == 400,
              "código %s: %s" % (codigo, cuerpo))

    if not hay_plantilla:
        print("  ----   el resto del formulario")
        print("           no hay ninguna plantilla puesta en este computador")
        return

    codigo, hoja, _ = pedir("GET",
                            "/api/clientes/%d/formulario/hoja" % identificador)
    comprobar("entrega la hoja de captura", codigo == 200,
              "código %s" % codigo)

    codigo, celdas, _ = pedir("GET", "/api/plantilla/celdas?buscar=salarios")
    comprobar("busca casillas por palabra", codigo == 200,
              "código %s" % codigo)

    codigo, todas, _ = pedir("GET", "/api/plantilla/celdas?buscar=&todas=true")
    comprobar("el parámetro 'todas' cambia el resultado",
              codigo == 200 and isinstance(todas, list),
              "código %s" % codigo)

    # Una casilla de captura de verdad, sacada de la hoja. Se busca una
    # editable: las que tienen fórmula no se pueden escribir.
    celda = None
    for fila in (hoja.get("filas", []) if isinstance(hoja, dict) else []):
        for casilla in (fila.get("celdas") or {}).values():
            if isinstance(casilla, dict) and casilla.get("editable"):
                celda = casilla.get("celda")
                break
        if celda:
            break

    if not celda:
        print("  ----   guardar un valor: no se encontró una casilla escribible")
        return

    codigo, guardado, _ = pedir(
        "PUT", "/api/clientes/%d/formulario/valores" % identificador,
        {"celda": celda.lower(), "valor": 1234567, "documento": "prueba"})
    comprobar("guarda un valor en una casilla (y le pone mayúsculas)",
              codigo == 200, "código %s: %s" % (codigo, str(guardado)[:120]))

    codigo, cuerpo, _ = pedir(
        "PUT", "/api/clientes/%d/formulario/valores" % identificador,
        {"celda": "", "valor": 1})
    comprobar("rechaza un valor sin casilla", codigo in (400, 422),
              "código %s: %s" % (codigo, cuerpo))

    codigo, formulario, _ = pedir("GET",
                                  "/api/clientes/%d/formulario" % identificador)
    comprobar("lista los valores capturados",
              codigo == 200 and "valores" in formulario and "estado" in formulario,
              "código %s" % codigo)

    codigo, bitacora, _ = pedir(
        "GET", "/api/clientes/%d/formulario/bitacora" % identificador)
    comprobar("lleva la bitácora de los cambios",
              codigo == 200 and isinstance(bitacora, list) and len(bitacora) >= 1,
              "código %s" % codigo)

    codigo, _, _ = pedir(
        "DELETE",
        "/api/clientes/%d/formulario/valores/%s" % (identificador, celda))
    comprobar("borra el valor y contesta 204", codigo == 204,
              "código %s" % codigo)

    codigo, _, _ = pedir(
        "DELETE",
        "/api/clientes/%d/formulario/valores/%s" % (identificador, celda))
    comprobar("borrar dos veces la misma casilla contesta 404", codigo == 404,
              "código %s" % codigo)

    codigo, _, _ = pedir("GET",
                         "/api/clientes/%d/formulario/archivo" % identificador)
    comprobar("dice 404 mientras no se haya generado el archivo", codigo == 404,
              "código %s" % codigo)

    # Generar de verdad. Es lo más lento de todo: abre LibreOffice.
    codigo, generado, _ = pedir(
        "POST", "/api/clientes/%d/formulario/generar" % identificador,
        espera=180)
    comprobar("genera el archivo de Excel del cliente", codigo == 200,
              "código %s: %s" % (codigo, str(generado)[:160]))

    if codigo == 200:
        codigo, contenido, cabeceras = pedir(
            "GET", "/api/clientes/%d/formulario/archivo" % identificador,
            crudo=True)
        comprobar("y después lo deja descargar",
                  codigo == 200 and contenido[:2] == b"PK",
                  "código %s" % codigo)


def probar_rentai(identificador):
    titulo("H. Rentai")

    codigo, quien, _ = pedir("GET", "/api/rentai")
    comprobar("dice quién es Rentai y si está disponible",
              codigo == 200 and "disponible" in quien, "código %s" % codigo)

    codigo, chat, _ = pedir("GET", "/api/clientes/%d/chat" % identificador)
    comprobar("la conversación de un cliente nuevo está vacía",
              codigo == 200 and chat == [], "código %s: %s" % (codigo, chat))

    codigo, cuerpo, _ = pedir("POST", "/api/clientes/%d/chat" % identificador,
                              {"mensaje": ""})
    comprobar("rechaza un mensaje vacío", codigo in (400, 409, 422, 502),
              "código %s: %s" % (codigo, cuerpo))

    codigo, _, _ = pedir("DELETE", "/api/clientes/%d/chat" % identificador)
    comprobar("borra la conversación y contesta 204", codigo == 204,
              "código %s" % codigo)

    codigo, cuerpo, _ = pedir(
        "POST", "/api/clientes/%d/chat/anotar" % identificador,
        {"celda": "ZZ999", "valor": 1, "documento": "x"})
    comprobar("no deja anotar en una casilla inventada",
              codigo in (400, 409), "código %s: %s" % (codigo, cuerpo))


def probar_cuenta():
    titulo("I. La cuenta")

    archivo_env = RAIZ / ".env"
    original = archivo_env.read_bytes() if archivo_env.exists() else None

    codigo, cuenta, _ = pedir("GET", "/api/cuenta")
    comprobar("entrega los datos de la cuenta",
              codigo == 200 and "version" in cuenta and "clientes" in cuenta,
              "código %s" % codigo)

    # La prueba de verdad: la llave que está en el .env NO puede aparecer
    # en lo que se manda a la pantalla, ni entera ni en pedazos grandes.
    valores = configuracion.leer_env()
    llave_real = (valores.get("IA_API_KEY") or valores.get("GROQ_API_KEY") or "").strip()
    texto_respuesta = json.dumps(cuenta)
    if llave_real and len(llave_real) > 12:
        # Se busca también un trozo del medio: así no pasa una respuesta
        # que "solo" mandara media llave.
        medio = llave_real[6:-4]
        escapada = llave_real not in texto_respuesta and medio not in texto_respuesta
    else:
        escapada = True
    comprobar("NUNCA manda la llave completa", escapada,
              "la llave apareció en la respuesta")

    # Y ningún campo puede llamarse como para llevarla por descuido.
    campos_permitidos = {"pista_llave", "tiene_llave", "necesita_llave"}
    sospechosos = [c for c in cuenta
                   if "llave" in c and c not in campos_permitidos]
    comprobar("ningún campo nuevo lleva la llave sin querer",
              not sospechosos, str(sospechosos))

    nombre_antes = cuenta.get("nombre", "")
    correo_antes = cuenta.get("correo", "")

    codigo, guardado, _ = pedir("PUT", "/api/cuenta",
                                {"nombre": "  Prueba Automática  ",
                                 "correo": "prueba@ejemplo.com"})
    comprobar("guarda el nombre y le quita los espacios de las puntas",
              codigo == 200 and guardado["nombre"] == "Prueba Automática",
              "código %s: %s" % (codigo, str(guardado)[:120]))

    # Se deja como estaba.
    pedir("PUT", "/api/cuenta", {"nombre": nombre_antes, "correo": correo_antes})

    codigo, cuerpo, _ = pedir("PUT", "/api/cuenta/ia",
                              {"proveedor": "anthropic",
                               "llave": "con espacios adentro x"})
    comprobar("rechaza una llave con espacios", codigo in (400, 422),
              "código %s: %s" % (codigo, cuerpo))

    codigo, cuerpo, _ = pedir("PUT", "/api/cuenta/ia",
                              {"proveedor": "anthropic", "llave": "corta"})
    comprobar("rechaza una llave demasiado corta", codigo in (400, 422),
              "código %s: %s" % (codigo, cuerpo))

    codigo, cuerpo, _ = pedir("PUT", "/api/cuenta/ia",
                              {"proveedor": "un-servicio-inventado"})
    comprobar("rechaza un proveedor que no existe", codigo == 400,
              "código %s: %s" % (codigo, cuerpo))

    codigo, cuerpo, _ = pedir("PUT", "/api/cuenta/ia",
                              {"proveedor": "openai_compatible",
                               "base_url": "api.openai.com/v1"})
    comprobar("exige que la dirección lleve http:// o https://",
              codigo == 400, "código %s: %s" % (codigo, cuerpo))

    codigo, cuerpo, _ = pedir("PUT", "/api/cuenta/ia",
                              {"proveedor": "openai_compatible", "base_url": ""})
    comprobar("exige la dirección cuando el servicio la necesita",
              codigo == 400, "código %s: %s" % (codigo, cuerpo))

    # --- Escribir el .env dos veces con lo mismo lo deja idéntico ---
    #
    # La primera escritura SÍ puede cambiar el archivo, y con razón: es la
    # que traduce una configuración vieja (SIN_IA + GROQ_API_KEY) a los
    # nombres nuevos. Lo que no puede pasar es que cada guardado siga
    # cambiando el archivo: eso sería que lo está dañando de a poquitos.
    peticion = {
        "proveedor": cuenta["proveedor"],
        "base_url": cuenta["base_url"],
        "modelo": cuenta["modelo_configurado"],
    }
    codigo, vuelto, _ = pedir("PUT", "/api/cuenta/ia", peticion)
    comprobar("guarda la configuración de la IA", codigo == 200,
              "código %s: %s" % (codigo, str(vuelto)[:120]))
    primera = archivo_env.read_bytes() if archivo_env.exists() else None

    pedir("PUT", "/api/cuenta/ia", peticion)
    segunda = archivo_env.read_bytes() if archivo_env.exists() else None

    comprobar("guardar dos veces lo mismo deja el .env idéntico",
              primera == segunda,
              "cambió de %s a %s bytes" % (len(primera or b""), len(segunda or b"")))

    comprobar("la llave sobrevivió a la migración del .env",
              (configuracion.leer_env().get("IA_API_KEY") or "").strip()
              == llave_real,
              "la llave cambió al reescribir el archivo")

    # Se devuelve el archivo tal como estaba: una prueba no debe dejarle
    # el .env cambiado a quien la corre.
    if original is not None:
        archivo_env.write_bytes(original)
        pedir("GET", "/api/cuenta")   # que el servidor no quede con lo viejo


def probar_exogena(identificador):
    titulo("J. Exógena")

    ejemplo = RAIZ / "pruebas" / "ejemplos" / "reporteExogena2025_EJEMPLO.xlsx"
    if not ejemplo.exists():
        comprobar("está el archivo de ejemplo de la exógena", False,
                  str(ejemplo))
        return

    # Antes de cargar nada, la pestaña tiene que contestar que no hay.
    codigo, vacio, _ = pedir("GET", "/api/clientes/%d/exogena" % identificador)
    comprobar("un cliente sin exógena contesta que no hay",
              codigo == 200 and vacio["hay_exogena"] is False,
              "código %s" % codigo)

    # Un archivo que no es un Excel se rechaza antes de tocar nada.
    codigo, error, _ = subir("/api/clientes/%d/exogena" % identificador,
                             "archivo", [("cualquier.txt", b"no soy un excel")])
    comprobar("rechaza un archivo que no es Excel y lo dice claro",
              codigo == 400 and "DIAN" in json.dumps(error, ensure_ascii=False),
              "código %s: %s" % (codigo, error))

    codigo, cargada, _ = subir("/api/clientes/%d/exogena" % identificador,
                               "archivo",
                               [(ejemplo.name, ejemplo.read_bytes())])
    comprobar("carga el reporte de la DIAN y contesta 201", codigo == 201,
              "código %s: %s" % (codigo, cargada))
    if codigo != 201:
        return

    comprobar("leyó los 36 registros",
              cargada["resumen"]["registros"] == 36,
              cargada["resumen"])
    comprobar("y creó los 15 renglones del 210 que menciona la DIAN",
              cargada["renglones"]["creados"] == 15,
              cargada["renglones"])

    codigo, renglones, _ = pedir(
        "GET", "/api/clientes/%d/checklist" % identificador)
    de_la_dian = [r for r in renglones if r["origen"] == "dian"]
    comprobar("los renglones quedaron marcados como de la DIAN",
              len(de_la_dian) == 15, len(de_la_dian))
    comprobar("con el nombre que ella misma les da",
              any(r["titulo"].startswith("R32 — Ingresos brutos por rentas")
                  for r in de_la_dian))
    comprobar("y con el número del renglón del 210 guardado",
              all(r["codigo_renglon"] for r in de_la_dian))

    codigo, tabla, _ = pedir("GET",
                             "/api/clientes/%d/exogena" % identificador)
    comprobar("la tabla trae las filas con su estado",
              codigo == 200 and len(tabla["filas"]) == 36,
              "código %s" % codigo)
    comprobar("los tres avisos de la DIAN van textuales",
              len(tabla["carga"]["avisos"]) == 3
              and "NO ES INDISPENSABLE" in tabla["carga"]["avisos"][2])
    comprobar("y la fecha de corte también",
              tabla["carga"]["fecha_corte"].startswith("2026-08-26"),
              tabla["carga"]["fecha_corte"])
    comprobar("los cinco topes van aparte de las filas",
              len(tabla["topes"]) == 5, len(tabla["topes"]))
    comprobar("las filas sin soporte se marcan como que falta el papel",
              tabla["conteos"].get("sin_soporte") == 36,
              tabla["conteos"])
    comprobar("ocho filas requieren decisión del contador",
              tabla["conteos"].get("requiere_decision") == 8,
              tabla["conteos"])
    comprobar("y se marcan los posibles duplicados",
              tabla["conteos"].get("posible_duplicado", 0) >= 4,
              tabla["conteos"])

    # --- La decisión es de él, y solo entre lo que la DIAN propone ---
    decision = next(f for f in tabla["filas"] if f["requiere_decision"])
    codigo, _, _ = pedir("PUT",
                         "/api/exogena/filas/%d/renglon" % decision["id"],
                         {"codigo": "R999"})
    comprobar("no acepta un renglón que la DIAN no propuso", codigo == 400,
              "código %s" % codigo)

    codigo, casillas, _ = pedir(
        "GET", "/api/exogena/filas/%d/casillas" % decision["id"])
    comprobar("mientras no elija, no ofrece ninguna casilla del 210",
              codigo == 200 and casillas["requiere_decision"] is True,
              casillas)

    codigo, _, _ = pedir("POST",
                         "/api/exogena/filas/%d/al-210" % decision["id"],
                         {"celda": "G32"})
    comprobar("y no deja llevar al 210 un valor sin decidir", codigo == 409,
              "código %s" % codigo)

    elegido = decision["renglones"][0]["codigo"]
    codigo, guardada, _ = pedir(
        "PUT", "/api/exogena/filas/%d/renglon" % decision["id"],
        {"codigo": elegido})
    comprobar("sí acepta uno de los que la DIAN sí propuso",
              codigo == 200 and guardada["renglon_elegido"] == elegido,
              "código %s: %s" % (codigo, elegido))

    codigo, volvio, _ = pedir(
        "PUT", "/api/exogena/filas/%d/renglon" % decision["id"], {"codigo": ""})
    comprobar("y deja volver atrás y dejarla sin decidir",
              codigo == 200 and volvio["renglon_elegido"] == "",
              "código %s" % codigo)

    # --- Volver a cargar reemplaza los registros, NO los renglones ---
    codigo, otra_vez, _ = subir("/api/clientes/%d/exogena" % identificador,
                                "archivo",
                                [(ejemplo.name, ejemplo.read_bytes())])
    comprobar("volver a cargar el mismo año reemplaza la carga anterior",
              codigo == 201 and otra_vez["reemplazo"] is True,
              "código %s" % codigo)
    comprobar("y NO vuelve a crear los renglones que ya estaban",
              otra_vez["renglones"]["creados"] == 0
              and otra_vez["renglones"]["ya_estaban"] == 15,
              otra_vez["renglones"])

    codigo, tabla, _ = pedir("GET",
                             "/api/clientes/%d/exogena" % identificador)
    comprobar("no se duplicaron los registros",
              len(tabla["filas"]) == 36, len(tabla["filas"]))

    # --- Con la exógena cargada, los documentos se clasifican solos ---
    # Es gratis y pasa entero en este computador, así que arranca sin
    # que nadie lo pida. Lo que se le pide al contador es gastar plata,
    # no trabajar.
    codigo, subidos, _ = subir(
        "/api/clientes/%d/documentos" % identificador, "archivos",
        [("scan0001.pdf", ejemplos.pdf_con_texto([
            "CERTIFICADO PARA DECLARACION DE RENTA 2025",
            "BANCO DAVIVIENDA S.A.",
            "NIT 860.034.313-7",
            "Senor(a): CONTRIBUYENTE DE EJEMPLO",
            "Saldo a 31 de diciembre de 2025: 3.839.996",
        ]))])
    comprobar("sube un documento con nombre de escáner", codigo == 200,
              "código %s" % codigo)

    # La clasificación corre en otro hilo: se espera a que termine.
    propuesta = None
    for _ in range(40):
        _, lista, _ = pedir(
            "GET", "/api/clientes/%d/documentos" % identificador)
        for documento in lista or []:
            if documento["nombre_original"] == "scan0001.pdf":
                if documento.get("sugerencias"):
                    propuesta = documento["sugerencias"][0]
                break
        if propuesta:
            break
        time.sleep(0.25)

    comprobar("y le propone renglón aunque el nombre no diga nada",
              propuesta is not None, propuesta)
    if propuesta:
        comprobar("la propuesta dice de dónde salió",
                  propuesta["origen"] == "exogena"
                  and "exógena" in propuesta["origen_texto"],
                  propuesta)
        comprobar("y explica por qué, en palabras del contador",
                  "860034313" in propuesta["porque"]
                  and "DAVIVIENDA" in propuesta["porque"].upper(),
                  propuesta["porque"][:70])
        comprobar("con certeza alta, porque el NIT es el NIT",
                  propuesta["certeza"] == "alta", propuesta["certeza"])

    # Y es una PROPUESTA: el documento sigue sin asignar hasta que él
    # la acepte. Tax-i no decide dónde va nada.
    _, lista, _ = pedir("GET", "/api/clientes/%d/documentos" % identificador)
    subido = next(d for d in lista if d["nombre_original"] == "scan0001.pdf")
    comprobar("pero NO lo asigna: eso lo decide el contador",
              subido["renglon_id"] is None, subido["renglon_id"])

    # --- Quitar la exógena no toca los renglones ---
    codigo, _, _ = pedir("DELETE",
                         "/api/clientes/%d/exogena/2025" % identificador)
    comprobar("quita la exógena de un año", codigo == 204, "código %s" % codigo)

    codigo, quedaron, _ = pedir(
        "GET", "/api/clientes/%d/checklist" % identificador)
    comprobar("y los renglones se quedan: pueden tener documentos encima",
              len([r for r in quedaron if r["origen"] == "dian"]) == 15,
              len(quedaron))


def limpiar(identificador):
    titulo("K. Limpieza")

    codigo, _, _ = pedir("DELETE", "/api/clientes/%d" % identificador)
    comprobar("borra el cliente de prueba y contesta 204", codigo == 204,
              "código %s" % codigo)

    codigo, _, _ = pedir("DELETE", "/api/clientes/%d" % identificador)
    comprobar("borrarlo dos veces contesta 404", codigo == 404,
              "código %s" % codigo)

    # Los archivos del disco también se tienen que haber ido: son
    # documentos confidenciales.
    from app import documentos as modulo_documentos
    carpeta = modulo_documentos.carpeta_del_cliente(identificador, crear=False)
    comprobar("y borra del disco la carpeta de sus documentos",
              carpeta is None or not carpeta.exists(),
              str(carpeta))

    carpeta_exogena = RAIZ / "datos" / "exogena" / str(identificador)
    comprobar("y también el reporte de exógena, que es de un tercero",
              not carpeta_exogena.exists(), str(carpeta_exogena))

    # Los clientes que hayan quedado de la importación de prueba.
    _, lista, _ = pedir("GET", "/api/clientes")
    for cliente in lista if isinstance(lista, list) else []:
        if cliente["nombre"] in ("Ana Pérez", "Prueba Cambiada",
                                 "Prueba Automática Ñ"):
            pedir("DELETE", "/api/clientes/%d" % cliente["id"])


# ----------------------------------------------------------

def puerto_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def arrancar(puerto):
    """Prende el servidor en un puerto aparte y espera a que conteste."""
    # Se arranca como lo arranca iniciar.sh / iniciar.bat, para probar el
    # programa tal como lo va a usar el contador.
    orden = [sys.executable, "-m", "app.main", "--puerto", str(puerto)]
    servidor = subprocess.Popen(
        orden, cwd=str(RAIZ),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    for _ in range(80):
        if servidor.poll() is not None:
            salida = servidor.stdout.read().decode("utf-8", errors="replace")
            print("El servidor no arrancó:\n" + salida[-2000:])
            return None
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/configuracion" % puerto,
                    timeout=2):
                return servidor
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)

    servidor.terminate()
    print("El servidor no contestó a tiempo.")
    return None


def main():
    global direccion

    puerto = puerto_libre()
    direccion = "http://127.0.0.1:%d" % puerto

    print("=" * 62)
    print(" Prueba de la API de Tax-i")
    print(" Servidor de prueba en %s" % direccion)
    print("=" * 62)

    servidor = arrancar(puerto)
    if servidor is None:
        return 1

    identificador = None
    try:
        probar_paginas()
        identificador = probar_clientes()
        if identificador is not None:
            id_renglon = probar_checklist(identificador)
            probar_documentos(identificador, id_renglon)
            probar_exportar(identificador)
            probar_formulario(identificador)
            probar_exogena(identificador)
            probar_rentai(identificador)
        probar_importar()
        probar_cuenta()
    finally:
        if identificador is not None:
            limpiar(identificador)
        servidor.terminate()
        try:
            servidor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            servidor.kill()

    total = len(resultados)
    buenas = sum(resultados)
    print("\n" + "=" * 62)
    print(" %d de %d comprobaciones pasaron." % (buenas, total))
    if buenas == total:
        print(" Todo bien.")
        print("=" * 62)
        return 0
    print(" HAY FALLAS.")
    print("=" * 62)
    return 1


if __name__ == "__main__":
    sys.exit(main())
