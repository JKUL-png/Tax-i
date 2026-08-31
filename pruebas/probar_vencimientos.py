"""
Revisa la tabla de vencimientos de app/vencimientos.py.

Corre con:
    .venv/bin/python pruebas/probar_vencimientos.py

Si la tabla está vacía, lo dice y no falla: vacía es el estado de
fábrica, y con la tabla vacía el programa funciona igual que siempre
(la fecha se escribe a mano).

Si tiene fechas, revisa que estén las 100 combinaciones de dígitos, que
las fechas existan de verdad y que ninguna caiga en fin de semana.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import vencimientos  # noqa: E402


def main():
    print("=" * 62)
    print(" Revisión de la tabla de vencimientos")
    print("=" * 62)

    anios = vencimientos.anios_disponibles()

    if not anios:
        print()
        print("  No hay ninguna tabla cargada todavía.")
        print()
        print("  Eso NO es un error: el programa funciona igual y la fecha")
        print("  de vencimiento se escribe a mano, como hasta ahora.")
        print()
        print("  Para cargarla, abra app/vencimientos.py, busque TABLAS y")
        print("  copie las fechas del calendario tributario oficial de su")
        print("  año gravable. Después vuelva a correr esta revisión.")
        print()
        return 0

    problemas_totales = 0
    for anio in anios:
        print()
        print("Año gravable " + anio)
        print("-" * (13 + len(anio)))

        problemas = vencimientos.revisar_tabla(anio)
        if not problemas:
            print("  OK     las 100 combinaciones están y las fechas cuadran")
        else:
            for problema in problemas:
                print("  REVISE " + problema)
            problemas_totales += len(problemas)

    print()
    print("=" * 62)
    if problemas_totales == 0:
        print(" Todo bien. La tabla se puede usar.")
    else:
        print(" Hay %d cosas por revisar antes de usar la tabla." % problemas_totales)
    print("=" * 62)
    return 1 if problemas_totales else 0


if __name__ == "__main__":
    sys.exit(main())
