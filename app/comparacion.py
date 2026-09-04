"""
El modo comparación: la propuesta de Tax-i contra el 210 que él llenó.

Para qué existe
---------------
Antes de darle esto a un contador para trabajo de verdad hay que saber
qué tan bueno es. No «se ve bien»: un número.

Aquí se carga un Formulario 210 que él ya llenó a mano y se compara
renglón por renglón contra lo que propuso el programa. Sale cuántos
coincidieron, cuántos no y en cuánto, cuántos propuso Tax-i que él dejó
vacíos, cuántos llenó él que Tax-i no vio — y el desglose por nivel, que
es lo que dice si los tres niveles significan algo o son decoración.

Por qué por RENGLÓN y no por celda
----------------------------------
Porque la plantilla tiene varias filas de detalle dentro de cada
renglón —«Salarios», «Cesantías e intereses»— y él pudo anotar la misma
cifra en otra de ellas. Comparar por celda contaría eso como un error
del programa cuando el renglón quedó bien. El renglón es la unidad en
la que se declara, y es la unidad en la que se mide.

Aquí no hay IA, no se manda nada a ninguna parte y no se toca el
archivo del contador: se abre, se lee y se cierra.
"""

from pathlib import Path

from app import bitacora, db, formulario, instrucciones, pasada
from app.plantilla_210 import HOJA_CAPTURA

# Cuánto se puede diferir y aun así llamarlo «coincide». Un peso, que es
# el redondeo con el que trabaja la declaración.
TOLERANCIA = 1.0

COINCIDE = "coincide"
DIFIERE = "difiere"
SOLO_TAXI = "solo_taxi"
SOLO_CONTADOR = "solo_contador"


class ComparacionInvalida(ValueError):
    """El archivo no se puede comparar. El mensaje es para el contador."""


def _celdas_por_renglon():
    """Qué casillas de la plantilla pertenecen a cada renglón.

    Sale de `formulario.celdas_de_renglon`, que ya sabe que el bloque de
    un renglón son sus filas de detalle y no la fila que lleva su
    número, y que deja fuera las casillas que ninguna fórmula lee.
    """
    mapa = {}
    for numero in sorted({c["renglon"] for c in formulario.mapa()["celdas"]
                          if c["renglon"]}, key=int):
        celdas = [c["celda"] for c in formulario.celdas_de_renglon(numero)]
        if celdas:
            mapa["R" + numero] = celdas
    return mapa


def _lo_que_lleno_el_contador(ruta_xlsx):
    """Lo que dice su archivo, sumado por renglón: {"R32": 84600000.0}."""
    ruta = Path(ruta_xlsx)
    try:
        valores = formulario.valores_calculados(ruta)
    except Exception:
        raise ComparacionInvalida(
            "No se pudo abrir ese archivo como un Formulario 210. Suba el"
            " .xlsx de la misma plantilla que usa el programa."
        )
    if not valores:
        raise ComparacionInvalida(
            "Ese archivo no tiene la hoja «%s», así que no es la plantilla"
            " del 210 que usa el programa." % HOJA_CAPTURA
        )

    suyos = {}
    for renglon, celdas in _celdas_por_renglon().items():
        total = 0.0
        hubo = False
        for celda in celdas:
            valor = valores.get(celda)
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                continue
            if valor:
                total += float(valor)
                hubo = True
        if hubo:
            suyos[renglon] = total
    return suyos


def _lo_que_propuso_taxi(cliente_id):
    """La propuesta vigente, sumada por renglón, con su nivel."""
    informe = pasada.resumen(cliente_id)
    nuestros = {}
    for renglon in informe["renglones"]:
        if renglon["total"] is None:
            continue
        nuestros[renglon["renglon"]] = {
            "total": float(renglon["total"]),
            "nivel": renglon["nivel"],
            "nombre": renglon["nombre"],
        }
    return nuestros, informe


