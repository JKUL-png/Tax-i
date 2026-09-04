"""
El cruce: lo que dicen sus papeles contra lo que reportó la DIAN.

Qué contesta
------------
La pregunta que el contador se hace apenas tiene las dos cosas cargadas:
«la DIAN dice que a este cliente le pagaron 47 millones por rentas de
trabajo; sus certificados suman 45,8 — ¿falta un certificado, o hay una
diferencia de verdad?».

Antes eso solo salía fila por fila, y únicamente después de que él
enlazara a mano un soporte a cada registro de la exógena. Aquí sale
solo, en cuanto hay exógena cargada y una propuesta corrida.

**Aquí no hay IA.** Son dos listas de números que ya están en la base y
una resta. Funciona completo con IA_PROVEEDOR=ninguno para lo que ya se
haya leído.

Por qué se compara por RENGLÓN y no fila por fila
-------------------------------------------------
Porque es lo único que se puede afirmar sin adivinar.

Un certificado de ingresos y retenciones trae una cifra; la exógena trae
esa misma plata repartida en tres filas de tres conceptos distintos. Para
casar la fila con el papel habría que suponer cuál corresponde a cuál, y
suponer aquí es exactamente lo que este programa no hace: una suposición
mala le pone «diferencia» a algo que estaba bien, y a la tercera vez que
eso pasa el contador deja de mirar los avisos.

El renglón sí se puede sumar de los dos lados sin suponer nada: de un
lado, lo que la DIAN mandó a ese renglón; del otro, lo que los documentos
proponen para el mismo. Y el renglón es además la unidad en la que él
declara.

Lo que NO hace, y no es un descuido
-----------------------------------
- **No dice quién tiene la razón.** «Diferencia» significa revíselo.
  Nunca «está mal» ni «hay un error». La cifra de la DIAN puede estar
  desactualizada —la propia DIAN lo advierte en su primer aviso— y el
  certificado puede estar incompleto. Eso lo resuelve él.
- **No suma las filas que requieren decisión.** Cuando la DIAN propone
  varios renglones para la misma cifra, meterla en uno para poder
  comparar sería elegir por él.
- **No corrige nada ni toca ninguna cifra.** Esto es una mirada.
"""

from app import db, instrucciones, pasada

# Cuánto se puede diferir y seguir llamándolo igual. Un peso: es el
# redondeo con el que trabaja la declaración.
TOLERANCIA = 1.0

DIFERENCIA = "diferencia"
SIN_SOPORTE = "sin_soporte"
SIN_REPORTAR = "sin_reportar"
COINCIDE = "coincide"


def _lo_que_reporto_la_dian(cliente_id):
    """Lo que los terceros mandaron a cada renglón: {"R32": {...}}.

    Se dejan afuera las filas que requieren decisión: cuando la DIAN
    propone varios renglones para la misma cifra, meterla en uno para
    poder comparar sería elegir por el contador, y elegir es criterio
    profesional suyo.
    """
    carga = db.obtener_carga_exogena(cliente_id)
    if carga is None:
        return {}, []

    por_renglon = {}
    aparte = []

    for fila in db.listar_filas_exogena(carga["id"]):
        if fila["valor"] is None:
            continue

        # El renglón que él ya eligió manda sobre lo que sugiere la DIAN.
        elegido = fila.get("renglon_elegido")
        codigos = [elegido] if elegido else [
            r["codigo"] for r in (fila.get("renglones") or [])
        ]

        if not codigos:
            continue
        if len(codigos) > 1 or (fila.get("requiere_decision") and not elegido):
            aparte.append({
                "fila_id": fila["id"],
                "detalle": fila["detalle"],
                "tercero": fila["nombre_reporta"],
                "valor": fila["valor"],
                "opciones": [r["codigo"] for r in (fila.get("renglones") or [])],
            })
            continue

        codigo = codigos[0]
        datos = por_renglon.setdefault(
            codigo, {"total": 0.0, "filas": []}
        )
        datos["total"] += float(fila["valor"])
        datos["filas"].append({
            "fila_id": fila["id"],
            "detalle": fila["detalle"],
            "tercero": fila["nombre_reporta"],
            "nit": fila["nit_reporta"],
            "valor": fila["valor"],
        })

    return por_renglon, aparte


