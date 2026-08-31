"""
El calendario de vencimientos, por los dos últimos dígitos de la cédula.

Qué es y qué no es
------------------
Esto NO calcula nada. Es una tabla de consulta: usted pega aquí las
fechas del calendario tributario oficial y el programa las busca. Es lo
mismo que hacía el contador mirando el PDF de la DIAN, pero sin tener
que mirarlo 150 veces seguidas después de importar un Excel.

No cruza la línea legal del proyecto: no dice si alguien está obligado a
declarar, ni calcula impuesto, ni sugiere cómo declarar. Solo dice en
qué fecha vence el plazo de quien tenga esos dos dígitos, y esa fecha
sale de una tabla que escribió el contador.

**Las fechas no se inventan.** Si la tabla está vacía —como viene de
fábrica—, el programa se comporta exactamente igual que antes: la fecha
se escribe a mano. Nunca propone una fecha que nadie le haya dado.

Cómo se llena
-------------
Abra este archivo, busque TABLAS, y escriba las fechas del calendario
oficial de su año gravable. Cada renglón es:

    ("00", "2026-08-12"),      dos dígitos, fecha en AAAA-MM-DD

Después, en la lista de clientes, aparece el botón para aplicarla.

Compruebe la tabla con:

    .venv/bin/python pruebas/probar_vencimientos.py

Esa prueba revisa que estén los 100 dígitos, que las fechas existan y
que no haya ninguna en fin de semana (en el calendario oficial no las
hay, así que una fecha en sábado casi siempre es un error de dedo).
"""

from datetime import date

# ----------------------------------------------------------
# Las tablas, por año gravable
#
# VIENEN VACÍAS A PROPÓSITO. Las fechas salen del calendario tributario
# oficial y no se sacan de memoria: quien las ponga tiene que estar
# mirando el documento de la DIAN.
#
# Formato:
#   "2025": [
#       ("00", "2026-08-12"),
#       ("01", "2026-08-12"),
#       ...
#       ("99", "2026-10-24"),
#   ],
# ----------------------------------------------------------

TABLAS = {
    # "2025": [ ... ],
}


def anios_disponibles():
    """Los años gravables que tienen tabla cargada."""
    return sorted(a for a, filas in TABLAS.items() if filas)


def hay_tabla(anio=None):
    """Dice si hay alguna tabla cargada con la que trabajar."""
    if anio is None:
        return bool(anios_disponibles())
    return bool(TABLAS.get(str(anio)))


def anio_mas_reciente():
    """El último año gravable con tabla, o None si no hay ninguna."""
    disponibles = anios_disponibles()
    return disponibles[-1] if disponibles else None


def _como_diccionario(anio):
    """La tabla de un año, en forma de {dos_digitos: fecha}."""
    return {
        str(digitos).zfill(2): fecha
        for digitos, fecha in TABLAS.get(str(anio), [])
    }


def buscar(dos_digitos, anio=None):
    """La fecha de vencimiento de esos dos dígitos, o None.

    Devuelve None cuando no hay tabla, cuando el año no está cargado o
    cuando esos dígitos no aparecen. None significa "no sé", y el
    programa deja la fecha como estaba en vez de poner cualquier cosa.
    """
    anio = str(anio) if anio else anio_mas_reciente()
    if not anio:
        return None
    limpios = str(dos_digitos or "").strip().zfill(2)
    return _como_diccionario(anio).get(limpios)


def revisar_tabla(anio):
    """Revisa una tabla y devuelve la lista de problemas que le ve.

    Lista vacía quiere decir que está bien. Se usa en la prueba y antes
    de aplicarla en lote: es preferible avisar de un error de dedo que
    escribirle a 150 clientes una fecha equivocada.
    """
    problemas = []
    filas = TABLAS.get(str(anio))

    if not filas:
        return ["No hay tabla cargada para el año gravable " + str(anio) + "."]

    vistos = {}
    for digitos, texto in filas:
        limpios = str(digitos).strip().zfill(2)

        if not limpios.isdigit() or len(limpios) != 2:
            problemas.append("«%s» no son dos dígitos." % digitos)
            continue
        if limpios in vistos:
            problemas.append("Los dígitos %s están dos veces." % limpios)
            continue
        vistos[limpios] = texto

        try:
            cuando = date.fromisoformat(str(texto))
        except (ValueError, TypeError):
            problemas.append(
                "La fecha de %s («%s») no está en formato AAAA-MM-DD."
                % (limpios, texto)
            )
            continue

        # weekday(): 5 es sábado y 6 domingo. El calendario oficial no
        # pone vencimientos en fin de semana, así que esto casi siempre
        # es un error al copiar. Se avisa, no se corrige solo.
        if cuando.weekday() >= 5:
            problemas.append(
                "La fecha de %s (%s) cae en fin de semana. Revísela."
                % (limpios, texto)
            )

    faltantes = [str(n).zfill(2) for n in range(100)
                 if str(n).zfill(2) not in vistos]
    if faltantes:
        problemas.append(
            "Faltan %d combinaciones de dígitos: %s%s"
            % (len(faltantes), ", ".join(faltantes[:10]),
               "…" if len(faltantes) > 10 else "")
        )

    return problemas
