"""
Prueba del Paso 2: escribir en la plantilla sin dañarla.

Se corre así, desde la carpeta del proyecto:

    .venv/bin/python pruebas/probar_escritura_210.py

No usa ninguna librería de pruebas: es un programa normal que hace cosas y
dice si salieron bien. Imprime una línea por comprobación. Al final dice
cuántas pasaron.

Lo que comprueba, en dos partes:

  A. Que se NIEGUE a escribir donde no debe (fórmula, otra hoja, otra
     columna, texto, celda combinada, fila fuera de la tabla).
  B. Que cuando sí escribe, el archivo quede sano: el original intacto, las
     902 fórmulas iguales, las 22 imágenes en su lugar y los valores
     escritos donde se pidió.
"""

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from openpyxl import load_workbook  # noqa: E402

from app.escribir_210 import (  # noqa: E402
    EscrituraBloqueada,
    EscritorPlantilla,
)
from app.plantilla_210 import contar_formulas_del_libro, es_formula  # noqa: E402

PLANTILLAS = RAIZ / "plantillas"

resultados = []


def comprobar(descripcion, condicion, detalle=""):
    """Anota una comprobación y la imprime."""
    resultados.append(bool(condicion))
    marca = "OK  " if condicion else "FALLA"
    linea = f"  {marca}  {descripcion}"
    if detalle:
        linea += f"  [{detalle}]"
    print(linea)


def se_niega(descripcion, funcion):
    """Comprueba que una escritura sea rechazada, y muestra el motivo."""
    try:
        funcion()
    except EscrituraBloqueada as error:
        comprobar(descripcion, True, str(error)[:70])
        return
    comprobar(descripcion, False, "NO se negó: la escribió")


def huella(ruta):
    return hashlib.md5(Path(ruta).read_bytes()).hexdigest()


def buscar_plantilla():
    encontradas = sorted(
        p for p in PLANTILLAS.glob("*.xlsx") if not p.name.startswith("~$")
    )
    if not encontradas:
        print("No hay ninguna plantilla .xlsx en plantillas/. No se puede probar.")
        sys.exit(1)
    return encontradas[0]


