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

import documentos_de_ejemplo as ejemplos  # noqa: E402

from app import clasificacion, db, exogena_cliente  # noqa: E402
from app.configuracion import CONFIG  # noqa: E402

# TODO lo de esta prueba corre con la IA apagada, que es el modo de
# fábrica. Se fuerza aquí y no con una variable de entorno porque la
# configuración sale del archivo .env del computador: si el
# desarrollador tiene la IA prendida, la prueba tiene que apagarla
# igual, o estaría midiendo otra cosa.
CONFIG._aplicar({"IA_PROVEEDOR": "ninguno"})
os.environ["IA_PROVEEDOR"] = "ninguno"

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
revisar("cuando varias fuentes llegan al mismo renglón, se muestra una",
        len({x["renglon_id"] for x in todas}) == len(todas),
        [x["origen"] for x in todas])
revisar("y gana la fuente más fuerte",
        todas[0]["origen"] in (clasificacion.POR_REGLA,
                               clasificacion.POR_EXOGENA,
                               clasificacion.POR_XML),
        todas[0]["origen"])

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
print("\nE. La capa 2 no puede salirse de la lista del cliente")
# ----------------------------------------------------------
#
# Esto es lo que hace que la promesa se cumpla. Al modelo se le PIDE que
# elija de la lista, pero además se le IMPIDE en código: lo que conteste
# fuera de la lista se descarta sin más. Pedir por favor no es lo mismo
# que impedir.

sus_renglones = ctx["renglones"]
uno = sus_renglones[0]["id"]
otro = sus_renglones[1]["id"]

def validar(respuesta):
    return clasificacion._validar(respuesta, sus_renglones)

revisar("acepta un renglón que sí está en la lista",
        validar({"renglon": uno, "certeza": "alta"})[0] == uno)

revisar("un id inventado se descarta",
        validar({"renglon": 999999, "certeza": "alta"})[0] is None)
revisar("un renglón de OTRO cliente se descarta",
        validar({"renglon": -1, "certeza": "alta"})[0] is None)
revisar("un nombre de renglón inventado se descarta",
        validar({"renglon": "Certificado que yo me inventé"})[0] is None)
revisar("una respuesta que no es un objeto se descarta",
        validar(["R32"])[0] is None)
revisar("y una respuesta que ni siquiera era JSON se descarta",
        clasificacion._json_de_la_respuesta("perdón, no entendí") is None)

# «No sé» es una respuesta correcta y esperada.
revisar("«no sé» deja el documento sin asignar",
        validar({"renglon": None, "certeza": "alta"})[0] is None)
revisar("y una respuesta vacía también",
        validar({})[0] is None)

# La certeza baja no se muestra.
principal, _, certeza = validar({"renglon": uno, "certeza": "baja"})
revisar("con certeza baja el renglón se lee pero no se propone",
        principal == uno and certeza == clasificacion.BAJA)
revisar("si no dice la certeza, no se le regala la más alta",
        validar({"renglon": uno})[2] == clasificacion.MEDIA)

# Los secundarios pasan por el mismo filtro.
_, secundarios, _ = validar(
    {"renglon": uno, "tambien": [otro, 999999, uno], "certeza": "alta"})
revisar("los renglones secundarios se validan igual que el principal",
        secundarios == [otro], secundarios)

revisar("el JSON envuelto en ``` se entiende igual",
        clasificacion._json_de_la_respuesta(
            '```json\n{"renglon": 3}\n```') == {"renglon": 3})

# Y con la IA apagada, la capa 2 simplemente no corre.
revisar("con IA_PROVEEDOR=ninguno la capa 2 no corre",
        not clasificacion.hay_ia(), CONFIG.proveedor)
revisar("y no rompe nada: devuelve vacío y ya",
        clasificacion.sugerir_con_ia("x.pdf", b"%PDF", ctx) == [])

# ----------------------------------------------------------
print("\nF. Aprender de las correcciones")
# ----------------------------------------------------------
#
# Lo más valioso que pasa en el programa: el contador corrige y el
# programa no vuelve a equivocarse igual.

# Un documento de un tercero que la exógena NO menciona: la capa 1 se
# queda callada, y eso está bien.
docu = por_nombre["0001.pdf"]
revisar("antes de enseñarle, no propone nada para este tercero",
        clasificacion.sugerir(docu["nombre"], docu["contenido"], ctx) is None)

# El contador lo asigna a mano. Eso es la corrección.
guardado, tamano = __import__("app.documentos", fromlist=["x"]).guardar_contenido(
    cliente["id"], docu["nombre"], docu["contenido"])
