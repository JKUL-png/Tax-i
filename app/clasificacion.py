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
POR_REGLA = "regla"
POR_EXOGENA = "exogena"
POR_XML = "xml"
POR_TEXTO = "texto"
POR_NOMBRE = "nombre"
POR_IA = "ia"

# Cómo se lee cada origen en pantalla. En este programa nada se muestra
# sin decir de dónde salió.
ORIGENES = {
    POR_REGLA: "porque usted lo corrigió antes",
    POR_EXOGENA: "por la exógena",
    POR_XML: "por el XML de la factura",
    POR_TEXTO: "por el texto del documento",
    POR_NOMBRE: "por el nombre del archivo",
    POR_IA: "lectura automática — verificar",
}

# Las clases de papel que se reconocen por una palabra. Sirven para que
# una corrección sea específica: «los certificados de cesantías de
# Porvenir van a R36» y no «todo lo de Porvenir va a R36».
#
# Es una lista corta y cerrada a propósito. No es una clasificación
# tributaria: es una etiqueta para agrupar correcciones.
TIPOS = (
    ("cesantias", ("cesantia", "cesantias")),
    ("ingresos_retenciones", ("retenciones", "ingresos y retenciones",
                              "formulario 220")),
    ("predial", ("predial", "avaluo", "catastral")),
    ("extracto", ("extracto", "movimientos")),
    ("factura", ("factura", "documento soporte")),
    ("retencion", ("retencion", "retefuente")),
    ("pension", ("pension", "pensiones")),
    ("saldo", ("saldo", "certificado bancario", "declaracion de renta")),
)

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

# Cuántos renglones de al lado se ofrecen como secundarios. Más de tres
# deja de ser una ayuda y pasa a ser una lista para descartar a mano.
SECUNDARIOS_MAXIMOS = 3

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
                # Los demás renglones de ese tercero, del que más veces
                # reporta al que menos. Se ofrecen como secundarios.
                "otros_codigos": [c for c, _ in mejor[1:]],
            })

    _repartir_palabras_propias(terceros)

    # Las reglas que el contador enseñó corrigiendo. No son de este
    # cliente: valen para todos, porque van por código de renglón y no
    # por id. Ver db.guardar_regla.
    reglas = {}
    for regla in db.listar_reglas():
        reglas[(regla["tercero"], regla["tipo"])] = regla

    return {
        "cliente_id": cliente_id,
        "renglones": renglones,
        "por_codigo": por_codigo,
        "por_titulo": {lectura.normalizar(r["titulo"]): r for r in renglones},
        "terceros": terceros,
        "reglas": reglas,
        "identificacion": propia,
        "hay_exogena": carga is not None,
    }


def tipo_de_documento(nombre_archivo, texto):
    """Qué clase de papel es, en una palabra. Vacío si no se sabe.

    Es una etiqueta para agrupar correcciones, NO una clasificación
    tributaria: el programa no dice qué es deducible ni cómo se declara.
    """
    donde = lectura.normalizar(nombre_archivo + " " + (texto or "")[:1500])
    for etiqueta, palabras in TIPOS:
        if any(palabra in donde for palabra in palabras):
            return etiqueta
    return ""


def llave_del_tercero(tercero=None, texto="", nombre_archivo=""):
    """Con qué se reconoce a quien emitió el documento.

    Su NIT cuando se pudo leer, porque es el único que no cambia. Si no
    hay NIT, las palabras con que se le reconoce, ordenadas para que la
    misma entidad dé siempre la misma llave.
    """
    if tercero:
        if tercero.get("nit"):
            return "nit:" + tercero["nit"]
        if tercero.get("palabras"):
            return "nombre:" + " ".join(sorted(tercero["palabras"]))
    nits = nits_del_texto(texto)
    if nits:
        # El más largo: el NIT completo antes que un pedazo suyo.
        return "nit:" + sorted(nits, key=len, reverse=True)[0]
    palabras = lectura.palabras_utiles(nombre_archivo)
    palabras = {p for p in palabras if len(p) >= LARGO_MINIMO_DE_PALABRA
                and p not in PALABRAS_DE_TODOS}
    if palabras:
        return "nombre:" + " ".join(sorted(palabras))
    return ""


