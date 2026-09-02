"""
Prueba del modo demostración y de la revisión de arranque.

Se corre así, desde la carpeta del proyecto:

    .venv/bin/python pruebas/probar_demostracion.py

Trabaja sobre una base de datos aparte, en una carpeta temporal. La base
del contador no se toca.

Lo que comprueba, y lo más importante es lo último:

  A. Prender la demostración carga un cliente inventado con documentos
     inventados, y TODO va marcado como ficticio.
  B. Prenderlo dos veces no acumula copias.
  C. Apagarlo borra lo inventado y NO toca ni un cliente de verdad.
  D. La revisión de arranque contesta en español, con qué hacer en cada
     caso, y sin jerga técnica.
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


def main():
    print("=" * 62)
    print(" Modo demostración y revisión de arranque")
    print("=" * 62)

    carpeta = Path(tempfile.mkdtemp(prefix="taxi-demo-"))
    try:
        from app import db
        db.CARPETA_DATOS = carpeta
        db.ARCHIVO_BD = carpeta / "base.db"
        db.crear_tablas()

        from app import demostracion, documentos, revision
        documentos.CARPETA_ARCHIVOS = carpeta / "archivos"
        documentos.CARPETA_PAPELERA = carpeta / "papelera"

        # Un cliente de VERDAD, para comprobar después que no se toca.
        real = db.crear_cliente("Cliente de verdad", "07", "2026-10-14")
        guardado, tamano = documentos.guardar_contenido(
            real["id"], "documento real.txt", b"esto es de un cliente real"
        )
        db.crear_documento(real["id"], "documento real.txt", guardado,
                           ".txt", tamano)

        # --------------------------------------------------------------
        titulo("A. Prender carga un cliente inventado, bien marcado")
        # --------------------------------------------------------------
        comprobar("de fábrica está apagado", demostracion.activo() is False)

        estado = demostracion.prender()
        comprobar("queda prendido", estado["activo"] is True)

        demos = db.clientes_de_demostracion()
        comprobar("cargó un cliente inventado", len(demos) == 1,
                  "%d" % len(demos))

        cliente = db.obtener_cliente(demos[0])
        comprobar("el nombre dice que es ficticio",
                  demostracion.MARCA in cliente["nombre"], cliente["nombre"])
        comprobar("y queda marcado en la base con es_demo",
                  cliente["es_demo"] == 1)

        archivos = db.listar_documentos(cliente["id"])
        comprobar("le cargó documentos", len(archivos) >= 4,
                  "%d documentos" % len(archivos))
        comprobar("y su checklist", len(db.listar_checklist(cliente["id"])) >= 5)

        # Cada documento tiene que gritar que es ficticio en lo primero
        # que se lee, para que se vea también en la vista previa sin
        # abrirlo. Se miran las primeras 200 letras y no la primera línea
        # exacta porque un XML está obligado a empezar con su declaración
        # (<?xml ...?>); ahí la advertencia va en el renglón siguiente.
        sin_advertencia = []
        for archivo in archivos:
            ruta = documentos.ruta_del_documento(
                cliente["id"], archivo["nombre_guardado"]
            )
            comienzo = ruta.read_text(encoding="utf-8")[:200].upper()
            if "FICTICIA" not in comienzo and "FICTICIO" not in comienzo:
                sin_advertencia.append(archivo["nombre_original"])
        comprobar("TODOS los documentos avisan de entrada que son ficticios",
                  not sin_advertencia, ", ".join(sin_advertencia))

        # --------------------------------------------------------------
        titulo("B. Prenderlo dos veces no acumula copias")
        # --------------------------------------------------------------
        demostracion.prender()
        comprobar("sigue habiendo un solo cliente inventado",
                  len(db.clientes_de_demostracion()) == 1)

        # --------------------------------------------------------------
        titulo("C. Apagarlo borra lo inventado y NO toca lo real")
        # --------------------------------------------------------------
        antes = len(db.listar_clientes())
        informe = demostracion.apagar()
        comprobar("dice cuántos quitó", informe["quitados"] == 1,
                  str(informe["quitados"]))
        comprobar("queda apagado", demostracion.activo() is False)
        comprobar("no quedó ningún cliente inventado",
                  db.clientes_de_demostracion() == [])
        comprobar("se fue exactamente uno",
                  len(db.listar_clientes()) == antes - 1)

        # Lo que de verdad importa de todo este archivo.
        sigue = db.obtener_cliente(real["id"])
        comprobar("EL CLIENTE DE VERDAD SIGUE AHÍ",
                  sigue is not None and sigue["nombre"] == "Cliente de verdad")
        comprobar("con su documento intacto en el disco",
                  len(db.listar_documentos(real["id"])) == 1)
        ruta_real = documentos.ruta_del_documento(real["id"], guardado)
        comprobar("y el archivo se puede leer igual",
                  ruta_real.exists()
                  and b"cliente real" in ruta_real.read_bytes())

        # --------------------------------------------------------------
        titulo("D. La revisión de arranque habla en español")
        # --------------------------------------------------------------
        informe = revision.revisar_todo(probar_conexion=False)
        titulos = [p["titulo"] for p in informe["puntos"]]
        comprobar("revisa dónde se guarda el trabajo",
                  any("guarda" in t for t in titulos), str(titulos))
        comprobar("revisa la plantilla del 210",
                  any("plantilla" in t.lower() for t in titulos))
        comprobar("revisa el servicio de IA",
                  any("IA" in t for t in titulos))
        comprobar("revisa LibreOffice",
                  any("LibreOffice" in t for t in titulos))
        comprobar("revisa los documentos por leer",
                  any("leer" in t.lower() for t in titulos))

        # Estar sin IA NO puede reportarse como una falla. Se prueba con
        # una configuración de mentira y no con la del computador donde
        # se corre la prueba: si el desarrollador tiene una llave puesta,
        # la prueba estaría midiendo su .env y no el programa.
        class _SinIA:
            sin_ia = True
            ia_disponible = False
            motivo = ""

        original = revision.CONFIG
        revision.CONFIG = _SinIA()
        try:
            punto_ia = revision.revisar_ia()
        finally:
            revision.CONFIG = original

        comprobar("estar sin IA se reporta como algo BIEN, no como falla",
                  punto_ia["nivel"] == "bien", punto_ia["nivel"])
        comprobar("y le dice al contador que así está bien",
                  "así está bien" in punto_ia["mensaje"])
        comprobar("y que el programa funciona completo igual",
                  "funciona" in punto_ia["mensaje"])

        # Ningún mensaje puede tener jerga de programador.
        JERGA = ("Traceback", "Errno", "OSError", "Exception", "None",
                 "null", "stack", "NoneType")
        con_jerga = []
        for punto in informe["puntos"]:
            texto = punto["mensaje"] + " " + punto["que_hacer"]
            for palabra in JERGA:
                if palabra in texto:
                    con_jerga.append("%s: %s" % (punto["titulo"], palabra))
        comprobar("ningún aviso tiene jerga técnica", not con_jerga,
                  ", ".join(con_jerga))

        # Todo lo que no está bien tiene que decir qué hacer.
        sin_instruccion = [
            p["titulo"] for p in informe["puntos"]
            if p["nivel"] != "bien" and not p["que_hacer"]
        ]
        comprobar("todo aviso o problema dice QUÉ HACER",
                  not sin_instruccion, ", ".join(sin_instruccion))

        # Y con la demostración prendida, la revisión lo tiene que decir.
        demostracion.prender()
        informe = revision.revisar_todo(probar_conexion=False)
        comprobar("con la demostración prendida, la revisión lo avisa",
                  any("demostración" in p["titulo"].lower()
                      for p in informe["puntos"]))
        demostracion.apagar()

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
