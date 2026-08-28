"""
Recálculo del libro con LibreOffice.

Para qué hace falta
-------------------
Cuando se escribe un valor en una celda, los resultados que quedaron
guardados en las celdas de fórmula son de antes del cambio. Excel los
vuelve a calcular al abrir el archivo, así que para el contador todo se ve
bien. El problema es nuestro: el programa necesita leer los totales para
mostrarlos en pantalla, y si los lee del archivo tal como quedó, lee
números viejos.

La solución es pasarle el archivo a LibreOffice, que sí puede recalcular
sin que nadie abra nada, y que vuelva a guardarlo con los resultados
adentro.

Si LibreOffice no está instalado, no pasa nada grave: el archivo se
entrega igual y el programa avisa que los totales solo se verán al abrirlo
en Excel. Nunca se rompe el flujo por esto.

Un detalle que costó encontrar
------------------------------
LibreOffice, de fábrica, NO recalcula al abrir un archivo de Excel: trae
puesto "nunca recalcular". Hay que decírselo con un ajuste de
configuración (OOXMLRecalcMode). Sin ese ajuste la conversión funciona,
no da ningún error, y devuelve el archivo con los totales viejos — que es
la peor forma de fallar, porque parece que funcionó.
"""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from openpyxl import load_workbook

# Cuánto se espera a LibreOffice antes de darlo por perdido. Este libro
# tiene 902 fórmulas y en las pruebas tardó menos de 3 segundos, así que
# 120 sobra de lejos. Se deja alto igual: un computador lento con un libro
# más grande no debería fallar por apuro.
TIEMPO_LIMITE = 120

# Dónde suele quedar instalado LibreOffice en cada sistema. Se prueban en
# orden y se usa el primero que exista.
RUTAS_CONOCIDAS = (
    # Mac
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    # Windows
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    # Linux
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
    "/snap/bin/libreoffice",
)

# Los errores que Excel muestra dentro de una celda. Si aparece uno de
# estos después de recalcular, algo se rompió.
ERRORES_DE_EXCEL = frozenset({
    "#REF!", "#NAME?", "#VALUE!", "#DIV/0!", "#N/A", "#NULL!", "#NUM!",
    "#GETTING_DATA", "#SPILL!", "#CALC!",
})

# El ajuste que obliga a recalcular. Se le pasa a LibreOffice en un perfil
# de usuario propio y desechable, para no tocarle la configuración al
# usuario ni chocar con una ventana de LibreOffice que esté abierta.
AJUSTE_RECALCULAR = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"
 xmlns:xs="http://www.w3.org/2001/XMLSchema"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop
 oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop
 oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>