def comparar(cliente, ruta_xlsx, nombre_archivo=""):
    """Compara y guarda el resultado. Devuelve el informe completo.

    No cambia ni una cifra del cliente: esto es una medición.
    """
    cliente_id = cliente["id"]
    nuestros, informe = _lo_que_propuso_taxi(cliente_id)
    if not informe["hay_pasada"]:
        raise ComparacionInvalida(
            "Todavía no hay una propuesta que comparar. Corra primero la"
            " propuesta del formulario."
        )

    suyos = _lo_que_lleno_el_contador(ruta_xlsx)
    nombres = pasada.catalogo_de_renglones()

    filas = []
    resumen = {COINCIDE: 0, DIFIERE: 0, SOLO_TAXI: 0, SOLO_CONTADOR: 0}
    por_nivel = {nivel: {COINCIDE: 0, DIFIERE: 0, SOLO_TAXI: 0}
                 for nivel in instrucciones.NIVELES}

    for renglon in sorted(set(nuestros) | set(suyos),
                          key=lambda c: int(instrucciones._numero_de_renglon(c) or 0)):
        nuestro = nuestros.get(renglon)
        suyo = suyos.get(renglon)
        numero = instrucciones._numero_de_renglon(renglon)

        if nuestro is not None and suyo is not None:
            diferencia = nuestro["total"] - suyo
            estado = COINCIDE if abs(diferencia) <= TOLERANCIA else DIFIERE
        elif nuestro is not None:
            diferencia = nuestro["total"]
            estado = SOLO_TAXI
        else:
            diferencia = -suyo
            estado = SOLO_CONTADOR

        resumen[estado] += 1
        if nuestro is not None:
            por_nivel[nuestro["nivel"]][estado] += 1

        filas.append({
            "renglon": renglon,
            "nombre": (nuestro or {}).get("nombre") or nombres.get(numero, ""),
            "taxi": None if nuestro is None else nuestro["total"],
            "contador": suyo,
            "diferencia": diferencia,
            "estado": estado,
            "nivel": (nuestro or {}).get("nivel", ""),
        })

    detalle = {
        "renglones": filas,
        "por_nivel": por_nivel,
        "pasada": {
            "id": informe["pasada"]["id"],
            "modelo": informe["pasada"]["modelo"],
            "proveedor": informe["pasada"]["proveedor"],
            "costo_usd": informe["pasada"]["costo_usd"],
        },
    }
    conteo = {
        "coinciden": resumen[COINCIDE],
        "difieren": resumen[DIFIERE],
        "solo_taxi": resumen[SOLO_TAXI],
        "solo_contador": resumen[SOLO_CONTADOR],
    }
    db.guardar_comparacion(cliente_id, informe["pasada"]["id"],
                           nombre_archivo, conteo, detalle)
    bitacora.anotar(cliente_id, bitacora.COMPARACION, nombre_archivo)

    conteo.update(detalle)
    conteo["acierto"] = _acierto(conteo)
    return conteo


def _acierto(conteo):
    """De los renglones que Tax-i propuso, en qué porcentaje acertó.

    Se mide contra lo que propuso, no contra todo el formulario: un
    renglón que él llenó y Tax-i ni vio se cuenta aparte, en
    'solo_contador', porque es un problema distinto —no verlo no es lo
    mismo que verlo mal— y arreglarlo es otro trabajo.
    """
    propuestos = conteo["coinciden"] + conteo["difieren"] + conteo["solo_taxi"]
    if not propuestos:
        return 0.0
    return round(100.0 * conteo["coinciden"] / propuestos, 1)


def ultima(cliente_id):
    """La última comparación de un cliente, o None."""
    guardada = db.ultima_comparacion(cliente_id)
    if guardada is None:
        return None
    informe = dict(guardada["detalle"])
    informe.update({
        "coinciden": guardada["coinciden"],
        "difieren": guardada["difieren"],
        "solo_taxi": guardada["solo_taxi"],
        "solo_contador": guardada["solo_contador"],
        "hecha_en": guardada["hecha_en"],
        "archivo": guardada["archivo"],
    })
    informe["acierto"] = _acierto(informe)
    return informe
