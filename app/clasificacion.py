"""
Capa 1: adivinar a qué renglón va un documento, SIN inteligencia artificial.

El trabajo que más tiempo le quita al contador no es leer los
documentos: es repartirlos. Le llegan cuarenta archivos revueltos por
WhatsApp y por correo y tiene que abrir uno por uno para saber qué es
cada cosa. Esto le propone dónde va cada uno.

**Sugiere, nunca asigna.** El documento entra sin asignar y con una
propuesta al lado que él acepta o cambia con un clic. Tax-i no decide
dónde va nada: si se equivoca al proponer, el costo es un clic; si
decidiera, el costo sería un soporte perdido en la casilla equivocada.

Todo lo de aquí es código: es exacto, es gratis, no manda nada a
ninguna parte y funciona igual con IA_PROVEEDOR=ninguno. La IA, cuando
llegue, es para lo que esta capa no alcanzó a resolver.

Cinco fuentes, de la más fuerte a la más débil
---------------------------------------------

  exogena   El NIT o el nombre de un tercero que le reportó a la DIAN
            aparece en el documento. Es la más fuerte que hay: ese
            tercero YA tiene un renglón, y lo puso la DIAN.
  xml       Es una factura electrónica: el NIT del emisor viene en un
            campo con nombre, no hay nada que adivinar.
  texto     Un NIT o un nombre de entidad en el texto del documento.
  nombre    Las palabras del nombre del archivo, contra los terceros
            conocidos y contra los títulos de los renglones.

Cada sugerencia dice de cuál fuente salió y con cuánta certeza, y las
dos cosas se muestran en pantalla. Una sugerencia sin origen visible es
una sugerencia en la que no se puede confiar.

La mitad de los archivos no se puede clasificar por el nombre
-------------------------------------------------------------
Es mitad y mitad en la vida real: unos llegan como «Certificado
Bancolombia 2025.pdf» y otros como «IMG_20260315_112233.jpg» o
«scan0001.pdf». Por eso la fuente del nombre es la más débil de todas y
casi nunca es la que resuelve: la que trabaja de verdad es la del texto
cruzada con la exógena.

Y hay documentos que no se pueden leer y punto: las fotos, los PDF que
son una foto escaneada y los PDF con contraseña. De esos no se sugiere
nada, y eso es lo correcto.
"""

import re

from app import db, lectura

# Certezas. Con baja no se muestra sugerencia: el documento queda sin
# asignar, que es mejor que mal asignado.
ALTA = "alta"
MEDIA = "media"
BAJA = "baja"

# De dónde salió cada sugerencia.
POR_EXOGENA = "exogena"
POR_XML = "xml"
POR_TEXTO = "texto"
POR_NOMBRE = "nombre"

# Cómo se lee cada origen en pantalla. En este programa nada se muestra
# sin decir de dónde salió.
ORIGENES = {
    POR_EXOGENA: "por la exógena",
    POR_XML: "por el XML de la factura",
    POR_TEXTO: "por el texto del documento",
    POR_NOMBRE: "por el nombre del archivo",
}

# Palabras que van al final del nombre de casi toda empresa colombiana y
# no distinguen a ninguna. Se quitan antes de comparar nombres.
COLETILLAS = (
    "sas", "s a s", "sa", "s a", "ltda", "limitada", "y cia", "e u",
    "compania de financiamiento", "compania", "corporacion",
    "sociedad anonima", "en liquidacion", "sucursal colombia",
)

# Un nombre de tercero más corto que esto no se busca dentro del texto:
# «bogota» solo daría falsos positivos.
LARGO_MINIMO_DE_NOMBRE = 8

