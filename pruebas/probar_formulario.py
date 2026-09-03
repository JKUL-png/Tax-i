"""
Prueba del Paso 5: el Formulario 210 dentro de la aplicación.

Se corre así, desde la carpeta del proyecto:

    .venv/bin/python pruebas/probar_formulario.py

Lo que comprueba:

  A. Que cada cliente tenga lo suyo y no vea lo del otro.
  B. Que no se pueda anotar un valor en una casilla con fórmula.
  C. Que el archivo se arme bien y traiga los totales calculados.
  D. Que los renglones de la liquidación (impuesto y saldos) no salgan en
     pantalla, que es una regla del proyecto.
  E. Que al eliminar un cliente no quede nada suyo en el disco.
  F. Que la hoja que se muestra en pantalla traiga lo que debe: las
     fórmulas marcadas como tales y los valores del cliente encima.
  G. Que se pueda subir otra plantilla, y que se rechace un archivo que
     no sirva.

Crea dos clientes de prueba y los borra al terminar, pase lo que pase.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from io import BytesIO  # noqa: E402

from openpyxl import Workbook  # noqa: E402

from app import db, formulario  # noqa: E402
from app.escribir_210 import EscrituraBloqueada  # noqa: E402

resultados = []


def comprobar(descripcion, condicion, detalle=""):
    resultados.append(bool(condicion))
    linea = f"  {'OK  ' if condicion else 'FALLA'}  {descripcion}"
    if detalle:
        linea += f"  [{detalle}]"
    print(linea)


def se_niega(descripcion, funcion):
    try:
        funcion()
    except EscrituraBloqueada as error:
        comprobar(descripcion, True, str(error)[:70])
        return
    comprobar(descripcion, False, "NO se negó")


def main():
    if formulario.ruta_plantilla() is None:
        print("No hay plantilla en plantillas/. No se puede probar.")
        return 1

    uno = db.crear_cliente("Cliente de prueba A", "11")
    dos = db.crear_cliente("Cliente de prueba B", "22")
    print(f"Clientes de prueba: {uno['id']} y {dos['id']}")

    try:
        # --------------------------------------------------------------
        print("\nA. Cada cliente tiene lo suyo")
        # --------------------------------------------------------------
        formulario.guardar_valor(uno["id"], "G115", 45000000, "certificado.pdf")
        formulario.guardar_valor(uno["id"], "G44", 3500000, "extracto.pdf")
        formulario.guardar_valor(dos["id"], "G115", 12000000, "otro.pdf")

        valores_uno = formulario.listar_valores(uno["id"])
        valores_dos = formulario.listar_valores(dos["id"])
        comprobar("el cliente A tiene sus 2 valores", len(valores_uno) == 2)
        comprobar("el cliente B tiene solo 1", len(valores_dos) == 1)
        comprobar(
            "la misma casilla tiene un valor distinto en cada cliente",
            valores_uno[-1]["valor"] == 45000000
            and valores_dos[0]["valor"] == 12000000,
            f"A={valores_uno[-1]['valor']} B={valores_dos[0]['valor']}",
        )
        comprobar(
            "los valores traen la descripción de la plantilla",
            valores_uno[-1]["descripcion"] == "Salarios",
            valores_uno[-1]["descripcion"],
        )

        # --------------------------------------------------------------
        print("\nB. Lo que no se puede anotar")
        # --------------------------------------------------------------
        se_niega("una casilla con fórmula (I42)",
                 lambda: formulario.guardar_valor(uno["id"], "I42", 1, "x"))
        se_niega("una casilla que no existe (ZZ9999)",
                 lambda: formulario.guardar_valor(uno["id"], "ZZ9999", 1, "x"))
        se_niega("una casilla de la columna de descripciones (F32)",
                 lambda: formulario.guardar_valor(uno["id"], "F32", 1, "x"))
        se_niega("texto en vez de número",
                 lambda: formulario.guardar_valor(uno["id"], "G44", "mucho", "x"))

        # --------------------------------------------------------------
        print("\nC. El archivo del cliente A")
        # --------------------------------------------------------------
        # Primero el camino normal: sin calcular los totales. Es lo que
        # hace el botón "Generar el archivo", y es el que usa el contador
        # casi siempre. Los totales los calcula Excel al abrir el archivo.
        rapido = formulario.generar(uno)
        archivo = formulario.archivo_cliente(uno["id"])

        comprobar("el archivo quedó en la carpeta del cliente A",
                  archivo.exists(), str(archivo.relative_to(RAIZ)))
        comprobar("el cliente B no tiene archivo todavía",
                  not formulario.archivo_cliente(dos["id"]).exists())
        comprobar("se escribieron los 2 valores",
                  rapido["valores_escritos"] == 2)
        comprobar("sin calcular totales, NO se llamó a LibreOffice",
                  rapido["recalculo"] is None and rapido["con_totales"] is False)
        comprobar("pero las 902 fórmulas se verificaron igual",
                  rapido["verificacion"]["formulas_comparadas"] == 902
                  and rapido["verificacion"]["formulas_distintas"] == 0)
        comprobar("y el archivo se entrega completo, para abrirlo en Excel",
                  archivo.exists() and archivo.stat().st_size > 0,
                  f"{archivo.stat().st_size} bytes")

        # Ahora el camino de "Actualizar totales", que sí pasa por
        # LibreOffice para poder mostrarlos dentro del programa.
        informe = formulario.generar(uno, con_totales=True)
        archivo = formulario.archivo_cliente(uno["id"])

        comprobar("pidiendo los totales, sí se llamó a LibreOffice",
                  informe["recalculo"] is not None
                  and informe["con_totales"] is True)
        comprobar("y también se verificaron las 902 fórmulas",
                  informe["verificacion"]["formulas_comparadas"] == 902
                  and informe["verificacion"]["formulas_distintas"] == 0)
        comprobar("se descarga con el nombre del cliente",
                  informe["nombre_descarga"]
                  == "Formulario 210 - Cliente de prueba A.xlsx",
                  informe["nombre_descarga"])

        if informe["recalculo"]["recalculado"]:
            totales = {t["renglon"]: t["valor"] for t in informe["totales"]}
            comprobar("el renglón 32 (rentas de trabajo) tomó los salarios",
                      totales.get("32") == 45000000, str(totales.get("32")))
            # OJO: la plantilla viene con datos de ejemplo adentro (un CDT
            # de 102.003.000, cuentas de Citibank y Davivienda...). El
            # patrimonio bruto es esos ejemplos MÁS lo que anotamos. No es
            # un error del programa: es lo que trae el archivo. El contador
            # tiene que poner en cero los ejemplos que no le sirvan.
            ejemplos_de_la_plantilla = 102003000
            comprobar("el renglón 29 suma el efectivo anotado a lo que ya"
                      " traía la plantilla de ejemplo",
                      totales.get("29") == ejemplos_de_la_plantilla + 3500000,
                      f"{totales.get('29')} = {ejemplos_de_la_plantilla}"
                      f" de ejemplo + 3500000 anotados")
        else:
            comprobar("sin LibreOffice, el archivo se entrega igual",
                      archivo.exists(), informe["recalculo"]["motivo"][:50])

        # --------------------------------------------------------------
        print("\nD. Lo que no se muestra en pantalla")
        # --------------------------------------------------------------
        # El programa no calcula impuestos ni saldos. Los renglones de la
        # liquidación privada están en el archivo, pero no en la pantalla.
        de_liquidacion = [
            t for t in informe["totales"]
            if 116 <= int(t["renglon"]) <= 137
        ]
        comprobar("ningún renglón de la liquidación privada sale en pantalla",
                  de_liquidacion == [], f"{len(de_liquidacion)} encontrados")
        comprobar("sí salen los renglones de patrimonio e ingresos",
                  any(t["renglon"] == "29" for t in informe["totales"]))

        # --------------------------------------------------------------
        print("\nE. El historial")
        # --------------------------------------------------------------
        historial = db.listar_bitacora_210(uno["id"])
        comprobar("quedaron los 2 movimientos del cliente A",
                  len(historial) == 2, f"{len(historial)}")
        comprobar("cada movimiento dice de dónde salió el dato",
                  all(m["documento"] for m in historial))

        db.borrar_valor_210(uno["id"], "G44")
        comprobar("quitar un valor lo saca de la lista",
                  len(formulario.listar_valores(uno["id"])) == 1)
        comprobar("y queda anotado en el historial",
                  len(db.listar_bitacora_210(uno["id"])) == 3)

        # --------------------------------------------------------------
        print("\nF. Al eliminar el cliente no queda nada suyo")
        # --------------------------------------------------------------
        carpeta = formulario.carpeta_cliente(uno["id"])
        db.eliminar_cliente(uno["id"])
        formulario.eliminar_carpeta_cliente(uno["id"])
        comprobar("la carpeta con su archivo de Excel se borró",
                  not carpeta.exists(), str(carpeta.relative_to(RAIZ)))
        comprobar("sus valores salieron de la base",
                  db.listar_valores_210(uno["id"]) == {})
        comprobar("su historial también",
                  db.listar_bitacora_210(uno["id"]) == [])
        comprobar("y el otro cliente sigue con lo suyo",
                  len(db.listar_valores_210(dos["id"])) == 1)

        # --------------------------------------------------------------
        print("\nG. La hoja que se ve en pantalla")
        # --------------------------------------------------------------
        hoja = formulario.hoja_del_cliente(dos["id"])
        comprobar("la hoja trae sus filas", len(hoja["filas"]) > 400,
                  f"{len(hoja['filas'])} filas")
        comprobar("dice de dónde salieron los valores que muestra",
                  hoja["origen"] in ("plantilla", "archivo"), hoja["origen"])

        por_celda = {}
        for fila in hoja["filas"]:
            for datos in fila["celdas"].values():
                por_celda[datos["celda"]] = (fila, datos)

        comprobar("las casillas con fórmula vienen marcadas y no editables",
                  por_celda["I42"][1]["tipo"] == "formula"
                  and not por_celda["I42"][1]["editable"])
        comprobar("las casillas de captura sí son editables",
                  por_celda["G115"][1]["editable"])
        comprobar("el valor anotado del cliente aparece en su casilla",
                  por_celda["G115"][1]["valor"] == 12000000
                  and por_celda["G115"][1]["anotado"],
                  str(por_celda["G115"][1]["valor"]))
        comprobar("y queda marcado como pendiente de recalcular",
                  por_celda["G115"][1]["pendiente"])
        comprobar("las filas traen la sangría de la plantilla",
                  any(f["sangria"] > 0 for f in hoja["filas"]))
        comprobar("las notas al pie vienen marcadas como notas",
                  any(f["es_nota"] for f in hoja["filas"]))

        # --------------------------------------------------------------
        print("\nH. Las casillas de un renglón: solo las que la plantilla LEE")
        # --------------------------------------------------------------
        #
        # Este bloque existe por un error que no rompía nada, que es lo
        # peor que puede pasar: «Llevar al Formulario 210» ofrecía G113 y
        # H113 para el renglón 32, y ninguna fórmula las lee. El contador
        # habría escrito los 84 millones ahí, habría visto que quedó
        # anotado, y el renglón 32 se habría quedado en cero.
        leidas = formulario.celdas_que_alguien_lee()
        comprobar("se sabe qué casillas lee alguna fórmula", len(leidas) > 100,
                  "%d casillas" % len(leidas))

        del32 = formulario.celdas_de_renglon("32")
        celdas32 = [c["celda"] for c in del32]
        # La fórmula que engañaba estaba en OTRA hoja del libro.
        comprobar("el renglón 32 ya no ofrece G113 ni H113",
                  "G113" not in celdas32 and "H113" not in celdas32,
                  celdas32[:6])
        comprobar("y sí ofrece la fila donde de verdad va el salario",
                  "G115" in celdas32, celdas32[:6])
        comprobar("todas las que ofrece las lee alguna fórmula",
                  all(c in leidas for c in celdas32))

        # El bloque se encuentra igual esté como esté la plantilla: con
        # el número del renglón repetido en todas sus filas o una sola vez.
        for numero in ("29", "30", "32", "132"):
            comprobar("el renglón %s tiene dónde escribir" % numero,
                      len(formulario.celdas_de_renglon(numero)) > 0, numero)

        # Escoger la casilla NO es una decisión tributaria: el renglón ya
        # está decidido y lo que falta es leer la etiqueta de la fila.
        recomendada, motivo, todas = formulario.elegir_casilla(
            "32", "Pagos por salarios (Concepto: 2276)")
        comprobar("«Pagos por salarios» cae solo en la fila «Salarios»",
                  recomendada and recomendada["celda"] == "G115",
                  recomendada and recomendada["celda"])
        comprobar("y dice por qué la escogió", bool(motivo), motivo)

        # Donde de verdad hay que decidir, no se adivina.
        recomendada, _m, todas = formulario.elegir_casilla(
            "29", "Saldo cuentas bancarias (Titular Principal)")
        comprobar("con muchas cuentas parecidas, le pregunta al contador",
                  recomendada is None, recomendada)
        comprobar("pero le muestra todas las opciones", len(todas) > 1,
                  len(todas))

        # Y lo que él escoja se recuerda, para no volvérselo a preguntar.
        formulario.recordar_casilla("29", todas[3]["celda"])
        recomendada, motivo, _t = formulario.elegir_casilla(
            "29", "Saldo cuentas bancarias (Titular Principal)")
        comprobar("la próxima vez propone la que él escogió",
                  recomendada and recomendada["celda"] == todas[3]["celda"],
                  recomendada and recomendada["celda"])
        comprobar("y le dice que fue la que usó antes",
                  "vez pasada" in motivo, motivo)
        db.guardar_ajuste(formulario._clave_de_recordada("29"), "")

        # --------------------------------------------------------------
        print("\nI. Subir otra plantilla")
        # --------------------------------------------------------------
        antes = formulario.ruta_plantilla()
        subidas = []
        try:
            # Un archivo que no es Excel
            try:
                formulario.guardar_plantilla_subida(
                    "cuentas.txt", b"esto no es un excel"
                )
                comprobar("rechaza un archivo que no es Excel", False, "lo aceptó")
            except formulario.SinPlantilla as error:
                comprobar("rechaza un archivo que no es Excel", True,
                          str(error)[:50])

            # Un Excel de verdad, pero sin la hoja de captura
            otro = Workbook()
            otro.active.title = "Mis cuentas"
            memoria = BytesIO()
            otro.save(memoria)
            try:
                formulario.guardar_plantilla_subida(
                    "otro.xlsx", memoria.getvalue()
                )
                comprobar("rechaza un Excel sin la hoja de captura", False,
                          "lo aceptó")
            except formulario.SinPlantilla as error:
                comprobar("rechaza un Excel sin la hoja de captura", True,
                          str(error)[:50])

            # La plantilla de verdad, subida con otro nombre
            copia = formulario.guardar_plantilla_subida(
                "Mi plantilla del contador.xlsx", antes.read_bytes()
            )
            subidas.append(copia)
            comprobar("acepta una plantilla que sí tiene la hoja de captura",
                      copia.exists(), copia.name)
            comprobar("y queda en uso de una vez",
                      formulario.ruta_plantilla().name == copia.name,
                      formulario.ruta_plantilla().name)
            comprobar("la plantilla original sigue donde estaba",
                      antes.exists())
            comprobar("las dos aparecen para elegir",
                      len(formulario.listar_plantillas()) >= 2,
                      str([p.name for p in formulario.listar_plantillas()]))

            formulario.elegir_plantilla(antes.name)
            comprobar("se puede volver a la anterior",
                      formulario.ruta_plantilla().name == antes.name)
        finally:
            for sobrante in subidas:
                sobrante.unlink(missing_ok=True)
            db.guardar_ajuste(formulario.CLAVE_PLANTILLA, antes.name)

    finally:
        for cliente in (uno, dos):
            db.eliminar_cliente(cliente["id"])
            formulario.eliminar_carpeta_cliente(cliente["id"])
        print("\nClientes de prueba eliminados.")

    total = len(resultados)
    buenas = sum(resultados)
    print(f"\n{buenas} de {total} comprobaciones pasaron.")
    if buenas != total:
        print("HAY FALLAS.")
        return 1
    print("Todo bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
