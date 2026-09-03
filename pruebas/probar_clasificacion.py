"""
Prueba de la capa 1: clasificar documentos SIN inteligencia artificial.

Se corre así, desde la carpeta del proyecto:

    .venv/bin/python pruebas/probar_clasificacion.py

Arma veinte documentos inventados (ver pruebas/documentos_de_ejemplo.py),
se los da a un cliente de mentiras que tiene cargada la exógena de
ejemplo, y mide cuántos resuelve la capa 1 sola.

**Aquí no hay ninguna llamada a un modelo de IA**, y la prueba lo
comprueba: corre con IA_PROVEEDOR=ninguno y falla si alguien mete una
dependencia de proveedores en el camino.

Lo que comprueba:

  A. Lee los NIT como vienen escritos en los documentos de verdad.
  B. Arma el contexto del cliente desde la exógena.
  C. Cada fuente encuentra lo suyo: XML, texto, exógena y nombre.
  D. No inventa: un tercero que la exógena no menciona no se sugiere,
     y lo que no se puede leer se queda sin sugerencia.
  E. El número: cuántos de los veinte resuelve, y con cuál fuente.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "pruebas"))

# La capa 1 tiene que funcionar con la IA apagada. Se apaga antes de
# importar nada, para que ningún módulo la lea prendida.
os.environ["IA_PROVEEDOR"] = "ninguno"

import documentos_de_ejemplo as ejemplos  # noqa: E402

from app import clasificacion, db, exogena_cliente  # noqa: E402

EJEMPLO_EXOGENA = RAIZ / "pruebas" / "ejemplos" / "reporteExogena2025_EJEMPLO.xlsx"

fallos = []
TOTAL = [0]


def revisar(que, condicion, detalle=""):
    TOTAL[0] += 1
    print(("  OK    " if condicion else "  FALLA ") + que
          + ("  [%s]" % str(detalle)[:70] if detalle else ""))
    if not condicion:
        fallos.append(que)


print("=" * 62)
print(" Clasificar documentos sin IA")
print("=" * 62)

if not EJEMPLO_EXOGENA.exists():
    print()
    print("  No está el reporte de exógena de ejemplo:")
    print("  " + str(EJEMPLO_EXOGENA.relative_to(RAIZ)))
    print()
    print("  Eso NO es un error: ese archivo se deja fuera del")
    print("  repositorio a propósito. Ver pruebas/probar_exogena.py.")
    print()
    sys.exit(0)

# --- Un computador de mentiras, para no tocar la base del contador ---
CARPETA = Path(tempfile.mkdtemp(prefix="taxi-clasificar-"))
db.CARPETA_DATOS = CARPETA
db.ARCHIVO_BD = CARPETA / "base.db"
exogena_cliente.CARPETA_EXOGENA = CARPETA / "exogena"
db.crear_tablas()

cliente = db.crear_cliente("Cliente de prueba", "77", None)
exogena_cliente.cargar(cliente["id"], EJEMPLO_EXOGENA, "ejemplo.xlsx")

# ----------------------------------------------------------
print("\nA. Leer los NIT como vienen escritos")
# ----------------------------------------------------------
revisar("con puntos y dígito de verificación",
        "900123456" in clasificacion.nits_del_texto("NIT 900.123.456-7"))
revisar("con puntos y sin dígito de verificación",
        "890903938" in clasificacion.nits_del_texto("NIT 890.903.938"))
revisar("todo pegado",
        "860034313" in clasificacion.nits_del_texto("Nit 8600343137"))
revisar("y una cifra suelta no se confunde con un NIT",
        clasificacion.nits_del_texto("Saldo a 31 de diciembre: 447.221") == set(),
        clasificacion.nits_del_texto("Saldo a 31 de diciembre: 447.221"))

# ----------------------------------------------------------
print("\nB. El contexto del cliente sale de su exógena")
# ----------------------------------------------------------
ctx = clasificacion.contexto(cliente["id"])
revisar("encontró la exógena cargada", ctx["hay_exogena"])
revisar("y los terceros que le reportan",
        len(ctx["terceros"]) >= 9, len(ctx["terceros"]))
revisar("cada tercero trae su renglón del 210",
        all(t["renglon"] and t["codigo"] for t in ctx["terceros"]))

# La cédula del propio contribuyente NO es un tercero: aparece en todos
# sus documentos, y si contara, todos caerían en el mismo renglón.
revisar("su propia cédula NO cuenta como tercero",
        all(t["nit"] != ctx["identificacion"] for t in ctx["terceros"]),
        ctx["identificacion"])

# ----------------------------------------------------------
print("\nC. Cada fuente encuentra lo suyo")
# ----------------------------------------------------------
CARPETA_DOCS = CARPETA / "documentos"
puestos = ejemplos.escribir_en(CARPETA_DOCS)
por_nombre = {d["nombre"]: d for d in puestos}


def sugerencia_de(nombre):
    documento = por_nombre[nombre]
    return clasificacion.sugerir(nombre, documento["contenido"], ctx)


s = sugerencia_de("factura_taller_metalico.xml")
revisar("el XML: sale del NIT del emisor, sin adivinar nada",
        s and s["origen"] == clasificacion.POR_XML and s["codigo"] == "74",
        s)

s = sugerencia_de("scan0001.pdf")
revisar("el texto: un archivo llamado «scan0001» se resuelve igual",
        s and s["codigo"] == "30", s)
revisar("y dice que salió del NIT que traía adentro",
        s and s["origen"] == clasificacion.POR_EXOGENA, s and s["origen"])

s = sugerencia_de("Certificado Bancolombia 2025.pdf")
revisar("el nombre del archivo también sirve cuando dice algo",
        s and s["codigo"] in ("29", "30"), s)

todas = clasificacion.sugerir_todas(
    "Certificado Bancolombia 2025.pdf",
    por_nombre["Certificado Bancolombia 2025.pdf"]["contenido"], ctx)
revisar("y cuando varias fuentes coinciden, se guardan todas",
        len(todas) >= 2, [x["origen"] for x in todas])

s = sugerencia_de("20260228_0001.pdf")
revisar("un PDF con candado pero sin clave sí se lee y se clasifica",
        s and s["codigo"] in ("29", "30"), s)

revisar("toda sugerencia dice de dónde salió y con cuánta certeza",
        all(x["origen"] in clasificacion.ORIGENES
            and x["certeza"] in (clasificacion.ALTA, clasificacion.MEDIA)
            for x in todas))

# ----------------------------------------------------------
print("\nD. No inventa")
# ----------------------------------------------------------
revisar("una foto de celular no se clasifica",
        sugerencia_de("IMG_20260315_112233.jpg") is None)
revisar("un PDF escaneado, que por dentro es una foto, tampoco",
        sugerencia_de("CamScanner 03-14-2026 10.15.pdf") is None)
revisar("un PDF con contraseña de verdad tampoco",
        sugerencia_de("adjunto.pdf") is None)

# Este es el que importa: el tercero existe, el documento se lee bien,
# pero la exógena no lo menciona. Callarse es la respuesta correcta.
revisar("un tercero que la exógena no menciona NO se inventa",
        sugerencia_de("0001.pdf") is None, sugerencia_de("0001.pdf"))

# Un cliente sin exógena no rompe nada: la capa 1 sigue corriendo con
# lo que pueda, que es el nombre del archivo contra sus renglones.
otro = db.crear_cliente("Sin exógena", "12", None)
db.crear_renglones(otro["id"], ["Soportes de vehículos"])
ctx_vacio = clasificacion.contexto(otro["id"])
revisar("un cliente sin exógena no rompe la clasificación",
        not ctx_vacio["hay_exogena"] and ctx_vacio["terceros"] == [])
revisar("y ahí el nombre del archivo sigue sirviendo",
        clasificacion.sugerir(
            "vehiculo soportes.pdf", b"%PDF-1.4", ctx_vacio) is not None)

# ----------------------------------------------------------
print("\nE. El número: cuántos resuelve la capa 1 sola")
# ----------------------------------------------------------
aciertos = 0
callados_bien = 0
errores = []
por_origen = {}

for documento in puestos:
    esperados = documento["renglones"]
    propuesta = clasificacion.sugerir(
        documento["nombre"], documento["contenido"], ctx)

    if not esperados:
        if propuesta is None:
            callados_bien += 1
        else:
            errores.append((documento["nombre"], "sugirió y no debía",
                            propuesta["codigo"]))
        continue

    if propuesta is None:
        errores.append((documento["nombre"], "no sugirió nada", ""))
    elif propuesta["codigo"] in esperados:
        aciertos += 1
        por_origen[propuesta["origen"]] = por_origen.get(
            propuesta["origen"], 0) + 1
    else:
        errores.append((documento["nombre"], "sugirió el renglón equivocado",
                        propuesta["codigo"]))

clasificables = sum(1 for d in puestos if d["renglones"])
sin_clasificar = len(puestos) - clasificables

print()
print("  De %d documentos:" % len(puestos))
print("    %2d se podían clasificar y acertó %d" % (clasificables, aciertos))
print("    %2d no se podían y se quedó callado en %d" % (sin_clasificar,
                                                        callados_bien))
print()
print("  Con cuál fuente resolvió cada uno:")
for origen, cuantos in sorted(por_origen.items(), key=lambda p: -p[1]):
    print("    %-28s %d" % (clasificacion.ORIGENES[origen], cuantos))
if errores:
    print()
    print("  Los que no salieron:")
    for nombre, que, detalle in errores:
        print("    %-46s %s %s" % (nombre[:46], que, detalle))
print()

revisar("acierta en la mayoría de los que se pueden clasificar",
        aciertos >= clasificables * 0.6,
        "%d de %d" % (aciertos, clasificables))
revisar("y no inventa en ninguno de los que no se pueden",
        callados_bien == sin_clasificar,
        "%d de %d" % (callados_bien, sin_clasificar))

shutil.rmtree(CARPETA, ignore_errors=True)

print("=" * 62)
print(" %d de %d comprobaciones pasaron." % (TOTAL[0] - len(fallos), TOTAL[0]))
print(" Todo bien." if not fallos else " HAY FALLAS.")
print("=" * 62)
sys.exit(1 if fallos else 0)