# Palabras que están en el nombre de media Colombia y no distinguen a
# nadie. «Banco Davivienda» y «Banco de Bogotá» comparten «banco»; lo
# que los separa es la otra palabra.
PALABRAS_DE_TODOS = {
    "banco", "bancos", "fondo", "fondos", "cesantia", "pension",
    "municipio", "alcaldia", "gobernacion", "compania", "financiamiento",
    "colombia", "colombiana", "nacional", "nacionales", "sociedad",
    "anonima", "empresa", "grupo", "servicios", "seguros", "cooperativa",
    "caja", "entidad", "sucursal", "direccion", "impuesto", "impuestos",
    "aduana", "aduanas", "distrital", "credito", "comercial", "comercio",
}

# Una palabra más corta que esto no alcanza para reconocer a nadie.
LARGO_MINIMO_DE_PALABRA = 5

# Los NIT colombianos de empresa tienen 9 dígitos y a veces vienen con
# el dígito de verificación pegado. Se buscan tiras de 8 a 11 dígitos,
# con o sin puntos y guiones.
NIT_ESCRITO = re.compile(r"\b\d{1,3}(?:[.\s]\d{3}){1,3}(?:\s*-\s*\d)?\b|\b\d{8,11}\b")


def _solo_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def _sin_coletillas(nombre):
    """El nombre de una empresa sin lo que le sobra para reconocerla."""
    limpio = lectura.normalizar(nombre)
    for coletilla in COLETILLAS:
        if limpio.endswith(" " + coletilla):
            limpio = limpio[: -(len(coletilla) + 1)].strip()
    return limpio


def nits_del_texto(texto):
    """Todos los NIT o cédulas que aparecen escritos, ya en dígitos.

    De «900.123.456-7» salen dos formas: con el dígito de verificación y
    sin él, porque los documentos lo escriben de las dos maneras y la
    exógena lo guarda sin él.
    """
    encontrados = set()
    for pedazo in NIT_ESCRITO.findall(texto or ""):
        digitos = _solo_digitos(pedazo)
        if not 8 <= len(digitos) <= 11:
            continue
        encontrados.add(digitos)
        # Sin el dígito de verificación.
        if len(digitos) >= 9:
            encontrados.add(digitos[:-1])
    return encontrados


# ----------------------------------------------------------
# Lo que hay que saber del cliente para poder sugerir
# ----------------------------------------------------------


def contexto(cliente_id):
    """Junta una sola vez lo que hace falta para clasificar sus documentos.

    Se arma una vez por tanda y no una vez por documento: con cuarenta
    archivos serían cuarenta consultas iguales a la base.

    Devuelve los renglones del cliente y los terceros que le reportaron
    a la DIAN, cada uno con el renglón al que la propia DIAN lo manda.
    """
    renglones = db.listar_checklist(cliente_id)
    por_codigo = {}
    for renglon in renglones:
        codigo = renglon.get("codigo_renglon") or ""
        if codigo:
            por_codigo.setdefault(codigo, renglon)

    terceros = []
    carga = db.obtener_carga_exogena(cliente_id)
    # La identificación del propio contribuyente NO cuenta como tercero:
    # su cédula aparece en todos sus documentos, y si contara, todos
    # caerían en los renglones que él mismo se reporta.
    propia = _solo_digitos(carga["identificacion"]) if carga else ""

    if carga:
        cuenta = {}
        nombres = {}
        for fila in db.listar_filas_exogena(carga["id"]):
            nit = _solo_digitos(fila["nit_reporta"])
            if not nit or nit == propia:
                continue
            nombres[nit] = fila["nombre_reporta"]
            for renglon in fila["renglones"]:
                codigo = renglon["codigo"][1:]
                cuenta.setdefault(nit, {})
                cuenta[nit][codigo] = cuenta[nit].get(codigo, 0) + 1

        for nit, codigos in cuenta.items():
            # El renglón al que ese tercero manda más veces. Si empatan,
            # se toma el de número más bajo para que el resultado sea
            # siempre el mismo y no dependa del orden de la base.
            mejor = sorted(codigos.items(), key=lambda par: (-par[1], int(par[0])))
            codigo, veces = mejor[0]
            hay_empate = len(mejor) > 1 and mejor[1][1] == veces
            if codigo not in por_codigo:
                continue
            terceros.append({
                "nit": nit,
                "nombre": nombres[nit],
                "clave": _sin_coletillas(nombres[nit]),
                "renglon": por_codigo[codigo],
                "codigo": codigo,
                # Cuando un tercero reporta cosas de varios renglones no
                # se puede saber cuál de ellos es ESTE documento. Se
                # propone el más frecuente, pero con menos certeza.
                "certeza": MEDIA if hay_empate else ALTA,
                "cuantos_renglones": len(codigos),
            })

    _repartir_palabras_propias(terceros)

    return {
        "cliente_id": cliente_id,
        "renglones": renglones,
        "terceros": terceros,
        "identificacion": propia,
        "hay_exogena": carga is not None,
    }


