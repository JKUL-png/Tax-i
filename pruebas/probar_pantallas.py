"""
Abre las pantallas en un navegador de verdad y revisa que no fallen.

Para qué sirve
--------------
Las pruebas de probar_api.py comprueban el servidor. Esta comprueba el
navegador: que el JavaScript no reviente, que los botones existan y que
la zona de revisión haga lo que promete.

Un error de JavaScript no se nota desde el servidor. La página carga con
código 200 y se ve casi bien, pero el botón no hace nada. Esto lo caza.

Cómo se corre
-------------
    .venv/bin/python -m pip install -r requirements-dev.txt
    .venv/bin/python -m playwright install chromium
    .venv/bin/python pruebas/probar_pantallas.py

Los datos: se crea un cliente de prueba, se usa y se borra al final.
Nunca toca clientes de verdad.
"""

import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

DIRECCION = "http://127.0.0.1:8899"
PUERTO = 8899

# Un nombre que nadie usaría de verdad, para no confundirlo con un
# cliente del contador si algo saliera mal y quedara en la base.
CLIENTE_DE_PRUEBA = "ZZ Prueba de pantallas — borrar"

bien = 0
mal = 0


def revisar(descripcion, condicion, detalle=""):
    global bien, mal
    if condicion:
        bien += 1
        print("  OK     " + descripcion)
    else:
        mal += 1
        print("  FALLA  " + descripcion)
        if detalle:
            print("           " + str(detalle))


def titulo(texto):
    print("\n" + texto)
    print("-" * len(texto))


# ----------------------------------------------------------
# Arrancar y apagar el servidor
# ----------------------------------------------------------


