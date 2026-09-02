"""
Prueba de la lectura de documentos: leer una vez y guardar en la base.

Se corre así, desde la carpeta del proyecto:

    .venv/bin/python pruebas/probar_extraccion.py

No se conecta a internet ni gasta cupo de ninguna IA: se levanta un
servicio de mentira aquí mismo, que además CUENTA cuántas veces lo
llaman. Eso último es lo que de verdad se está probando: que un
documento se lea una sola vez y que después nadie lo vuelva a mandar.

Trabaja sobre una base de datos aparte, en una carpeta temporal. La base
del contador no se toca.

Lo que comprueba:

  A. Un XML lo lee el PROGRAMA, no la IA. Es la regla del proyecto: si
     hay estructura, se parsea; no se le pregunta a un modelo.
  B. Un PDF o un texto sí pasa por la IA, pero UNA sola vez, y lo que
     sale de este computador es el texto, nunca el archivo.
  C. Lo ya leído no se vuelve a leer ni a pagar.
  D. RentAI arma su contexto con las filas de la BASE, no remandando los
     documentos, y distingue lo que leyó un modelo de lo que leyó el
     programa.
  E. Con la IA apagada, lo ya leído se sigue viendo, y un documento
     nuevo queda PENDIENTE en vez de darse por fallido.
  F. Un documento ilegible no traba la fila de los demás.
  G. La fila trabaja en otro hilo —confirmar es instantáneo—, vive en
     SQLite y retoma donde iba si se cierra el programa a mitad.
"""

import json
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


# ----------------------------------------------------------
# Un servicio de IA de mentira, que cuenta cuántas veces lo llaman
# ----------------------------------------------------------

PUERTO = 8232
LLAMADAS = {"cuantas": 0, "lo_que_recibio": ""}


