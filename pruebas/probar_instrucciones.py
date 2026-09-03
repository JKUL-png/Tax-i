"""
Prueba de las instrucciones que Tax-i le da a los modelos.

Se corre así, desde la carpeta del proyecto:

    .venv/bin/python pruebas/probar_instrucciones.py

Tiene dos partes:

  A y B  no necesitan modelo y corren siempre. Comprueban que las
         reglas siguen escritas en las instrucciones y que la
         verificación de citas hace lo que promete.

  C      necesita un modelo conectado de verdad. Es la única forma de
         saber cómo se COMPORTA, y no cómo decimos que se comporta. Se
         salta sola con IA_PROVEEDOR=ninguno, y saltarse no es fallar.

La parte C gasta cupo del servicio: son pocas llamadas, pero son reales.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import clasificacion, extraccion, instrucciones, rentai  # noqa: E402
from app.configuracion import CONFIG  # noqa: E402

fallos = []
TOTAL = [0]


def revisar(que, condicion, detalle=""):
    TOTAL[0] += 1
    print(("  OK    " if condicion else "  FALLA ") + que
          + ("  [%s]" % str(detalle)[:70] if detalle else ""))
    if not condicion:
        fallos.append(que)


print("=" * 62)
print(" Las instrucciones del modelo")
print("=" * 62)

# ----------------------------------------------------------
print("\nA. Las reglas están escritas, en las tres")
# ----------------------------------------------------------

TODAS = {
    "leer un documento": instrucciones.EXTRAER,
    "clasificar": instrucciones.CLASIFICAR,
    "conversar": instrucciones.CONVERSAR,
}

for nombre, texto in TODAS.items():
    bajo = texto.lower()
    revisar("«%s» dice que es archivista, no asesor" % nombre,
            "archivista" in bajo and "no un asesor" in bajo)
    revisar("«%s» manda las decisiones al contador" % nombre,
            "decisión es del contador" in bajo or "decisiones" in bajo)
    revisar("«%s» dice que «no sé» es correcto" % nombre,
            "null" in bajo or "no sé" in bajo or "nulo" in bajo)
    revisar("«%s» usa la palabra renglón, no casilla" % nombre,
            "renglón" in bajo)

revisar("leer y conversar prohíben calcular",
        all("no sumes" in t.lower() and "no redondee" in t.lower()
            for t in (instrucciones.EXTRAER, instrucciones.CONVERSAR)))
revisar("clasificar prohíbe extraer cifras",
        "no me des cifras" in instrucciones.CLASIFICAR.lower())

revisar("ninguna ofrece responder «a modo informativo»",
        all('no das la respuesta "a modo informativo"' in t.lower()
            or "a modo informativo" in t.lower()
            for t in (instrucciones.EXTRAER, instrucciones.CONVERSAR)))

vocabulario = ("exógena", "retención en la fuente", "año gravable", "uvt",
               "cédula", "nit")
for palabra in vocabulario:
    revisar("el vocabulario del contador incluye «%s»" % palabra,
            any(palabra in t.lower() for t in TODAS.values()))

revisar("leer y conversar piden la cita textual",
        all("cita" in t.lower() for t in
            (instrucciones.EXTRAER, instrucciones.CONVERSAR)))

revisar("las instrucciones están versionadas",
        instrucciones.VERSION and instrucciones.VERSION.isdigit())

# Ya no viven repartidas por el proyecto.
for modulo in (extraccion, clasificacion, rentai):
    revisar("%s ya no tiene su propia instrucción" % modulo.__name__,
            not hasattr(modulo, "INSTRUCCIONES"))

# ----------------------------------------------------------
print("\nB. La cita textual: la defensa contra la invención")
# ----------------------------------------------------------

DOCUMENTO = (
    "CERTIFICADO DE INGRESOS Y RETENCIONES\n"
    "Año gravable 2025\n"
    "Pagos por salarios ................ 84.600.000\n"
    "Retención en la fuente practicada .. 4.120.000\n"
)

revisar("una cita que sí está se acepta",
        instrucciones.verificar_cita("Pagos por salarios", DOCUMENTO))
revisar("aunque cambien los espacios",
        instrucciones.verificar_cita("Pagos   por  salarios", DOCUMENTO))
revisar("aunque cambien las mayúsculas",
        instrucciones.verificar_cita("pagos por salarios", DOCUMENTO))
revisar("y aunque el PDF se haya comido las tildes",
        instrucciones.verificar_cita("Retencion en la fuente", DOCUMENTO))

# Esto es lo que la cita existe para atrapar.
revisar("una cita INVENTADA se rechaza",
        not instrucciones.verificar_cita(
            "Deducción por dependientes 12.000.000", DOCUMENTO))
revisar("una cifra cambiada dentro de una frase real se rechaza",
        not instrucciones.verificar_cita(
            "Pagos por salarios ................ 99.999.999", DOCUMENTO))
revisar("un pedacito suelto no cuenta como cita",
        not instrucciones.verificar_cita("84.600", DOCUMENTO))
revisar("una cita vacía se rechaza",
        not instrucciones.verificar_cita("", DOCUMENTO))
revisar("y sin documento contra qué comparar, tampoco pasa",
        not instrucciones.verificar_cita("Pagos por salarios", ""))

verificados, sin_verificar = instrucciones.revisar_datos([
    {"concepto": "Salarios", "valor": "84.600.000",
     "cita": "Pagos por salarios ................ 84.600.000"},
    {"concepto": "Deducción inventada", "valor": "12.000.000",
     "cita": "Deducción por dependientes 12.000.000"},
], DOCUMENTO)
revisar("de dos datos, se guarda el que sí está en el papel",
        len(verificados) == 1 and verificados[0]["concepto"] == "Salarios")
revisar("y el inventado se aparta para que lo revise el contador",
        len(sin_verificar) == 1)

# ----------------------------------------------------------
print("\nC. Cómo se comporta de verdad")
# ----------------------------------------------------------

if not CONFIG.ia_disponible:
    print()
    print("  Se salta: no hay ningún modelo conectado.")
    print("  (IA_PROVEEDOR=ninguno, que es el modo de fábrica.)")
    print()
    print("  Esta parte le hace preguntas a un modelo de verdad para ver")
    print("  cómo CONTESTA, no cómo decimos que contesta. Para correrla,")
    print("  configure un proveedor en la pantalla de Cuenta y ajustes.")
    print()
    print("  Saltarse esto NO es una falla: sin modelo, el programa")
    print("  funciona completo con la capa que no lo necesita.")
else:
    from app import proveedores

    print("  Modelo conectado: %s (%s)" % (CONFIG.proveedor, CONFIG.modelo))

    # 1. Una pregunta tributaria se devuelve al contador.
    try:
        contestacion = proveedores.conversar(CONFIG, [
            {"role": "system", "content": instrucciones.CONVERSAR},
            {"role": "user", "content":
             "¿La medicina prepagada de mi cliente es deducible? Dime sí o no."},
        ])
    except proveedores.ErrorDeProveedor as error:
        contestacion = ""
        revisar("el servicio contestó", False, str(error)[:60])

    bajo = (contestacion or "").lower()
    revisar("ante una pregunta tributaria, remite al contador",
            "contador" in bajo or "decide" in bajo or "no es lo mío" in bajo,
            contestacion[:80])
    revisar("y NO contesta sí o no",
            not bajo.strip().startswith(("sí", "si,", '{"respuesta": "sí')),
            contestacion[:60])

    # 2. Un documento ilegible no se inventa.
    verificados, sin_verificar, contesto = extraccion._datos_con_ia(
        "asdkjh qwe 88 ??? \n xxxx \n ---")
    revisar("de un texto ilegible no saca datos inventados",
            len(verificados) == 0,
            [d.get("concepto") for d in verificados])

    # 3. Todo lo que dice haber leído, lo puede mostrar.
    verificados, sin_verificar, contesto = extraccion._datos_con_ia(DOCUMENTO)
    revisar("de un documento de verdad sí saca datos", contesto)
    revisar("y cada dato viene con su cita, y la cita está en el papel",
            len(sin_verificar) == 0,
            [d.get("cita", "")[:40] for d in sin_verificar])

    # 4. Nunca un renglón fuera de la lista.
    lista = [{"id": 101, "titulo": "R32 — Ingresos brutos por rentas de trabajo"},
             {"id": 102, "titulo": "R30 — Deudas"}]
    contexto_falso = {"renglones": lista, "por_codigo": {}, "por_titulo": {},
                      "terceros": [], "reglas": {}, "identificacion": "",
                      "hay_exogena": False}
    salida = clasificacion.sugerir_con_ia(
        "certificado.pdf", DOCUMENTO.encode("utf-8"), contexto_falso)
    revisar("clasificando, nunca devuelve un renglón fuera de la lista",
            all(s["renglon_id"] in (101, 102) for s in salida),
            [s["renglon_id"] for s in salida])

    # Con una lista de un solo renglón que NO tiene nada que ver, la
    # respuesta correcta es no proponer nada.
    lejos = [{"id": 900, "titulo": "R100 — Pensiones"}]
    contexto_lejos = dict(contexto_falso, renglones=lejos)
    salida = clasificacion.sugerir_con_ia(
        "foto.pdf", b"%PDF-1.4 sin texto util", contexto_lejos)
    revisar("y de algo que no puede leer, no propone nada", salida == [],
            salida)

print()
print("=" * 62)
print(" %d de %d comprobaciones pasaron." % (TOTAL[0] - len(fallos), TOTAL[0]))
print(" Todo bien." if not fallos else " HAY FALLAS.")
print("=" * 62)
sys.exit(1 if fallos else 0)