def _renglon_de_la_regla(regla, contexto_cliente):
    """El renglón de ESTE cliente que corresponde a una regla aprendida.

    Primero por el código del 210, que es el que no cambia de cliente a
    cliente. Si no, por el título. Si el cliente no tiene ese renglón,
    la regla no aplica y no se propone nada: no se le inventa un renglón
    que él no creó.
    """
    codigo = regla.get("codigo_renglon") or ""
    if codigo and codigo in contexto_cliente["por_codigo"]:
        return contexto_cliente["por_codigo"][codigo]
    titulo = regla.get("titulo") or ""
    return contexto_cliente["por_titulo"].get(titulo)


def _regla_que_aplica(contexto_cliente, llave, tipo):
    """La regla más específica que sirva: primero con tipo, después sin él."""
    if not llave:
        return None
    for clave in ((llave, tipo), (llave, "")):
        regla = contexto_cliente["reglas"].get(clave)
        if regla is not None:
            return regla
    return None


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

    # El texto se saca UNA vez y se reparte: lo usan la regla aprendida,
    # el cruce con la exógena y —cuando llegue— la capa 2.
    texto, _motivo = lectura.texto_del_documento(nombre_archivo, contenido)
    texto_normal = lectura.normalizar(texto)
    tipo = tipo_de_documento(nombre_archivo, texto)

    # Quién emite el documento, que es lo que la regla aprendida usa.
    quien = (_tercero_por_nit(contexto_cliente, nits_del_texto(texto))
             or _tercero_por_nombre(contexto_cliente, texto_normal)
             or _tercero_por_palabras(contexto_cliente, nombre_archivo))
    llave = llave_del_tercero(quien, texto, nombre_archivo)

    # --- 0. Lo que el contador ya corrigió antes ---
    # Va de primera y le gana a todo lo demás: si él ya dijo una vez que
    # los certificados de este tercero van a este renglón, el programa no
    # tiene nada que discutirle.
    regla = _regla_que_aplica(contexto_cliente, llave, tipo)
    if regla is not None:
        renglon = _renglon_de_la_regla(regla, contexto_cliente)
        if renglon is not None:
            agregar({
                "renglon_id": renglon["id"],
                "titulo": renglon["titulo"],
                "codigo": renglon.get("codigo_renglon") or "",
                "origen": POR_REGLA,
                "certeza": ALTA,
                "porque": "Usted mandó a este renglón %s antes."
                          % ("otro documento de %s" % regla["tercero_nombre"]
                             if regla["tercero_nombre"] else "un documento así"),
            })

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

    # --- 4. Los renglones de al lado ---
    # Un certificado de ingresos y retenciones soporta el ingreso en un
    # renglón Y la retención en otro. Cuando el tercero reporta cosas de
    # varios renglones, los demás se ofrecen como secundarios, con menos
    # certeza: el principal es una propuesta y estos, una posibilidad.
    if quien is not None and quien.get("otros_codigos"):
        for codigo in quien["otros_codigos"][:SECUNDARIOS_MAXIMOS]:
            renglon = contexto_cliente["por_codigo"].get(codigo)
            if renglon is None:
                continue
            agregar({
                "renglon_id": renglon["id"],
                "titulo": renglon["titulo"],
                "codigo": codigo,
                "origen": POR_EXOGENA,
                "certeza": MEDIA,
                "porque": "%s también le reporta a la DIAN en este renglón."
                          % quien["nombre"],
            })

    # Con certeza baja no se propone nada: sin asignar es mejor que mal
    # asignado. La puerta queda cerrada aquí, en un solo sitio, y no en
    # cada fuente por separado.
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


