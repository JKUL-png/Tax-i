"""
Prueba de la lectura de documentos: los XML, con código y gratis.

Se corre así, desde la carpeta del proyecto:

    .venv/bin/python pruebas/probar_extraccion.py

En Windows:

    .venv\\Scripts\\python pruebas\\probar_extraccion.py

Aquí NO hay ninguna llamada a un modelo, y la prueba lo comprueba: corre
con IA_PROVEEDOR=ninguno y falla si alguien mete una dependencia de
proveedores en el camino de leer un XML.

Trabaja sobre una base de datos aparte, en una carpeta temporal. La base
del contador no se toca.

Qué cambió y por qué esta prueba es tan corta ahora
---------------------------------------------------
Este archivo probaba dos cosas: que un XML lo leyera el programa, y que
un PDF pasara por la IA una sola vez. Lo segundo se fue en septiembre de
2026: los PDF los lee la pasada del formulario, todo el cliente junto y
en una sola llamada, y eso se prueba en pruebas/probar_pasada.py.

Lo que quedó aquí es lo que no cuesta nada y corre solo.

Lo que comprueba:

  A. Un XML lo lee el PROGRAMA, no la IA. Es la regla del proyecto: si
     hay estructura, se parsea; no se le pregunta a un modelo.
  B. Lo que no es XML queda pendiente, y eso NO es un fallo: es que lo
     lee la pasada.
  C. Lo ya leído no se vuelve a leer.
  D. RentAI arma su contexto con las filas de la BASE, no remandando los
     documentos, y distingue lo que leyó el programa de lo que leyó un
     modelo.
  E. Con la IA apagada, todo esto funciona igual de completo.
"""

import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

resultados = []


def comprobar(descripcion, condicion, detalle=""):
    resultados.append(bool(condicion))
    print(("  OK    " if condicion else "  FALLA ") + descripcion
          + (("  [" + str(detalle)[:80] + "]") if detalle else ""))


def titulo(texto):
    print("\n" + texto)


class _SinIA:
    proveedor = "ninguno"
    llave = ""
    base_url = ""
    modelo = ""
    ia_disponible = False
    motivo = "Modo sin IA activo."


# Una factura electrónica de mentira, con la forma real (UBL 2.1).
FACTURA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:ID>FE-991</cbc:ID>
 <cbc:IssueDate>2025-03-04</cbc:IssueDate>
 <cac:AccountingSupplierParty><cac:Party><cac:PartyTaxScheme>
   <cbc:RegistrationName>Droguería Ejemplo SAS</cbc:RegistrationName>
   <cbc:CompanyID>900123456</cbc:CompanyID>
 </cac:PartyTaxScheme></cac:Party></cac:AccountingSupplierParty>
 <cac:LegalMonetaryTotal>
   <cbc:PayableAmount currencyID="COP">250000</cbc:PayableAmount>
 </cac:LegalMonetaryTotal>
