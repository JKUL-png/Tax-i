"""
Prueba de la pasada: el Formulario 210 propuesto de una sola vez.

Se corre así, desde la carpeta del proyecto:

    .venv/bin/python pruebas/probar_pasada.py

En Windows:

    .venv\\Scripts\\python pruebas\\probar_pasada.py

No se conecta a internet ni gasta un peso: se levanta un servicio de IA
de mentira aquí mismo, que además GUARDA lo que le mandaron. Eso último
es media prueba — así se comprueba que lo que sale de este computador es
texto y nunca un archivo.

Trabaja sobre una base de datos aparte, en una carpeta temporal. La base
del contador no se toca.

Lo que comprueba, que son las siete reglas de la pasada:

  A. El código suma y el modelo NUNCA. Tres componentes de un renglón
     llegan por separado y el total lo hace Python.
  B. Una cita textual falsa se detecta y se descarta, y el valor queda
     para revisión manual.
  C. Los niveles A, B y C se asignan comprobándolos contra la fuente, no
     creyéndole al modelo. El código solo puede BAJARLOS.
  D. Aprobar en bloque no toca los de nivel C.
  E. Las 902 fórmulas de la plantilla siguen idénticas después de
     escribir lo aprobado.
  F. Todo lo que no es la pasada corre con IA_PROVEEDOR=ninguno.
  G. Ningún archivo crudo sale hacia el modelo: ni el PDF, ni el Excel
     de la exógena. Se mira el cuerpo real de la petición.

Y de paso: que la respuesta que no valida se reintenta UNA vez, que los
tokens quedan anotados, y que un cliente con demasiados documentos se
parte por BLOQUES DE DOCUMENTOS y nunca por renglones.
"""

import json
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "pruebas"))

resultados = []


def comprobar(descripcion, condicion, detalle=""):
    resultados.append(bool(condicion))
    print(("  OK    " if condicion else "  FALLA ") + descripcion
          + (("  [" + str(detalle)[:80] + "]") if detalle else ""))


def titulo(texto):
    print("\n" + texto)


# ----------------------------------------------------------
# El servicio de IA de mentira
#
# Guarda TODO lo que le mandan, que es lo que después se revisa para
# saber que no salió ningún archivo. Y contesta lo que se le diga,
# para poder probar cada caso: la cita buena, la inventada, el nivel
# exagerado y la respuesta que no es JSON.
# ----------------------------------------------------------

PUERTO = 8233
LLAMADAS = {"cuantas": 0, "cuerpos": [], "respuestas": []}