def _repartir_palabras_propias(terceros):
    """Le deja a cada tercero las palabras con las que se le reconoce.

    Solo las que no comparte con NINGÚN otro tercero de este cliente. Si
    dos las comparten, esa palabra no sirve para distinguirlos: entre
    «BANCO DE BOGOTÁ» y «BOGOTÁ DISTRITO CAPITAL», la palabra «bogotá»
    no dice cuál de los dos es, así que se descarta. El de Bogotá se
    queda sin palabra propia y no se puede reconocer por el nombre del
    archivo — que es la verdad: «certificado bogota.pdf» es ambiguo.
    """
    de_cada_uno = {}
    for tercero in terceros:
        de_cada_uno[tercero["nit"]] = {
            palabra for palabra in lectura.palabras_utiles(tercero["nombre"])
            if len(palabra) >= LARGO_MINIMO_DE_PALABRA
            and palabra not in PALABRAS_DE_TODOS
        }

    for tercero in terceros:
        propias = set(de_cada_uno[tercero["nit"]])
        for nit, palabras in de_cada_uno.items():
            if nit != tercero["nit"]:
                propias -= palabras
        tercero["palabras"] = propias


def _tercero_por_nit(contexto_cliente, nits):
    for tercero in contexto_cliente["terceros"]:
        if tercero["nit"] in nits:
            return tercero
    return None


def _tercero_por_nombre(contexto_cliente, texto):
    """Busca el nombre de un tercero dentro de un texto ya normalizado.

    Se busca el nombre sin las coletillas de sociedad: en el certificado
    dice «BANCOLOMBIA S.A.» y en la exógena «BANCOLOMBIA S.A.», pero en
    el nombre del archivo dice «Bancolombia» a secas.
    """
    if not texto:
        return None
    encontrados = []
    for tercero in contexto_cliente["terceros"]:
        clave = tercero["clave"]
        if len(clave) < LARGO_MINIMO_DE_NOMBRE:
            continue
        if clave in texto:
            encontrados.append((len(clave), tercero))
    if encontrados:
        # El nombre más largo que haya coincidido: «banco de bogota» le
        # gana a un pedazo suyo que también estuviera en otro nombre.
        encontrados.sort(key=lambda par: par[0], reverse=True)
        return encontrados[0][1]
    return None


def _tercero_por_palabras(contexto_cliente, texto):
    """Reconoce al tercero por sus palabras propias, no por el nombre entero.

    Hace falta para los nombres de archivo: el certificado se llama
    «Certificado Davivienda 2025.pdf», no «BANCO DAVIVIENDA S.A.».
    Buscar el nombre completo ahí no encuentra nunca nada.

    Si dos terceros empatan, no se propone ninguno: no hay forma de
    saber cuál es.
    """
    palabras = lectura.palabras_utiles(texto)
    if not palabras:
        return None

    puntajes = []
    for tercero in contexto_cliente["terceros"]:
        comunes = palabras & tercero.get("palabras", set())
        if comunes:
            puntajes.append((len(comunes), tercero))

    if not puntajes:
        return None
    puntajes.sort(key=lambda par: par[0], reverse=True)
    if len(puntajes) > 1 and puntajes[1][0] == puntajes[0][0]:
        return None
    return puntajes[0][1]


