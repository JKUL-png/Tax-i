"""
El modo demostración: un cliente de mentira para poder mostrar el programa.

Para qué
--------
Un contador que quiera enseñarle Tax-i a un colega tiene hoy un problema:
lo único que hay en el programa son documentos de clientes de verdad. No
puede abrirlo en una reunión, ni grabar un video, ni pasarle el
computador a nadie.

Este modo carga un cliente **inventado**, con documentos inventados, para
que haya algo que mostrar sin exponer a nadie.

Todo lo de aquí es falso a propósito
------------------------------------
El cliente se llama con una advertencia adentro del nombre. Los
documentos empiezan diciendo, en mayúsculas y en la primera línea, que
son ficticios. Las cédulas no son cédulas de nadie: son secuencias
obvias. Las empresas no existen.

Nada de esto se parece a un documento real ni por accidente, y esa es la
idea: si alguien ve una de estas pantallas en una captura o en un video,
tiene que ser evidente en dos segundos que no es de nadie.

Cómo NO se mezcla con lo real
-----------------------------
Cada cliente inventado lleva `es_demo = 1` en la base. Con eso:

  - la pantalla los muestra siempre marcados, y pone un aviso arriba
    mientras el modo esté prendido;
  - apagar el modo los borra a TODOS de un golpe, con sus documentos,
    sin tocar ni un cliente de verdad.

Los clientes de verdad nunca llevan esa marca: la pantalla no tiene forma
de ponerla, solo la pone este archivo.
"""

from pathlib import Path

from app import db, documentos, formulario

# La marca que llevan en el nombre. Sale en la lista, en el riel, en la
# pantalla del cliente y en cualquier captura que alguien tome.
MARCA = "(EJEMPLO FICTICIO)"

# La advertencia que encabeza cada documento inventado. Va en la primera
# línea para que se vea también en la vista previa, sin abrir el archivo.
ADVERTENCIA = (
    "*** DOCUMENTO FICTICIO — DATOS INVENTADOS PARA UNA DEMOSTRACIÓN ***\n"
    "*** NO CORRESPONDE A NINGUNA PERSONA NI EMPRESA REAL           ***\n"
    "\n"
)


# El cliente de ejemplo y lo que le llegó. Los renglones del checklist
# son los que un contador pediría de verdad; los documentos, no.
CLIENTE = {
    "nombre": "Juan Ejemplo Demostración " + MARCA,
    "dos_digitos": "42",
    "fecha_vencimiento": None,   # las fechas salen del calendario oficial
    "notas": ("Cliente inventado del modo demostración. Se puede borrar"
              " apagando ese modo."),
}

CHECKLIST = (
    "Certificado de ingresos y retenciones",
    "Certificados bancarios",
    "Certificado de aportes a salud y pensión",
    "Certificado de medicina prepagada",
    "Certificado de intereses de vivienda",
    "Declaración del año anterior",
)

DOCUMENTOS = (
    (
        "Certificado de ingresos y retenciones 2025.txt",
        "CERTIFICADO DE INGRESOS Y RETENCIONES\n"
        "Año gravable 2025\n"
        "\n"
        "Empleador : EMPRESA DE EJEMPLO S.A.S. (no existe)\n"
        "NIT       : 900.000.000-0\n"
        "Empleado  : Juan Ejemplo Demostración\n"
        "Documento : 1.111.111.142\n"
        "\n"
        "Pagos por salarios ................. 48.000.000\n"
        "Cesantías e intereses .............. 4.000.000\n"
        "Aportes obligatorios a salud ....... 1.920.000\n"
        "Aportes obligatorios a pensión ..... 1.920.000\n"
        "Retención en la fuente practicada .. 2.400.000\n",
    ),
    (
        "Certificado bancario Banco de Ejemplo.txt",
        "CERTIFICADO PARA DECLARACIÓN DE RENTA\n"
        "BANCO DE EJEMPLO (entidad inventada)\n"
        "Año gravable 2025\n"
        "\n"
        "Titular          : Juan Ejemplo Demostración\n"
        "Cuenta de ahorros: ****4242\n"
        "\n"
        "Saldo a 31 de diciembre ............ 12.500.000\n"
        "Rendimientos financieros ........... 320.000\n"
        "Retención sobre rendimientos ....... 22.400\n"
        "GMF (4x1000) pagado ................ 180.000\n",
    ),
    (
        "Certificado medicina prepagada.txt",
        "CERTIFICADO DE PAGOS — MEDICINA PREPAGADA\n"
        "PREPAGADA DE EJEMPLO S.A. (no existe)\n"
        "Año gravable 2025\n"
        "\n"
        "Afiliado : Juan Ejemplo Demostración\n"
        "Plan     : Plan de ejemplo\n"
        "\n"
        "Total pagado en el año ............. 3.600.000\n"
        "\n"
        "Nota: este certificado es inventado. El programa NO decide si un\n"
        "pago es deducible; eso lo determina el contador.\n",
    ),
    (
        "Factura de ejemplo.xml",
        None,   # el XML se arma aparte, abajo
    ),
)