fila = db.crear_documento(cliente["id"], docu["nombre"], guardado, "pdf", tamano)
destino = next(r for r in ctx["renglones"] if r["codigo_renglon"] == "33")
regla = clasificacion.aprender_de_la_correccion(fila, destino["id"], ctx)
revisar("la corrección queda guardada como regla", regla is not None, regla)
revisar("y la regla NO guarda el nombre del archivo ni su contenido",
        regla and "0001" not in str(regla) and "COMFANDI" not in str(regla).upper())

# Y ahora sí la propone. El contexto se vuelve a armar porque las
# reglas se cargan con él.
ctx2 = clasificacion.contexto(cliente["id"])
propuesta = clasificacion.sugerir(docu["nombre"], docu["contenido"], ctx2)
revisar("la próxima vez propone lo que él decidió",
        propuesta and propuesta["codigo"] == "33", propuesta)
revisar("y dice que salió de una corrección suya",
        propuesta and propuesta["origen"] == clasificacion.POR_REGLA)
revisar("con certeza alta: su decisión le gana a cualquier deducción",
        propuesta and propuesta["certeza"] == clasificacion.ALTA)

# Y sirve en OTRO cliente, porque la regla va por código de renglón.
tercer = db.crear_cliente("Otro cliente", "44", None)
db.crear_renglon(tercer["id"], "R33 — Trabajo", codigo_renglon="33",
                 origen="dian")
ctx3 = clasificacion.contexto(tercer["id"])
otra = clasificacion.sugerir(docu["nombre"], docu["contenido"], ctx3)
revisar("y la misma regla sirve en otro cliente distinto",
        otra and otra["codigo"] == "33", otra)

# Si el otro cliente no tiene ese renglón, no se le inventa.
cuarto = db.crear_cliente("Cliente sin ese renglón", "55", None)
db.crear_renglones(cuarto["id"], ["Soportes de vehículos"])
ctx4 = clasificacion.contexto(cuarto["id"])
revisar("pero a un cliente que no tiene ese renglón no se le inventa",
        clasificacion.sugerir(docu["nombre"], docu["contenido"], ctx4) is None)

# La corrección se puede cambiar: manda la última palabra.
otro_destino = next(r for r in ctx["renglones"] if r["codigo_renglon"] == "74")
clasificacion.aprender_de_la_correccion(fila, otro_destino["id"], ctx)
ctx5 = clasificacion.contexto(cliente["id"])
cambiada = clasificacion.sugerir(docu["nombre"], docu["contenido"], ctx5)
revisar("si vuelve a corregir, manda su última palabra",
        cambiada and cambiada["codigo"] == "74", cambiada)

revisar("y las reglas se pueden ver y borrar: son suyas",
        len(db.listar_reglas()) >= 1
        and db.eliminar_regla(db.listar_reglas()[0]["id"]))

# ----------------------------------------------------------
print("\nG. Varios renglones para un mismo documento")
# ----------------------------------------------------------
# Un certificado de ingresos y retenciones soporta el ingreso en un
# renglón y la retención en otro. Obligar a elegir uno solo sería
# obligar a subir el mismo papel dos veces.

r_uno = ctx["renglones"][0]["id"]
r_dos = ctx["renglones"][1]["id"]
db.asignar_documento(fila["id"], r_uno)
db.agregar_renglon_a_documento(fila["id"], r_dos)
puestos_ahora = db.renglones_del_documento(fila["id"])
revisar("un documento puede ir a dos renglones",
        len(puestos_ahora) == 2, [r["renglon_id"] for r in puestos_ahora])
revisar("uno de los dos es el principal",
        sum(1 for r in puestos_ahora if r["principal"]) == 1)
revisar("y el principal es el que ve el resto del programa",
        db.obtener_documento(fila["id"])["renglon_id"] == r_uno)

conteos = db.contar_documentos_por_renglon(cliente["id"])
revisar("el checklist lo cuenta en los dos renglones",
        conteos.get(r_uno) == 1 and conteos.get(r_dos) == 1, conteos)

db.quitar_renglon_de_documento(fila["id"], r_uno)
revisar("quitarle uno deja el otro",
        len(db.renglones_del_documento(fila["id"])) == 1)
revisar("y el principal se rehace solo",
        db.obtener_documento(fila["id"])["renglon_id"] == r_dos)

# ----------------------------------------------------------
print("\nH. El número: cuántos resuelve la capa 1 sola")
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
