"""
La pasada: el Formulario 210 de un cliente propuesto de una sola vez.

El problema que resuelve
------------------------
El contador que usa Tax-i lo resolvía más rápido por fuera. Él manda
todos los documentos y la exógena de un cliente juntos, pide el
formulario lleno con notas, y revisa al final. El flujo anterior del
programa —clasificar documento por documento, asignarle renglón,
transcribir valor por valor— le agregaba trabajo en vez de quitárselo.

Aquí se copia su forma de trabajar. Una llamada por cliente, con todo
adentro, y sale la propuesta completa del formulario.

Por qué junto y no por partes
-----------------------------
Porque partirlo era el error de fondo. Un certificado suelto no dice a
qué renglón va; ese mismo certificado al lado de la fila de la exógena
que reporta la misma cifra, sí. Al leer los documentos por separado, el
modelo tenía que decidir sin poder mirar la exógena — que es
exactamente lo primero que mira el contador.

Lo que NO cambia
----------------
- **El modelo nunca calcula.** Si un renglón necesita varias cifras, las
  devuelve por separado y el que suma es el código, aquí abajo. Una
  suma del modelo no se puede cotejar con ningún papel.
- **Cita textual obligatoria y verificada.** Cada valor viene con la
  frase exacta de donde salió, y esa frase se busca en el original. La
  que no aparece, no se guarda: se marca para revisión manual. Una cita
  inventada indica que el resto de ese dato tampoco es confiable.
- **Nada entra solo al formulario.** Lo que sale de aquí es una
  PROPUESTA, en su propia tabla. Al 210 llega cuando el contador
  aprueba, y por el mismo camino de siempre —`formulario.guardar_valor`,
  que revisa que la celda no tenga fórmula.
- **Ningún archivo sale del computador.** De un PDF se manda el texto
  que se extrajo aquí; de la exógena, las filas ya parseadas por
  `app/exogena.py`. Nunca el archivo.

Los tres niveles
----------------
Cada valor viene marcado con cuánto tuvo que interpretar el modelo:

  A  dato directo — la fuente dice a qué renglón va
  B  regla de la DIAN aplicada — el «Uso declaración Sugerida» trae una
     condición y se cumple
  C  lo interpretó el modelo

**El nivel no filtra ni bloquea nada.** Todo llega lleno; el nivel solo
le dice al contador dónde mirar primero. Y lo comprueba el código, no
el modelo: ver `instrucciones.comprobar_nivel`, que solo puede bajarlo.
"""

import json
from datetime import datetime

from app import (bitacora, clasificacion, db, documentos,
                 exogena_cliente, formulario, instrucciones, lectura,
                 proveedores)
from app.configuracion import CONFIG

# Cuánto texto de cada documento se le manda. Un certificado de ingresos
# y retenciones real cabe entero; de un extracto de cuarenta páginas se
# manda el principio, que es donde están los totales.
#
# Este número es el que decide lo que cuesta una pasada: los documentos
# son el 80% de lo que se manda. Subirlo se paga en cada cliente.
LETRAS_POR_DOCUMENTO = 3000

# Cuándo hay que partir la pasada en bloques.
#
# No es porque no quepa —el modelo tiene un millón de tokens de
# contexto— sino porque la calidad se cae cuando se le manda demasiado
# de una vez, y porque la respuesta también tiene un techo.
#
# Se parte por BLOQUES DE DOCUMENTOS, nunca por renglones: el modelo
# necesita ver todos los renglones y toda la exógena para decidir bien.
# Lo que se reparte es lo que sobra.
TOPE_DE_DOCUMENTOS = 40
TOPE_DE_LETRAS = 300000

# Cuántas letras son un token, más o menos, en español. Sirve para
# estimar antes de mandar; el número de verdad lo dice el servicio
# después, y ese es el que se guarda.
LETRAS_POR_TOKEN = 3.5


class SinIA(Exception):
    """La pasada necesita un modelo y no hay ninguno configurado."""


class PasadaFallida(Exception):
    """No se pudo completar la pasada. El texto se le muestra al contador."""


class PasadaEnCurso(Exception):
    """Ese cliente ya tiene una pasada corriendo. No se arranca otra."""


# Cuánto margen se le da a una pasada por encima de lo que el servicio
# podría tardar, para lo que hace este computador: abrir los PDF, sacarles
# el texto y escribir en la base.
MARGEN_DEL_TECHO = 120


def _techo_de_una_pasada(bloques):
    """Cuánto puede tardar una pasada, como máximo, sin estar colgada.

    Se calcula, no se inventa: por bloque caben dos peticiones —la buena
    y el único reintento— de hasta SEGUNDOS_DE_ESPERA_DE_LA_PASADA cada
    una, más las esperas por cupo. Si mañana se cambia el tiempo de
    espera del servicio, este techo se mueve solo.
    """
    por_bloque = (proveedores.SEGUNDOS_DE_ESPERA_DE_LA_PASADA * 2
                  + sum(proveedores.ESPERAS_POR_CUPO))
    return por_bloque * max(1, int(bloques or 1)) + MARGEN_DEL_TECHO


def _segundos_desde(marca):
    """Cuántos segundos pasaron desde una fecha de la base. O None."""
    try:
        return (datetime.now() - datetime.fromisoformat(marca)).total_seconds()
    except (TypeError, ValueError):
        return None


