"""
El juego de documentos con el que se mide la clasificación.

Los documentos NO están guardados en el repositorio: se arman aquí con
código, cada vez que corre la prueba. Dos razones, y la segunda es la
que manda:

  1. Así el juego es reproducible y se puede cambiar sin subir binarios.
  2. Un documento tributario no entra a un repositorio público, ni
     siquiera uno inventado. Si hubiera archivos de ejemplo adentro, el
     día que alguien ponga ahí el de un cliente de verdad —«total, es
     igual que el que ya está»— no habría marcha atrás.

Todo lo de aquí es INVENTADO: el contribuyente, los NIT de las empresas
pequeñas, las cifras y los números de cuenta. Coincide a propósito con
el reporte de exógena de ejemplo, porque de eso se trata el cruce.

Cómo llegan los archivos de verdad
----------------------------------
Es mitad y mitad, y el juego lo refleja:

  - La mitad llega con un nombre que dice qué es: «Certificado
    Bancolombia 2025.pdf».
  - La otra mitad llega con el nombre que le puso la cámara o el
    escáner: «IMG_20260315_112233.jpg», «scan0001.pdf», «WhatsApp Image
    2026-03-14 at 9.21.11 AM.jpeg». Esos no dicen nada.

Y hay tres casos que en la vida real aparecen siempre:

  - PDF con contraseña. Los bancos los mandan así.
  - PDF que es una foto escaneada: no tiene texto adentro.
  - Fotos sueltas tomadas con el celular.
"""

import zlib
from io import BytesIO
from pathlib import Path


# ----------------------------------------------------------
# Armar un PDF a mano
# ----------------------------------------------------------
#
# Sin librerías nuevas: un PDF con texto es un archivo de texto con una
# tabla de posiciones al final. Con esto alcanza para probar la lectura,
# que es de lo que se trata.


def pdf_con_texto(lineas):
    """Un PDF de una página con esas líneas escritas. Devuelve bytes."""
    contenido = ["BT", "/F1 10 Tf", "12 TL", "40 780 Td"]
    for linea in lineas:
        escapada = (linea.replace("\\", r"\\")
                         .replace("(", r"\(")
                         .replace(")", r"\)"))
        contenido.append("(%s) Tj T*" % escapada)
    contenido.append("ET")
    flujo = "\n".join(contenido).encode("latin-1", errors="replace")
    comprimido = zlib.compress(flujo)

    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
        b" /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comprimido)
        + comprimido + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica"
        b" /Encoding /WinAnsiEncoding >>",
    ]

    salida = BytesIO()
    salida.write(b"%PDF-1.4\n")
    posiciones = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(salida.tell())
        salida.write(b"%d 0 obj\n" % numero + cuerpo + b"\nendobj\n")

    inicio_tabla = salida.tell()
    salida.write(b"xref\n0 %d\n" % (len(objetos) + 1))
    salida.write(b"0000000000 65535 f \n")
    for posicion in posiciones:
        salida.write(b"%010d 00000 n \n" % posicion)
    salida.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                 % (len(objetos) + 1, inicio_tabla))
    return salida.getvalue()


def pdf_sin_texto():
    """Un PDF de una página en blanco: como el que sale de escanear."""
    return pdf_con_texto([])


def pdf_con_clave(lineas, clave="secreta"):
    """Un PDF con contraseña, de los que mandan los bancos."""
    from pypdf import PdfReader, PdfWriter

    lector = PdfReader(BytesIO(pdf_con_texto(lineas)))
    escritor = PdfWriter()
    for pagina in lector.pages:
        escritor.add_page(pagina)
    escritor.encrypt(clave)
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def pdf_con_candado_sin_clave(lineas):
    """Un PDF 'protegido' pero que abre con clave vacía.

    Es el caso más común de todos: el banco le pone el candado para que
    nadie lo edite, no para que nadie lo lea.
    """
    from pypdf import PdfReader, PdfWriter

    lector = PdfReader(BytesIO(pdf_con_texto(lineas)))
    escritor = PdfWriter()
    for pagina in lector.pages:
        escritor.add_page(pagina)
    escritor.encrypt("", owner_password="dueno")
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def foto():
    """Una foto de celular. No tiene texto y no se puede leer."""
    # Un JPEG mínimo pero válido: cabecera, un poco de relleno y el final.
    return (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01"
            b"\x00\x01\x00\x00" + b"\x00" * 120 + b"\xff\xd9")


