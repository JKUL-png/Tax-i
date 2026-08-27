"""
Las dos salidas del programa.

  1. **El resumen del cliente**: qué documentos llegaron, cuáles faltan y
     qué archivos hay guardados. Para imprimir, guardar o archivar.

  2. **El mensaje de "esto es lo que me falta"**: un texto corto y cortés,
     listo para copiar y mandarle al cliente por WhatsApp.

Los dos se arman con los datos que ya están en la base. Aquí no se calcula
nada de impuestos, no se dice qué es deducible, no se opina sobre si el
cliente debe declarar. Solo se relaciona lo que llegó y lo que falta.
"""

from datetime import date, datetime

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# Va al pie de las dos salidas. Es la línea legal del brief: este programa
# organiza y reporta, no hace impuestos.
NOTA_LEGAL = (
    "Este documento relaciona los documentos recibidos y los pendientes. "
    "No contiene cálculos tributarios ni asesoría."
)


def fecha_en_palabras(iso):
    """Convierte '2026-09-15' en '15 de septiembre de 2026'."""
    if not iso:
        return ""
    try:
        leida = date.fromisoformat(iso)
    except ValueError:
        return iso
    return "{} de {} de {}".format(leida.day, MESES[leida.month - 1], leida.year)


def fecha_corta(iso_con_hora):
    """Convierte '2026-08-26T14:03:00' en '26/08/2026'."""
    if not iso_con_hora:
        return ""
    try:
        leida = datetime.fromisoformat(iso_con_hora)
    except ValueError:
        return iso_con_hora
    return leida.strftime("%d/%m/%Y")


def peso_en_palabras(bytes_):
    """Convierte 1536000 en '1,5 MB'."""
    if bytes_ < 1024:
        return str(bytes_) + " B"
    if bytes_ < 1024 * 1024:
        return str(round(bytes_ / 1024)) + " KB"
    return "{:.1f}".format(bytes_ / (1024 * 1024)).replace(".", ",") + " MB"


def primer_nombre(nombre_completo):
    """Saca el primer nombre, para saludar por el nombre y no por el apellido."""
    partes = (nombre_completo or "").split()
    return partes[0] if partes else ""


# ----------------------------------------------------------
# El resumen del cliente
# ----------------------------------------------------------


def armar_resumen(cliente, renglones, documentos):
    """Arma el resumen como datos, para que la pantalla lo dibuje.

    Devolver datos y no texto permite que la misma información sirva para
    la página imprimible y para el archivo .txt, sin escribirla dos veces.
    """
    recibidos = [r for r in renglones if r["estado"] == "recibido"]
    faltantes = [r for r in renglones if r["estado"] != "recibido"]

    return {
        "cliente": {
            "nombre": cliente["nombre"],
            "dos_digitos": cliente["dos_digitos"],
            "fecha_vencimiento": cliente["fecha_vencimiento"],
            "fecha_vencimiento_texto": fecha_en_palabras(
                cliente["fecha_vencimiento"]
            ),
            "notas": cliente.get("notas") or "",
        },
        "checklist": {
            "total": len(renglones),
            "recibidos": [r["titulo"] for r in recibidos],
            "faltantes": [r["titulo"] for r in faltantes],
        },
        "documentos": [
            {
                "nombre": d["nombre_original"],
                "tipo": d["tipo"],
                "peso": peso_en_palabras(d["tamano"]),
                "fecha": fecha_corta(d["subido_en"]),
                "venia_en_zip": d["venia_en_zip"],
            }
            for d in documentos
        ],
        "generado_en": fecha_en_palabras(date.today().isoformat()),
        "nota_legal": NOTA_LEGAL,
    }