def hace_cuanto(segundos):
    """«unos segundos», «40 segundos», «3 minutos».

    Concuerda el singular a propósito: un «hace 1 segundos» en pantalla
    hace dudar de todo lo demás que diga el programa.
    """
    segundos = int(segundos or 0)
    if segundos < 10:
        return "unos segundos"
    if segundos < 90:
        return "%d segundos" % segundos
    minutos = round(segundos / 60)
    return "%d minuto%s" % (minutos, "" if minutos == 1 else "s")


def pasada_en_curso(cliente_id):
    """La pasada que este cliente tiene corriendo de verdad. O None.

    Que una pasada tarde varios minutos es normal —el servicio tiene
    cinco minutos por bloque y puede haber varios—, así que no se puede
    dar por muerta a la primera. Lo que no es normal es una que lleva más
    de lo que físicamente podría tardar: esa se quedó abierta porque
    cerraron el programa a la mitad, y se cierra aquí.

    Sin esa parte, un solo cierre a destiempo dejaría a ese cliente sin
    poder pedir propuesta nunca más, que es un daño peor que el que se
    está evitando.

    Se marca como fallida y no como terminada, para que `ultima_pasada`
    la salte y no le tape al contador la propuesta buena que ya tenía.
    """
    fila = db.pasada_corriendo(cliente_id)
    if fila is None:
        return None

    segundos = _segundos_desde(fila["corrida_en"])
    if segundos is None or segundos > _techo_de_una_pasada(fila["bloques"]):
        db.cerrar_pasada(
            fila["id"], "fallo",
            motivo="Se interrumpió: el programa se cerró mientras corría."
                   " Lo que alcanzara a gastar no quedó anotado.",
        )
        return None

    return {
        "id": fila["id"],
        "segundos": int(segundos),
        "desde_hace": hace_cuanto(segundos),
        "bloques": fila["bloques"],
    }


# ---------------------------------------------------------------------------
# 1. Armar lo que se le manda
#
# Todo esto es código puro: no habla con nadie, no gasta un peso y se
# puede probar solo. Devuelve texto, nada más que texto — que es también
# la garantía de que ningún archivo sale del computador.
# ---------------------------------------------------------------------------


def catalogo_de_renglones():
    """Los renglones del 210 con su nombre oficial, sacados de la plantilla.

    No es una lista escrita a mano: sale del mapa de la plantilla del
    contador. Si él cambia de plantilla, la lista cambia sola, y ningún
    nombre de renglón lo inventó nadie.
    """
    nombres = {}
    for celda in formulario.mapa()["celdas"]:
        numero = celda.get("renglon")
        if not numero or numero in nombres:
            continue
        descripcion = " ".join((celda.get("descripcion") or "").split())
        if descripcion:
            nombres[numero] = descripcion[:80]
    return nombres


def _texto_de_renglones(nombres):
    return "\n".join(
        "R%s %s" % (numero, nombres[numero])
        for numero in sorted(nombres, key=lambda n: int(n))
    )


def _texto_de_renglones_propios(cliente_id):
    """Los renglones que el contador creó para ESTE cliente."""
    propios = db.listar_checklist(cliente_id)
    if not propios:
        return "Este cliente todavía no tiene renglones creados."
    lineas = []
    for renglon in propios:
        titulo = renglon["titulo"]
        codigo = renglon.get("codigo_renglon") or ""
        # El título de los renglones que salieron de la exógena ya trae
        # el código adentro («R29 — Patrimonio Bruto»). Ponérselo otra
        # vez delante deja «29 R29 — …», que se lee mal y gasta tokens.
        prefijo = ""
        if codigo and not titulo.upper().startswith("R" + codigo):
            prefijo = "R%s " % codigo
        marca = "recibido" if renglon["estado"] == "recibido" else "falta"
        lineas.append("- %s%s [%s]" % (prefijo, titulo, marca))
    return "\n".join(lineas)


# Cuántas de sus decisiones anteriores se le mandan al modelo. Con más,
# el contexto crece sin que las sugerencias mejoren: las que valen son
# las que él ha repetido.
REGLAS_QUE_SE_MANDAN = 40


def _texto_de_lo_aprendido():
    """Lo que el contador ya decidió antes, para que el modelo lo siga.

    Esta es la única forma en que este programa «aprende»: de las
    correcciones de ÉL. Cada vez que asigna un documento a mano se
    guarda qué tercero, qué clase de papel y a qué renglón lo mandó
    (`db.guardar_regla`), por código de renglón del 210 — así una
    corrección hecha en un cliente sirve en todos.

    Y es la única forma que puede haber. Meterle reglas tributarias
    escritas de memoria sería derecho inventado por un modelo, que es
    justo lo que este proyecto prohíbe para las fechas de vencimiento y
    por el mismo motivo. Lo que sí tiene firma profesional detrás es lo
    que decidió él.

    Las reglas no llevan ni el nombre de un cliente, ni el de un
    archivo, ni una letra de su contenido: solo quién emite y a qué
    renglón va. El tercero, además, ya va en la exógena que se manda.
    """
    reglas = db.listar_reglas()
    if not reglas:
        return ""

    # Primero las que él ha repetido más veces: son las que más pesan.
    reglas.sort(key=lambda r: (-r.get("veces", 1), r["id"]))
    lineas = []
    for regla in reglas[:REGLAS_QUE_SE_MANDAN]:
        frase = clasificacion.descripcion_de_regla(regla)
        veces = regla.get("veces", 1)
        if veces > 1:
            frase += " (lo ha hecho %d veces)" % veces
        lineas.append("- " + frase)
    return "\n".join(lineas)


