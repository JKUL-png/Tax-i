"""
Prueba del respaldo completo: llevarse todo y traerlo de vuelta.

Se corre así, desde la carpeta del proyecto:

    .venv/bin/python pruebas/probar_respaldo.py

Trabaja sobre dos carpetas temporales que hacen de "computador A" y
"computador B". La base del contador no se toca.

Es la prueba más importante de la fase 3: si al contador se le daña el
disco en octubre, esto es lo único que le devuelve la temporada.

Lo que comprueba:

  A. El respaldo lleva la base, los documentos y un LÉEME que explica
     cómo devolverlo. NO lleva el .env, donde vive la llave.
  B. Un archivo que no es un respaldo se rechaza ANTES de tocar nada.
  C. Restaurar en otro computador devuelve clientes, checklists,
     documentos y lo ya leído de cada uno, con tildes y todo.
  D. Restaurar encima de un computador con trabajo NO lo borra: lo aparta
     primero, con la fecha en el nombre.
"""

import shutil, sys, tempfile, zipfile
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
fallos = []
TOTAL = [0]
def revisar(q, c, d=""):
    TOTAL[0] += 1
    print(("  OK    " if c else "  FALLA ") + q + ("  [%s]" % str(d)[:70] if d else ""))
    if not c: fallos.append(q)

# --- "Computador A": se arma trabajo de verdad ---
A = Path(tempfile.mkdtemp(prefix="taxi-A-"))
from app import db, documentos, respaldo
def apuntar_a(carpeta):
    db.CARPETA_DATOS = carpeta; db.ARCHIVO_BD = carpeta / "base.db"
    documentos.CARPETA_ARCHIVOS = carpeta / "archivos"
    respaldo.CARPETA_DATOS = carpeta
apuntar_a(A); db.crear_tablas()

c1 = db.crear_cliente("Juan Ejemplo Muñoz", "05", "2026-10-14")
c2 = db.crear_cliente("Ana: Gómez/Díaz", "31", None)   # nombre con caracteres que Windows prohíbe
db.crear_renglones(c1["id"], ["Certificado de ingresos", "Extracto bancario"])
for cli, nombre, contenido in [
    (c1, "certificado.pdf", b"%PDF-1.4 certificado de ejemplo"),
    (c1, "extracto.pdf", b"%PDF-1.4 extracto"),
    (c2, "factura.xml", b"<Invoice/>"),
]:
    g, t = documentos.guardar_contenido(cli["id"], nombre, contenido)
    d = db.crear_documento(cli["id"], nombre, g, Path(nombre).suffix.lstrip("."), t)
    db.guardar_datos_extraidos(cli["id"], d["id"],
        [{"concepto": "Salarios", "valor": "45.000.000"}], "ia")

print("\nA. Armar el respaldo")
zip_path = A / "respaldo.zip"
informe = respaldo.armar(zip_path)
revisar("se armó el archivo", zip_path.exists())
revisar("lleva los 2 clientes", informe["clientes"] == 2, str(informe))
revisar("lleva los 3 documentos", informe["documentos"] == 3, str(informe))
with zipfile.ZipFile(zip_path) as z: nombres = z.namelist()
revisar("adentro va la base de datos", "base.db" in nombres)
revisar("adentro va el LÉEME que explica cómo devolverlo", "RESPALDO.txt" in nombres)
revisar("las carpetas llevan el nombre del cliente, no solo el número",
        any("Juan" in n for n in nombres), [n for n in nombres if "Juan" in n][:1])
revisar("un nombre con ':' y '/' se limpió para Windows",
        not any(":" in n for n in nombres),
        [n for n in nombres if "Ana" in n][:1])
revisar("el .env NO va en el respaldo", not any(".env" in n for n in nombres))

print("\nB. Revisar antes de tocar nada")
info = respaldo.revisar(zip_path)
revisar("dice cuántos documentos trae", info["documentos"] == 3, str(info["documentos"]))
malo = A / "malo.zip"
with zipfile.ZipFile(malo, "w") as z: z.writestr("cualquier.txt", "nada")
try:
    respaldo.revisar(malo); revisar("rechaza un ZIP que no es respaldo", False)
except respaldo.RespaldoInvalido as e:
    revisar("rechaza un ZIP que no es respaldo", "no trae la base" in str(e), str(e)[:50])
try:
    respaldo.revisar(A / "certificado.pdf" ); revisar("rechaza lo que no es ZIP", False)
except respaldo.RespaldoInvalido as e:
    revisar("rechaza lo que ni siquiera es un ZIP", True, str(e)[:45])
except Exception as e:
    revisar("rechaza lo que ni siquiera es un ZIP", False, type(e).__name__)

print("\nC. Restaurar en OTRO computador, vacío")
B = Path(tempfile.mkdtemp(prefix="taxi-B-"))
apuntar_a(B); db.crear_tablas()
revisar("el computador B empieza vacío", len(db.listar_clientes()) == 0)
r = respaldo.restaurar(zip_path)
revisar("volvieron los 2 clientes", r["clientes"] == 2, str(r))
revisar("volvieron los 3 documentos", r["documentos"] == 3, str(r))
nombres_b = sorted(x["nombre"] for x in db.listar_clientes())
revisar("con sus nombres, tildes incluidas",
        "Juan Ejemplo Muñoz" in nombres_b, str(nombres_b))
revisar("el checklist volvió", len(db.listar_checklist(c1["id"])) == 2)
revisar("lo ya leído de los documentos volvió",
        len(db.listar_datos_extraidos(c1["id"])) == 2,
        "%d datos" % len(db.listar_datos_extraidos(c1["id"])))
ruta = documentos.ruta_del_documento(c1["id"], db.listar_documentos(c1["id"])[0]["nombre_guardado"])
revisar("y los archivos están en el disco, con su contenido",
        ruta and ruta.exists() and b"%PDF" in ruta.read_bytes(), str(ruta))

print("\nD. Restaurar encima NO borra lo que había")
otro = db.crear_cliente("Trabajo del computador B", "77", None)
r2 = respaldo.restaurar(zip_path)
revisar("guardó una copia de lo que había antes",
        bool(r2["copia_de_seguridad"]), r2["copia_de_seguridad"])
copia = B / Path(r2["copia_de_seguridad"]).name
revisar("la copia existe de verdad y tiene la base",
        (copia / "base.db").exists(), str(copia))
import sqlite3
vieja = sqlite3.connect(copia / "base.db")
nombres_viejos = [f[0] for f in vieja.execute("SELECT nombre FROM clientes")]
revisar("y adentro está el cliente que se iba a perder",
        "Trabajo del computador B" in nombres_viejos, str(nombres_viejos))

shutil.rmtree(A, ignore_errors=True); shutil.rmtree(B, ignore_errors=True)
print()
print("=" * 62)
print(" %d de %d comprobaciones pasaron." % (TOTAL[0] - len(fallos), TOTAL[0]))
print(" Todo bien." if not fallos else " HAY FALLAS.")
print("=" * 62)
sys.exit(1 if fallos else 0)