class _ServicioFalso(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        largo = int(self.headers.get("Content-Length") or 0)
        LLAMADAS["cuantas"] += 1
        LLAMADAS["lo_que_recibio"] = self.rfile.read(largo).decode(
            "utf-8", "replace"
        )

        contestacion = json.dumps({"datos": [
            {"concepto": "Salarios", "valor": "45.000.000",
             "detalle": "Enero a diciembre"},
            {"concepto": "Retención practicada", "valor": "1.200.000",
             "detalle": ""},
        ]})
        cuerpo = json.dumps(
            {"choices": [{"message": {"content": contestacion}}]}
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, formato, *argumentos):
        pass


class _ConIA:
    proveedor = "openai_compatible"
    llave = "x" * 20
    base_url = "http://127.0.0.1:%d" % PUERTO
    modelo = "modelo-de-prueba"
    ia_disponible = True
    motivo = ""


class _SinIA:
    proveedor = "ninguno"
    llave = ""
    base_url = ""
    modelo = ""
    ia_disponible = False
    motivo = "La IA está apagada."


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
    print(" Lectura de documentos: una sola vez, guardada en la base")
    print("=" * 62)

    carpeta = Path(tempfile.mkdtemp(prefix="taxi-extraccion-"))
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), _ServicioFalso)
    servidor.daemon_threads = True
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    try:
        # La base de prueba vive aparte. La del contador no se toca.
        from app import db
        db.CARPETA_DATOS = carpeta
        db.ARCHIVO_BD = carpeta / "base.db"
        db.crear_tablas()

        from app import documentos, extraccion, rentai
        documentos.CARPETA_ARCHIVOS = carpeta / "archivos"
        extraccion.CONFIG = _ConIA()

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
        LLAMADAS["cuantas"] = 0
        informe = extraccion.extraer(documento_xml)
        comprobar("el documento queda listo",
                  informe["estado"] == "listo", informe["motivo"])
        comprobar("lo leyó el código, no un modelo",
                  informe["origen"] == "codigo")
        comprobar("no se llamó a la IA ni una vez",
                  LLAMADAS["cuantas"] == 0,
                  "%d llamadas" % LLAMADAS["cuantas"])

        filas = db.listar_datos_extraidos(
            cliente_id, documento_id=documento_xml["id"]
        )
        comprobar("guardó los campos del XML", len(filas) >= 4,
                  "%d datos" % len(filas))
        comprobar("copió el total tal cual, sin convertir ni redondear",
                  any(f["valor"] == "250000" for f in filas))
        comprobar("cada dato dice de qué documento salió",
                  all(f["nombre_original"] == "factura.xml" for f in filas))

        # --------------------------------------------------------------
        titulo("B. Un texto sí pasa por la IA, pero una sola vez")
        # --------------------------------------------------------------
        LLAMADAS["cuantas"] = 0
        informe = extraccion.extraer(documento_txt)
        comprobar("el documento queda listo",
                  informe["estado"] == "listo", informe["motivo"])
        comprobar("queda marcado como lectura automática",
                  informe["origen"] == "ia")
        comprobar("se llamó a la IA exactamente una vez",
                  LLAMADAS["cuantas"] == 1, "%d" % LLAMADAS["cuantas"])
        comprobar("salió el TEXTO, no el archivo",
                  "Salarios 45.000.000" in LLAMADAS["lo_que_recibio"]
                  and "certificado.txt" not in LLAMADAS["lo_que_recibio"])

        # --------------------------------------------------------------
        titulo("C. Lo ya leído no se vuelve a leer ni a pagar")
        # --------------------------------------------------------------
        LLAMADAS["cuantas"] = 0
        informes = extraccion.extraer_pendientes(cliente_id)
        comprobar("no quedaba nada pendiente", len(informes) == 0,
                  "%d" % len(informes))
        comprobar("y no se gastó ni una llamada",
                  LLAMADAS["cuantas"] == 0, "%d" % LLAMADAS["cuantas"])

        # --------------------------------------------------------------
        titulo("D. RentAI arma su contexto con la BASE, no con los documentos")
        # --------------------------------------------------------------
        LLAMADAS["cuantas"] = 0
        contexto = rentai.resumen_de_documentos(cliente_id)
        comprobar("armar el contexto no llama a la IA",
                  LLAMADAS["cuantas"] == 0)
        comprobar("trae los datos que ya estaban guardados",
                  "Salarios" in contexto and "45.000.000" in contexto)
        comprobar("marca como LECTURA AUTOMÁTICA lo que leyó un modelo",
                  "LECTURA AUTOMÁTICA" in contexto)
        comprobar("y marca como exacto lo que leyó el programa del XML",
                  "exacto" in contexto)
        comprobar("NO remanda el texto crudo del certificado",
                  "CERTIFICADO DE INGRESOS" not in contexto)
        comprobar("el contexto es mucho más corto que los documentos",
                  len(contexto) < 900, "%d letras" % len(contexto))

        # --------------------------------------------------------------
        titulo("E. Con la IA apagada, lo ya leído se sigue viendo")
        # --------------------------------------------------------------
        extraccion.CONFIG = _SinIA()
        contexto = rentai.resumen_de_documentos(cliente_id)
        comprobar("lo extraído sigue disponible sin IA",
                  "45.000.000" in contexto)

        suelto = subir("suelto.txt", "algo sin estructura".encode("utf-8"))
        informe = extraccion.extraer(suelto)
        comprobar("un documento nuevo queda PENDIENTE, no fallido",
                  informe["estado"] == "pendiente", informe["motivo"])

        otra_factura = subir("factura2.xml", FACTURA_XML)
        comprobar("pero un XML se lee igual, porque no necesita IA",
                  extraccion.extraer(otra_factura)["estado"] == "listo")

        # --------------------------------------------------------------
        titulo("F. Un documento malo no traba a los demás")
        # --------------------------------------------------------------
        extraccion.CONFIG = _ConIA()
        roto = subir("roto.zzz", b"\x00\x01 esto no es nada")
        otro_bueno = subir("factura3.xml", FACTURA_XML)

        informes = extraccion.extraer_pendientes(cliente_id)
        por_nombre = {i["nombre"]: i for i in informes}
        comprobar("el ilegible queda marcado como fallo",
                  por_nombre.get("roto.zzz", {}).get("estado") == "fallo",
                  por_nombre.get("roto.zzz", {}).get("motivo", ""))
        comprobar("pero los de después SÍ se procesaron",
                  por_nombre.get("factura3.xml", {}).get("estado") == "listo")
        comprobar("el motivo del fallo se le puede mostrar al contador",
                  bool(por_nombre.get("roto.zzz", {}).get("motivo")))

        estado = extraccion.resumen(cliente_id)
        comprobar("el resumen cuenta bien lo que falló",
                  estado["estados"]["fallo"] == 1, str(estado["estados"]))
        comprobar("un fallo NO se reintenta solo",
                  extraccion.resumen(cliente_id)["sin_leer"] == 0,
                  "sin leer: %d" % estado["sin_leer"])

        # --------------------------------------------------------------
        titulo("G. La fila trabaja aparte y sobrevive a cerrar el programa")
        # --------------------------------------------------------------
        from app import cola

        comprobar("el procesar automático viene APAGADO de fábrica",
                  cola.procesar_automaticamente() is False)

        for numero in range(4):
            subir("tanda%d.txt" % numero,
                  ("Salarios %d" % numero).encode("utf-8"))

        comienzo = time.monotonic()
        arrancó = cola.arrancar(cliente_id)
        tardó = time.monotonic() - comienzo
        comprobar("arrancar la fila contesta al instante",
                  arrancó and tardó < 0.3, "%.3f s" % tardó)
        comprobar("hay un hilo trabajando", cola.trabajando())
        comprobar("pedirla otra vez no amontona hilos",
                  cola.arrancar(cliente_id) is False)

        for _ in range(300):
            if not cola.trabajando():
                break
            time.sleep(0.1)
        comprobar("termina sola", not cola.trabajando())
        comprobar("y deja los de la tanda leídos",
                  extraccion.resumen(cliente_id)["sin_leer"] == 0)

        # Se simula que se cerró el programa con un documento a medio leer.
        for numero in range(3):
            subir("tarde%d.txt" % numero, ("otro %d" % numero).encode("utf-8"))
        a_medias = db.documentos_sin_leer(cliente_id)[0]
        db.marcar_lectura(a_medias["id"], "leyendo")

        fila = cola.al_arrancar_el_programa()
        comprobar("al volver a abrir, rescata el que quedó a medio leer",
                  fila["rescatados"] == 1, str(fila))
        comprobar("el que estaba a medias vuelve a pendiente",
                  db.obtener_documento(a_medias["id"])["estado_lectura"]
                  == "pendiente")
        comprobar("sabe cuántos quedan sin leer",
                  fila["pendientes"] == 3, str(fila))
        comprobar("y NO se pone a leer solo al arrancar",
                  not cola.trabajando())

        comprobar("el interruptor se guarda en la base, no en memoria",
                  cola.cambiar_automatico(True) is True
                  and db.leer_ajuste(cola.CLAVE_AUTOMATICO) == "si")
        comprobar("y se puede volver a apagar",
                  cola.cambiar_automatico(False) is False)

    finally:
        servidor.shutdown()
        servidor.server_close()
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