</Invoice>""".encode("utf-8")


def main():
    print("=" * 62)
    print(" Leer los XML: con código, gratis y sin salir del computador")
    print("=" * 62)

    carpeta = Path(tempfile.mkdtemp(prefix="taxi-extraccion-"))

    try:
        from app import db
        db.CARPETA_DATOS = carpeta
        db.ARCHIVO_BD = carpeta / "base.db"
        db.crear_tablas()

        from app import documentos, extraccion, rentai
        documentos.CARPETA_ARCHIVOS = carpeta / "archivos"
        rentai.CONFIG = _SinIA()

        cliente = db.crear_cliente("Cliente de prueba lectura", "05", None)
        cliente_id = cliente["id"]

        def subir(nombre, contenido):
            guardado, tamano = documentos.guardar_contenido(
                cliente_id, nombre, contenido
            )
            return db.crear_documento(
                cliente_id, nombre, guardado,
                Path(nombre).suffix.lstrip("."), tamano
            )

        documento_xml = subir("factura.xml", FACTURA_XML)
        documento_txt = subir(
            "certificado.txt",
            "CERTIFICADO DE INGRESOS\nSalarios 45.000.000\n".encode("utf-8")
        )

        # --------------------------------------------------------------
        titulo("A. Un XML lo lee el programa, NO la IA")
        # --------------------------------------------------------------
        informe = extraccion.extraer(documento_xml)

        comprobar("el XML se leyó", informe["estado"] == "listo", informe)
        comprobar("y lo leyó el CÓDIGO, no un modelo",
                  informe["origen"] == "codigo", informe["origen"])

        datos = db.listar_datos_extraidos(
            cliente_id, documento_id=documento_xml["id"])
        conceptos = {fila["concepto"]: fila["valor"] or fila["detalle"]
                     for fila in datos}
        comprobar("sacó el número del documento",
                  conceptos.get("Número del documento") == "FE-991")
        comprobar("sacó el NIT del emisor",
                  conceptos.get("NIT del emisor") == "900123456")
        comprobar("sacó el total, como cifra",
                  conceptos.get("Total del documento") == "250000")
        comprobar("todo quedó marcado como leído por el programa",
                  all(f["origen"] == "codigo" for f in datos))

        # --------------------------------------------------------------
        titulo("B. Lo que no es XML queda pendiente, y eso no es un fallo")
        # --------------------------------------------------------------
        informe = extraccion.extraer(documento_txt)
        comprobar("un texto no se lee aquí", informe["estado"] == "pendiente",
                  informe["estado"])
        comprobar("y se dice sin alarma quién lo va a leer",
                  "propuesta del formulario" in informe["motivo"],
                  informe["motivo"])
        comprobar("no se le inventó ni un dato",
                  db.listar_datos_extraidos(
                      cliente_id, documento_id=documento_txt["id"]) == [])

        # --------------------------------------------------------------
        titulo("C. Lo ya leído no se vuelve a leer")
        # --------------------------------------------------------------
        antes = len(db.listar_datos_extraidos(cliente_id))
        pendientes = extraccion.leer_xml_pendientes(cliente_id)
        comprobar("el XML ya leído no vuelve a la lista",
                  all(i["documento_id"] != documento_xml["id"]
                      for i in pendientes),
                  [i["documento_id"] for i in pendientes])
        comprobar("y no se duplicó ni un dato",
                  len(db.listar_datos_extraidos(cliente_id)) == antes)

        # --------------------------------------------------------------
        titulo("D. RentAI arma su contexto con la BASE, no con los archivos")
        # --------------------------------------------------------------
        resumen = rentai.resumen_de_documentos(cliente_id)

        comprobar("el contexto trae lo que se le sacó al XML",
                  "FE-991" in resumen, resumen[:70])
        comprobar("y dice que ese lo leyó el programa y es exacto",
                  "exacto" in resumen)
        comprobar("del que no se ha leído dice que no sabe qué dice",
                  "certificado.txt" in resumen
                  and "TODAVÍA NO SE HAN LEÍDO" in resumen)
        comprobar("y le dice al modelo que NO adivine su contenido",
                  "No adivines su contenido" in resumen)
        comprobar("el texto del XML NO se remanda entero",
                  "PayableAmount" not in resumen)

        # --------------------------------------------------------------
        titulo("E. Todo esto funciona con IA_PROVEEDOR=ninguno")
        # --------------------------------------------------------------
        import app.proveedores as proveedores
        llamadas = {"cuantas": 0}
        original = proveedores.conversar_detallado

        def espia(*args, **kwargs):
            llamadas["cuantas"] += 1
            return original(*args, **kwargs)

        proveedores.conversar_detallado = espia
        try:
            otro = subir("factura2.xml", FACTURA_XML.replace(
                b"FE-991", b"FE-992"))
            informe = extraccion.extraer(otro)
        finally:
            proveedores.conversar_detallado = original

        comprobar("leer un XML no llama a ningún servicio",
                  llamadas["cuantas"] == 0, llamadas["cuantas"])
        comprobar("y sale bien igual", informe["estado"] == "listo")

        estado = extraccion.resumen(cliente_id)
        comprobar("el resumen cuenta los dos XML leídos",
                  estado["estados"]["listo"] == 2, str(estado["estados"]))
        comprobar("y el texto sigue pendiente, esperando la pasada",
                  estado["estados"]["pendiente"] == 1, str(estado["estados"]))

    finally:
        shutil.rmtree(carpeta, ignore_errors=True)

    print()
    print("=" * 62)
    print(" %d de %d comprobaciones pasaron."
          % (sum(resultados), len(resultados)))
    print(" Todo bien." if all(resultados) else " HAY FALLAS.")
    print("=" * 62)
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