def clasificar_documento(documento, contexto_cliente, con_ia=False):
    """Le propone renglón a un documento y lo guarda. Devuelve cuántas.

    Con con_ia=False solo corre la capa 1, que es gratis. La capa 2 se
    pide aparte, porque cuesta.

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

    # La capa 2 corre SOLO si la capa 1 no encontró nada. Si el NIT del
    # banco estaba impreso en el certificado, no hay nada que preguntar
    # ni por qué pagar.
    if not propuestas and con_ia:
        try:
            propuestas = sugerir_con_ia(
                documento["nombre_original"], contenido, contexto_cliente)
        except Exception:
            propuestas = []

    db.guardar_sugerencias(
        documento["cliente_id"], documento["id"], propuestas)
    return len(propuestas)


def clasificar_pendientes(cliente_id=None, con_ia=False):
    """Clasifica todo lo que esté esperando. Devuelve un informe."""
    pendientes = db.documentos_sin_clasificar(cliente_id)
    informe = {"revisados": 0, "con_sugerencia": 0, "con_ia": bool(con_ia)}

    # El contexto se arma una vez por cliente, no una por documento.
    contextos = {}
    for documento in pendientes:
        suyo = documento["cliente_id"]
        if suyo not in contextos:
            contextos[suyo] = contexto(suyo)
        cuantas = clasificar_documento(documento, contextos[suyo], con_ia)
        informe["revisados"] += 1
        if cuantas:
            informe["con_sugerencia"] += 1
    return informe


def arrancar(cliente_id=None, con_ia=False):
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
                clasificar_pendientes(cliente_id, con_ia)
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


# ----------------------------------------------------------
# Capa 2: preguntarle al modelo, y SOLO lo que sobró
# ----------------------------------------------------------
#
# Esta capa corre únicamente cuando la capa 1 no encontró nada. Si el
# NIT del banco estaba impreso en el certificado, no hay nada que
# preguntar: ya se sabe.
#
# Cinco reglas, y las cinco están puestas en código, no en el texto que
# se le manda al modelo. Pedirle algo por favor no es lo mismo que
# impedírselo:
#
#   1. LISTA CERRADA. Elige entre los renglones que ese cliente YA
#      tiene. No puede inventar renglones ni proponer nombres nuevos.
#      La respuesta se valida contra la lista y lo que no esté, se
#      descarta sin más.
#   2. «NO SÉ» ES UNA RESPUESTA CORRECTA. Si no está claro, devuelve
#      nulo y el documento se queda sin asignar. Un documento sin
#      asignar es mejor que uno mal asignado, y no se le empuja a
#      contestar.
#   3. CERTEZA. Con 'baja' no se propone nada.
#   4. POCO TEXTO. Los primeros 1.500 caracteres y el nombre del
#      archivo. Para saber qué clase de papel es, sobra.
#   5. NI UNA CIFRA. Esta capa clasifica y nada más. Sacar los datos es
#      otro trabajo y lo hace app/extraccion.py, una sola vez.
#
# Y todo lo anterior sigue funcionando con IA_PROVEEDOR=ninguno: esta
# capa simplemente no corre, y se dice sin alarma.

import json

from app import proveedores
from app.configuracion import CONFIG

# Cuánto texto se le manda. Para identificar un tipo de documento
# alcanza y sobra; con más se gasta cupo sin acertar más.
LETRAS_PARA_CLASIFICAR = 1500

INSTRUCCIONES = """\
Tu único trabajo es decir a cuál renglón de una lista corresponde un
documento. No eres un asesor tributario.

Reglas:

1. Elige SOLO de la lista que te doy. Si crees que va en algo que no
   está en la lista, la respuesta es null.
2. Si no estás seguro, responde null. Es la respuesta correcta y la
   esperada muchas veces. NO adivines: un documento sin clasificar es
   mejor que uno mal clasificado.
3. No extraigas cifras, ni fechas, ni nombres. No los necesito.
4. No expliques nada ni digas si algo es deducible o cómo declararlo.

Responde SOLO un JSON, sin nada alrededor:

  {"renglon": 12, "tambien": [15], "certeza": "alta"}

  renglon   el número de la lista, o null si no sabes
  tambien   otros renglones de la lista que este mismo documento
            soporte, o [] si no aplica
  certeza   "alta", "media" o "baja"