def main():
    plantilla = buscar_plantilla()
    print(f"Plantilla: {plantilla.name}")

    huella_antes = huella(plantilla)
    formulas_antes = contar_formulas_del_libro(plantilla)
    partes_antes = set(zipfile.ZipFile(plantilla).namelist())

    # ------------------------------------------------------------------
    print("\nA. Escrituras que se deben rechazar")
    # ------------------------------------------------------------------
    escritor = EscritorPlantilla(plantilla, nombre_salida="prueba_paso2.xlsx")

    se_niega(
        "celda con fórmula (I28 = IF(ROUND(H30*1%...)))",
        lambda: escritor.escribir("I28", 123, documento="prueba"),
    )
    se_niega(
        "celda con fórmula escrita a mano (G58)",
        lambda: escritor.escribir("G58", 123, documento="prueba"),
    )
    se_niega(
        "otra hoja (Formulario 210)",
        lambda: escritor.escribir(
            "G32", 123, documento="prueba", hoja="Formulario 210"
        ),
    )
    se_niega(
        "hoja de tablas estructurales (Tablas de impuestos)",
        lambda: escritor.escribir(
            "G32", 123, documento="prueba", hoja="Tablas de impuestos"
        ),
    )
    se_niega(
        "columna que no es de valores (F32, la descripción)",
        lambda: escritor.escribir("F32", 123, documento="prueba"),
    )
    se_niega(
        "texto en vez de número",
        lambda: escritor.escribir("G32", "1.500.000", documento="prueba"),
    )
    se_niega(
        "vacío en vez de 0",
        lambda: escritor.escribir("G32", None, documento="prueba"),
    )
    se_niega(
        "celda combinada que no es la esquina (H45)",
        lambda: escritor.escribir("H45", 123, documento="prueba"),
    )
    se_niega(
        "fila fuera de la tabla (G5000)",
        lambda: escritor.escribir("G5000", 123, documento="prueba"),
    )
    se_niega(
        "coordenada inventada (ZZ)",
        lambda: escritor.escribir("ZZ", 123, documento="prueba"),
    )

    comprobar(
        "después de 10 rechazos no quedó ningún cambio anotado",
        escritor.cambios == {} and escritor.bitacora == [],
        f"cambios={len(escritor.cambios)}",
    )

    # ------------------------------------------------------------------
    print("\nB. Escrituras válidas")
    # ------------------------------------------------------------------
    escritor.escribir("G32", 1500000, documento="factura_electronica.pdf")
    escritor.escribir("H104", 2300000, documento="certificado_banco.pdf")
    escritor.escribir("I484", 0, documento="digitado por el contador")
    # La misma celda dos veces: debe quedar el último valor, y la bitácora
    # debe registrar los dos movimientos.
    escritor.escribir("G32", 1750000, documento="factura_electronica.pdf (v2)")

    ruta_salida, ruta_bitacora = escritor.guardar()
    print(f"  archivo generado: {ruta_salida.relative_to(RAIZ)}")

    # ------------------------------------------------------------------
    print("\nC. El original quedó intacto")
    # ------------------------------------------------------------------
    comprobar(
        "la plantilla original no cambió (misma huella MD5)",
        huella(plantilla) == huella_antes,
    )
    comprobar(
        "el archivo generado es otro archivo",
        ruta_salida.resolve() != plantilla.resolve(),
    )

    # ------------------------------------------------------------------
    print("\nD. El archivo generado quedó sano")
    # ------------------------------------------------------------------
    partes_despues = set(zipfile.ZipFile(ruta_salida).namelist())
    perdidas = partes_antes - partes_despues
    comprobar(
        f"no se perdió ninguna de las {len(partes_antes)} partes internas",
        not perdidas,
        f"perdidas: {sorted(perdidas)[:3]}" if perdidas else "",
    )

    imagenes_antes = [p for p in partes_antes if p.startswith("xl/media/")]
    imagenes_despues = [p for p in partes_despues if p.startswith("xl/media/")]
    comprobar(
        f"las {len(imagenes_antes)} imágenes siguen ahí (incluidas las de Copyright)",
        len(imagenes_antes) == len(imagenes_despues),
        f"{len(imagenes_despues)} encontradas",
    )

    formulas_despues = contar_formulas_del_libro(ruta_salida)
    comprobar(
        f"las {sum(formulas_antes.values())} fórmulas del libro siguen ahí",
        formulas_antes == formulas_despues,
        f"antes {sum(formulas_antes.values())} / después {sum(formulas_despues.values())}",
    )

    libro_antes = load_workbook(plantilla, data_only=False)
    libro_despues = load_workbook(ruta_salida, data_only=False)
    comprobar(
        "las 15 hojas siguen con el mismo nombre y en el mismo orden",
        libro_antes.sheetnames == libro_despues.sheetnames,
    )

    distintas = []
    for nombre in libro_antes.sheetnames:
        hoja_a, hoja_d = libro_antes[nombre], libro_despues[nombre]
        for fila in hoja_a.iter_rows():
            for celda in fila:
                if es_formula(celda.value):
                    if hoja_d[celda.coordinate].value != celda.value:
                        distintas.append(f"{nombre}!{celda.coordinate}")
    comprobar(
        "ni una sola fórmula cambió de texto",
        not distintas,
        f"cambiadas: {distintas[:3]}" if distintas else "",
    )

    # ------------------------------------------------------------------
    print("\nE. Los valores quedaron donde se pidió")
    # ------------------------------------------------------------------
    hoja = libro_despues["Detalle renglón 210"]
    comprobar("G32 quedó en 1750000 (el último valor escrito)",
              hoja["G32"].value == 1750000, repr(hoja["G32"].value))
    comprobar("H104 quedó en 2300000",
              hoja["H104"].value == 2300000, repr(hoja["H104"].value))
    comprobar("I484 quedó en 0 (limpiar es escribir 0, no vaciar)",
              hoja["I484"].value == 0, repr(hoja["I484"].value))

    hoja_original = libro_antes["Detalle renglón 210"]
    intactas = ["G44", "H105", "I665", "G115", "H204"]
    iguales = all(
        hoja[c].value == hoja_original[c].value for c in intactas
    )
    comprobar("las celdas vecinas que no se tocaron siguen igual", iguales,
              ", ".join(intactas))

    formato_igual = all(
        hoja[c].number_format == hoja_original[c].number_format
        for c in ("G32", "H104", "I484")
    )
    comprobar("el formato de número de las celdas escritas no cambió",
              formato_igual)

    xml = zipfile.ZipFile(ruta_salida).read("xl/workbook.xml").decode("utf-8")
    comprobar("el libro quedó marcado para recalcular al abrirlo en Excel",
              "fullCalcOnLoad" in xml)

    # ------------------------------------------------------------------
    print("\nF. La bitácora")
    # ------------------------------------------------------------------
    datos = json.loads(ruta_bitacora.read_text(encoding="utf-8"))
    cambios = datos["cambios"]
    comprobar("quedaron los 4 movimientos, no 3", len(cambios) == 4,
              f"{len(cambios)} movimientos")
    primero = cambios[0]
    comprobar(
        "cada movimiento trae hoja, celda, antes, después, documento y hora",
        all(k in primero for k in
            ("hoja", "celda", "valor_anterior", "valor_nuevo", "documento",
             "fecha_hora")),
    )
    comprobar("el primer cambio de G32 registra el valor anterior (0)",
              primero["celda"] == "G32" and primero["valor_anterior"] == 0,
              f"anterior={primero['valor_anterior']!r}")
    comprobar("el segundo cambio de G32 registra como anterior el 1500000",
              cambios[3]["valor_anterior"] == 1500000,
              f"anterior={cambios[3]['valor_anterior']!r}")
    comprobar("la hora quedó registrada",
              bool(re.match(r"\d{4}-\d{2}-\d{2}T", primero["fecha_hora"])),
              primero["fecha_hora"])

    # ------------------------------------------------------------------
    print("\nG. No se puede seguir escribiendo después de guardar")
    # ------------------------------------------------------------------
    se_niega(
        "escribir después de guardar",
        lambda: escritor.escribir("G44", 1, documento="prueba"),
    )

    total = len(resultados)
    buenas = sum(resultados)
    print(f"\n{buenas} de {total} comprobaciones pasaron.")
    if buenas != total:
        print("HAY FALLAS. No seguir al Paso 3 sin arreglarlas.")
        return 1
    print("Todo bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