def _linea_de_exogena(numero, fila):
    """Una fila de la exógena en una sola línea, compacta y completa.

    El «Uso declaración Sugerida» va TEXTUAL y entero: es lo que hace
    posible el nivel B, y es de la DIAN, no nuestro. Los saltos de línea
    se aplastan a espacios para que la fila quepa en un renglón, pero no
    se recorta ni se reescribe una palabra.
    """
    uso = " ".join((fila.get("uso_sugerido") or "").split())
    return "E%d|%s|%s|%s|%s" % (
        numero,
        fila.get("nombre_reporta") or "",
        " ".join((fila.get("detalle") or "").split()),
        _cifra_limpia(fila.get("valor")),
        uso,
    )


def _cifra_limpia(valor):
    """La cifra sin el «.0» que le pega SQLite a los enteros.

    Parece un detalle y no lo es: ese punto cero sale en cada una de las
    cincuenta filas de la exógena, gasta tokens en cada pasada de cada
    cliente, y encima el modelo lo copia en la cita.
    """
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


def _texto_de_exogena(filas_numeradas):
    if not filas_numeradas:
        return "Este cliente no tiene exógena cargada."
    cabecera = (
        "Cada línea es: referencia|quién reportó|qué reportó|valor|"
        "Uso declaración Sugerida (textual, de la DIAN)."
    )
    lineas = [_linea_de_exogena(numero, fila)
              for numero, fila in filas_numeradas]
    return cabecera + "\n" + "\n".join(lineas)


def _texto_de_documentos(documentos_numerados):
    if not documentos_numerados:
        return "Este cliente no tiene documentos con texto legible."
    partes = []
    for numero, documento, texto in documentos_numerados:
        partes.append("--- D%d «%s» ---\n%s" % (
            numero, documento["nombre_original"], texto
        ))
    return "\n\n".join(partes)


def _texto_del_documento(documento):
    """El texto de un documento, sacado en ESTE computador. ('', motivo)."""
    ruta = documentos.ruta_del_documento(
        documento["cliente_id"], documento["nombre_guardado"]
    )
    if ruta is None or not ruta.exists():
        return "", "El archivo ya no está en el disco."
    texto, motivo = lectura.texto_del_documento(
        documento["nombre_guardado"], ruta.read_bytes()
    )
    return texto, motivo


def armar_entrada(cliente):
    """Todo lo que se le va a mandar al modelo, ya en texto.

    Devuelve un diccionario con:

      instrucciones   los dos bloques que se repiten en cada cliente y
                      que por eso se pueden cachear
      bloques         uno o más textos de usuario. Más de uno solo
                      cuando el cliente tiene demasiados documentos.
      indice          de la referencia («E7», «D3») a lo que representa,
                      con el texto exacto que se mandó. Es contra ese
                      texto contra el que se verifican las citas.
      sin_texto       los documentos de los que no se pudo sacar nada
      renglones       {numero: nombre} de los renglones válidos

    No llama a nadie ni gasta nada. Se puede probar sola.
    """
    cliente_id = cliente["id"]
    nombres = catalogo_de_renglones()

    carga = db.obtener_carga_exogena(cliente_id)
    filas = db.listar_filas_exogena(carga["id"]) if carga else []
    filas_numeradas = list(enumerate(filas, start=1))

    indice = {}
    for numero, fila in filas_numeradas:
        indice["E%d" % numero] = {
            "tipo": "exogena",
            "fila": fila,
            "texto": _linea_de_exogena(numero, fila),
        }

    numerados = []
    sin_texto = []
    siguiente = 1
    # En el orden en que se subieron, no al revés. `listar_documentos`
    # los devuelve del más nuevo al más viejo porque así se ven mejor en
    # pantalla, pero aquí lo que importa es que D1, D2, D3… salgan
    # siempre iguales para el mismo cliente: esas referencias son las
    # que el modelo cita y las que después se buscan en el índice.
    for documento in sorted(db.listar_documentos(cliente_id),
                            key=lambda d: d["id"]):
        texto, motivo = _texto_del_documento(documento)
        if not texto.strip():
            sin_texto.append({
                "documento_id": documento["id"],
                "nombre": documento["nombre_original"],
                "porque": motivo or "No se pudo sacar texto del archivo.",
            })
            continue
        recortado = texto[:LETRAS_POR_DOCUMENTO]
        indice["D%d" % siguiente] = {
            "tipo": "documento",
            "documento": documento,
            "texto": recortado,
        }
        numerados.append((siguiente, documento, recortado))
        siguiente += 1

    texto_exogena = _texto_de_exogena(filas_numeradas)
    texto_propios = _texto_de_renglones_propios(cliente_id)

    aprendido = _texto_de_lo_aprendido()
    bloque_aprendido = ""
    if aprendido:
        bloque_aprendido = (
            "LO QUE ESTE CONTADOR YA DECIDIÓ ANTES\n"
            "Son decisiones suyas, tomadas corrigiendo a mano en otros"
            " clientes. Si alguna aplica a un documento de este, síguela y"
            " dilo en la nota. No son ley ni te autorizan a opinar de"
            " impuestos: son cómo trabaja él.\n%s\n\n" % aprendido
        )

    bloques = []
    for grupo in _repartir(numerados):
        bloques.append(
            "CLIENTE: %s (cédula termina en %s)\n\n"
            "%s"
            "RENGLONES QUE EL CONTADOR YA CREÓ PARA ESTE CLIENTE\n%s\n\n"
            "EXÓGENA (lo que los terceros le reportaron a la DIAN)\n%s\n\n"
            "DOCUMENTOS DEL CLIENTE\n%s"
            % (cliente["nombre"], cliente["dos_digitos"], bloque_aprendido,
               texto_propios, texto_exogena, _texto_de_documentos(grupo))
        )

    return {
        "instrucciones": [
            instrucciones.PASADA,
            "RENGLONES DEL FORMULARIO 210\n"
            "Solo puedes proponer renglones de esta lista, con el código"
            " exacto.\n" + _texto_de_renglones(nombres),
        ],
        "bloques": bloques,
        "indice": indice,
        "sin_texto": sin_texto,
        "renglones": nombres,
        "documentos": len(numerados),
        "filas_exogena": len(filas_numeradas),
        "reglas": len(db.listar_reglas()),
    }