def texto_del_resumen(resumen):
    """Convierte el resumen en un texto plano, para guardarlo como archivo."""
    cliente = resumen["cliente"]
    lista = resumen["checklist"]
    renglones = []

    renglones.append("RESUMEN DE DOCUMENTOS")
    renglones.append("=" * 60)
    renglones.append("")
    renglones.append(cliente["nombre"])
    renglones.append("Cédula termina en " + cliente["dos_digitos"])

    if cliente["fecha_vencimiento_texto"]:
        renglones.append(
            "Fecha de vencimiento: " + cliente["fecha_vencimiento_texto"]
        )
        renglones.append(
            "  (referencia tomada del calendario oficial — verificable y editable)"
        )
    else:
        renglones.append("Fecha de vencimiento: sin registrar")

    if cliente["notas"]:
        renglones.append("")
        renglones.append("Datos adicionales:")
        for linea in cliente["notas"].split("\n"):
            renglones.append("  " + linea)

    faltan = len(lista["faltantes"])
    renglones.append("")
    renglones.append("-" * 60)
    renglones.append(
        "CHECKLIST: {} de {} recibidos".format(
            len(lista["recibidos"]), lista["total"]
        )
        + ("" if faltan == 0 else ", faltan {}".format(faltan))
    )
    renglones.append("-" * 60)

    renglones.append("")
    renglones.append("RECIBIDOS ({})".format(len(lista["recibidos"])))
    if lista["recibidos"]:
        for titulo in lista["recibidos"]:
            renglones.append("  [X] " + titulo)
    else:
        renglones.append("  (ninguno todavía)")

    renglones.append("")
    renglones.append("FALTAN ({})".format(faltan))
    if lista["faltantes"]:
        for titulo in lista["faltantes"]:
            renglones.append("  [ ] " + titulo)
    else:
        renglones.append("  (nada pendiente)")

    renglones.append("")
    renglones.append("ARCHIVOS GUARDADOS ({})".format(len(resumen["documentos"])))
    if resumen["documentos"]:
        for documento in resumen["documentos"]:
            linea = "  - {} ({}, {}, {})".format(
                documento["nombre"], documento["tipo"],
                documento["peso"], documento["fecha"],
            )
            if documento["venia_en_zip"]:
                linea += " [venía en " + documento["venia_en_zip"] + "]"
            renglones.append(linea)
    else:
        renglones.append("  (ninguno todavía)")

    renglones.append("")
    renglones.append("-" * 60)
    renglones.append("Generado el " + resumen["generado_en"] + ".")
    renglones.append(resumen["nota_legal"])
    renglones.append("")

    return "\n".join(renglones)


# ----------------------------------------------------------
# El mensaje para el cliente
# ----------------------------------------------------------


def mensaje_de_faltantes(cliente, renglones):
    """Arma el mensaje listo para copiar y mandar por WhatsApp.

    Es un borrador: la pantalla lo muestra en un campo editable para que
    el contador lo ajuste antes de mandarlo. El programa no le pone en la
    boca ningún consejo tributario — solo dice qué documentos faltan.
    """
    faltantes = [r["titulo"] for r in renglones if r["estado"] != "recibido"]
    recibidos = len(renglones) - len(faltantes)

    nombre = primer_nombre(cliente["nombre"])
    saludo = "Hola " + nombre + ", buen día." if nombre else "Buen día."

    lineas = [saludo, ""]

    if not renglones:
        lineas.append(
            "Todavía no tengo armada la lista de documentos para su renta."
        )
        return "\n".join(lineas)

    if not faltantes:
        lineas.append(
            "Ya tengo los {} documentos que necesitaba para su renta. "
            "No me falta nada por ahora.".format(len(renglones))
        )
    else:
        lineas.append("Para su declaración de renta me falta recibir:")
        lineas.append("")
        for titulo in faltantes:
            lineas.append("• " + titulo)
        lineas.append("")
        lineas.append(
            "Ya tengo {} de {} documentos.".format(recibidos, len(renglones))
        )

    if cliente["fecha_vencimiento"]:
        lineas.append("")
        lineas.append(
            "La fecha de vencimiento para presentar es el "
            + fecha_en_palabras(cliente["fecha_vencimiento"]) + "."
        )

    lineas.append("")
    lineas.append("Quedo atento. Gracias.")

    return "\n".join(lineas)
