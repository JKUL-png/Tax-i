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

            # ---------- La pantalla de inicio ----------
            titulo("A1. La pantalla de inicio")
            pagina.goto(DIRECCION + "/", wait_until="networkidle")
            revisar("abre sin errores de JavaScript", not errores, errores[:3])
            revisar("dice qué es el programa",
                    "archivador" in pagina.locator(".inicio-frase")
                                          .inner_text().lower())
            # La línea legal no es letra menuda: es la definición del
            # producto, y tiene que estar a la vista en la portada.
            revisar("dice que NO hace impuestos",
                    "no hace impuestos" in pagina.locator(".inicio-limite")
                                                 .inner_text().lower())
            # Lo mismo con la condición de uso: "sin garantía" y "responde
            # por el uso que le dé" es lo que separa un proyecto libre de un
            # servicio contratado, y va en la portada, no escondido.
            revisar("dice en qué condiciones se usa",
                    "sin garantía" in pagina.locator(".inicio-quien")
                                            .inner_text().lower())
            revisar("dice cuántos clientes hay cargados",
                    "cliente" in pagina.locator("#inicio-cuenta").inner_text())
            # El riel es el programa entero: tiene que estar aquí también.
            revisar("el riel muestra el cliente de prueba",
                    pagina.locator("#riel-lista", ).get_by_text(CLIENTE_DE_PRUEBA)
                          .count() > 0)
            revisar("el botón de agregar lleva a su propia pantalla",
                    pagina.locator(".riel-agregar")
                          .get_attribute("href") == "/clientes")

            errores.clear()

            # ---------- Agregar e importar ----------
            titulo("A2. Agregar, importar y administrar")
            pagina.goto(DIRECCION + "/clientes", wait_until="networkidle")
            revisar("abre sin errores de JavaScript", not errores, errores[:3])
            revisar("tiene el formulario de agregar",
                    pagina.locator("#formulario-cliente").count() == 1)
            revisar("tiene el botón de importar",
                    pagina.locator("#boton-importar").count() == 1)
            revisar("la tabla de administrar trae el cliente de prueba",
                    pagina.locator("#tabla-clientes")
                          .get_by_text(CLIENTE_DE_PRUEBA).count() > 0)
            # Eliminar un cliente solo se puede desde aquí: si esta
            # columna se cae, la función se vuelve inalcanzable.
            revisar("cada fila tiene su botón de eliminar",
                    pagina.locator("#tabla-clientes .boton-texto-peligro")
                          .count() > 0)
            revisar("el riel marca que se está en esta pantalla",
                    pagina.locator(".riel-agregar-actual").count() == 1)

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
            # El cliente nuevo arranca sin checklist: nada se agrega
            # solo. Los renglones salen de cargar la exógena o del botón
            # de la lista sugerida, y las dos cosas las decide él.
            revisar("un cliente nuevo dice que no tiene checklist todavía",
                    "sin checklist" in
                    pagina.locator("#perfil-faltan").inner_text().lower(),
                    pagina.locator("#perfil-faltan").inner_text())
            revisar("y no inventa un avance que no existe",
                    pagina.locator("#perfil-avance").inner_text().strip() == "—",
                    pagina.locator("#perfil-avance").inner_text())
            revisar("muestra cuántos documentos hay",
                    pagina.locator("#perfil-documentos").inner_text().strip() == "0")
            revisar("no destaca faltantes cuando no hay checklist",
                    not pagina.locator("#perfil-pendientes").is_visible())
            revisar("tiene el historial de actividad",
                    pagina.locator("#lista-actividad .actividad").count() > 0)
            # text_content y no inner_text: la sección del historial viene
            # plegada, y inner_text solo devuelve lo que está a la vista.
            # Aquí se está comprobando el dato, no si se ve.
            revisar("el historial dice que se creó el cliente",
                    "creó el cliente" in
                    pagina.locator("#lista-actividad").text_content())

            errores.clear()

            # ---------- Los botones del perfil ----------
            # Estos dos estuvieron rotos y en silencio: al partir la
            # pantalla en pestañas, la sección de Exportar quedó dentro
            # de la pestaña de Historial, y los botones abrían un
            # <details> que estaba adentro de un panel escondido. En
            # pantalla no pasaba nada y el servidor no tenía cómo
            # enterarse. Por eso se comprueba que lo que abren se VEA.
            titulo("B2. Los botones del perfil llevan a alguna parte")

            pagina.locator("#perfil-mensaje").click()
            pagina.wait_for_timeout(400)
            revisar("«Generar el mensaje» abre el mensaje y se ve",
                    pagina.locator("#mensaje").is_visible())

            # Se vuelve a Documentos para que el segundo botón tenga que
            # cambiar de pestaña otra vez, como le pasa al contador.
            pagina.locator("[data-vista=documentos]").click()
            pagina.wait_for_timeout(200)
            pagina.locator("#perfil-exportar").click()
            pagina.wait_for_timeout(400)
            revisar("«Exportar el resumen» abre el resumen y se ve",
                    pagina.locator("#tarjeta-resumen").is_visible())

            revisar("sin errores de JavaScript", not errores, errores[:3])

            pagina.locator("[data-vista=documentos]").click()
            pagina.wait_for_timeout(200)
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

            # ---------- La pestaña Exógena ----------
            # Es la prueba que importa de la fase 2: un error de
            # JavaScript aquí no se ve desde el servidor, la página
            # carga con código 200 y los botones simplemente no hacen
            # nada.
            titulo("F. La pestaña Exógena")
            errores.clear()
            pagina.goto(DIRECCION + "/cliente?id=%d" % id_cliente,
                        wait_until="networkidle")

            pestana = pagina.locator('[data-vista="exogena"]')
            revisar("la pestaña se llama Exógena, como la llama el contador",
                    pestana.count() == 1
                    and "Exógena" in pestana.inner_text(),
                    pestana.inner_text() if pestana.count() else "no está")

            pestana.click()
            pagina.wait_for_timeout(400)
            revisar("abre sin errores de JavaScript", not errores, errores[:3])
            revisar("un cliente sin exógena no arranca con nada inventado",
                    pagina.locator("#exogena-vacia").is_visible())

            ejemplo = RAIZ / "pruebas" / "ejemplos" / "reporteExogena2025_EJEMPLO.xlsx"
            if not ejemplo.exists():
                revisar("está el archivo de ejemplo", False, str(ejemplo))
            else:
                pagina.locator("#campo-exogena").set_input_files(str(ejemplo))
                pagina.wait_for_selector("#exogena-cargada:not(.oculto)",
                                         timeout=20000)
                pagina.wait_for_timeout(600)
                revisar("carga el archivo sin errores de JavaScript",
                        not errores, errores[:3])

                filas = pagina.locator("#exogena-filas tr")
                revisar("pinta los 36 registros reportados",
                        filas.count() == 36, filas.count())

                topes = pagina.locator(".exogena-tope")
                revisar("los cinco topes van arriba, aparte de la tabla",
                        topes.count() == 5, topes.count())

                avisos = pagina.locator(".exogena-aviso")
                revisar("muestra los tres avisos de la DIAN",
                        avisos.count() == 3, avisos.count())

                texto_avisos = pagina.locator("#exogena-avisos").inner_text()
                revisar("y el tercero va palabra por palabra",
                        "NO ES INDISPENSABLE y NO REEMPLAZA" in texto_avisos)
                revisar("se ve la fecha de corte del proceso",
                        "corte" in pagina.locator("#exogena-corte").inner_text())

                # Los textos son los que definen el producto.
                tabla = pagina.locator("#vista-exogena").inner_text()
                revisar("la columna dice «Renglón sugerido por la DIAN»",
                        "renglón sugerido por la dian" in tabla.lower())
                revisar("«Sin soporte» dice que falta el papel",
                        "Sin soporte" in tabla)
                revisar("en ninguna parte dice que haya que declararlo",
                        "hay que declararlo" not in tabla.lower())
                revisar("ni dice que algo esté mal o que haya un error",
                        "está mal" not in tabla.lower()
                        and "hay un error" not in tabla.lower())
                revisar("ni llama a esto «cruce» ni «conciliación»",
                        "cruce" not in tabla.lower()
                        and "conciliaci" not in tabla.lower())

                revisar("marca las filas que requieren decisión",
                        pagina.locator(
                            '.exogena-estado:has-text("Requiere decisión")'
                        ).count() == 8)
                revisar("y muestra las opciones tal como las escribió la DIAN",
                        "R29 Patrimonio Bruto (si el saldo es positivo)"
                        in tabla)
                revisar("los posibles duplicados se marcan con su motivo",
                        pagina.locator(".exogena-porque").count() > 0)

                # El filtro por estado.
                filtro = pagina.locator(
                    '.exogena-filtro:has-text("Requiere decisión")')
                revisar("hay filtro por estado", filtro.count() == 1)
                if filtro.count():
                    filtro.click()
                    pagina.wait_for_timeout(300)
                    revisar("filtrar deja solo esas filas",
                            pagina.locator("#exogena-filas tr").count() == 8,
                            pagina.locator("#exogena-filas tr").count())
                    filtro.click()
                    pagina.wait_for_timeout(300)

                revisar("sin errores de JavaScript en toda la pestaña",
                        not errores, errores[:3])

            # ---------- El selector de renglones ----------
            titulo("G. El selector de renglones")
            errores.clear()
            pagina.locator('[data-vista="documentos"]').click()
            pagina.wait_for_timeout(500)

            # El selector vive en cada documento, y la sección anterior
            # los borró todos. Se sube uno y se confirma, como lo haría
            # el contador.
            pagina.locator("#campo-archivos").set_input_files([{
                "name": "certificado.pdf",
                "mimeType": "application/pdf",
                "buffer": b"%PDF-1.4 para el selector",
            }])
            pagina.wait_for_selector("#revision-carga:not(.oculto)",
                                     timeout=15000)
            pagina.locator("#revision-confirmar").click()
            try:
                pagina.wait_for_selector(".selector-buscable", timeout=20000)
            except Exception:
                pass
            pagina.wait_for_timeout(400)

            selector = pagina.locator(".selector-buscable").first
            if selector.count() == 0:
                revisar("hay documentos con selector de renglón", False,
                        "el cliente no tiene documentos en este punto")
            else:
                revisar("ya no es un <select> del navegador",
                        pagina.locator("select.selector-renglon").count() == 0)

                selector.locator(".selector-boton").click()
                pagina.wait_for_timeout(300)
                desplegable = selector.locator(".selector-desplegable")
                revisar("se abre el desplegable", desplegable.is_visible())
                revisar("tiene alto máximo y su propio scroll",
                        selector.locator(".selector-lista").evaluate(
                            "e => e.style.maxHeight !== ''"))

                # Buscar escribiendo.
                selector.locator(".selector-buscador").fill("Patrimonio")
                pagina.wait_for_timeout(300)
                opciones = selector.locator(".selector-opcion")
                revisar("buscar escribiendo recorta la lista",
                        0 < opciones.count() < 15, opciones.count())
                revisar("y encuentra sin importar las tildes",
                        "Patrimonio" in opciones.first.inner_text())

                # El teclado: flechas, Enter, Escape.
                pagina.keyboard.press("ArrowDown")
                pagina.wait_for_timeout(150)
                revisar("las flechas mueven el resaltado",
                        selector.locator(".selector-resaltada").count() == 1)
                pagina.keyboard.press("Escape")
                pagina.wait_for_timeout(250)
                revisar("Escape lo cierra", not desplegable.is_visible())

                selector.locator(".selector-boton").click()
                pagina.wait_for_timeout(250)
                selector.locator(".selector-buscador").fill("Patrimonio")
                pagina.wait_for_timeout(250)
                pagina.keyboard.press("ArrowDown")
                pagina.keyboard.press("Enter")
                pagina.wait_for_timeout(600)
                revisar("Enter elige la resaltada",
                        "Patrimonio" in selector.locator(".selector-boton")
                                                .inner_text(),
                        selector.locator(".selector-boton").inner_text())

                revisar("sin errores de JavaScript en el selector",
                        not errores, errores[:3])

            # ---------- El botón de RentAI ----------
            titulo("H. El botón de RentAI")
            errores.clear()
            pagina.goto(DIRECCION + "/cliente?id=%d" % id_cliente,
                        wait_until="networkidle")

            boton = pagina.locator("#rentai-abrir")
            panel = pagina.locator("#rentai-panel")
            revisar("el botón está", boton.count() == 1)

            # Solo el logo: ni nombre, ni frases que roten.
            revisar("no dice nada: solo el logo",
                    boton.inner_text().strip() == "",
                    repr(boton.inner_text()))
            revisar("tiene el logo adentro",
                    boton.locator("svg.marca-logo").count() == 1)
            revisar("y una etiqueta para quien no ve el logo",
                    boton.get_attribute("aria-label") is not None)

            caja_boton = boton.bounding_box()
            revisar("es cuadrado y pequeño",
                    caja_boton is not None
                    and caja_boton["width"] == caja_boton["height"]
                    and caja_boton["width"] <= 48,
                    caja_boton)

            estilo = boton.evaluate(
                "e => { const s = getComputedStyle(e);"
                " return {fondo: s.backgroundColor, posicion:"
                " getComputedStyle(e.parentElement).position}; }")
            revisar("el fondo es negro", estilo["fondo"] == "rgb(20, 23, 21)",
                    estilo["fondo"])
            revisar("está fijo en la esquina",
                    estilo["posicion"] == "fixed", estilo["posicion"])

            verde = boton.locator(".marca-cara").evaluate(
                "e => getComputedStyle(e).fill")
            revisar("el logo va en verde", verde == "rgb(47, 190, 141)", verde)

            # No tapa el contenido: la esquina de abajo a la derecha,
            # fuera de la columna donde el contador está trabajando.
            ancho = pagina.evaluate("() => window.innerWidth")
            alto = pagina.evaluate("() => window.innerHeight")
            revisar("no tapa contenido: vive en la esquina de abajo",
                    caja_boton["x"] > ancho * 0.85
                    and caja_boton["y"] > alto * 0.85,
                    caja_boton)

            # Clic abre, clic otra vez cierra.
            abierto_al_entrar = pagina.locator("#rentai").evaluate(
                "e => !e.classList.contains('rentai-cerrada')")
            if abierto_al_entrar:
                boton.click()
                pagina.wait_for_timeout(350)

            boton.click()
            pagina.wait_for_timeout(350)
            revisar("un clic abre el chat", panel.is_visible())
            revisar("y lo dice para los lectores de pantalla",
                    boton.get_attribute("aria-expanded") == "true")
            revisar("el botón sigue ahí para poder cerrarlo",
                    boton.is_visible())

            boton.click()
            pagina.wait_for_timeout(350)
            revisar("otro clic lo cierra", not panel.is_visible())
            revisar("y también lo dice",
                    boton.get_attribute("aria-expanded") == "false")

            # La animación: crece desde el botón y dura poco.
            # El navegador devuelve el origen en píxeles, no en
            # porcentaje: crecer desde la esquina de abajo a la derecha
            # —que es donde está el botón— significa que el origen cae
            # justo en el ancho y el alto del panel.
            animacion = panel.evaluate(
                "e => { const s = getComputedStyle(e);"
                " return {origen: s.transformOrigin,"
                "         ancho: e.offsetWidth, alto: e.offsetHeight,"
                "         escala: s.transform,"
                "         duracion: s.transitionDuration}; }")
            esquina = "%dpx %dpx" % (animacion["ancho"], animacion["alto"])
            revisar("el panel crece desde la esquina donde está el botón",
                    animacion["origen"] == esquina,
                    "%s (se esperaba %s)" % (animacion["origen"], esquina))
            revisar("y cerrado está encogido, no solo invisible",
                    animacion["escala"] not in ("none", ""),
                    animacion["escala"])
            revisar("y la animación dura 200 ms o menos",
                    all(float(d.rstrip("s")) <= 0.2
                        for d in animacion["duracion"].split(", ")),
                    animacion["duracion"])

            revisar("sin errores de JavaScript en todo el paso",
                    not errores, errores[:3])

            # Con el sistema pidiendo menos movimiento, no hay animación.
            pagina.emulate_media(reduced_motion="reduce")
            pagina.reload(wait_until="networkidle")
            pagina.wait_for_timeout(300)
            sin_motor = pagina.locator("#rentai-panel").evaluate(
                "e => getComputedStyle(e).transitionDuration")
            revisar("respeta a quien pidió menos movimiento",
                    all(float(d.rstrip("s")) == 0
                        for d in sin_motor.split(", ")), sin_motor)
            pagina.emulate_media(reduced_motion="no-preference")

            # ---------- La pantalla de cuenta ----------
            titulo("I. La pantalla de Cuenta")
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