# ----------------------------------------------------------
# El XML de una factura electrónica
# ----------------------------------------------------------


def xml_de_factura(nit_emisor, emisor, receptor, numero, fecha, total):
    """Una factura electrónica en el formato de la DIAN (UBL 2.1)."""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"'
            ' xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:'
            'CommonBasicComponents-2"'
            ' xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:'
            'CommonAggregateComponents-2">\n'
            '  <cbc:ID>%s</cbc:ID>\n'
            '  <cbc:UUID>a1b2c3d4e5f60718293a4b5c6d7e8f90</cbc:UUID>\n'
            '  <cbc:IssueDate>%s</cbc:IssueDate>\n'
            '  <cac:AccountingSupplierParty><cac:Party><cac:PartyTaxScheme>\n'
            '    <cbc:RegistrationName>%s</cbc:RegistrationName>\n'
            '    <cbc:CompanyID>%s</cbc:CompanyID>\n'
            '  </cac:PartyTaxScheme></cac:Party></cac:AccountingSupplierParty>\n'
            '  <cac:AccountingCustomerParty><cac:Party><cac:PartyTaxScheme>\n'
            '    <cbc:RegistrationName>%s</cbc:RegistrationName>\n'
            '    <cbc:CompanyID>1023456789</cbc:CompanyID>\n'
            '  </cac:PartyTaxScheme></cac:Party></cac:AccountingCustomerParty>\n'
            '  <cac:LegalMonetaryTotal>\n'
            '    <cbc:PayableAmount currencyID="COP">%s</cbc:PayableAmount>\n'
            '  </cac:LegalMonetaryTotal>\n'
            '</Invoice>\n'
            % (numero, fecha, emisor, nit_emisor, receptor, total)
            ).encode("utf-8")


# ----------------------------------------------------------
# El juego de veinte
# ----------------------------------------------------------
#
# Cada uno dice a qué renglones del 210 PODRÍA ir. Una sugerencia se
# cuenta como acertada si cae en esa lista. Los que tienen la lista
# vacía son los que NO se deben poder clasificar: una foto sin texto, un
# PDF con contraseña, un tercero que la exógena no menciona. En esos,
# acertar es quedarse callado.


def _cir(empresa, nit):
    return [
        "CERTIFICADO DE INGRESOS Y RETENCIONES",
        "Año gravable 2025 - Formulario 220",
        "Nombre o razon social del agente retenedor: %s" % empresa,
        "NIT del agente retenedor: %s" % nit,
        "Apellidos y nombres del empleado: GOMEZ RIVERA CARLOS ANDRES",
        "Cedula de ciudadania: 1023456789",
        "Pagos por salarios: 29.044.349",
        "Cesantias e intereses de cesantias: 2.460.998",
        "Aportes obligatorios a salud: 1.201.119",
        "Retencion en la fuente practicada: 0",
    ]


def _certificado_banco(banco, nit, cuenta):
    return [
        "CERTIFICADO PARA DECLARACION DE RENTA 2025",
        "%s" % banco,
        "NIT %s" % nit,
        "Senor(a): GOMEZ RIVERA CARLOS ANDRES  C.C. 1023456789",
        "Numero de cuenta: %s" % cuenta,
        "Saldo a 31 de diciembre de 2025: 8.000.514",
        "Rendimientos financieros del periodo: 106.246",
        "Gravamen a los movimientos financieros: 12.400",
    ]


