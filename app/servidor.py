"""
El servidor web, hecho solo con lo que Python ya trae adentro.

Por qué existe este archivo
---------------------------
Antes esto lo hacía FastAPI. Se sacó por una razón concreta, no por
gusto: FastAPI arrastra `pydantic_core`, que es un archivo compilado sin
firmar, y el Control inteligente de aplicaciones de Windows 11 lo BLOQUEA.
El programa ni siquiera alcanzaba a arrancar en el computador de destino,
y la única salida era pedirle al contador que apagara una seguridad de
Windows que después no se puede volver a prender fácil.

Python trae su propio servidor (`http.server`), y viene firmado por la
Python Software Foundation. Windows confía en él. Con esto, el programa
no tiene NINGÚN archivo compilado sin firmar, y no hay nada que bloquear.

De paso: instalar el programa dejó de bajar cinco librerías y ahora baja
dos, las dos de Python puro. En el computador del contador, cada librería
menos es una cosa menos que puede fallar.

Qué hace y qué no
-----------------
Esto NO es un FastAPI casero. Es lo mínimo que el programa necesita:
direcciones con partes variables, JSON de ida y vuelta, archivos que se
suben, archivos que se descargan, y errores con un mensaje que se pueda
mostrar en pantalla. Nada más. Si algún día hace falta algo distinto, se
agrega aquí y se lee en veinte líneas.

Para la pantalla no cambió nada: las mismas direcciones, los mismos
códigos y el mismo JSON de siempre. El navegador no sabe —ni tiene por
qué saber— con qué está hecho el servidor.
"""

import json
import mimetypes
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

# La única librería de afuera que se usa aquí, y es de Python puro: sabe
# separar los archivos que manda el navegador cuando uno sube documentos.
#
# Se importa como "python_multipart" y no como "multipart" a secas porque
# existe OTRA librería distinta que también se llama así; con el nombre
# largo no hay forma de que se cargue la equivocada.
import python_multipart

# Techo de lo que se acepta recibir de una sola vez. El límite de verdad
# de cada cosa lo pone quien la recibe (25 MB un documento, 100 MB un
# ZIP); esto es solo para no dejar que alguien mande algo absurdo y llene
# la memoria antes de que nadie alcance a revisarlo.
LIMITE_PETICION = 220 * 1024 * 1024

# Formas de escribir "sí" en la dirección: ?todas=true, ?todas=1, ?todas=si
VALORES_SI = {"true", "1", "si", "sí", "yes", "on"}


class ErrorHttp(Exception):
    """Un error que hay que mostrarle al contador en la pantalla.

    El texto se manda tal cual al navegador, así que se escribe pensando
    en quien lo va a leer, no en quien programó.
    """

    def __init__(self, codigo, detalle):
        super().__init__(detalle)
        self.codigo = codigo
        self.detalle = detalle


class Respuesta:
    """Una respuesta que no es JSON: un archivo, un texto, o nada."""

    def __init__(self, cuerpo=b"", codigo=200,
                 tipo="application/octet-stream", cabeceras=None):
        if isinstance(cuerpo, str):
            cuerpo = cuerpo.encode("utf-8")
        self.cuerpo = cuerpo
        self.codigo = codigo
        self.tipo = tipo
        self.cabeceras = cabeceras or {}

    @classmethod
    def texto(cls, texto, tipo="text/plain; charset=utf-8", cabeceras=None):
        return cls(texto, tipo=tipo, cabeceras=cabeceras)

    @classmethod
    def archivo(cls, ruta, tipo=None, nombre_visible=None, descargar=False):
        """Entrega un archivo del disco.

        `nombre_visible` es el nombre con el que el navegador lo va a
        mostrar o guardar. Va codificado (filename*=UTF-8) porque si no,
        un archivo que se llame "Declaración Muñoz.pdf" llega con la
        tilde y la eñe partidas.
        """
        ruta = Path(ruta)
        if tipo is None:
            tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"

        cabeceras = {}
        if nombre_visible:
            como = "attachment" if descargar else "inline"
            cabeceras["Content-Disposition"] = (
                "%s; filename*=UTF-8''%s" % (como, quote(nombre_visible))
            )

        return cls(ruta.read_bytes(), tipo=tipo, cabeceras=cabeceras)