# ----------------------------------------------------------
# Sugerir
# ----------------------------------------------------------


def _sugerencia(tercero, origen, porque, certeza=None):
    return {
        "renglon_id": tercero["renglon"]["id"],
        "titulo": tercero["renglon"]["titulo"],
        "codigo": tercero["codigo"],
        "origen": origen,
        "certeza": certeza or tercero["certeza"],
        "porque": porque,
    }


def sugerir(nombre_archivo, contenido, contexto_cliente):
    """Propone a qué renglón va un documento. Devuelve la mejor, o None.

    Recibe el contenido en bytes y no una ruta, para poder probarlo sin
    tocar el disco.

    Devuelve un diccionario con el renglón, el origen, la certeza y una
    frase que explica por qué, o None cuando no hay nada claro. Devolver
    None es una respuesta correcta y frecuente: una foto de celular o un
    PDF con contraseña no se pueden clasificar, y forzarlos sería peor.
    """
    todas = sugerir_todas(nombre_archivo, contenido, contexto_cliente)
    return todas[0] if todas else None


def sugerir_todas(nombre_archivo, contenido, contexto_cliente):
    """Todas las pistas que se encontraron, de la más fuerte a la más débil."""
    encontradas = []
    vistos = set()

    def agregar(sugerencia):
        if sugerencia is None:
            return
        llave = (sugerencia["renglon_id"], sugerencia["origen"])
        if llave in vistos:
            return
        vistos.add(llave)
        encontradas.append(sugerencia)

    nombre_normal = lectura.normalizar(nombre_archivo)

    # --- 1. Si es una factura electrónica, el emisor viene con nombre ---
    if nombre_archivo.lower().endswith(".xml"):
        datos = lectura.leer_xml(contenido)
        if datos:
            nit = _solo_digitos(datos.get("nit_emisor", ""))
            tercero = None
            if nit:
                tercero = _tercero_por_nit(contexto_cliente, {nit, nit[:-1]})
            if tercero is None and datos.get("emisor"):
                tercero = _tercero_por_nombre(
                    contexto_cliente, _sin_coletillas(datos["emisor"]))
            if tercero is not None:
                agregar(_sugerencia(
                    tercero, POR_XML,
                    "La factura la emitió %s, que le reporta a la DIAN en"
                    " este renglón." % tercero["nombre"]))

    # --- 2. El texto del documento ---
    texto, _motivo = lectura.texto_del_documento(nombre_archivo, contenido)
    texto_normal = lectura.normalizar(texto)

    if texto:
        tercero = _tercero_por_nit(contexto_cliente, nits_del_texto(texto))
        if tercero is not None:
            agregar(_sugerencia(
                tercero, POR_EXOGENA,
                "El documento trae el NIT %s, que es el de %s en la"
                " exógena." % (tercero["nit"], tercero["nombre"])))

        tercero = _tercero_por_nombre(contexto_cliente, texto_normal)
        if tercero is not None:
            agregar(_sugerencia(
                tercero, POR_TEXTO,
                "El documento nombra a %s, que le reporta a la DIAN en este"
                " renglón." % tercero["nombre"]))

    # --- 3. El nombre del archivo ---
    # Aquí es al revés que en el texto: el archivo casi nunca trae el
    # nombre completo de la entidad, trae una palabra suya.
    tercero = (_tercero_por_nombre(contexto_cliente, nombre_normal)
               or _tercero_por_palabras(contexto_cliente, nombre_archivo))
    if tercero is not None:
        agregar(_sugerencia(
            tercero, POR_NOMBRE,
            "El nombre del archivo dice %s." % tercero["nombre"],
            certeza=MEDIA))

    sugerido, palabras = lectura.sugerir_renglon(
        nombre_archivo, contexto_cliente["renglones"])
    if sugerido is not None:
        renglon = next(
            (r for r in contexto_cliente["renglones"] if r["id"] == sugerido),
            None)
        if renglon is not None:
            agregar({
                "renglon_id": renglon["id"],
                "titulo": renglon["titulo"],
                "codigo": renglon.get("codigo_renglon") or "",
                "origen": POR_NOMBRE,
                "certeza": MEDIA,
                "porque": "El nombre del archivo y el del renglón comparten:"
                          " %s." % ", ".join(palabras),
            })

    # Con certeza baja no se propone nada: sin asignar es mejor que mal
    # asignado. Hoy ninguna fuente devuelve baja, pero la puerta queda
    # cerrada aquí y no en cada fuente.
    return [s for s in encontradas if s["certeza"] in (ALTA, MEDIA)]


