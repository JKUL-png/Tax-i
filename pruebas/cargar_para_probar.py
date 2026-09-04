"""
Deja un cliente cargado con todo, para probar el programa de punta a punta.

Se corre así, desde la carpeta del proyecto:

    .venv/bin/python pruebas/cargar_para_probar.py                   (Mac)
    .venv\\Scripts\\python.exe pruebas\\cargar_para_probar.py         (Windows)

Y para cargárselo a un cliente que ya existe, se le pasa su nombre:

    .venv/bin/python pruebas/cargar_para_probar.py "Pedro Ruiz"

Le carga a ese cliente —o al «Cliente de ejemplo», si no se dice cuál—
su reporte de exógena y un montón de documentos, y después imprime un
paso a paso para ir viendo cada cosa en pantalla.

TODO lo que carga es INVENTADO. Los documentos son los que llegan de
verdad —unos con nombre que dice qué son y otros con el nombre que les
puso la cámara o el escáner, más una foto, un escaneado sin texto y un
PDF con contraseña— pero los datos no son de nadie.

Esto ESCRIBE en la base de este computador. Solo le agrega cosas al
cliente que se le diga y no toca a ningún otro.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "pruebas"))

import documentos_de_ejemplo as papeles  # noqa: E402
import exogena_de_ejemplo as reporte  # noqa: E402

from app import clasificacion, db, documentos, exogena_cliente  # noqa: E402

# A qué cliente se le carga todo. Se puede cambiar al correrlo:
#
#     .venv/bin/python pruebas/cargar_para_probar.py "Pedro Ruiz"
#
# Si no existe, se crea.
NOMBRE_CLIENTE = sys.argv[1] if len(sys.argv) > 1 else "Cliente de ejemplo"

# El titular que aparece DENTRO de los documentos inventados. Se llama
# así a propósito: nadie puede confundir estos papeles con los de una
# persona de verdad.
TITULAR = "CONTRIBUYENTE DE EJEMPLO"
CEDULA = "1000000001"


def _cert(entidad, nit, lineas):
    return papeles.pdf_con_texto(
        ["*** DOCUMENTO FICTICIO — DATOS INVENTADOS ***",
         entidad, "NIT " + nit,
         "Titular: %s  C.C. %s" % (TITULAR, CEDULA)] + lineas)


# Los que se agregan. La mitad con nombre que dice qué son y la mitad
# con el que les puso la cámara o el escáner, que es como llegan.
NUEVOS = [
    # Se clasifican por el texto, aunque el nombre no diga nada.
    ("scan0001.pdf", lambda: _cert(
        "BANCO DAVIVIENDA S.A.", "860.034.313-7",
        ["CERTIFICADO PARA DECLARACION DE RENTA 2025",
         "Cuenta de ahorros No. 0087-4455-2211",
         "Saldo a 31 de diciembre de 2025: 18.750.000"])),

    ("documento.pdf", lambda: _cert(
        "COMERCIALIZADORA EL ROBLE S.A.S.", "900.123.456-7",
        ["CERTIFICADO DE INGRESOS Y RETENCIONES 2025",
         "Pagos por salarios: 84.600.000",
         "Retencion en la fuente practicada: 4.120.000"])),

    # Un PDF con el candado que ponen los bancos, pero con clave vacía:
    # sí se puede leer, y por eso se clasifica.
    ("20260228_0001.pdf", lambda: papeles.pdf_con_candado_sin_clave(
        ["*** DOCUMENTO FICTICIO — DATOS INVENTADOS ***",
         "BANCOLOMBIA S.A.", "NIT 890.903.938-8",
         "Titular: %s" % TITULAR,
         "Saldo del credito a 31 de diciembre: 96.400.000"])),

    # Una factura electrónica: el NIT del emisor viene en un campo.
    ("f9a2c1.xml", lambda: papeles.xml_de_factura(
        "901555222", "TALLERES Y SERVICIOS DEL SUR S.A.S.",
        TITULAR, "FE-9911", "2025-09-22", "1250000.00")),

    # Con nombre que sí dice qué es.
    ("Certificado cesantias Proteccion 2025.pdf", lambda: _cert(
        "FONDO DE CESANTIAS PROTECCION", "800.229.739-1",
        ["CERTIFICADO DE CESANTIAS 2025",
         "Valor total abonado en el periodo: 7.049.100"])),

    ("Impuesto predial Villa del Roble.pdf", lambda: _cert(
        "MUNICIPIO DE VILLA DEL ROBLE", "890.900.111-1",
        ["IMPUESTO PREDIAL UNIFICADO 2025",
         "Avaluo catastral: 185.000.000"])),

    # Los tres que NO se pueden leer. Quedarse callado es lo correcto.
    ("IMG_20260315_112233.jpg", papeles.foto),
    ("CamScanner 03-14-2026 10.15.pdf", papeles.pdf_sin_texto),
    ("adjunto.pdf", lambda: papeles.pdf_con_clave(
        ["BANCO DE BOGOTA", "Certificado con contraseña"])),

    # Un tercero que la exógena NO menciona: se queda sin propuesta, y
    # sirve para probar que el programa aprende cuando usted lo corrige.
    ("0001.pdf", lambda: _cert(
        "CAJA DE COMPENSACION FAMILIAR DEL VALLE", "890.303.093-2",
        ["CERTIFICADO DE APORTES 2025", "Valor aportado: 1.850.000"])),
]


def buscar_cliente():
    for cliente in db.listar_clientes():
        if cliente["nombre"].strip().lower() == NOMBRE_CLIENTE.lower():
            return cliente
    return None


def main():
    print("=" * 66)
    print(" Dejar el cliente listo para probar")
    print("=" * 66)

    db.crear_tablas()
    cliente = buscar_cliente()
    if cliente is None:
        cliente = db.crear_cliente(NOMBRE_CLIENTE, "41", None,
                                   "Cliente de prueba. Datos inventados.")
        print("\n  Se creó el cliente «%s»." % NOMBRE_CLIENTE)
    cliente_id = cliente["id"]
    print("\n  Cliente: %s (id %d)" % (cliente["nombre"], cliente_id))
    print("  Ya tenía %d documento(s) y %d renglón(es)."
          % (len(db.listar_documentos(cliente_id)),
             len(db.listar_checklist(cliente_id))))

    # --- 1. La exógena ---
    carpeta = RAIZ / "datos" / "exogena" / str(cliente_id)
    archivo = reporte.escribir(
        carpeta / "reporteExogena2025_PRUEBA.xlsx", TITULAR, CEDULA)
    resultado = exogena_cliente.cargar(cliente_id, archivo, archivo.name)
    print("\n  Exógena cargada: %d registros, %d renglones creados."
          % (resultado["resumen"]["registros"],
             resultado["renglones"]["creados"]))
    print("     %d requieren decisión suya, %d marcados como posible"
          " duplicado." % (resultado["resumen"]["requieren_decision"],
                           resultado["resumen"]["posibles_duplicados"]))

    # --- 2. Los documentos ---
    ya_estan = {d["nombre_original"] for d in db.listar_documentos(cliente_id)}
    puestos = 0
    for nombre, hacer in NUEVOS:
        if nombre in ya_estan:
            continue
        contenido = hacer()
        guardado, tamano = documentos.guardar_contenido(
            cliente_id, nombre, contenido)
        db.crear_documento(
            cliente_id=cliente_id,
            nombre_original=nombre,
            nombre_guardado=guardado,
            extension=Path(guardado).suffix.lower(),
            tamano=tamano,
            huella=documentos.huella_del_contenido(contenido),
        )
        puestos += 1
    print("\n  Documentos agregados: %d" % puestos)

    # --- 3. Clasificar, que es gratis y local ---
    db.marcar_para_clasificar(cliente_id)
    informe = clasificacion.clasificar_pendientes(cliente_id)
    sugerencias = db.sugerencias_del_cliente(cliente_id)
    altas = sum(1 for lista in sugerencias.values()
                for s in lista if s["certeza"] == "alta" and s["principal"])
    print("  Se revisaron %d y %d quedaron con propuesta (%d de ellas con"
          " certeza alta)." % (informe["revisados"],
                               informe["con_sugerencia"], altas))

    total_docs = len(db.listar_documentos(cliente_id))
    sin_asignar = sum(1 for d in db.listar_documentos(cliente_id)
                      if d["renglon_id"] is None)

    print()
    print("=" * 66)
    print(" Listo. Abra el programa y entre a «%s»." % NOMBRE_CLIENTE)
    print("=" * 66)
    print("""
  Arranque el programa así, y abra http://localhost:8000

      .venv/bin/python -m app.main       (Mac)
      py -m app.main                     (Windows)

  1. DOCUMENTOS — %d en total, %d sin asignar todavía.
     Arriba están los «Sin asignar» y abajo los «Ya asignados».
     Cada uno sin asignar tiene su propuesta al lado, y al lado de la
     propuesta dice DE DÓNDE salió: por la exógena, por el XML, por el
     texto o por el nombre del archivo.

     Fíjese en «scan0001.pdf»: el nombre no dice nada y aun así sabe que
     es de Davivienda, porque le leyó el NIT por dentro.

     Y fíjese en los que NO tienen propuesta: la foto, el escaneado sin
     texto y «adjunto.pdf», que tiene contraseña. Quedarse callado ahí
     es lo correcto.

  2. ACEPTAR VARIAS DE UN GOLPE — arriba de la lista hay una barra
     verde. Apriete «Verlas y aceptarlas todas»: le muestra la lista
     completa ANTES de tocar nada. Cancele y no pasa nada.

  3. EL SELECTOR — en cualquier documento, abra el campo del renglón.
     Escriba «patrimonio» y verá que busca. Pruebe las flechas, Enter y
     Escape.

  4. QUE APRENDA — busque «0001.pdf», que quedó sin propuesta porque su
     tercero no está en la exógena. Asígnelo a mano a cualquier renglón.
     Después vaya a «Cuenta y ajustes» y baje hasta «Lo que el programa
     aprendió de usted»: ahí está la regla, y la puede borrar.

  5. EXÓGENA — la pestaña al lado de «Formulario 210».
     Arriba, los tres avisos de la DIAN, textuales, con la fecha de
     corte. Después los cinco topes. Después la tabla.
     Filtre por «Requiere decisión»: son las filas donde la DIAN propone
     más de un renglón, y le muestra las opciones como ella las
     escribió. Tax-i no elige por usted.
     Filtre por «Posible duplicado»: verá las cesantías, que las
     reportan el empleador y el fondo con cifras casi iguales. Cada
     marca dice por qué se marcó.

  6. LLEVAR AL 210 — en una fila que NO requiera decisión, apriete
     «Llevar al Formulario 210». Le pregunta antes de escribir.
     (Hace falta una plantilla en la carpeta plantillas/.)

  7. LA PROPUESTA — pestaña «Formulario 210», sub-pestaña «Propuesta».
     Es el camino nuevo, y el único que gasta plata. Antes de apretar
     nada le dice cuántos documentos va a mandar y cuánto cuesta más o
     menos. Apriete «Proponer el formulario» y espere.
     Lo que sale es una PROPUESTA: nada entró al 210 todavía. Los
     renglones en amarillo son los que el modelo tuvo que interpretar
     —son por donde hay que empezar—; los demás traen la cifra, la
     frase exacta del papel de donde salió y un enlace para abrir el
     documento al lado. «Aceptar los de nivel A y B» muestra la lista
     completa antes de confirmar.
     Si no ve el botón sino un aviso de que está apagada, es que está
     en IA_PROVEEDOR=ninguno, que es el modo de fábrica. Todo lo demás
     de arriba funciona igual.

  8. COMPARAR — al final de esa misma pestaña. Suba un 210 lleno a mano
     y le dice, renglón por renglón, en cuántos coincidió. Es la
     medición que sirve para decidir si esto ayuda de verdad. No cambia
     ni una cifra del cliente.

  9. RENTAI — el cuadradito negro de abajo a la derecha. Un clic abre,
     otro cierra. Quédese mirando el logo unos segundos: parpadea, y de
     vez en cuando se queda pensando o hace el guiño con el visto.

  Para volver atrás: borre el cliente desde la lista de clientes, o
  quite la exógena desde su pestaña. Los documentos borrados van a
  datos/papelera/, no al vacío.
""" % (total_docs, sin_asignar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
