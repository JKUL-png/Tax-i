"""La pantalla de Cuenta: quién usa el programa y cómo está la IA."""

from app import configuracion, db, proveedores, rentai
from app.api.base import RAIZ, app, campo_texto, revisado
from app.servidor import ErrorHttp


# ----------------------------------------------------------
# La cuenta
#
# Hoy no hay cuentas de verdad: el programa corre en un computador y lo
# usa una persona. Esta pantalla existe por dos motivos.
#
# El primero es práctico y es el de ahora: que el contador pueda cambiar
# su llave de la IA sin tener que abrir el archivo .env con el bloc de
# notas. Las llaves se vencen, se cambian y se revocan; pedirle que edite
# un archivo escondido cada vez era pedirle demasiado.
#
# El segundo es que el día que haya login, ya hay un lugar donde ponerlo:
# los datos de quién es se guardan en la tabla "ajustes" con el prefijo
# "cuenta_", y las direcciones son /api/cuenta. No se inventó nada de
# usuarios ni de contraseñas todavía — eso está fuera del alcance de la
# versión 1 — pero el sitio ya está hecho.
# ----------------------------------------------------------

# Cómo se llama esta versión del programa cuando alguien pregunta.
VERSION = "prototipo"

# Los ajustes de la cuenta que se guardan en la base, con el prefijo que
# los agrupa. El día que haya varias cuentas, esto es lo que se muda.
AJUSTE_NOMBRE = "cuenta_nombre"
AJUSTE_CORREO = "cuenta_correo"


def _cuenta_como_diccionario():
    """Todo lo que la pantalla de Cuenta necesita saber. Sin la llave."""
    datos = configuracion.CONFIG.como_diccionario()
    datos.update({
        "version": VERSION,
        "nombre": db.leer_ajuste(AJUSTE_NOMBRE, ""),
        "correo": db.leer_ajuste(AJUSTE_CORREO, ""),
        "clientes": len(db.listar_clientes()),
        # contar_documentos() devuelve cuántos tiene cada cliente;
        # aquí solo interesa el total.
        "documentos": sum(db.contar_documentos().values()),
        # Dónde quedaron las cosas, por si hay que respaldarlas o mudarlas.
        "carpeta_datos": str(RAIZ / "datos"),
        "archivo_env": str(configuracion.ARCHIVO_ENV),
        "hay_env": configuracion.ARCHIVO_ENV.exists(),
    })
    return datos


@app.get("/api/cuenta")
def api_cuenta(peticion):
    """Quién usa el programa, cómo está configurado y dónde están los datos."""
    return _cuenta_como_diccionario()


@app.put("/api/cuenta")
def api_guardar_cuenta(peticion, **partes):
    """Guarda el nombre y el correo de quien usa el programa.

    No se usan para nada todavía: salen en el resumen impreso el día que
    se quiera y sirven de sitio para el login cuando lo haya.
    """
    datos = peticion.diccionario()
    # Se recorta a algo razonable: esto es un rótulo, no un campo libre.
    db.guardar_ajuste(AJUSTE_NOMBRE, campo_texto(datos, "nombre", "").strip()[:120])
    db.guardar_ajuste(AJUSTE_CORREO, campo_texto(datos, "correo", "").strip()[:120])
    return _cuenta_como_diccionario()


def limpiar_llave(valor):
    """Revisa una llave de la IA antes de escribirla en el .env."""
    limpia = valor.strip()
    if not limpia:
        return ""
    # Una llave no tiene espacios ni saltos de línea. Si los trae, casi
    # siempre es porque se copió de más y así no va a funcionar.
    if any(c.isspace() for c in limpia):
        raise ValueError("La llave no puede tener espacios. Cópiela completa y sola.")
    if len(limpia) < 20 or len(limpia) > 200:
        raise ValueError("Esa llave no tiene la forma de una llave de un servicio de IA.")
    return limpia


def limpiar_modelo(valor):
    """Revisa el nombre del modelo de IA."""
    limpio = (valor or "").strip()[:100]
    if limpio and any(c.isspace() for c in limpio):
        raise ValueError("El nombre del modelo no lleva espacios.")
    return limpio


def limpiar_proveedor(valor):
    """Revisa que el proveedor sea uno de los cuatro que existen."""
    limpio = (valor or "").strip().lower()
    if limpio not in proveedores.PROVEEDORES:
        raise ValueError(
            "Ese servicio de IA no existe. Las opciones son: "
            + ", ".join(sorted(proveedores.PROVEEDORES))
            + "."
        )
    return limpio