</oor:items>
"""


def buscar_libreoffice():
    """Devuelve la ruta del programa de LibreOffice, o None si no está.

    Primero mira las rutas típicas de cada sistema y después busca en el
    PATH, por si el usuario lo instaló en otro lado.
    """
    for ruta in RUTAS_CONOCIDAS:
        candidata = Path(ruta)
        if candidata.exists():
            return candidata
    for nombre in ("soffice", "libreoffice"):
        encontrada = shutil.which(nombre)
        if encontrada:
            return Path(encontrada)
    return None


def celdas_con_error(ruta_xlsx):
    """Lista las celdas que quedaron mostrando un error de Excel.

    Se lee con data_only=True, que trae los resultados en vez de las
    fórmulas. Es la única forma de ver un #REF!. Esta carga es de solo
    lectura y NUNCA se guarda: si se guardara, borraría las fórmulas.
    """
    libro = load_workbook(Path(ruta_xlsx), data_only=True)
    encontradas = []
    for nombre in libro.sheetnames:
        hoja = libro[nombre]
        for fila in hoja.iter_rows():
            for celda in fila:
                valor = celda.value
                if isinstance(valor, str) and valor.strip() in ERRORES_DE_EXCEL:
                    encontradas.append(f"{nombre}!{celda.coordinate}={valor.strip()}")
    return encontradas


def recalcular(ruta_xlsx, tiempo_limite=TIEMPO_LIMITE):
    """Recalcula el libro con LibreOffice y lo vuelve a guardar.

    Devuelve un informe (diccionario) y NUNCA lanza una excepción por que
    LibreOffice falte o falle: en ese caso el archivo se queda como estaba
    y el informe explica por qué. El programa tiene que seguir andando.

        {"recalculado": True/False,
         "motivo": "...",              texto para mostrarle al contador
         "segundos": 1.8,
         "programa": "/Applications/..."}
    """
    ruta_xlsx = Path(ruta_xlsx)
    informe = {
        "recalculado": False,
        "motivo": "",
        "segundos": 0.0,
        "programa": "",
    }

    programa = buscar_libreoffice()
    if programa is None:
        informe["motivo"] = (
            "LibreOffice no está instalado, así que no se pudieron calcular"
            " los totales. El archivo está completo y correcto: los totales"
            " aparecen al abrirlo en Excel."
        )
        return informe
    informe["programa"] = str(programa)

    comenzó = time.monotonic()

    # Carpetas desechables: un perfil de usuario propio para LibreOffice y
    # una carpeta de salida. Las dos se borran solas al terminar.
    with tempfile.TemporaryDirectory() as temporal:
        temporal = Path(temporal)
        perfil = temporal / "perfil"
        (perfil / "user").mkdir(parents=True)
        # encoding explícito: sin esto, en Windows se escribe en cp1252.
        (perfil / "user" / "registrymodifications.xcu").write_text(
            AJUSTE_RECALCULAR, encoding="utf-8"
        )
        salida = temporal / "salida"
        salida.mkdir()

        orden = [
            str(programa),
            "--headless",       # sin ventanas
            "--norestore",      # que no intente recuperar documentos
            "--nolockcheck",
            f"-env:UserInstallation={perfil.as_uri()}",
            "--convert-to", "xlsx",
            "--outdir", str(salida),
            str(ruta_xlsx),
        ]

        try:
            resultado = subprocess.run(
                orden,
                capture_output=True,
                timeout=tiempo_limite,
                # encoding explícito y errors="replace": los mensajes de
                # LibreOffice traen tildes, y en Windows se leen en cp1252
                # y revientan la lectura.
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            informe["segundos"] = round(time.monotonic() - comenzó, 1)
            informe["motivo"] = (
                f"LibreOffice se demoró más de {tiempo_limite} segundos y se"
                f" canceló. El archivo está completo: los totales aparecen"
                f" al abrirlo en Excel."
            )
            return informe
        except OSError as error:
            informe["segundos"] = round(time.monotonic() - comenzó, 1)
            informe["motivo"] = (
                f"No se pudo ejecutar LibreOffice ({error}). El archivo está"
                f" completo: los totales aparecen al abrirlo en Excel."
            )
            return informe

        informe["segundos"] = round(time.monotonic() - comenzó, 1)

        if resultado.returncode != 0:
            informe["motivo"] = (
                f"LibreOffice terminó con un error (código"
                f" {resultado.returncode}). El archivo está completo: los"
                f" totales aparecen al abrirlo en Excel."
            )
            return informe

        recalculado = salida / ruta_xlsx.name
        if not recalculado.exists():
            informe["motivo"] = (
                "LibreOffice no devolvió ningún archivo. El archivo está"
                " completo: los totales aparecen al abrirlo en Excel."
            )
            return informe

        # Solo aquí se reemplaza el archivo. Si algo hubiera fallado antes,
        # el archivo original de trabajo sigue intacto.
        shutil.copy2(recalculado, ruta_xlsx)

    informe["recalculado"] = True
    informe["motivo"] = (
        f"Totales calculados con LibreOffice en {informe['segundos']}"
        f" segundos."
    )
    return informe
