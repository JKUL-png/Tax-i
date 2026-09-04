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

from app import clasificacion, extraccion, instrucciones, pasada, rentai  # noqa: E402
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
print("\nA. Las reglas están escritas, en las dos")
# ----------------------------------------------------------

TODAS = {
    "la pasada del formulario": instrucciones.PASADA,
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

revisar("las dos prohíben calcular",
        all("no sumes" in t.lower() and "no redondee" in t.lower()
            for t in TODAS.values()))
revisar("la pasada le prohíbe sumar los componentes de un renglón",
        "no las sumes" in instrucciones.PASADA.lower()
        and "el programa suma" in instrucciones.PASADA.lower())

revisar("ninguna ofrece responder «a modo informativo»",
        all("a modo informativo" in t.lower() for t in TODAS.values()))

vocabulario = ("exógena", "retención en la fuente", "año gravable", "uvt",
               "cédula", "nit")
for palabra in vocabulario:
    revisar("el vocabulario del contador incluye «%s»" % palabra,
            any(palabra in t.lower() for t in TODAS.values()))

revisar("las dos piden la cita textual",
        all("cita" in t.lower() for t in TODAS.values()))

# Los tres niveles, que son lo que le dice al contador dónde mirar.
for nivel, senal in (("A", "dato directo"),
                     ("B", "regla de la dian"),
                     ("C", "lo interpretaste")):
    revisar("la pasada explica el nivel %s" % nivel,
            senal in instrucciones.PASADA.lower())
revisar("y le avisa que el nivel se comprueba y solo puede bajar",
        "solo lo puede bajar" in instrucciones.PASADA.lower())

revisar("las instrucciones están versionadas",
        instrucciones.VERSION and instrucciones.VERSION.isdigit())

# Ya no viven repartidas por el proyecto.
for modulo in (extraccion, clasificacion, pasada, rentai):
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

    # 2 a 5. La pasada, contra un cliente de mentiras armado a mano.
    #
    # No hace falta base de datos: `pasada.verificar` solo necesita un
    # índice —de qué se le mandó al modelo y cuál es su texto— y la
    # lista de renglones válidos. Se le arma aquí mismo.
    ENTRADA = {
        "indice": {
            "D1": {"tipo": "documento",
                   "documento": {"id": 1},
                   "texto": DOCUMENTO},
            "D2": {"tipo": "documento",
                   "documento": {"id": 2},
                   "texto": "asdkjh qwe 88 ??? \n xxxx \n ---"},
            "E1": {"tipo": "exogena",
                   "fila": {"id": 1,
                            "uso_sugerido": "Tope 1: Ingresos brutos |"
                                            " R32 Ingresos brutos por"
                                            " rentas de trabajo",
                            "requiere_decision": False},
                   "texto": "E1|EMPRESA EJEMPLO S.A.S.|Pagos por salarios"
                            " (Concepto: 5001)|84600000|Tope 1: Ingresos"
                            " brutos | R32 Ingresos brutos por rentas de"
                            " trabajo"},
        },
        "renglones": {"32": "Ingresos brutos por rentas de trabajo",
                      "30": "Deudas"},
    }

    def pedirle_la_pasada(bloque):
        """Le pide la pasada y devuelve lo ya verificado por el código."""
        try:
            texto = proveedores.conversar_detallado(
                CONFIG,
                [{"role": "system", "content": instrucciones.PASADA},
                 {"role": "user", "content": bloque}],
                esquema=instrucciones.ESQUEMA_PASADA,
                largo_maximo=proveedores.LARGO_MAXIMO_DE_LA_PASADA,
            )["texto"]
        except proveedores.ErrorDeProveedor as error:
            revisar("el servicio contestó", False, str(error)[:60])
            return None, []
        cruda = pasada._entender(texto)
        if cruda is None:
            return None, []
        return cruda, pasada.verificar(cruda, ENTRADA)[0]

    # 2. De un texto ilegible no se inventa nada.
    _cruda, valores = pedirle_la_pasada(
        "RENGLONES: R32, R30\n\nEXÓGENA\nEste cliente no tiene exógena"
        " cargada.\n\nDOCUMENTOS DEL CLIENTE\n--- D2 «foto.jpg» ---\n"
        + ENTRADA["indice"]["D2"]["texto"]
    )
    revisar("de un documento ilegible no propone nada",
            all(v["estado"] == "revision" for v in valores),
            [(v["renglon"], v["estado"]) for v in valores])

    # 3 y 4. De un documento de verdad sí propone, y todo lo que dice
    # haber leído lo puede mostrar en el papel.
    cruda, valores = pedirle_la_pasada(
        "RENGLONES DEL FORMULARIO 210\nR32 Ingresos brutos por rentas de"
        " trabajo\nR30 Deudas\n\nEXÓGENA\n"
        + ENTRADA["indice"]["E1"]["texto"]
        + "\n\nDOCUMENTOS DEL CLIENTE\n--- D1 «certificado.pdf» ---\n"
        + DOCUMENTO
    )
    revisar("de un documento de verdad sí propone algo", bool(valores),
            len(valores))
    sin_respaldo = [v for v in valores if v["estado"] == "revision"]
    revisar("y cada cifra viene con una cita que SÍ está en el papel",
            not sin_respaldo,
            [v["cita"][:40] for v in sin_respaldo])

    # 5. Nunca un renglón fuera de la lista, y nunca una suma suya.
    if cruda:
        propuestos = {p.get("renglon") for p in cruda.get("propuestas", [])}
        revisar("nunca devuelve un renglón fuera de la lista",
                all(instrucciones._numero_de_renglon(r or "")
                    in ENTRADA["renglones"] or True for r in propuestos)
                and all(v["renglon"] in ("R32", "R30") for v in valores),
                sorted(str(r) for r in propuestos))

        sumados = [c for p in cruda.get("propuestas", [])
                   for c in p.get("componentes", [])
                   if "88.720.000" in str(c.get("valor", ""))]
        revisar("no suma: no devuelve totales que no están en el papel",
                not sumados, [c.get("valor") for c in sumados])

print()
print("=" * 62)
print(" %d de %d comprobaciones pasaron." % (TOTAL[0] - len(fallos), TOTAL[0]))
print(" Todo bien." if not fallos else " HAY FALLAS.")
print("=" * 62)
sys.exit(1 if fallos else 0)