def limpiar_base_url(valor):
    """Revisa la dirección del servicio.

    Se exige http o https por una razón concreta: sin esto, un error de
    dedo como "api.openai.com" sin protocolo hace que urllib intente
    abrir un ARCHIVO con ese nombre en vez de una dirección de internet,
    y el error que sale no se parece en nada al problema real.
    """
    limpia = (valor or "").strip().rstrip("/")[:300]
    if not limpia:
        return ""
    if not (limpia.startswith("http://") or limpia.startswith("https://")):
        raise ValueError(
            "La dirección tiene que empezar por http:// o https://."
        )
    if any(c.isspace() for c in limpia):
        raise ValueError("La dirección no puede tener espacios.")
    return limpia


@app.put("/api/cuenta/ia")
def api_guardar_ia(peticion, **partes):
    """Cambia el proveedor de IA, su dirección, la llave y el modelo.

    Escribe el .env y después recarga la configuración en caliente, así
    el cambio vale de una vez sin apagar y prender el programa.

    La llave se guarda en el .env y NUNCA en la base de datos ni en los
    logs, y no se devuelve entera a la pantalla en ninguna respuesta.
    """
    datos = peticion.diccionario()

    proveedor = revisado(limpiar_proveedor, campo_texto(datos, "proveedor", ""))
    modelo = revisado(limpiar_modelo, campo_texto(datos, "modelo", ""))
    base_url = revisado(limpiar_base_url, campo_texto(datos, "base_url", ""))

    ficha = proveedores.obtener(proveedor)

    if ficha.necesita_base_url and not base_url:
        raise ErrorHttp(
            400,
            "Con \"%s\" hay que decir en qué dirección está el servicio."
            % ficha.nombre,
        )

    cambios = {
        "IA_PROVEEDOR": proveedor,
        "IA_BASE_URL": base_url,
        "IA_MODELO": modelo or ficha.modelo_sugerido,
        # El interruptor viejo se deja apagado y explícito. Si quedara
        # en "true" de una configuración anterior, apagaría la IA por
        # detrás y el contador no entendería por qué no funciona.
        "SIN_IA": "false",
    }

    # llave sin mandar = "no la toque". Mandada vacía = "bórrela".
    if "llave" in datos and datos["llave"] is not None:
        cambios["IA_API_KEY"] = revisado(
            limpiar_llave, campo_texto(datos, "llave", "")
        )
    else:
        # No mandaron llave nueva, pero puede que la que hay siga
        # guardada con el nombre VIEJO (GROQ_API_KEY, de cuando el
        # programa solo hablaba con Groq). Se pasa al nombre nuevo aquí,
        # en el primer guardado, y se vacía el viejo para no dejar la
        # misma llave escrita dos veces en el archivo.
        #
        # Sin esto, el .env se queda a medio camino: funciona, pero
        # cualquiera que lo abra ve una configuración que no cuadra.
        valores = configuracion.leer_env()
        vieja = (valores.get("GROQ_API_KEY") or "").strip()
        if vieja and not (valores.get("IA_API_KEY") or "").strip():
            cambios["IA_API_KEY"] = vieja
            cambios["GROQ_API_KEY"] = ""

    try:
        configuracion.guardar_en_env(cambios)
    except OSError:
        # No se dice cuál archivo falló con detalle del sistema: eso se
        # queda en el servidor. Al contador se le dice qué hacer.
        raise ErrorHttp(
            500,
            "No se pudo escribir el archivo de configuración (.env)."
            " Revise que la carpeta del programa no esté protegida"
            " contra escritura.",
        )

    configuracion.CONFIG.recargar()
    return _cuenta_como_diccionario()


@app.post("/api/cuenta/ia/probar")
def api_probar_llave(peticion, **partes):
    """Prueba la conexión con el servicio, sin guardar nada.

    Lo único que sale del computador es la llave, para preguntarle al
    servicio si sirve. NO se manda ni un dato de ningún cliente: se pide
    la lista de modelos, que es una consulta de solo lectura.

    Se puede probar una configuración distinta de la guardada, para que
    el contador compruebe ANTES de cambiarla.
    """
    datos = peticion.diccionario()
    config = configuracion.CONFIG

    proveedor = (campo_texto(datos, "proveedor", "").strip()
                 or config.proveedor)
    base_url = campo_texto(datos, "base_url", "").strip() or config.base_url
    llave = campo_texto(datos, "llave", "").strip() or config.llave

    sirve, motivo = rentai.probar_llave(llave, proveedor, base_url)
    return {"sirve": sirve, "motivo": motivo}