# ----------------------------------------------------------
# Clasificar en segundo plano
# ----------------------------------------------------------
#
# Por qué esto corre solo y la lectura con IA no:
#
#   Clasificar es GRATIS. Pasa entero en este computador, no sale ni una
#   letra a ninguna parte y no gasta cupo de ningún servicio. Entonces
#   pasa solo, apenas se confirma la carga.
#
#   Leer con IA CUESTA. Por eso esa fila la arranca el contador cuando
#   decide gastar (ver app/cola.py).
#
# Es la regla de la casa: lo gratis pasa solo, lo que cuesta se pide.

import threading

from app import documentos as archivos

_hilo = None
_candado = threading.Lock()


def clasificar_documento(documento, contexto_cliente):
    """Le propone renglón a un documento y lo guarda. Devuelve cuántas.

    Nunca lanza excepción: un archivo dañado no puede trabar la tanda.
    """
    try:
        ruta = archivos.ruta_del_documento(
            documento["cliente_id"], documento["nombre_guardado"])
        contenido = ruta.read_bytes() if ruta and ruta.exists() else b""
    except Exception:
        contenido = b""

    try:
        propuestas = sugerir_todas(
            documento["nombre_original"], contenido, contexto_cliente)
    except Exception:
        # El detalle técnico NO se guarda: podría traer texto del
        # documento, y eso no puede quedar en un registro.
        propuestas = []

    db.guardar_sugerencias(
        documento["cliente_id"], documento["id"], propuestas)
    return len(propuestas)


def clasificar_pendientes(cliente_id=None):
    """Clasifica todo lo que esté esperando. Devuelve un informe."""
    pendientes = db.documentos_sin_clasificar(cliente_id)
    informe = {"revisados": 0, "con_sugerencia": 0}

    # El contexto se arma una vez por cliente, no una por documento.
    contextos = {}
    for documento in pendientes:
        suyo = documento["cliente_id"]
        if suyo not in contextos:
            contextos[suyo] = contexto(suyo)
        cuantas = clasificar_documento(documento, contextos[suyo])
        informe["revisados"] += 1
        if cuantas:
            informe["con_sugerencia"] += 1
    return informe


def arrancar(cliente_id=None):
    """Pone a clasificar en otro hilo. Vuelve enseguida.

    Subir sigue siendo instantáneo: el contador confirma la carga y ya,
    mientras esto trabaja por detrás.
    """
    global _hilo

    with _candado:
        if _hilo is not None and _hilo.is_alive():
            return False

        def trabajar():
            try:
                clasificar_pendientes(cliente_id)
            except Exception:
                # Nunca se registra el detalle: podría traer el nombre o
                # el contenido de un documento de un cliente.
                pass

        _hilo = threading.Thread(target=trabajar, daemon=True)
        _hilo.start()
        return True


def trabajando():
    """¿Hay una tanda de clasificación andando?"""
    return _hilo is not None and _hilo.is_alive()