"""


def hay_ia():
    """¿Está prendida la IA? Si no, la capa 2 no corre y punto."""
    return bool(CONFIG.ia_disponible)


def _lista_para_el_modelo(renglones):
    return "\n".join("%d: %s" % (r["id"], r["titulo"]) for r in renglones)


def _json_de_la_respuesta(contenido):
    """Saca el JSON de lo que contestó, aunque venga envuelto en ```."""
    limpio = (contenido or "").strip()
    if limpio.startswith("```"):
        limpio = limpio.split("```")[1] if "```" in limpio[3:] else limpio[3:]
        if limpio.lstrip().lower().startswith("json"):
            limpio = limpio.lstrip()[4:]
    try:
        return json.loads(limpio.strip())
    except ValueError:
        # Contestó algo que no era JSON. No es motivo para tumbar nada:
        # se trata como «no sé».
        return None


def _validar(respuesta, renglones):
    """Deja pasar SOLO lo que está en la lista del cliente.

    Esta función es la que hace que la promesa se cumpla. Se lo pedimos
    en el texto, pero se lo impedimos aquí: un modelo puede devolver un
    id inventado, el id de otro cliente o una frase, y nada de eso pasa.

    Devuelve (principal, secundarios, certeza). Con «no sé» devuelve
    (None, [], "").
    """
    if not isinstance(respuesta, dict):
        return None, [], ""

    permitidos = {r["id"]: r for r in renglones}

    def id_valido(valor):
        if isinstance(valor, bool) or not isinstance(valor, (int, str)):
            return None
        try:
            numero = int(valor)
        except (TypeError, ValueError):
            return None
        return numero if numero in permitidos else None

    principal = id_valido(respuesta.get("renglon"))
    if principal is None:
        return None, [], ""

    certeza = str(respuesta.get("certeza", "")).strip().lower()
    if certeza not in (ALTA, MEDIA, BAJA):
        # Si no dijo con cuánta certeza, se toma la más baja que se
        # muestra. Nunca se le regala certeza a una respuesta.
        certeza = MEDIA

    secundarios = []
    crudos = respuesta.get("tambien")
    if isinstance(crudos, list):
        for valor in crudos[:SECUNDARIOS_MAXIMOS]:
            otro = id_valido(valor)
            if otro is not None and otro != principal and otro not in secundarios:
                secundarios.append(otro)

    return principal, secundarios, certeza


def sugerir_con_ia(nombre_archivo, contenido, contexto_cliente):
    """Le pregunta al modelo. Devuelve una lista de sugerencias, o [].

    Devuelve [] cuando la IA está apagada, cuando el documento no tiene
    texto, cuando el modelo dijo que no sabe, cuando contestó algo que
    no estaba en la lista y cuando la certeza fue baja. Las cinco son
    respuestas correctas.
    """
    if not hay_ia():
        return []

    renglones = contexto_cliente["renglones"]
    if not renglones:
        return []

    texto, _motivo = lectura.texto_del_documento(nombre_archivo, contenido)
    if not texto.strip():
        # De una foto o de un PDF con contraseña no hay texto que
        # mandar. No se manda el archivo: nunca sale del computador.
        return []

    try:
        contenido_modelo = proveedores.conversar(CONFIG, [
            {"role": "system", "content": INSTRUCCIONES},
            {"role": "user", "content":
             "Renglones disponibles:\n%s\n\nNombre del archivo: %s\n\n"
             "Documento:\n%s" % (_lista_para_el_modelo(renglones),
                                 nombre_archivo,
                                 texto[:LETRAS_PARA_CLASIFICAR])},
        ])
    except proveedores.ErrorDeProveedor:
        # El servicio falló. No es un fallo del documento: se queda sin
        # sugerencia y ya.
        return []

    principal, secundarios, certeza = _validar(
        _json_de_la_respuesta(contenido_modelo), renglones)

    if principal is None or certeza == BAJA:
        return []

    por_id = {r["id"]: r for r in renglones}
    salida = [{
        "renglon_id": principal,
        "titulo": por_id[principal]["titulo"],
        "codigo": por_id[principal].get("codigo_renglon") or "",
        "origen": POR_IA,
        "certeza": certeza,
        "porque": "Lectura automática del texto del documento. Verifique.",
    }]
    for otro in secundarios:
        salida.append({
            "renglon_id": otro,
            "titulo": por_id[otro]["titulo"],
            "codigo": por_id[otro].get("codigo_renglon") or "",
            "origen": POR_IA,
            "certeza": MEDIA,
            "porque": "Lectura automática: este documento también podría"
                      " soportar este renglón. Verifique.",
        })
    return salida