def arrancar_servidor():
    proceso = subprocess.Popen(
        [sys.executable, "-c",
         "from app.main import app; from app import db;"
         " db.crear_tablas();"
         " app.arrancar(puerto=%d)" % PUERTO],
        cwd=str(RAIZ),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    for _ in range(60):
        try:
            urllib.request.urlopen(DIRECCION + "/api/clientes", timeout=1)
            return proceso
        except urllib.error.HTTPError:
            return proceso
        except Exception:
            time.sleep(0.25)
    proceso.terminate()
    raise SystemExit("El servidor no arrancó.")


def pedir(camino, metodo="GET", cuerpo=None):
    import json
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    peticion = urllib.request.Request(
        DIRECCION + camino, data=datos, method=metodo,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(peticion, timeout=20) as r:
        crudo = r.read().decode("utf-8")
        return json.loads(crudo) if crudo else None


# ----------------------------------------------------------
# La prueba
# ----------------------------------------------------------


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Falta playwright. Instálelo con:")
        print("  .venv/bin/python -m pip install -r requirements-dev.txt")
        print("  .venv/bin/python -m playwright install chromium")
        return 0

    print("=" * 62)
    print(" Revisión de las pantallas en un navegador de verdad")
    print("=" * 62)

    servidor = arrancar_servidor()
    id_cliente = None

    try:
        cliente = pedir("/api/clientes", "POST", {
            "nombre": CLIENTE_DE_PRUEBA,
            "dos_digitos": "99",
            "fecha_vencimiento": "2026-12-15",
        })
        id_cliente = cliente["id"]

        with sync_playwright() as p:
            navegador = p.chromium.launch()
            pagina = navegador.new_page()

            # Cualquier error de JavaScript se guarda para revisarlo.
            errores = []
            pagina.on("pageerror", lambda e: errores.append(str(e)))
            pagina.on("console", lambda m: (
                errores.append(m.text) if m.type == "error" else None
            ))

            # ---------- La lista de clientes ----------
            titulo("A. La lista de clientes")
            pagina.goto(DIRECCION + "/", wait_until="networkidle")
            revisar("abre sin errores de JavaScript", not errores, errores[:3])
            revisar("muestra el cliente de prueba",
                    pagina.locator("text=" + CLIENTE_DE_PRUEBA).count() > 0)
            revisar("tiene el buscador",
                    pagina.locator("#buscar-cliente").count() == 1)
            revisar("tiene el selector de orden",
                    pagina.locator("#orden-clientes").count() == 1)
            revisar("tiene los filtros de estado",
                    pagina.locator("#filtro-estado").count() == 1)

            errores.clear()

            # ---------- El perfil del cliente ----------
            titulo("B. El perfil del cliente")
            pagina.goto(DIRECCION + "/cliente?id=" + str(id_cliente),
                        wait_until="networkidle")
            revisar("abre sin errores de JavaScript", not errores, errores[:3])
            revisar("muestra el nombre",
                    CLIENTE_DE_PRUEBA in pagina.locator("#nombre-cliente").inner_text())
            revisar("dice cuántos días faltan",
                    "alta" in pagina.locator("#perfil-plazo").inner_text().lower()
                    or "Faltan" in pagina.locator("#perfil-plazo").inner_text()
                    or "Venció" in pagina.locator("#perfil-plazo").inner_text())
            revisar("muestra la fecha en palabras",
                    "diciembre" in pagina.locator("#perfil-fecha").inner_text())
            revisar("muestra el avance del checklist",
                    "/" in pagina.locator("#perfil-avance").inner_text())
            revisar("muestra cuántos documentos hay",
                    pagina.locator("#perfil-documentos").inner_text().strip() == "0")
            revisar("destaca lo que falta",
                    pagina.locator("#perfil-pendientes").is_visible())
            revisar("tiene el historial de actividad",
                    pagina.locator("#lista-actividad .actividad").count() > 0)
            # text_content y no inner_text: la sección del historial viene
            # plegada, y inner_text solo devuelve lo que está a la vista.
            # Aquí se está comprobando el dato, no si se ve.
            revisar("el historial dice que se creó el cliente",
                    "creó el cliente" in
                    pagina.locator("#lista-actividad").text_content())

            errores.clear()

            # ---------- La zona de revisión ----------
            titulo("C. Confirmación antes de subir")
            pagina.locator("#plegable-subir").evaluate("e => e.open = true")

            revisar("la zona de revisión empieza escondida",
                    not pagina.locator("#revision-carga").is_visible())

            # Se sueltan dos archivos en el campo, como si se arrastraran.
            pagina.locator("#campo-archivos").set_input_files([
                {"name": "certificado.pdf", "mimeType": "application/pdf",
                 "buffer": b"%PDF-1.4 uno"},
                {"name": "banco.pdf", "mimeType": "application/pdf",
                 "buffer": b"%PDF-1.4 dos"},
            ])
            pagina.wait_for_timeout(300)

            revisar("los archivos entran a la zona de revisión",
                    pagina.locator("#revision-carga").is_visible())
            revisar("se ven los dos, con su nombre",
                    pagina.locator("#revision-lista .revision-renglon").count() == 2)
            revisar("se ve el tamaño de cada uno",
                    "B" in pagina.locator("#revision-lista .documento-detalle")
                                 .first.inner_text())

            # Nada se subió todavía: eso es lo importante.
            documentos = pedir("/api/clientes/%d/documentos" % id_cliente)
            revisar("NO se subió nada todavía", len(documentos) == 0,
                    "había %d documentos" % len(documentos))

            # Quitar uno con su casilla
            pagina.locator("#revision-lista .documento-casilla").first.check()
            pagina.wait_for_timeout(150)
            revisar("marcar habilita el botón de quitar",
                    not pagina.locator("#revision-quitar-marcados").is_disabled())
            pagina.locator("#revision-quitar-marcados").click()
            pagina.wait_for_timeout(200)
            revisar("quitar los marcados deja solo uno",
                    pagina.locator("#revision-lista .revision-renglon").count() == 1)

            # Confirmar la carga: ahora sí sube
            pagina.locator("#revision-confirmar").click()
            pagina.wait_for_timeout(1200)

            documentos = pedir("/api/clientes/%d/documentos" % id_cliente)
            revisar("al confirmar, el documento sí entra", len(documentos) == 1,
                    "quedaron %d" % len(documentos))
            revisar("la zona de revisión queda vacía",
                    not pagina.locator("#revision-carga").is_visible())
            revisar("sin errores de JavaScript en todo el paso",
                    not errores, errores[:3])

            errores.clear()

            # ---------- Quitar todos ----------
            titulo("D. El botón de quitar todos")
            pagina.locator("#campo-archivos").set_input_files([
                {"name": "uno.pdf", "mimeType": "application/pdf",
                 "buffer": b"%PDF-1.4 tres"},
                {"name": "dos.pdf", "mimeType": "application/pdf",
                 "buffer": b"%PDF-1.4 cuatro"},
                {"name": "tres.pdf", "mimeType": "application/pdf",
                 "buffer": b"%PDF-1.4 cinco"},
            ])
            pagina.wait_for_timeout(300)
            revisar("entran los tres",
                    pagina.locator("#revision-lista .revision-renglon").count() == 3)
            pagina.locator("#revision-quitar-todos").click()
            pagina.wait_for_timeout(200)
            revisar("quitar todos vacía la zona de un golpe",
                    not pagina.locator("#revision-carga").is_visible())
            documentos = pedir("/api/clientes/%d/documentos" % id_cliente)
            revisar("y no subió ninguno", len(documentos) == 1)

            errores.clear()

            # ---------- Borrado en lote con confirmación ----------
            titulo("E. Borrar documentos ya confirmados")
            pagina.reload(wait_until="networkidle")
            pagina.locator("#plegable-documentos").evaluate("e => e.open = true")
            pagina.wait_for_timeout(400)

            revisar("cada documento tiene su casilla",
                    pagina.locator("#lista-documentos .documento-casilla").count() == 1)
            pagina.locator("#documentos-todos").check()
            pagina.wait_for_timeout(200)
            revisar("marcar todos habilita el botón de eliminar",
                    not pagina.locator("#documentos-eliminar").is_disabled())

            pagina.locator("#documentos-eliminar").click()
            pagina.wait_for_timeout(300)

            revisar("pregunta antes de borrar",
                    pagina.locator("#confirmar").is_visible())
            frase = pagina.locator("#confirmar-frase").inner_text()
            revisar("la pregunta dice CUÁNTOS archivos", "1 archivo" in frase, frase)
            quien = pagina.locator("#confirmar-cliente").inner_text()
            revisar("la pregunta dice DE QUÉ CLIENTE",
                    CLIENTE_DE_PRUEBA in quien, quien)
            revisar("la pregunta nombra el archivo",
                    pagina.locator("#confirmar-lista li").count() == 1)

            # Cancelar no borra nada
            pagina.locator("#confirmar-no").click()
            pagina.wait_for_timeout(300)
            documentos = pedir("/api/clientes/%d/documentos" % id_cliente)
            revisar("cancelar no borra nada", len(documentos) == 1)

            # Ahora sí
            pagina.locator("#documentos-eliminar").click()
            pagina.wait_for_timeout(300)
            pagina.locator("#confirmar-si").click()
            pagina.wait_for_timeout(900)

            documentos = pedir("/api/clientes/%d/documentos" % id_cliente)
            revisar("confirmar sí borra", len(documentos) == 0)

            bitacora = pedir("/api/clientes/%d/bitacora" % id_cliente)
            acciones = [a["accion"] for a in bitacora]
            revisar("el borrado quedó en la bitácora",
                    "documentos_borrados" in acciones, acciones)
            revisar("la subida también quedó en la bitácora",
                    "documentos_subidos" in acciones, acciones)

            papelera = RAIZ / "datos" / "papelera" / str(id_cliente)
            revisar("el archivo está en la papelera, no destruido",
                    papelera.exists() and any(papelera.iterdir()))

            revisar("sin errores de JavaScript en todo el paso",
                    not errores, errores[:3])

            errores.clear()

            # ---------- La pantalla de cuenta ----------
            titulo("F. La pantalla de Cuenta")
            pagina.goto(DIRECCION + "/cuenta", wait_until="networkidle")
            revisar("abre sin errores de JavaScript", not errores, errores[:3])
            revisar("deja elegir el proveedor de IA",
                    pagina.locator("#ia-proveedor").count() == 1)
            revisar("tiene el botón de probar la conexión",
                    pagina.locator("#boton-probar").count() == 1)

            navegador.close()

    finally:
        if id_cliente is not None:
            try:
                pedir("/api/clientes/%d" % id_cliente, "DELETE")
            except Exception:
                pass
        servidor.terminate()
        servidor.wait(timeout=10)

    print()
    print("=" * 62)
    print(" %d de %d comprobaciones pasaron." % (bien, bien + mal))
    print(" Todo bien." if mal == 0 else " HAY FALLAS.")
    print("=" * 62)
    return 1 if mal else 0


if __name__ == "__main__":
    sys.exit(main())