class Peticion:
    """Lo que mandó el navegador, ya listo para usar."""

    def __init__(self, metodo, camino, consulta, cabeceras, cuerpo):
        self.metodo = metodo
        self.camino = camino
        self.consulta = consulta      # {"buscar": "salarios", ...}
        self.cabeceras = cabeceras
        self.cuerpo = cuerpo          # bytes, tal como llegaron

    # --- Lo que viene en la dirección: /api/algo?buscar=x&todas=true ---

    def texto_de(self, nombre, por_defecto=""):
        return self.consulta.get(nombre, por_defecto)

    def si_o_no(self, nombre, por_defecto=False):
        valor = self.consulta.get(nombre)
        if valor is None:
            return por_defecto
        return valor.strip().lower() in VALORES_SI

    # --- Lo que viene en el cuerpo ---

    def json(self):
        """El cuerpo entendido como JSON.

        Si viene mal armado se contesta 400 con un mensaje, en vez de
        dejar que reviente con un error de programador.
        """
        if not self.cuerpo:
            raise ErrorHttp(400, "Falta la información de la petición.")
        try:
            return json.loads(self.cuerpo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ErrorHttp(400, "La información llegó mal armada.")

    def diccionario(self):
        """El cuerpo como diccionario, comprobando que sea uno."""
        datos = self.json()
        if not isinstance(datos, dict):
            raise ErrorHttp(400, "La información llegó mal armada.")
        return datos

    def lista(self):
        """El cuerpo como lista, comprobando que sea una."""
        datos = self.json()
        if not isinstance(datos, list):
            raise ErrorHttp(400, "La información llegó mal armada.")
        return datos

    def archivos(self, campo):
        """Los archivos que subió el navegador, como pares (nombre, bytes).

        El navegador manda las subidas en un formato con separadores
        (multipart/form-data). Se usa la librería `multipart`, que es de
        Python puro: no trae nada compilado que Windows pueda bloquear.
        """
        tipo = self.cabeceras.get("content-type", "")
        if "multipart/form-data" not in tipo:
            raise ErrorHttp(400, "No llegó ningún archivo.")

        # Primero se recogen, y solo cuando la librería terminó de leer
        # todo se abren. Leerlos o cerrarlos dentro del aviso no funciona:
        # la librería avisa que el archivo llegó y DESPUÉS le hace el
        # último guardado, así que cerrarlo antes la deja escribiendo
        # sobre un archivo cerrado.
        recogidos = []

        python_multipart.parse_form(
            {"Content-Type": tipo},
            BytesIO(self.cuerpo),
            on_field=lambda campo_suelto: None,
            on_file=recogidos.append,
        )

        encontrados = []
        for archivo in recogidos:
            try:
                del_campo = (archivo.field_name or b"").decode("utf-8", "replace")
                if del_campo != campo:
                    continue
                nombre = (archivo.file_name or b"").decode("utf-8", "replace")
                # El archivo puede haber quedado en memoria o en un archivo
                # temporal del sistema, según su tamaño. Con seek(0) y
                # read() se lee igual en los dos casos.
                archivo.file_object.seek(0)
                encontrados.append((nombre, archivo.file_object.read()))
            finally:
                # close() borra el temporal si lo hubo. Son documentos
                # confidenciales: no se pueden quedar dando vueltas por
                # las carpetas temporales del computador.
                archivo.close()

        if not encontrados:
            raise ErrorHttp(400, "No llegó ningún archivo.")
        return encontrados


class Aplicacion:
    """Las direcciones del programa y qué función atiende cada una."""

    def __init__(self):
        self.rutas = []          # [(metodo, regex, funcion, codigo)]
        self.estaticos = []      # [(prefijo, carpeta)]

    # --- Declarar direcciones ---

    def ruta(self, metodo, patron, codigo=200):
        """Decorador que conecta una dirección con la función que la atiende.

        En el patrón, lo que va entre llaves es una parte variable:

            /api/clientes/{id_cliente}/documentos

        Las partes que se llaman `id_algo` llegan convertidas a número,
        porque son identificadores de la base de datos. Si alguien pide
        /api/clientes/abc, se contesta 404 en vez de reventar. Las demás
        llegan como texto.
        """
        expresion = "^" + re.sub(
            r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", r"(?P<\1>[^/]+)", patron
        ) + "$"
        compilada = re.compile(expresion)

        def guardar(funcion):
            self.rutas.append((metodo, compilada, funcion, codigo))
            return funcion

        return guardar

    def get(self, patron, codigo=200):
        return self.ruta("GET", patron, codigo)

    def post(self, patron, codigo=200):
        return self.ruta("POST", patron, codigo)

    def put(self, patron, codigo=200):
        return self.ruta("PUT", patron, codigo)

    def patch(self, patron, codigo=200):
        return self.ruta("PATCH", patron, codigo)

    def delete(self, patron, codigo=204):
        return self.ruta("DELETE", patron, codigo)

    def carpeta_estatica(self, prefijo, carpeta):
        """Sirve los archivos de una carpeta (el CSS, el JavaScript)."""
        self.estaticos.append((prefijo, Path(carpeta).resolve()))

    # --- Buscar cuál atiende ---

    def buscar(self, metodo, camino):
        """Devuelve (funcion, partes, codigo), o levanta 404 o 405."""
        habia_camino = False

        for metodo_ruta, compilada, funcion, codigo in self.rutas:
            encontrado = compilada.match(camino)
            if not encontrado:
                continue
            habia_camino = True
            if metodo_ruta != metodo:
                continue

            partes = {}
            for nombre, valor in encontrado.groupdict().items():
                valor = unquote(valor)
                if nombre.startswith("id_"):
                    if not valor.lstrip("-").isdigit():
                        raise ErrorHttp(404, "Esa dirección no existe.")
                    valor = int(valor)
                partes[nombre] = valor
            return funcion, partes, codigo

        if habia_camino:
            raise ErrorHttp(405, "Esa dirección no admite esa operación.")
        raise ErrorHttp(404, "Esa dirección no existe.")

    def archivo_estatico(self, camino):
        """El archivo de una carpeta estática, o None si no es de ahí."""
        for prefijo, carpeta in self.estaticos:
            if not camino.startswith(prefijo):
                continue

            relativo = unquote(camino[len(prefijo):])
            destino = (carpeta / relativo).resolve()

            # Nadie puede salirse de la carpeta con ../ para leerse el
            # .env o la base de datos. Se compara la ruta ya resuelta.
            try:
                destino.relative_to(carpeta)
            except ValueError:
                raise ErrorHttp(404, "Ese archivo no existe.")

            if not destino.is_file():
                raise ErrorHttp(404, "Ese archivo no existe.")
            return destino

        return None

    # --- Prender ---

    def arrancar(self, maquina="127.0.0.1", puerto=8000, al_arrancar=None):
        """Prende el servidor y se queda atendiendo hasta que lo apaguen."""
        if al_arrancar is not None:
            al_arrancar()

        aplicacion = self

        class Manejador(_Manejador):
            pass

        Manejador.aplicacion = aplicacion

        # ThreadingHTTPServer atiende cada petición en su propio hilo. Hace
        # falta: generar el Formulario 210 abre LibreOffice y se demora
        # medio minuto, y sin hilos la pantalla se quedaría congelada
        # todo ese rato sin poder ni cargar el CSS.
        servidor = ThreadingHTTPServer((maquina, puerto), Manejador)
        servidor.daemon_threads = True
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            print("\n  Tax-i apagado.")
        finally:
            servidor.server_close()


class _Manejador(BaseHTTPRequestHandler):
    """Traduce entre lo que habla el navegador y las funciones de arriba."""

    aplicacion = None

    # HTTP/1.1 deja reusar la conexión, que es lo que hace que la pantalla
    # cargue rápido. A cambio, hay que mandar SIEMPRE el Content-Length
    # exacto: si no, el navegador se queda esperando datos que no llegan.
    protocol_version = "HTTP/1.1"

    server_version = "Taxi"
    sys_version = ""

    def do_GET(self):
        self._atender("GET")

    def do_POST(self):
        self._atender("POST")

    def do_PUT(self):
        self._atender("PUT")

    def do_PATCH(self):
        self._atender("PATCH")

    def do_DELETE(self):
        self._atender("DELETE")

    def do_HEAD(self):
        self._atender("GET", solo_cabeceras=True)

    # ------------------------------------------------------

    def _atender(self, metodo, solo_cabeceras=False):
        try:
            respuesta = self._resolver(metodo)
        except ErrorHttp as error:
            respuesta = self._como_error(error.codigo, error.detalle)
        except Exception:
            # Un error que no se esperaba. Al contador se le dice algo
            # que pueda entender; el detalle técnico va a la consola,
            # SIN nombres de clientes ni contenido de documentos.
            traceback.print_exc(file=sys.stderr)
            respuesta = self._como_error(
                500, "Al programa le pasó algo que no esperaba. El detalle"
                     " quedó en la ventana negra."
            )

        self._mandar(respuesta, solo_cabeceras)

    def _resolver(self, metodo):
        partido = urlparse(self.path)
        camino = partido.path

        # Los archivos sueltos (CSS, JavaScript) se atienden primero: son
        # los más pedidos y no tienen nada que validar.
        estatico = self.aplicacion.archivo_estatico(camino)
        if estatico is not None:
            if metodo != "GET":
                raise ErrorHttp(405, "Esa dirección no admite esa operación.")
            return Respuesta.archivo(estatico)

        funcion, partes, codigo = self.aplicacion.buscar(metodo, camino)

        consulta = {
            nombre: valores[0]
            for nombre, valores in parse_qs(partido.query).items()
        }
        peticion = Peticion(
            metodo=metodo,
            camino=camino,
            consulta=consulta,
            cabeceras={n.lower(): v for n, v in self.headers.items()},
            cuerpo=self._leer_cuerpo(),
        )

        resultado = funcion(peticion, **partes)

        if isinstance(resultado, Respuesta):
            return resultado
        if resultado is None:
            return Respuesta(b"", codigo=204, tipo="")
        return Respuesta(
            json.dumps(resultado, ensure_ascii=False).encode("utf-8"),
            codigo=codigo,
            tipo="application/json; charset=utf-8",
        )

    def _leer_cuerpo(self):
        """Lee el cuerpo de la petición, sin pasarse del techo."""
        largo = self.headers.get("Content-Length")
        if not largo:
            return b""
        try:
            largo = int(largo)
        except ValueError:
            raise ErrorHttp(400, "La petición llegó mal armada.")
        if largo < 0:
            raise ErrorHttp(400, "La petición llegó mal armada.")
        if largo > LIMITE_PETICION:
            raise ErrorHttp(413, "Eso pesa demasiado para mandarlo de una vez.")
        return self.rfile.read(largo)

    def _como_error(self, codigo, detalle):
        """El error, en el mismo formato que la pantalla ya sabe leer."""
        return Respuesta(
            json.dumps({"detail": detalle}, ensure_ascii=False).encode("utf-8"),
            codigo=codigo,
            tipo="application/json; charset=utf-8",
        )

    def _mandar(self, respuesta, solo_cabeceras=False):
        cuerpo = respuesta.cuerpo or b""
        try:
            self.send_response(respuesta.codigo)
            if respuesta.tipo:
                self.send_header("Content-Type", respuesta.tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            for nombre, valor in respuesta.cabeceras.items():
                self.send_header(nombre, valor)
            self.end_headers()
            if not solo_cabeceras and cuerpo:
                self.wfile.write(cuerpo)
        except ConnectionError:
            # El navegador se fue antes de que le contestáramos: cerró la
            # pestaña, recargó con F5 o se le cayó la red. No es un error
            # del programa, así que no ensucia la ventana negra.
            #
            # Se atrapa ConnectionError, que es la madre de las tres, y no
            # una lista: Mac tira BrokenPipeError, Windows tira
            # ConnectionAbortedError (el WinError 10053) y cualquiera de
            # los dos puede tirar ConnectionResetError. Listando solo dos
            # se colaba justo la de Windows, que es donde vive el contador,
            # y le llenaba la pantalla de un traceback que no significaba
            # nada.
            #
            # end_headers() también escribe al socket, por eso está
            # adentro del try y no afuera.
            self.close_connection = True

    def log_message(self, formato, *argumentos):
        """Lo que sale en la ventana negra.

        Se escribe solo el método y la dirección, sin lo que va después
        del signo de interrogación y sin el cuerpo. Es la regla del
        proyecto: en los registros no puede quedar nada de ningún
        cliente, ni nombres, ni cifras, ni texto de documentos.
        """
        camino = urlparse(self.path).path
        sys.stderr.write("  %s %s\n" % (self.command, camino))