# Una factura electrónica inventada, con la forma real (UBL 2.1), para
# poder mostrar que los XML los lee el programa solo, sin gastar IA.
FACTURA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!-- FACTURA FICTICIA. Datos inventados para una demostración. -->
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:ID>EJEMPLO-0001</cbc:ID>
 <cbc:IssueDate>2025-06-15</cbc:IssueDate>
 <cac:AccountingSupplierParty><cac:Party><cac:PartyTaxScheme>
   <cbc:RegistrationName>DROGUERÍA DE EJEMPLO S.A.S.</cbc:RegistrationName>
   <cbc:CompanyID>900000001</cbc:CompanyID>
 </cac:PartyTaxScheme></cac:Party></cac:AccountingSupplierParty>
 <cac:AccountingCustomerParty><cac:Party><cac:PartyTaxScheme>
   <cbc:RegistrationName>Juan Ejemplo Demostración</cbc:RegistrationName>
 </cac:PartyTaxScheme></cac:Party></cac:AccountingCustomerParty>
 <cac:LegalMonetaryTotal>
   <cbc:PayableAmount currencyID="COP">185000</cbc:PayableAmount>
 </cac:LegalMonetaryTotal>
</Invoice>
"""


def activo():
    """¿Hay algún cliente de demostración cargado ahora mismo?"""
    return bool(db.clientes_de_demostracion())


def estado():
    """En qué va la demostración, para contárselo a la pantalla."""
    ids = db.clientes_de_demostracion()
    return {
        "activo": bool(ids),
        "clientes": len(ids),
        "marca": MARCA,
    }


def prender():
    """Carga el cliente inventado con sus documentos. Devuelve el estado.

    Si ya estaba prendido no hace nada: no se acumulan copias del mismo
    cliente de ejemplo cada vez que alguien aprieta el botón.
    """
    if activo():
        return estado()

    cliente = db.crear_cliente(
        CLIENTE["nombre"], CLIENTE["dos_digitos"],
        CLIENTE["fecha_vencimiento"], CLIENTE["notas"],
        es_demo=True,
    )
    cliente_id = cliente["id"]

    db.crear_renglones(cliente_id, list(CHECKLIST))

    for nombre, cuerpo in DOCUMENTOS:
        if cuerpo is None:
            contenido = FACTURA_XML.encode("utf-8")
        else:
            contenido = (ADVERTENCIA + cuerpo).encode("utf-8")

        nombre_guardado, tamano = documentos.guardar_contenido(
            cliente_id, nombre, contenido
        )
        db.crear_documento(
            cliente_id=cliente_id,
            nombre_original=nombre,
            nombre_guardado=nombre_guardado,
            extension=Path(nombre_guardado).suffix.lower(),
            tamano=tamano,
            huella=documentos.huella_del_contenido(contenido),
        )

    return estado()


def apagar():
    """Borra TODOS los clientes de demostración, con sus documentos.

    Solo toca los que llevan la marca `es_demo`. Un cliente de verdad no
    la lleva nunca —la pantalla no tiene forma de ponerla—, así que aquí
    no hay manera de borrar el trabajo de nadie.

    Devuelve cuántos se quitaron.
    """
    ids = db.clientes_de_demostracion()
    for cliente_id in ids:
        # Primero los archivos del disco y después la fila de la base:
        # al revés, se perdería la ruta de la carpeta que hay que borrar.
        documentos.eliminar_carpeta_cliente(cliente_id)
        formulario.eliminar_carpeta_cliente(cliente_id)
        db.eliminar_cliente(cliente_id)
    return {"quitados": len(ids), **estado()}