# ----------------------------------------------------------
# Aprender de las correcciones
# ----------------------------------------------------------
#
# Cuando el contador cambia una sugerencia, eso es lo más valioso que
# pasa en todo el programa: acaba de enseñar algo que ninguna regla
# sabía. Se guarda qué tercero, qué clase de papel y a qué renglón lo
# mandó él.
#
# La próxima vez que llegue un documento parecido, se propone lo que él
# decidió. Y vale para TODOS sus clientes, no solo para ese: la regla se
# guarda por código de renglón del 210, que es el mismo en todas partes.
#
# Con el uso, la capa determinista crece y la IA se necesita menos.
#
# Lo que NO se guarda: ni el nombre del cliente, ni el del archivo, ni
# una letra de su contenido. Solo quién emite y a qué renglón va.


def aprender_de_la_correccion(documento, renglon_id, contexto_cliente=None):
    """Guarda lo que el contador acaba de enseñar. Devuelve la regla.

    Se llama cuando él asigna un documento a mano, haya habido
    sugerencia o no: si acertamos, la regla refuerza; si nos
    equivocamos, la corrige.
    """
    renglon = db.obtener_renglon(renglon_id)
    if renglon is None:
        return None

    if contexto_cliente is None:
        contexto_cliente = contexto(documento["cliente_id"])

    try:
        ruta = archivos.ruta_del_documento(
            documento["cliente_id"], documento["nombre_guardado"])
        contenido = ruta.read_bytes() if ruta and ruta.exists() else b""
    except Exception:
        contenido = b""

    nombre = documento["nombre_original"]
    try:
        texto, _motivo = lectura.texto_del_documento(nombre, contenido)
    except Exception:
        texto = ""

    quien = (_tercero_por_nit(contexto_cliente, nits_del_texto(texto))
             or _tercero_por_nombre(
                 contexto_cliente, lectura.normalizar(texto))
             or _tercero_por_palabras(contexto_cliente, nombre))
    llave = llave_del_tercero(quien, texto, nombre)
    if not llave:
        # No se pudo saber quién lo emite. Sin eso no hay regla que
        # guardar: una regla sin tercero se aplicaría a todo.
        return None

    return db.guardar_regla(
        tercero=llave,
        tipo=tipo_de_documento(nombre, texto),
        codigo_renglon=renglon.get("codigo_renglon") or "",
        titulo=lectura.normalizar(renglon["titulo"]),
        tercero_nombre=quien["nombre"] if quien else "",
    )


def descripcion_de_regla(regla):
    """La regla escrita en una frase, para mostrarla en pantalla."""
    quien = regla.get("tercero_nombre") or ""
    if not quien:
        llave = regla.get("tercero") or ""
        quien = llave.split(":", 1)[-1] if ":" in llave else llave
        if llave.startswith("nit:"):
            quien = "el NIT " + quien
    clase = {
        "cesantias": "los certificados de cesantías",
        "ingresos_retenciones": "los certificados de ingresos y retenciones",
        "predial": "los recibos de predial",
        "extracto": "los extractos",
        "factura": "las facturas",
        "retencion": "los certificados de retención",
        "pension": "los certificados de pensión",
        "saldo": "los certificados de saldos",
    }.get(regla.get("tipo") or "", "los documentos")

    return "%s de %s van al renglón %s." % (
        clase.capitalize(), quien,
        ("R" + regla["codigo_renglon"]) if regla.get("codigo_renglon")
        else regla.get("titulo", ""),
    )