def _lo_que_dicen_los_papeles(cliente_id):
    """Lo que los documentos proponen para cada renglón: {"R32": {...}}.

    Sale de la propuesta ya verificada: solo entran los valores cuya
    cita se encontró en el papel. Lo que no se pudo verificar no cuenta
    para un cruce — sería comparar contra algo que no se sabe si existe.
    """
    ultima = db.ultima_pasada(cliente_id)
    if ultima is None:
        return {}

    por_renglon = {}
    for valor in db.listar_valores_de_pasada(ultima["id"]):
        if valor["fuente"] != "documento" or not valor["verificada"]:
            continue
        if valor["numero"] is None:
            continue
        if valor["estado"] not in ("propuesto", "aprobado"):
            continue
        datos = por_renglon.setdefault(
            valor["renglon"], {"total": 0.0, "documentos": []}
        )
        datos["total"] += float(valor["numero"])
        datos["documentos"].append({
            "documento_id": valor["documento_id"],
            "nombre": valor["nombre_original"] or "",
            "valor": valor["numero"],
            "cita": valor["cita"],
        })
    return por_renglon


def revisar(cliente_id):
    """Cruza los dos lados y devuelve lo que hay que mirar.

    Devuelve un informe listo para pintar. Nunca lanza excepción por
    que falte una de las dos partes: sin exógena, o sin propuesta
    corrida, simplemente no hay nada que cruzar y se dice.
    """
    dian, requieren_decision = _lo_que_reporto_la_dian(cliente_id)
    papeles = _lo_que_dicen_los_papeles(cliente_id)
    nombres = {}
    try:
        nombres = pasada.catalogo_de_renglones()
    except Exception:
        # Sin plantilla no hay nombres oficiales. El cruce se puede hacer
        # igual: los números no dependen de ella.
        nombres = {}

    hallazgos = []
    for codigo in sorted(set(dian) | set(papeles),
                         key=lambda c: int(
                             instrucciones._numero_de_renglon(c) or 0)):
        de_la_dian = dian.get(codigo)
        de_los_papeles = papeles.get(codigo)
        numero = instrucciones._numero_de_renglon(codigo)

        base = {
            "renglon": codigo,
            "nombre": nombres.get(numero, ""),
            "dian": de_la_dian["total"] if de_la_dian else None,
            "papeles": de_los_papeles["total"] if de_los_papeles else None,
            "filas": de_la_dian["filas"] if de_la_dian else [],
            "documentos": de_los_papeles["documentos"] if de_los_papeles else [],
        }

        if de_la_dian and de_los_papeles:
            base["diferencia"] = de_la_dian["total"] - de_los_papeles["total"]
            base["estado"] = (COINCIDE if abs(base["diferencia"]) <= TOLERANCIA
                              else DIFERENCIA)
        elif de_la_dian:
            base["diferencia"] = de_la_dian["total"]
            base["estado"] = SIN_SOPORTE
        else:
            base["diferencia"] = -de_los_papeles["total"]
            base["estado"] = SIN_REPORTAR
        hallazgos.append(base)

    return {
        "hay_cruce": bool(dian) and bool(papeles),
        "hay_exogena": bool(dian) or bool(requieren_decision),
        "hay_propuesta": bool(papeles),
        "hallazgos": hallazgos,
        "diferencias": sum(1 for h in hallazgos if h["estado"] == DIFERENCIA),
        "sin_soporte": sum(1 for h in hallazgos if h["estado"] == SIN_SOPORTE),
        "sin_reportar": sum(1 for h in hallazgos if h["estado"] == SIN_REPORTAR),
        "coinciden": sum(1 for h in hallazgos if h["estado"] == COINCIDE),
        # Las que la DIAN mandó a varios renglones. No se cruzan y se
        # dice por qué: elegir es criterio del contador.
        "requieren_decision": requieren_decision,
    }