def _repartir(numerados):
    """Parte los documentos en bloques, si son demasiados.

    Se parte por DOCUMENTOS, nunca por renglones: cada bloque lleva la
    exógena entera y la lista de renglones entera, porque el modelo
    necesita verlas completas para decidir bien. Lo único que se reparte
    es la pila de papeles.
    """
    if not numerados:
        return [[]]
    letras = sum(len(texto) for _, _, texto in numerados)
    if len(numerados) <= TOPE_DE_DOCUMENTOS and letras <= TOPE_DE_LETRAS:
        return [numerados]

    cuantos = max(1, min(TOPE_DE_DOCUMENTOS,
                         len(numerados) // 2 + len(numerados) % 2))
    return [numerados[i:i + cuantos]
            for i in range(0, len(numerados), cuantos)]


def tokens_estimados(entrada):
    """Cuántos tokens va a costar, más o menos, antes de mandarla."""
    letras = sum(len(t) for t in entrada["instrucciones"])
    letras += sum(len(b) for b in entrada["bloques"])
    return int(letras / LETRAS_POR_TOKEN)


# ---------------------------------------------------------------------------
# 2. Pedírselo al modelo
# ---------------------------------------------------------------------------


def _entender(texto):
    """El JSON de la respuesta, o None si contestó otra cosa.

    None significa «no era el JSON que se le pidió» y se reintenta una
    vez. Es distinto de una respuesta vacía, que significa «lo miré y no
    encontré nada» y no se reintenta.
    """
    limpio = (texto or "").strip()
    if limpio.startswith("```"):
        limpio = limpio.split("```")[1] if "```" in limpio[3:] else limpio[3:]
        if limpio.lstrip().lower().startswith("json"):
            limpio = limpio.lstrip()[4:]
    try:
        entendido = json.loads(limpio.strip())
    except ValueError:
        return None
    if not isinstance(entendido, dict):
        return None
    if not isinstance(entendido.get("propuestas"), list):
        return None
    return entendido


def _pedir_un_bloque(entrada, bloque, numero_de_bloque, reproche=""):
    """Una llamada al modelo. Devuelve (entendido, uso, costo)."""
    mensajes = [{"role": "system", "content": texto}
                for texto in entrada["instrucciones"]]
    contenido = bloque
    if numero_de_bloque > 1 or len(entrada["bloques"]) > 1:
        contenido = (
            "Este es el bloque %d de %d de los documentos de este cliente."
            " La exógena y los renglones van completos en todos.\n\n%s"
            % (numero_de_bloque, len(entrada["bloques"]), bloque)
        )
    if reproche:
        contenido += "\n\n" + reproche
    mensajes.append({"role": "user", "content": contenido})

    respuesta = proveedores.conversar_detallado(
        CONFIG, mensajes,
        esquema=instrucciones.ESQUEMA_PASADA,
        largo_maximo=proveedores.LARGO_MAXIMO_DE_LA_PASADA,
        segundos=proveedores.SEGUNDOS_DE_ESPERA_DE_LA_PASADA,
        cachear=True,
    )
    return (_entender(respuesta["texto"]), respuesta["uso"],
            respuesta["costo"])


REPROCHE = (
    "Tu respuesta anterior no se pudo entender: no era el JSON del"
    " formato que te pedí. Contesta SOLO el JSON, sin una palabra por"
    " fuera y sin ```."
)


# ---------------------------------------------------------------------------
# 3. Verificar lo que contestó
#
# Esta es la parte que hace que el resto sea confiable, y corre igual
# con cualquier proveedor: la salida estructurada ahorra reintentos,
# no reemplaza esta comprobación.
# ---------------------------------------------------------------------------


def _celda_para(numero, texto):
    """En cuál casilla de la plantilla va este valor. ('', motivo) si empatan.

    Escoger la casilla DENTRO de un renglón no es una decisión
    tributaria: el renglón ya está decidido. Lo que falta es en cuál
    fila de la hoja de trabajo va, y eso se resuelve leyendo la
    etiqueta. Si dos filas empatan, escoge el contador.
    """
    try:
        recomendada, motivo, _todas = formulario.elegir_casilla(numero, texto)
    except formulario.SinPlantilla:
        return "", ""
    if recomendada is None:
        return "", ""
    return recomendada["celda"], motivo


def verificar(cruda, entrada, bloque=1):
    """Convierte lo que contestó el modelo en valores comprobados.

    Devuelve (valores, lecturas). Cada valor trae ya:

      - la cita buscada en el texto original, y si no apareció, botado
      - el nivel comprobado contra la fuente, que solo se puede bajar
      - la cifra convertida por el código, no por el modelo
      - la casilla de la plantilla que le corresponde

    Nada de esto se le pide al modelo por favor: se comprueba.
    """
    indice = entrada["indice"]
    nombres = entrada["renglones"]
    valores = []

    for propuesta in cruda.get("propuestas") or []:
        if not isinstance(propuesta, dict):
            continue
        codigo = str(propuesta.get("renglon") or "").strip().upper()
        numero = instrucciones._numero_de_renglon(codigo)
        if not numero or numero not in nombres:
            # Se inventó un renglón que no está en la lista. Se descarta
            # sin ruido: pedirle que no invente no es lo mismo que
            # impedírselo, y esto es lo segundo.
            continue

        for componente in propuesta.get("componentes") or []:
            if isinstance(componente, dict):
                valores.append(
                    _revisar_componente(componente, codigo, numero,
                                        nombres[numero], indice, bloque)
                )

    return valores, _revisar_lecturas(cruda.get("lecturas") or [], indice)


def _revisar_componente(componente, codigo, numero, nombre, indice, bloque):
    referencia = str(componente.get("referencia") or "").strip().upper()
    fuente = str(componente.get("fuente") or "").strip().lower()
    cita = str(componente.get("cita") or "").strip()
    origen = indice.get(referencia)

    valor = {
        "renglon": codigo,
        "renglon_nombre": nombre,
        "valor": str(componente.get("valor") or "").strip(),
        "numero": None,
        "fuente": fuente,
        "referencia": referencia,
        "documento_id": None,
        "fila_exogena_id": None,
        "cita": cita,
        "verificada": False,
        "nivel": "C",
        "nivel_pedido": str(componente.get("nivel") or "").strip().upper(),
        "condicion": str(componente.get("condicion") or "").strip(),
        "nota": str(componente.get("nota") or "").strip(),
        "motivo": "",
        "celda": "",
        "celda_motivo": "",
        "estado": "propuesto",
        "bloque": bloque,
    }

    if origen is None:
        valor["estado"] = "revision"
        valor["motivo"] = ("Dijo que salió de «%s», que no existe entre lo"
                           " que se le mandó." % (referencia or "—"))
        return valor

    if origen["tipo"] == "documento":
        valor["documento_id"] = origen["documento"]["id"]
        valor["fuente"] = "documento"
    else:
        valor["fila_exogena_id"] = origen["fila"]["id"]
        valor["fuente"] = "exogena"

    # La cita, contra el texto que de verdad se le mandó.
    if not instrucciones.verificar_cita(cita, origen["texto"]):
        valor["estado"] = "revision"
        valor["motivo"] = ("La frase que citó no aparece en el original."
                           " Una cita inventada hace dudar del resto de"
                           " ese dato, así que no se guarda el valor.")
        return valor
    valor["verificada"] = True

    # La cifra la convierte el código, con la misma función que ya usa la
    # exógena. El modelo copia; convertir es una cuenta.
    numero_leido = exogena_cliente.cifra(valor["valor"])
    if numero_leido is None:
        valor["estado"] = "revision"
        valor["motivo"] = "Lo que copió como valor no es una cifra."
        return valor
    valor["numero"] = numero_leido

    # El nivel, comprobado contra la fuente.
    fila = origen.get("fila") or {}
    nivel, motivo = instrucciones.comprobar_nivel(
        valor["nivel_pedido"], codigo, valor["fuente"],
        condicion=valor["condicion"],
        uso_sugerido=fila.get("uso_sugerido") or "",
        requiere_decision=bool(fila.get("requiere_decision")),
        texto_documento=origen["texto"] if origen["tipo"] == "documento" else "",
    )
    valor["nivel"] = nivel
    if motivo:
        valor["motivo"] = motivo

    valor["celda"], valor["celda_motivo"] = _celda_para(
        numero, valor["nota"] or valor["cita"]
    )
    return valor


def _revisar_lecturas(crudas, indice):
    """Los datos sueltos que leyó y no ubicó, con su cita verificada.

    Van a `datos_extraidos` para que RentAI los siga viendo. Es lo que
    antes hacía una segunda llamada por documento; ahora sale de la
    misma respuesta y no cuesta nada aparte.
    """
    listas = {}
    for lectura_cruda in crudas:
        if not isinstance(lectura_cruda, dict):
            continue
        referencia = str(lectura_cruda.get("referencia") or "").strip().upper()
        origen = indice.get(referencia)
        if origen is None or origen["tipo"] != "documento":
            continue
        cita = str(lectura_cruda.get("cita") or "").strip()
        if not instrucciones.verificar_cita(cita, origen["texto"]):
            continue
        concepto = str(lectura_cruda.get("concepto") or "").strip()
        if not concepto:
            continue
        listas.setdefault(origen["documento"]["id"], []).append({
            "concepto": concepto,
            "valor": str(lectura_cruda.get("valor") or "").strip(),
            "detalle": str(lectura_cruda.get("detalle") or "").strip(),
            "cita": cita,
        })
    return listas


# ---------------------------------------------------------------------------
# 4. Correr la pasada entera
# ---------------------------------------------------------------------------


def correr(cliente):
    """Le pide al modelo el formulario de un cliente y guarda la propuesta.

    No toca el formulario del cliente. Lo que devuelve queda en
    `pasada_valores`, esperando a que él apruebe.

    Si un bloque falla, los demás se guardan igual y la pasada queda
    marcada como 'parcial': lo que sí se pudo leer se muestra, y lo que
    no, se dice. Lo que nunca pasa es que el formulario quede a medias,
    porque el formulario no se toca hasta la aprobación.
    """
    if not CONFIG.ia_disponible:
        raise SinIA(CONFIG.motivo)

    cliente_id = cliente["id"]

    # El candado. Va ANTES de armar la entrada porque armarla ya cuesta:
    # abre todos los PDF del cliente y les saca el texto.
    #
    # Sin esto, cada clic en «proponer» arrancaba otra pasada completa en
    # paralelo, y todas cobraban. Pasa más fácil de lo que parece: una
    # pasada larga no se ve trabajar, el contador cree que se trabó,
    # recarga con F5 —y recargar NO la detiene, el servidor sigue y paga
    # hasta el final— y vuelve a darle al botón.
    en_curso = pasada_en_curso(cliente_id)
    if en_curso:
        raise PasadaEnCurso(
            "Ya hay una propuesta corriendo para este cliente, desde hace"
            " %s. Espere a que termine: pedir otra ahora la cobraría dos"
            " veces y propondría lo mismo." % en_curso["desde_hace"]
        )

    try:
        entrada = armar_entrada(cliente)
    except formulario.SinPlantilla as error:
        raise PasadaFallida(
            "Para proponer el formulario hace falta la plantilla del 210."
            " %s" % error
        )

    if not entrada["indice"]:
        raise PasadaFallida(
            "Este cliente no tiene ni exógena cargada ni documentos con"
            " texto legible. No hay de dónde proponer nada."
        )

    pasada_id = db.crear_pasada(
        cliente_id, proveedor=CONFIG.proveedor, modelo=CONFIG.modelo,
        version=instrucciones.VERSION, documentos=entrada["documentos"],
        filas_exogena=entrada["filas_exogena"], bloques=len(entrada["bloques"]),
    )

    valores = []
    lecturas = {}
    uso_total = dict(proveedores.SIN_USO)
    costo_total = 0.0
    fallidos = []

    for numero, bloque in enumerate(entrada["bloques"], start=1):
        try:
            cruda, uso, costo = _pedir_un_bloque(entrada, bloque, numero)
            if cruda is None:
                # Un solo reintento, diciéndole qué salió mal. Si vuelve
                # a fallar no se insiste: sería pagar dos veces por nada.
                cruda, uso2, costo2 = _pedir_un_bloque(
                    entrada, bloque, numero, reproche=REPROCHE
                )
                uso = _sumar_uso(uso, uso2)
                costo += costo2
        except proveedores.ErrorDeProveedor as error:
            fallidos.append("Bloque %d: %s" % (numero, error))
            continue

        uso_total = _sumar_uso(uso_total, uso)
        costo_total += costo

        if cruda is None:
            fallidos.append(
                "Bloque %d: el modelo contestó dos veces algo que no se"
                " pudo entender." % numero
            )
            continue

        del_bloque, lecturas_del_bloque = verificar(cruda, entrada, numero)
        valores.extend(del_bloque)
        for documento_id, filas in lecturas_del_bloque.items():
            lecturas.setdefault(documento_id, []).extend(filas)

    if fallidos and not valores:
        db.cerrar_pasada(pasada_id, "fallo", uso_total, costo_total,
                         motivo=" | ".join(fallidos))
        raise PasadaFallida(" ".join(fallidos))

    _marcar_conflictos(valores)
    db.guardar_valores_de_pasada(pasada_id, cliente_id, valores)
    _guardar_lecturas(cliente_id, lecturas)

    estado = "parcial" if fallidos else "lista"
    db.cerrar_pasada(pasada_id, estado, uso_total, costo_total,
                     motivo=" | ".join(fallidos))

    bitacora.anotar(
        cliente_id, bitacora.PASADA,
        "Propuesta del formulario: %d valores en %d renglones."
        % (len(valores), len({v["renglon"] for v in valores})),
        cantidad=len(valores),
    )
    return resumen(cliente_id)


def _sumar_uso(uno, otro):
    junto = {clave: (uno.get(clave, 0) or 0) + (otro.get(clave, 0) or 0)
             for clave in ("entrada", "salida", "cache_lectura",
                           "cache_escritura")}
    junto["medido"] = bool(uno.get("medido") or otro.get("medido"))
    return junto


def _marcar_conflictos(valores):
    """Marca los renglones donde dos bloques propusieron cosas distintas.

    No se resuelve solo y no se elige uno: se marcan los dos y se le
    dice al contador. Elegir entre dos lecturas distintas del mismo
    renglón es exactamente lo que este programa no debe hacer por él.
    """
    por_renglon = {}
    for valor in valores:
        por_renglon.setdefault(valor["renglon"], []).append(valor)

    for suyos in por_renglon.values():
        bloques = {v["bloque"] for v in suyos}
        if len(bloques) < 2:
            continue
        celdas = {(v["celda"], v["numero"]) for v in suyos}
        if len(celdas) > 1:
            for valor in suyos:
                valor["conflicto"] = True
                if not valor["motivo"]:
                    valor["motivo"] = (
                        "Dos bloques de documentos propusieron cosas"
                        " distintas para este renglón. Revíselos juntos."
                    )


def _guardar_lecturas(cliente_id, lecturas):
    """Deja en `datos_extraidos` lo que la pasada leyó y no ubicó.

    Así RentAI sigue teniendo con qué contestar sobre los documentos sin
    que haya que volver a leerlos, que era justo lo que hacía la vieja
    cola de lectura — solo que ahora sale de la misma llamada.
    """
    for documento_id, filas in lecturas.items():
        db.guardar_datos_extraidos(cliente_id, documento_id, filas, "pasada")
        db.marcar_lectura(documento_id, "listo")


# ---------------------------------------------------------------------------
# 5. Lo que ve la pantalla, y la aprobación
# ---------------------------------------------------------------------------


# El ajuste que decide si la propuesta se pide sola al confirmar una
# carga. Guardado en la base, no en el .env: es una preferencia de
# trabajo del contador, no configuración del programa.
#
# Viene APAGADO de fábrica, y eso no es timidez: la pasada cuesta plata.
# Es la regla de la casa — lo que es gratis y pasa en este computador
# ocurre sin pedir permiso; lo que cuesta lo pide él.
CLAVE_AUTOMATICO = "proponer_al_confirmar"


def proponer_al_confirmar():
    """¿Está prendido el pedir la propuesta al confirmar una carga?"""
    return db.leer_ajuste(CLAVE_AUTOMATICO, "no") == "si"


def cambiar_automatico(prendido):
    """Prende o apaga el pedirla sola. Devuelve cómo quedó."""
    db.guardar_ajuste(CLAVE_AUTOMATICO, "si" if prendido else "no")
    return proponer_al_confirmar()


def _que_cambio_desde_la_pasada(cliente_id, pasada):
    """Qué llegó después de la última propuesta.

    Sin esto, el contador sube tres documentos más y la pantalla le
    sigue mostrando la propuesta vieja como si estuviera al día. No se
    vuelve a correr sola —eso cuesta— pero sí se le dice, con el botón
    al lado, para que no tenga que acordarse él.
    """
    cuando = (pasada or {}).get("corrida_en") or ""
    if not cuando:
        return {"documentos": 0, "exogena": False}

    nuevos = sum(
        1 for documento in db.listar_documentos(cliente_id)
        if (documento.get("subido_en") or "") > cuando
    )
    carga = db.obtener_carga_exogena(cliente_id)
    return {
        "documentos": nuevos,
        "exogena": bool(carga and (carga.get("cargado_en") or "") > cuando),
    }


def resumen(cliente_id):
    """La propuesta vigente de un cliente, lista para dibujar.

    Los valores van agrupados por renglón, y la SUMA la hace este
    código, nunca el modelo. El nivel del renglón es el peor de sus
    componentes: si una de tres cifras la interpretó el modelo, ese
    renglón hay que mirarlo.
    """
    # Si hay una corriendo se dice, y eso es la mitad del arreglo: al
    # recargar la página el contador ve que SÍ está trabajando, en vez de
    # un botón libre que lo invita a pagar otra vez.
    corriendo = pasada_en_curso(cliente_id)

    pasada = db.ultima_pasada(cliente_id)
    if pasada is None:
        return {
            "hay_pasada": False,
            "ia_disponible": CONFIG.ia_disponible,
            "motivo": CONFIG.motivo,
            "automatico": proponer_al_confirmar(),
            "cambios": {"documentos": 0, "exogena": False},
            "corriendo": corriendo,
            "renglones": [],
        }

    valores = db.listar_valores_de_pasada(pasada["id"])
    por_renglon = {}
    for valor in valores:
        por_renglon.setdefault(valor["renglon"], []).append(valor)

    renglones = []
    for codigo in sorted(por_renglon,
                         key=lambda c: int(instrucciones._numero_de_renglon(c) or 0)):
        suyos = por_renglon[codigo]
        buenos = [v for v in suyos if v["estado"] in ("propuesto", "aprobado")]
        # La suma, aquí, en código. Por casilla: tres certificados de
        # salario van a la fila «Salarios» y se suman ahí; el de
        # cesantías va a la suya y no se mezcla.
        totales = {}
        for valor in buenos:
            if valor["numero"] is not None:
                totales[valor["celda"]] = (
                    totales.get(valor["celda"], 0) + valor["numero"]
                )
        renglones.append({
            "renglon": codigo,
            "nombre": suyos[0]["renglon_nombre"],
            "nivel": instrucciones.nivel_del_renglon(
                [v["nivel"] for v in buenos]
            ) if buenos else "C",
            "total": sum(totales.values()) if totales else None,
            "totales_por_casilla": [
                {"celda": celda, "valor": total}
                for celda, total in totales.items()
            ],
            "conflicto": any(v["conflicto"] for v in suyos),
            "componentes": suyos,
        })

    cuentan = [r for r in renglones if r["total"] is not None]
    return {
        "hay_pasada": True,
        "ia_disponible": CONFIG.ia_disponible,
        "motivo": CONFIG.motivo,
        "automatico": proponer_al_confirmar(),
        # Qué llegó después de esta propuesta. La pantalla lo avisa con
        # el botón al lado; volver a correrla la pide él.
        "cambios": _que_cambio_desde_la_pasada(cliente_id, pasada),
        "corriendo": corriendo,
        "pasada": pasada,
        "renglones": renglones,
        "propuestos": len(cuentan),
        "para_revisar": sum(1 for r in cuentan if r["nivel"] == "C"),
        "en_revision_manual": sum(
            1 for v in valores if v["estado"] == "revision"
        ),
        "sin_casilla": sum(
            1 for v in valores
            if v["estado"] == "propuesto" and not v["celda"]
        ),
    }


def para_aprobar_en_bloque(cliente_id):
    """Los valores de nivel A y B que se pueden aprobar de un golpe.

    Se muestran ANTES de confirmar. Aceptar veinte propuestas a ciegas
    es justo el error que este programa no debe dejar cometer.
    """
    pasada = db.ultima_pasada(cliente_id)
    if pasada is None:
        return []
    return [
        valor for valor in db.listar_valores_de_pasada(pasada["id"])
        if valor["estado"] == "propuesto"
        and valor["nivel"] in ("A", "B")
        and valor["verificada"]
        and valor["celda"]
        and not valor["conflicto"]
    ]


def aprobar(cliente, ids):
    """Pasa las propuestas aprobadas al formulario del cliente.

    Es el único punto por el que la pasada toca el 210, y lo hace por el
    mismo camino de siempre: `formulario.guardar_valor`, que revisa que
    la celda exista, que sea de captura y que no tenga fórmula.

    Los valores que van a la misma casilla se suman aquí, en código.
    """
    cliente_id = cliente["id"]
    pasada = db.ultima_pasada(cliente_id)
    if pasada is None:
        raise PasadaFallida("Este cliente no tiene ninguna propuesta.")

    elegidos = {int(i) for i in ids}
    valores = [v for v in db.listar_valores_de_pasada(pasada["id"])
               if v["id"] in elegidos]
    if not valores:
        raise PasadaFallida("No se escogió ninguna propuesta.")

    rechazados = [v for v in valores
                  if not v["verificada"] or not v["celda"]
                  or v["numero"] is None]
    if rechazados:
        raise PasadaFallida(
            "%d de las propuestas escogidas no se pueden anotar: les falta"
            " la verificación de la cita o la casilla. Revíselas una por"
            " una." % len(rechazados)
        )

    # Todo lo que ya estaba anotado en esa casilla más lo nuevo. Se
    # reemplaza, no se acumula sobre lo anterior: lo anterior también
    # salió de esta misma propuesta.
    por_casilla = {}
    for valor in valores:
        datos = por_casilla.setdefault(
            valor["celda"], {"total": 0, "de": []}
        )
        datos["total"] += valor["numero"]
        datos["de"].append(
            valor["nombre_original"] or ("exógena %s" % valor["referencia"])
        )

    anotadas = []
    for celda, datos in por_casilla.items():
        origen = ", ".join(sorted(set(datos["de"])))[:190]
        anotadas.append(
            formulario.guardar_valor(cliente_id, celda, datos["total"], origen)
        )

    db.cambiar_estado_de_valores([v["id"] for v in valores], "aprobado")
    for valor in valores:
        if valor["celda"]:
            formulario.recordar_casilla(
                instrucciones._numero_de_renglon(valor["renglon"]),
                valor["celda"],
            )

    bitacora.anotar(
        cliente_id, bitacora.PASADA_APROBADA,
        "Aprobó %d valores propuestos en %d casillas."
        % (len(valores), len(por_casilla)),
        cantidad=len(valores),
    )
    return {"anotadas": anotadas, "aprobados": len(valores)}


def descartar(cliente_id, ids):
    """Marca propuestas como descartadas. No se borran: quedan con su rastro."""
    cuantas = db.cambiar_estado_de_valores([int(i) for i in ids], "descartado")
    if cuantas:
        bitacora.anotar(cliente_id, bitacora.PASADA_DESCARTADA,
                        "Descartó %d valores propuestos." % cuantas,
                        cantidad=cuantas)
    return cuantas


def cambiar_casilla(cliente_id, valor_id, celda):
    """El contador escoge la casilla cuando el programa no pudo."""
    pasada = db.ultima_pasada(cliente_id)
    if pasada is None:
        raise PasadaFallida("Este cliente no tiene ninguna propuesta.")
    celda = str(celda or "").strip().upper()
    if celda and celda not in formulario.indice():
        raise PasadaFallida("La casilla %s no existe en la plantilla." % celda)

    with db.conectar() as conexion:
        conexion.execute(
            "UPDATE pasada_valores SET celda = ?, celda_motivo = ?"
            " WHERE id = ? AND pasada_id = ?",
            (celda, "La escogió usted.", int(valor_id), pasada["id"]),
        )
    return resumen(cliente_id)