class _ServicioFalso(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        largo = int(self.headers.get("Content-Length") or 0)
        crudo = self.rfile.read(largo)
        LLAMADAS["cuantas"] += 1
        LLAMADAS["cuerpos"].append(crudo)

        siguiente = (LLAMADAS["respuestas"].pop(0)
                     if LLAMADAS["respuestas"] else "{}")
        cuerpo = json.dumps({
            "choices": [{"message": {"content": siguiente}}],
            "usage": {"prompt_tokens": 4321, "completion_tokens": 765},
        }).encode("utf-8")

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
    motivo = "Modo sin IA activo."


# ----------------------------------------------------------
# Los documentos de mentira
# ----------------------------------------------------------

CERTIFICADO = (
    "*** DOCUMENTO FICTICIO - DATOS INVENTADOS ***\n"
    "COMERCIALIZADORA EL ROBLE S.A.S.\n"
    "NIT 900.456.789-1\n"
    "CERTIFICADO DE INGRESOS Y RETENCIONES 2025\n"
    "Pagos por salarios 60.000.000\n"
    "Prima de servicios 14.600.000\n"
    "Bonificaciones 10.000.000\n"
    "Retencion en la fuente practicada 3.100.000\n"
).encode("utf-8")

EXTRACTO = (
    "*** DOCUMENTO FICTICIO - DATOS INVENTADOS ***\n"
    "BANCO DE EJEMPLO\n"
    "Saldo a 31 de diciembre: -2.342.990\n"
).encode("utf-8")


def _referencia_de(entrada, aguja):
    """La referencia («D2», «E7») de lo que contenga ese texto.

    La prueba NO se inventa las referencias: las busca en lo que se le
    va a mandar de verdad al modelo. Así, si mañana cambia el orden de
    los documentos o el archivo de exógena de ejemplo, la prueba sigue
    midiendo lo que dice medir en vez de fallar por otra cosa.
    """
    for referencia, origen in entrada["indice"].items():
        if aguja in origen["texto"]:
            return referencia
    raise AssertionError("No encontré «%s» en lo que se manda." % aguja)


def _respuesta_normal(entrada):
    """Lo que contestaría un modelo que se porta bien... casi.

    Cuatro cosas puestas a propósito:
      - R32 llega en TRES componentes. El total lo tiene que hacer el
        código; el modelo no suma nunca.
      - El tercer componente trae una cita INVENTADA. Tiene que caerse.
      - R30 sale de la fila de la exógena que SÍ nombra ese renglón: se
        queda en nivel A.
      - R74 pide nivel "A" sin que nada lo respalde: tiene que bajar a C.
    """
    certificado = _referencia_de(entrada, "Pagos por salarios 60.000.000")
    extracto = _referencia_de(entrada, "Saldo a 31 de diciembre")
    deudas = _referencia_de(entrada, "Cuentas por pagar de clientes")

    return json.dumps({
        "propuestas": [
            {"renglon": "R32", "componentes": [
                {"valor": "60.000.000", "fuente": "documento",
                 "referencia": certificado,
                 "cita": "Pagos por salarios 60.000.000",
                 "nivel": "C", "condicion": "",
                 "nota": "Del certificado de El Roble."},
                {"valor": "14.600.000", "fuente": "documento",
                 "referencia": certificado,
                 "cita": "Prima de servicios 14.600.000",
                 "nivel": "C", "condicion": "",
                 "nota": "Del mismo certificado."},
                {"valor": "10.000.000", "fuente": "documento",
                 "referencia": certificado,
                 "cita": "Auxilio de transporte 10.000.000",
                 "nivel": "C", "condicion": "",
                 "nota": "Esta cita NO está en el papel."},
            ]},
            {"renglon": "R30", "componentes": [
                {"valor": "2.500.000", "fuente": "exogena",
                 "referencia": deudas,
                 "cita": "Cuentas por pagar de clientes",
                 "nivel": "A", "condicion": "",
                 "nota": "La exógena lo asigna a R30 Deudas."},
            ]},
            {"renglon": "R74", "componentes": [
                {"valor": "5.000.000", "fuente": "documento",
                 "referencia": extracto,
                 "cita": "Saldo a 31 de diciembre: -2.342.990",
                 "nivel": "A", "condicion": "",
                 "nota": "Dice A pero el papel no nombra el renglón."},
            ]},
        ],
        "lecturas": [
            {"referencia": certificado, "concepto": "Retención en la fuente",
             "valor": "3.100.000", "detalle": "Año gravable 2025",
             "cita": "Retencion en la fuente practicada 3.100.000"},
            {"referencia": certificado, "concepto": "Dato inventado",
             "valor": "99", "detalle": "",
             "cita": "esta frase tampoco está en el papel"},
        ],
        "sin_ubicar": [{"referencia": extracto, "porque": "No dice de qué es."}],
    })


def main():
    print("=" * 62)
    print(" La pasada: el formulario propuesto de una sola vez")
    print("=" * 62)

    from app import formulario
    if formulario.ruta_plantilla() is None:
        print("\nNo hay plantilla en plantillas/. No se puede probar la"
              " pasada: los renglones y las casillas salen de ella.")
        return 1

    carpeta = Path(tempfile.mkdtemp(prefix="taxi-pasada-"))
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), _ServicioFalso)
    servidor.daemon_threads = True
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    try:
        from app import db
        db.CARPETA_DATOS = carpeta
        db.ARCHIVO_BD = carpeta / "base.db"
        db.crear_tablas()

        from app import (comparacion, cruce, documentos, exogena_cliente,
                         pasada)
        documentos.CARPETA_ARCHIVOS = carpeta / "archivos"
        pasada.CONFIG = _ConIA()

        cliente = db.crear_cliente("Cliente de prueba pasada", "07")
        cliente_id = cliente["id"]

        ejemplo = RAIZ / "pruebas" / "ejemplos" / "reporteExogena2025_EJEMPLO.xlsx"
        if not ejemplo.exists():
            print("Falta el archivo de exógena de ejemplo.")
            return 1
        exogena_cliente.CARPETA_EXOGENA = carpeta / "exogena"
        exogena_cliente.cargar(cliente_id, ejemplo, ejemplo.name)

        def subir(nombre, contenido):
            guardado, tamano = documentos.guardar_contenido(
                cliente_id, nombre, contenido
            )
            return db.crear_documento(
                cliente_id, nombre, guardado,
                Path(nombre).suffix.lstrip("."), tamano
            )

        subir("certificado_el_roble.txt", CERTIFICADO)
        subir("extracto_banco.txt", EXTRACTO)

        # R30 tiene seis filas de detalle en la plantilla y ninguna gana
        # sola, así que el programa NO escoge: se lo pregunta al
        # contador. Aquí se simula que ya se lo preguntó una vez y él
        # dijo H104. Es el mismo camino que usa el programa de verdad
        # —formulario.casilla_recordada— y sin él este renglón se
        # quedaría fuera del bloque, que es justo lo correcto.
        formulario.recordar_casilla("30", "H104")

        # --------------------------------------------------------------
        titulo("G. Lo que sale es TEXTO. Ningún archivo crudo.")
        # --------------------------------------------------------------
        entrada = pasada.armar_entrada(cliente)

        comprobar("armar la entrada no llama a nadie",
                  LLAMADAS["cuantas"] == 0)
        comprobar("todo lo que se manda es texto",
                  all(isinstance(t, str) for t in entrada["instrucciones"])
                  and all(isinstance(b, str) for b in entrada["bloques"]))

        LLAMADAS["respuestas"] = [_respuesta_normal(entrada)]
        informe = pasada.correr(cliente)

        crudo = b"".join(LLAMADAS["cuerpos"])
        comprobar("en la petición NO va ningún PDF", b"%PDF" not in crudo)
        comprobar("ni ningún Excel ni ZIP", b"PK\x03\x04" not in crudo)
        comprobar("ni el nombre del archivo de la exógena",
                  ejemplo.name.encode("utf-8") not in crudo)
        comprobar("sí va el texto que se extrajo aquí",
                  b"Pagos por salarios 60.000.000" in crudo)

        # --------------------------------------------------------------
        titulo("A. El código suma. El modelo nunca.")
        # --------------------------------------------------------------
        por_renglon = {r["renglon"]: r for r in informe["renglones"]}
        r32 = por_renglon.get("R32")

        comprobar("R32 llegó en tres componentes por separado",
                  r32 is not None and len(r32["componentes"]) == 3,
                  len(r32["componentes"]) if r32 else "no llegó")
        # 60.000.000 + 14.600.000. El tercero se cae por la cita falsa.
        comprobar("el total lo sumó el código: 74.600.000",
                  r32 and r32["total"] == 74600000, r32 and r32["total"])
        cruda = _respuesta_normal(entrada)
        comprobar("y ese total NO venía en la respuesta del modelo",
                  "74600000" not in cruda and "74.600.000" not in cruda)

        # --------------------------------------------------------------
        titulo("B. Una cita falsa se detecta y se descarta")
        # --------------------------------------------------------------
        inventado = [c for c in r32["componentes"]
                     if "Auxilio de transporte" in (c["cita"] or "")]
        comprobar("el componente con la cita inventada quedó marcado",
                  len(inventado) == 1
                  and inventado[0]["estado"] == "revision",
                  inventado[0]["estado"] if inventado else "no está")
        comprobar("y no se dio por verificado",
                  inventado and inventado[0]["verificada"] == 0)
        comprobar("el motivo dice que la frase no aparece",
                  inventado and "no aparece en el original"
                  in (inventado[0]["motivo"] or ""),
                  inventado and inventado[0]["motivo"])
        comprobar("el programa lo cuenta como revisión manual",
                  informe["en_revision_manual"] >= 1,
                  informe["en_revision_manual"])

        guardados = db.listar_datos_extraidos(cliente_id)
        conceptos = {fila["concepto"] for fila in guardados}
        comprobar("de las lecturas sueltas se guardó la verificada",
                  "Retención en la fuente" in conceptos, sorted(conceptos))
        comprobar("y NO se guardó la de la cita inventada",
                  "Dato inventado" not in conceptos, sorted(conceptos))

        # --------------------------------------------------------------
        titulo("C. El nivel se comprueba contra la fuente, no se cree")
        # --------------------------------------------------------------
        r30 = por_renglon.get("R30")
        directo = r30["componentes"][0] if r30 else None
        comprobar("el que la exógena sí respalda se queda en A",
                  directo and directo["nivel"] == "A",
                  directo and directo["nivel"])

        r74 = por_renglon.get("R74")
        exagerado = r74["componentes"][0] if r74 else None
        comprobar("el que dijo A sin respaldo BAJA a C",
                  exagerado and exagerado["nivel"] == "C",
                  exagerado and exagerado["nivel"])
        comprobar("se guarda lo que el modelo había pedido",
                  exagerado and exagerado["nivel_pedido"] == "A")
        comprobar("y el motivo explica por qué se le bajó",
                  exagerado and "no dice a qué renglón va"
                  in (exagerado["motivo"] or ""),
                  exagerado and exagerado["motivo"])
        comprobar("el nivel del renglón es el PEOR de sus componentes",
                  r32["nivel"] == "C", r32["nivel"])

        # El nivel B, con la condición textual de la DIAN.
        from app import instrucciones
        uso = "Tope 3 | R30 Deudas (si el saldo es negativo)"
        nivel, _motivo = instrucciones.comprobar_nivel(
            "B", "R30", "exogena",
            condicion="R30 Deudas (si el saldo es negativo)",
            uso_sugerido=uso)
        comprobar("B se sostiene cuando la condición está en la exógena",
                  nivel == "B", nivel)
        nivel, motivo = instrucciones.comprobar_nivel(
            "B", "R30", "exogena", condicion="porque me pareció",
            uso_sugerido=uso)
        comprobar("y baja a C cuando la condición se la inventó",
                  nivel == "C", motivo)

        # --------------------------------------------------------------
        titulo("D. Aprobar en bloque no toca los de nivel C")
        # --------------------------------------------------------------
        en_bloque = pasada.para_aprobar_en_bloque(cliente_id)
        niveles = {v["nivel"] for v in en_bloque}
        comprobar("en el bloque solo hay niveles A y B",
                  niveles <= {"A", "B"}, sorted(niveles))
        comprobar("ningún valor de nivel C entró al bloque",
                  all(v["nivel"] != "C" for v in en_bloque))
        comprobar("ni ninguno sin cita verificada",
                  all(v["verificada"] for v in en_bloque))

        antes_c = [c for r in informe["renglones"] for c in r["componentes"]
                   if c["nivel"] == "C" and c["estado"] == "propuesto"]
        pasada.aprobar(cliente, [v["id"] for v in en_bloque])
        despues = pasada.resumen(cliente_id)
        siguen = [c for r in despues["renglones"] for c in r["componentes"]
                  if c["nivel"] == "C" and c["estado"] == "propuesto"]
        comprobar("los de nivel C siguen esperando, sin tocar",
                  len(siguen) == len(antes_c) and len(siguen) > 0,
                  "%d antes, %d después" % (len(antes_c), len(siguen)))

        anotados = db.listar_valores_210(cliente_id)
        comprobar("lo aprobado sí quedó en el Formulario 210",
                  len(anotados) == len({v["celda"] for v in en_bloque}),
                  "%d celdas" % len(anotados))

        # --------------------------------------------------------------
        titulo("El cruce: sus papeles contra lo que reportó la DIAN")
        # --------------------------------------------------------------
        informe_cruce = cruce.revisar(cliente_id)

        comprobar("hay las dos mitades: exógena y propuesta",
                  informe_cruce["hay_cruce"],
                  {k: v for k, v in informe_cruce.items()
                   if not isinstance(v, list)})

        por_renglon = {h["renglon"]: h for h in informe_cruce["hallazgos"]}

        # R32 solo lo dicen los papeles: ningún tercero lo reportó en la
        # exógena de ejemplo con ese renglón a solas.
        r32_cruce = por_renglon.get("R32")
        comprobar("un renglón que solo dicen los papeles se marca",
                  r32_cruce is not None
                  and r32_cruce["estado"] in ("sin_reportar", "diferencia"),
                  r32_cruce and r32_cruce["estado"])
        comprobar("y con la suma que hizo el código, no el modelo",
                  r32_cruce and r32_cruce["papeles"] == 74600000,
                  r32_cruce and r32_cruce["papeles"])

        # Lo que la DIAN reporta y nadie respalda todavía.
        sin_soporte = [h for h in informe_cruce["hallazgos"]
                       if h["estado"] == "sin_soporte"]
        comprobar("lo que la DIAN reporta sin soporte se marca",
                  len(sin_soporte) > 0, len(sin_soporte))
        comprobar("y dice quién lo reportó, para no tener que ir a buscarlo",
                  all(h["filas"] for h in sin_soporte))

        # Elegir es criterio del contador: esas filas no se cruzan.
        comprobar("las filas que requieren decisión NO se cruzan",
                  len(informe_cruce["requieren_decision"]) > 0,
                  len(informe_cruce["requieren_decision"]))
        codigos_cruzados = set(por_renglon)
        comprobar("y ninguna se coló en un renglón",
                  all(len(f["opciones"]) != 1
                      or f["opciones"][0] not in codigos_cruzados
                      for f in informe_cruce["requieren_decision"]))

        # Y lo más importante: esto no llama a nadie.
        antes_de_cruzar = LLAMADAS["cuantas"]
        cruce.revisar(cliente_id)
        comprobar("cruzar no llama a ningún servicio ni cuesta un peso",
                  LLAMADAS["cuantas"] == antes_de_cruzar,
                  LLAMADAS["cuantas"] - antes_de_cruzar)

        # --------------------------------------------------------------
        titulo("E. Las 902 fórmulas siguen idénticas después de escribir")
        # --------------------------------------------------------------
        # El archivo del cliente se escribe DENTRO del proyecto y no en
        # la carpeta temporal, porque `generar` informa la ruta relativa
        # a la raíz. Va a datos/, que nunca se sube a git, y se borra al
        # terminar.
        formulario.CARPETA_FORMULARIOS = RAIZ / "datos" / "formularios-prueba"
        salida = formulario.generar(cliente)
        verificacion = salida["verificacion"]
        comprobar("el archivo se generó y se verificó",
                  verificacion is not None
                  and verificacion["formulas_comparadas"] == 902,
                  verificacion and verificacion.get("formulas_comparadas"))
        comprobar("ninguna de las 902 fórmulas cambió",
                  verificacion and verificacion["formulas_distintas"] == 0,
                  verificacion and verificacion.get("formulas_distintas"))

        # --------------------------------------------------------------
        titulo("Los tokens quedan anotados, para saber cuánto costó")
        # --------------------------------------------------------------
        gasto = db.gasto_de_pasadas(cliente_id)
        comprobar("se anotaron los tokens que reportó el servicio",
                  gasto["entrada"] == 4321 and gasto["salida"] == 765,
                  str(gasto))
        comprobar("y quedó una pasada registrada", gasto["pasadas"] == 1)

        # --------------------------------------------------------------
        titulo("Una respuesta que no valida se reintenta UNA vez")
        # --------------------------------------------------------------
        LLAMADAS["cuantas"] = 0
        LLAMADAS["respuestas"] = ["no soy json", _respuesta_normal(entrada)]
        pasada.correr(cliente)
        comprobar("se reintentó una sola vez y salió bien",
                  LLAMADAS["cuantas"] == 2, LLAMADAS["cuantas"])

        LLAMADAS["cuantas"] = 0
        LLAMADAS["respuestas"] = ["tampoco", "sigo sin ser json"]
        try:
            pasada.correr(cliente)
            fallo = ""
        except pasada.PasadaFallida as error:
            fallo = str(error)
        comprobar("si vuelve a fallar NO se insiste una tercera vez",
                  LLAMADAS["cuantas"] == 2, LLAMADAS["cuantas"])
        comprobar("y se dice en español qué pasó",
                  "no se pudo entender" in fallo, fallo[:60])

        # --------------------------------------------------------------
        titulo("Un cliente muy grande se parte por DOCUMENTOS")
        # --------------------------------------------------------------
        for numero in range(pasada.TOPE_DE_DOCUMENTOS + 5):
            subir("relleno%d.txt" % numero,
                  ("Documento de relleno %d con su cifra 1.000\n"
                   % numero).encode("utf-8"))
        grande = pasada.armar_entrada(cliente)
        comprobar("con muchos documentos se parte en bloques",
                  len(grande["bloques"]) > 1, len(grande["bloques"]))
        comprobar("cada bloque lleva la exógena entera",
                  all("EXÓGENA" in b for b in grande["bloques"]))
        comprobar("y los renglones van completos en las instrucciones",
                  "RENGLONES DEL FORMULARIO 210" in grande["instrucciones"][1])
        repartidos = sum(b.count("--- D") for b in grande["bloques"])
        comprobar("ningún documento se manda dos veces",
                  repartidos == grande["documentos"],
                  "%d en los bloques, %d en total"
                  % (repartidos, grande["documentos"]))

        # --------------------------------------------------------------
        titulo("F. Sin IA configurada, todo lo demás sigue funcionando")
        # --------------------------------------------------------------
        pasada.CONFIG = _SinIA()
        comparacion.pasada.CONFIG = _SinIA()
        LLAMADAS["cuantas"] = 0

        try:
            pasada.correr(cliente)
            se_nego = False
            motivo = ""
        except pasada.SinIA as error:
            se_nego = True
            motivo = str(error)
        comprobar("la pasada no corre y lo dice sin alarma",
                  se_nego and "sin IA" in motivo, motivo[:60])
        comprobar("y no llamó a nadie", LLAMADAS["cuantas"] == 0)

        sigue = pasada.resumen(cliente_id)
        comprobar("lo ya propuesto se sigue viendo",
                  sigue["hay_pasada"] and len(sigue["renglones"]) > 0)
        comprobar("la pantalla dice por qué está apagada",
                  not sigue["ia_disponible"] and bool(sigue["motivo"]))

        tabla = exogena_cliente.tabla(cliente_id)
        comprobar("la exógena se sigue leyendo entera, sin IA",
                  len(tabla["filas"]) > 0, "%d filas" % len(tabla["filas"]))
        comprobar("el checklist sigue ahí",
                  len(db.listar_checklist(cliente_id)) > 0)
        comprobar("y se puede anotar a mano en el 210",
                  formulario.guardar_valor(
                      cliente_id, "H104", 123456, "digitado a mano"
                  )["valor"] == 123456)

        # --------------------------------------------------------------
        titulo("El modo comparación mide, y no toca ni una cifra")
        # --------------------------------------------------------------
        antes_de_comparar = len(db.listar_valores_210(cliente_id))
        informe_comparacion = comparacion.comparar(
            cliente, salida_del_archivo(carpeta, cliente_id), "mi_210.xlsx"
        )
        comprobar("compara renglón por renglón",
                  len(informe_comparacion["renglones"]) > 0,
                  len(informe_comparacion["renglones"]))
        comprobar("y da el porcentaje de acierto",
                  isinstance(informe_comparacion["acierto"], float),
                  informe_comparacion["acierto"])
        comprobar("desglosa por nivel A, B y C",
                  set(informe_comparacion["por_nivel"]) == {"A", "B", "C"},
                  sorted(informe_comparacion["por_nivel"]))
        comprobar("no cambió ningún valor del cliente",
                  len(db.listar_valores_210(cliente_id)) == antes_de_comparar,
                  antes_de_comparar)

    finally:
        servidor.shutdown()
        servidor.server_close()
        shutil.rmtree(carpeta, ignore_errors=True)
        shutil.rmtree(RAIZ / "datos" / "formularios-prueba", ignore_errors=True)

    print()
    print("=" * 62)
    print(" %d de %d comprobaciones pasaron."
          % (sum(resultados), len(resultados)))
    print(" Todo bien." if all(resultados) else " HAY FALLAS.")
    print("=" * 62)
    return 0 if all(resultados) else 1


def salida_del_archivo(carpeta, cliente_id):
    """El .xlsx que acabamos de generar, que aquí hace de «el suyo».

    Comparar el formulario contra sí mismo tiene que dar 100%: es la
    forma de saber que la comparación mide lo que dice medir antes de
    creerle un número sobre el trabajo de verdad.
    """
    from app import formulario
    return formulario.archivo_cliente(cliente_id)


if __name__ == "__main__":
    sys.exit(main())