DOCUMENTOS = [
    # ---------- Los que llegan con un nombre que dice qué son ----------
    {"nombre": "Certificado de ingresos y retenciones 2025 - Agroindustrias.pdf",
     "hacer": lambda: pdf_con_texto(_cir("AGROINDUSTRIAS DEL VALLE S.A.S.",
                                         "900.123.456-7")),
     "renglones": ["29", "32", "33", "36", "59", "76", "100"]},

    {"nombre": "Certificado Bancolombia 2025.pdf",
     "hacer": lambda: pdf_con_texto(_certificado_banco(
         "BANCOLOMBIA S.A.", "890.903.938-8", "22003344556")),
     "renglones": ["29", "30"]},

    {"nombre": "certificado davivienda saldos.pdf",
     "hacer": lambda: pdf_con_texto(_certificado_banco(
         "BANCO DAVIVIENDA S.A.", "860.034.313-7", "4405566778")),
     "renglones": ["30"]},

    {"nombre": "Certificado de cesantias Porvenir.pdf",
     "hacer": lambda: pdf_con_texto([
         "FONDO DE CESANTIAS PORVENIR",
         "NIT 800.170.043-1",
         "CERTIFICADO DE CESANTIAS E INTERESES 2025",
         "Afiliado: GOMEZ RIVERA CARLOS ANDRES  C.C. 1023456789",
         "Valor total de las cesantias abonadas: 2.460.907",
     ]),
     "renglones": ["29", "32", "36", "51", "67", "84"]},

    {"nombre": "Impuesto predial Palmira 2025.pdf",
     "hacer": lambda: pdf_con_texto([
         "MUNICIPIO DE PALMIRA - SECRETARIA DE HACIENDA",
         "NIT 890.100.200-5",
         "IMPUESTO PREDIAL UNIFICADO VIGENCIA 2025",
         "Propietario: GOMEZ RIVERA CARLOS ANDRES",
         "Avaluo catastral: 60.512.304",
     ]),
     "renglones": ["29"]},

    {"nombre": "Certificado banco de bogota.pdf",
     "hacer": lambda: pdf_con_texto(_certificado_banco(
         "BANCO DE BOGOTA", "860.002.964-4", "9911223344")),
     "renglones": ["30"]},

    {"nombre": "factura_taller_metalico.xml",
     "hacer": lambda: xml_de_factura(
         "901234567", "TALLER METALICO ANDINO S.A.S.",
         "GOMEZ RIVERA CARLOS ANDRES", "DSE0042", "2025-08-14", "114465.00"),
     "renglones": ["74"]},

    {"nombre": "Retencion notaria Bogota.pdf",
     "hacer": lambda: pdf_con_texto([
         "BOGOTA DISTRITO CAPITAL",
         "NIT 899.999.061-9",
         "CERTIFICADO DE RETENCION POR VENTA ANTE NOTARIOS",
         "Vendedor: GOMEZ RIVERA CARLOS ANDRES  C.C. 1023456789",
         "Retencion practicada: 334.238",
     ]),
     "renglones": ["132"]},

    {"nombre": "Extracto NU Colombia diciembre.pdf",
     "hacer": lambda: pdf_con_texto([
         "NU COLOMBIA COMPANIA DE FINANCIAMIENTO S.A.",
         "NIT 901.658.107-2",
         "EXTRACTO DICIEMBRE 2025",
         "Titular: GOMEZ RIVERA CARLOS ANDRES",
         "Saldo cuenta de ahorros: 447.221",
         "Rendimientos CDT pagados: 106.246",
     ]),
     "renglones": ["29", "30", "58", "59", "132"]},

    {"nombre": "Certificado plataforma digital andina.pdf",
     "hacer": lambda: pdf_con_texto([
         "PLATAFORMA DIGITAL ANDINA S.A.S.",
         "NIT 901.345.678-1",
         "CERTIFICADO DE INGRESOS DISTRIBUIDOS 2025",
         "Tercero: GOMEZ RIVERA CARLOS ANDRES",
         "Ingreso distribuido: 1.212.729",
     ]),
     "renglones": ["74"]},

    # ---------- Los que llegan con el nombre de la cámara ----------
    {"nombre": "IMG_20260315_112233.jpg",
     "hacer": foto,
     "renglones": []},

    {"nombre": "scan0001.pdf",
     "hacer": lambda: pdf_con_texto(_certificado_banco(
         "BANCO DAVIVIENDA S.A.", "860.034.313-7", "110022334455")),
     "renglones": ["30"]},

    {"nombre": "WhatsApp Image 2026-03-14 at 9.21.11 AM.jpeg",
     "hacer": foto,
     "renglones": []},

    {"nombre": "documento.pdf",
     "hacer": lambda: pdf_con_texto(_cir("AGROINDUSTRIAS DEL VALLE S.A.S.",
                                         "900.123.456-7")),
     "renglones": ["29", "32", "33", "36", "59", "76", "100"]},

    # Un PDF que salió del escáner: adentro no hay texto, hay una foto.
    {"nombre": "CamScanner 03-14-2026 10.15.pdf",
     "hacer": pdf_sin_texto,
     "renglones": []},

    # El candado que ponen los bancos, pero con la clave vacía: sí abre.
    {"nombre": "20260228_0001.pdf",
     "hacer": lambda: pdf_con_candado_sin_clave(_certificado_banco(
         "BANCOLOMBIA S.A.", "890.903.938-8", "33004455667")),
     "renglones": ["29", "30"]},

    # Este sí tiene contraseña de verdad. No hay nada que hacer.
    {"nombre": "adjunto.pdf",
     "hacer": lambda: pdf_con_clave(_certificado_banco(
         "BANCO DE BOGOTA", "860.002.964-4", "5566778899")),
     "renglones": []},

    {"nombre": "f9a2c1.xml",
     "hacer": lambda: xml_de_factura(
         "901345678", "PLATAFORMA DIGITAL ANDINA S.A.S.",
         "GOMEZ RIVERA CARLOS ANDRES", "FE-8891", "2025-11-03", "1212729.00"),
     "renglones": ["74"]},

    {"nombre": "Escaneado_20260301.pdf",
     "hacer": lambda: pdf_con_texto([
         "FONDO DE CESANTIAS PORVENIR",
         "NIT 800.170.043-1",
         "CERTIFICADO DE CESANTIAS 2025",
         "Afiliado: GOMEZ RIVERA CARLOS ANDRES",
         "Valor abonado: 2.460.907",
     ]),
     "renglones": ["29", "32", "36", "51", "67", "84"]},

    # Los dos casos donde el nombre del archivo es lo ÚNICO que hay:
    # el contador lo nombró bien, pero por dentro es una foto y no se
    # puede leer una sola letra. Sin la fuente del nombre, estos dos se
    # perderían.
    {"nombre": "Certificado Davivienda 2025.pdf",
     "hacer": pdf_sin_texto,
     "renglones": ["30"]},

    {"nombre": "certificado porvenir cesantias.jpg",
     "hacer": foto,
     "renglones": ["29", "32", "36", "51", "67", "84"]},

    # Un tercero que la exógena NO menciona. Acertar aquí es callarse:
    # inventarle un renglón sería peor que dejarlo sin asignar.
    {"nombre": "0001.pdf",
     "hacer": lambda: pdf_con_texto([
         "CAJA DE COMPENSACION FAMILIAR COMFANDI",
         "NIT 890.303.093-2",
         "CERTIFICADO DE APORTES 2025",
         "Afiliado: GOMEZ RIVERA CARLOS ANDRES",
     ]),
     "renglones": []},
]


def escribir_en(carpeta):
    """Deja los veinte documentos en una carpeta. Devuelve la lista."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    puestos = []
    for documento in DOCUMENTOS:
        contenido = documento["hacer"]()
        ruta = carpeta / documento["nombre"]
        ruta.write_bytes(contenido)
        puestos.append({
            "nombre": documento["nombre"],
            "ruta": ruta,
            "contenido": contenido,
            "renglones": documento["renglones"],
        })
    return puestos
