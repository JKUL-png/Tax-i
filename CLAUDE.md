# Convenciones del proyecto — Asistente de organización documental para renta

El brief completo está en `PROYECTO-ASISTENTE-RENTA.md`. Este archivo son las reglas de trabajo.
Ante cualquier duda de alcance, manda el brief.

**Qué es:** un archivador local que recibe documentos desordenados (PDF, fotos, XML, ZIP),
los identifica, dice cuáles faltan por cliente y genera un resumen. **No hace impuestos.**

---

## Stack

- **Backend:** Python 3.9+, **sin framework web**. El servidor está en
  `app/servidor.py`, hecho con lo que Python ya trae (`http.server`).
  Antes era FastAPI; se sacó en agosto de 2026 porque arrastraba
  `pydantic_core`, un archivo compilado sin firmar que el Control
  inteligente de aplicaciones de Windows 11 bloquea, y el programa no
  arrancaba en el computador de destino.
- **Base de datos:** SQLite (archivo local)
- **Frontend:** HTML + CSS + JavaScript plano. **Sin framework, sin build, sin npm.**
- **IA:** cualquier proveedor, elegido en el `.env` y en la pantalla de Cuenta.
  La capa que traduce de uno a otro está en `app/proveedores.py`. Cuatro opciones:
  `ninguno` (de fábrica), `anthropic`, `openai_compatible` (OpenAI, Groq,
  OpenRouter, Together, LM Studio…) y `ollama` (en el propio computador).
  **`ninguno` tiene que seguir funcionando completo**: la IA acelera, no habilita.
  Antes estaba atado solo a Groq; se abrió en agosto de 2026.
  Al elegir un servicio se elige a quién se le confían los textos: hay capas
  gratis que entrenan con lo que uno les manda y donde revisores humanos pueden
  leerlo. Eso pesa más que el precio.
- **Corre en:** `http://localhost:8000`

Antes de agregar una dependencia nueva, preguntar. Cada librería es una cosa más que puede
fallar al instalar en el computador del contador.

**Y una regla dura: la librería tiene que ser de Python puro.** Si trae archivos `.pyd`
o `.so` —código compilado— no entra. Windows 11 los bloquea cuando no vienen firmados por
una empresa que Microsoft ya conoce, y las librerías de Python no vienen firmadas. Cuando
eso pasa el programa ni siquiera arranca, y la única salida es pedirle al contador que
apague una seguridad de su computador. Se comprueba con `pruebas/revisar_windows.py`.

---

## Estructura de carpetas

```
asistente-renta/
├── app/
│   ├── main.py           # las direcciones del programa (la API)
│   ├── servidor.py       # el servidor web, hecho con lo que trae Python
│   ├── db.py             # SQLite
│   ├── documentos.py     # clasificación y extracción
│   ├── checklist.py      # qué falta por cliente
│   ├── exportar.py       # resumen
│   ├── plantilla_210.py  # mapa de la plantilla de Excel
│   ├── escribir_210.py   # escritura quirúrgica sobre el .xlsx
│   ├── recalcular.py     # totales con LibreOffice
│   ├── formulario.py     # el Formulario 210 de cada cliente
│   ├── rentai.py         # la asistente que conversa y propone
│   ├── proveedores.py    # con cuál servicio de IA se habla
│   ├── extraccion.py     # leerle los datos a un documento UNA vez
│   ├── exogena.py        # leer el reporte de la DIAN. Solo parseo, sin IA
│   ├── exogena_cliente.py # los renglones y la tabla de cada cliente
│   ├── clasificacion.py  # a qué renglón va cada documento, y lo aprendido
│   ├── cola.py           # la fila de documentos por leer, en otro hilo
│   ├── respaldo.py       # llevarse todo en un ZIP, y traerlo de vuelta
│   ├── demostracion.py   # el cliente inventado, para mostrar el programa
│   ├── revision.py       # ¿está todo listo para trabajar?
│   ├── bitacora.py       # qué pasó con cada cliente y cuándo
│   ├── vencimientos.py   # la tabla del calendario oficial (viene vacía)
│   └── api/              # las direcciones, un archivo por asunto
├── static/               # HTML, CSS, JS
├── plantillas/           # las plantillas de Excel del contador (NUNCA a git)
├── pruebas/              # programas que comprueban que todo siga funcionando
├── datos/                # NUNCA se sube a git
│   ├── archivos/         # documentos subidos, por cliente
│   ├── papelera/         # lo borrado, por si fue un error. No se vacía sola
│   ├── formularios/      # el Excel generado de cada cliente
│   ├── exogena/          # los reportes de la DIAN, por cliente
│   └── base.db
├── .env                  # configuración de la IA — NUNCA se sube a git
├── docs/capturas/        # las capturas del README. Clientes INVENTADOS
├── LICENSE               # AGPL-3.0, texto íntegro de la FSF
├── README.md             # la portada del repositorio
├── requirements.txt
├── iniciar.command       # Mac, doble clic desde el Finder
├── iniciar.sh            # Mac, desde la terminal
└── iniciar.bat           # Windows
```

**Licencia: AGPL-3.0.** El repositorio es público. Antes de subir cualquier cosa,
dos comprobaciones que no se saltan: que no salga ningún documento ni nombre de
cliente de verdad —tampoco en las capturas— y que el `.env` siga fuera. Lo que
se publica queda clonado; no hay marcha atrás.

---

## Multiplataforma: se desarrolla en Mac, se usa en Windows

**Un solo código que corre en ambos.** No se hacen dos versiones del programa, solo dos
lanzadores. Estas reglas no son opcionales — son los errores que aparecen *solo* en Windows,
cuando ya está en manos del contador y no lo puedes depurar.

1. **Rutas: siempre `pathlib.Path`.** Nunca armar rutas pegando texto con `/` o `\`.
   Nunca rutas absolutas — todo relativo a la raíz del proyecto.

2. **Encoding: siempre explícito.**
   ```python
   open(ruta, encoding="utf-8")          # bien
   open(ruta)                             # mal — en Windows usa cp1252 y rompe las tildes
   ```
   Aplica también a `subprocess`, a leer/escribir JSON y a la conexión de SQLite.

3. **Nombres de archivo: sanitizar antes de guardar.** Windows prohíbe `< > : " / \ | ? *`,
   no acepta nombres terminados en punto o espacio, y tiene nombres reservados
   (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`). Un cliente que manda
   `Certificado 2025: Bancolombia.pdf` rompe el guardado en Windows y funciona en Mac.

4. **Basura de macOS al importar:** ignorar `.DS_Store`, la carpeta `__MACOSX` dentro de los
   ZIP, y los archivos que empiezan por `._`. No son documentos.

5. **ZIP con tildes:** los ZIP hechos en Windows traen los nombres en cp437, no en UTF-8.
   Manejar el caso al descomprimir o los nombres salen ilegibles.

6. **Saltos de línea:** LF en todo el repositorio, **menos `iniciar.bat`**, que necesita CRLF
   (con LF, `cmd.exe` puede fallar al leer las etiquetas del archivo). Está configurado
   en `.gitattributes`; no cambiarlo.

7. **Comando de Python:** en Mac es `python3`, en Windows es `py`. Cada lanzador usa el suyo;
   ambos crean el entorno virtual e instalan `requirements.txt` si no existe.

8. **Un `.bat` descargado de internet lo bloquea el Control inteligente de aplicaciones,
   y ese bloqueo NO tiene botón para continuar.** Windows le pone la "Marca de la Web"
   a todo lo que se baja, y Smart App Control rechaza los `.bat` que la traen. Es un
   bloqueo distinto del que sacó a FastAPI: aquel era por un binario compilado sin
   firmar y no se podía esquivar; este se quita desbloqueando el archivo
   (Propiedades → Desbloquear, o `Unblock-File` en PowerShell).

   **Nunca se le dice a nadie que apague el Control inteligente por esto.** Es la
   protección del computador donde viven documentos tributarios de terceros, y
   desbloquear el archivo resuelve exactamente lo mismo sin bajar ninguna defensa.
   La instrucción de desbloquear va ANTES de descomprimir, porque desbloquear el ZIP
   desbloquea todo lo de adentro de una vez.

8. **Probar en ambos antes de dar algo por terminado.** Si solo se probó en Mac, decirlo
   explícitamente en vez de afirmar que funciona.

---

## Código

- **Comentarios en español.** También los mensajes de error y los textos de la interfaz.
- Nombres de variables y funciones en español cuando sean del dominio
  (`cliente`, `checklist`, `fecha_vencimiento`), en inglés cuando sean técnicos estándar.
- Código simple y directo. El desarrollador no tiene formación formal en programación:
  preferir lo legible sobre lo elegante, y explicar en lenguaje claro qué hace cada pieza.
- **El código maneja los datos, la IA maneja lo desordenado.** Nunca se le pide a la IA que
  calcule, sume, compare cifras ni decida fechas. Si es XML, se parsea — no se manda a la IA.
- **El modelo no tiene memoria; la memoria del sistema es la base de datos.** Cada documento
  se lee UNA vez, al procesarlo (`app/extraccion.py`), y lo que se le sacó queda en la tabla
  `datos_extraidos`. Después, cuando el contador le pregunta algo a RentAI, se le mandan esas
  filas — nunca los documentos otra vez. Se paga una vez por documento en vez de en cada
  pregunta, y lo ya extraído se sigue viendo con `IA_PROVEEDOR=ninguno`.

---

## La información exógena

La exógena es lo que los terceros —bancos, empleadores, notarías,
municipios— le reportaron a la DIAN sobre un contribuyente. El contador la
descarga del portal de la DIAN como un Excel y es lo primero que mira. La
pestaña se llama **Exógena**, que es la palabra que él usa: ni "reporte", ni
"cruce", ni "conciliación".

- **Se lee con código, nunca con IA.** Es una tabla bien formada.
  `app/exogena.py` la parsea y funciona completo con `IA_PROVEEDOR=ninguno`.
  Si alguna vez parece que hace falta IA para leerla, algo se entendió mal.
- **Nada de números de fila fijos.** La fila de encabezados se busca por el
  texto «Uso declaración Sugerida». El formato puede cambiar el año que viene.
- **Los tres avisos legales de la DIAN se guardan y se muestran textuales.**
  Son de ella, no nuestros. Junto con la fecha de corte, porque el primero
  dice que la información cambia si un tercero la modifica después.
- **Cuando la DIAN propone varios renglones, Tax-i no elige.** Ni con IA, ni
  con reglas, ni mirando el signo del valor. Se marca "requiere decisión" y se
  le muestran las opciones palabra por palabra, con el doble espacio de la
  DIAN incluido. Elegir es criterio profesional.
- **Los posibles duplicados solo se marcan**, con el motivo de por qué se
  marcaron. No se unen, no se descartan y no se elige cuál vale.
- **Los renglones salen del archivo oficial**, con el nombre que la propia
  DIAN les da, y quedan marcados con `origen='dian'`. El contador los puede
  renombrar, reordenar y quitar: son suyos.
- **Volver a cargar reemplaza los registros, nunca los renglones.** Pueden
  tener documentos asignados, y borrarlos en octubre es un daño real.
- **Nada se agrega solo.** Un cliente nuevo arranca con el checklist vacío.
  Los renglones salen de cargar la exógena o del botón de la lista sugerida, y
  las dos cosas las decide el contador.
- **Al 210, uno por uno y con aprobación explícita.** Nunca en lote, nunca
  automático, y nunca un valor que todavía requiera decisión.

Cómo se escriben los textos de esa pantalla, que es lo que define el producto:

- **"Sin soporte"** significa falta el papel. Nunca "hay que declararlo".
- **"Diferencia"** significa revíselo. Nunca "está mal" ni "hay un error".
- La columna dice **"Renglón sugerido por la DIAN"**, no "sugerido" a secas.

---

## Clasificar los documentos

Repartir los documentos es el trabajo que más tiempo le quita al contador:
le llegan cuarenta archivos revueltos por WhatsApp y por correo y tiene que
abrir uno por uno. `app/clasificacion.py` le propone dónde va cada uno.

- **Sugiere, nunca asigna.** El documento entra sin asignar, con la propuesta
  al lado. `documentos.renglon_id` es la única verdad sobre dónde está cada
  documento, y ahí solo escribe el contador. Equivocarse al proponer cuesta
  un clic; equivocarse al decidir cuesta un soporte perdido.
- **Toda sugerencia dice de dónde salió** —por la exógena, por el XML, por el
  texto o por el nombre del archivo— y con cuánta certeza. Una sugerencia sin
  origen a la vista es una en la que no se puede confiar.
- **Con certeza baja no se propone nada.** Sin asignar es mejor que mal
  asignado.
- **Nunca se inventa un tercero.** Si la exógena no lo menciona y el nombre no
  dice nada, se queda callado. Callarse es una respuesta correcta y frecuente.
- **Clasificar arranca solo; leer con IA no.** Es la regla de la casa: lo que
  es gratis y pasa en este computador ocurre sin pedir permiso; lo que cuesta
  plata lo pide el contador. Por eso la capa 1 corre al confirmar la carga y
  la capa 2 —y la cola de lectura— esperan a que él las arranque.
- **La capa 2 elige de una lista cerrada, y se valida en código.** Solo los
  renglones que ese cliente ya tiene. Pedirle al modelo que no invente no es
  lo mismo que impedírselo: la respuesta se compara contra la lista y lo que
  no esté se descarta. **«No sé» es una respuesta correcta y esperada**, y no
  se le empuja a contestar. Nunca se le piden cifras: eso lo hace
  `app/extraccion.py`, una sola vez por documento.
- **Un documento puede ir a varios renglones.** Un certificado de ingresos y
  retenciones soporta el ingreso en uno y la retención en otro.
  `documentos.renglon_id` guarda el principal —es donde el resto del programa
  ya sabe buscarlo— y `documento_renglones` guarda todos.
- **Cuando el contador corrige, el programa aprende.** Se guarda qué tercero,
  qué clase de papel y a qué renglón lo mandó él, **por código de renglón del
  210 y nunca por id**: así una corrección hecha en un cliente sirve en todos.
  Las reglas se ven y se borran en Cuenta y ajustes: un programa que aprende
  sin que se pueda ver qué aprendió es un programa en el que no se puede
  confiar. Las reglas no guardan ni el nombre de un cliente, ni el de un
  archivo, ni una letra de su contenido.
- **Aceptar varias de un golpe muestra la lista antes de confirmar.** Aceptar
  veinte propuestas a ciegas es justo el error que este programa no debe
  dejar cometer.
- La mitad de los archivos llega con nombre de cámara o de escáner
  (`IMG_20260315.jpg`, `scan0001.pdf`). Por eso el nombre del archivo es la
  fuente más débil: la que trabaja de verdad es el texto cruzado con la
  exógena.
- Hay documentos que no se pueden leer y punto: las fotos, los PDF que son una
  foto escaneada y los que traen contraseña. De esos no sale sugerencia, y eso
  se dice sin alarma.

Los documentos con que se mide esto **no están en el repositorio**: se arman
con código en `pruebas/documentos_de_ejemplo.py`. Ningún documento tributario
entra a un repositorio público, ni siquiera uno inventado.

---

## Reglas innegociables

### Línea legal

El prototipo **jamás**:
- Calcula el impuesto a cargo ni el saldo a favor
- Dice qué es deducible y qué no
- Sugiere cómo declarar
- Afirma que un cliente está o no obligado a declarar

El prototipo **sí**: dice qué llegó y qué falta, muestra lo que dice cada documento marcándolo
como lectura automática, organiza y exporta.

- **Todo dato extraído por IA se muestra marcado como "lectura automática — verificar"**,
  junto a un enlace para abrir el documento original.
- **El checklist es editable por el contador.** Él decide qué necesita cada cliente.
- **Borrar documentos pide confirmación que diga cuántos y de qué cliente**, y el
  archivo va a `datos/papelera/`, no al vacío. Borrar los soportes de un cliente
  en plena temporada es un daño real.
- **Todo cambio queda en la bitácora** (`app/bitacora.py`): subir, borrar, marcar
  un renglón, generar el formulario. Es lo que contesta cuando algo no cuadra.
- Las fechas de vencimiento se muestran como referencia verificable y son editables.
  No se inventan fechas: la tabla sale del calendario oficial.

### Privacidad

Los documentos son información tributaria confidencial de terceros que no dieron
consentimiento al desarrollador.

- Los archivos **nunca salen del computador**, salvo la página específica que se manda a la
  API para lectura.
- **Modo sin IA** (`IA_PROVEEDOR=ninguno` en `.env`, el de fábrica): nada sale del
  equipo. Debe funcionar completo. Con `ollama` tampoco sale nada: el modelo corre aquí.
- Con la IA encendida sale: nombre del cliente, TEXTO de sus documentos, checklist y
  conversación. Los archivos nunca se mandan: de un PDF se manda el texto extraído aquí.
- **La llave nunca aparece entera**: ni en pantalla, ni en los logs, ni en la base de
  datos, ni en ninguna respuesta de la API. Solo vive en el `.env`, y en pantalla se
  muestra un pedacito (`pista_llave`).
- La bitácora SÍ guarda nombres de archivo, y por eso vive en `datos/base.db`, no en
  los logs. Los logs siguen sin llevar ni un nombre de cliente.
- **No registrar contenido de documentos en logs.** Ni nombres de clientes, ni cifras, ni texto
  extraído. Solo eventos y errores técnicos.
- `datos/` y `.env` nunca se suben a git.
- En las primeras pruebas se usan documentos ficticios o del propio contador, no de clientes reales.

**Si una decisión técnica compromete alguna de estas reglas, decirlo antes de implementarla.**

---

## Cómo trabajar

- **Primero el flujo sin IA completo** (clientes → subir → checklist manual → exportar).
  Que eso funcione de punta a punta. Después la clasificación automática.
- **No agregar funciones que no estén en la sección 8 del brief**, por buenas que parezcan.
  Fuera de alcance en la versión 1: otros impuestos, múltiples usuarios,
  nube, login, pagos, recordatorios automáticos.
  (El chat con IA —Rentai— entró al alcance por decisión del dueño del proyecto
  en agosto de 2026. El brief original lo tenía afuera.)
- **Las fechas de vencimiento no se calculan: se buscan.** La tabla está en
  `app/vencimientos.py` y **viene vacía a propósito**. Sin tabla, la fecha se
  escribe a mano, como siempre. Nunca rellenar esa tabla de memoria: las fechas
  salen del calendario tributario oficial. Se comprueba con
  `pruebas/probar_vencimientos.py`.
- Explicar cada paso en lenguaje claro, sin jerga.
- Reportar los resultados como son: si algo no se probó, decirlo.

---

## Pruebas

    .venv/bin/python pruebas/probar_api.py           # el servidor, por HTTP real
    .venv/bin/python pruebas/probar_pantallas.py     # el navegador, con Playwright
    .venv/bin/python pruebas/revisar_windows.py      # el entorno
    .venv/bin/python pruebas/probar_vencimientos.py  # la tabla de fechas
    .venv/bin/python pruebas/probar_extraccion.py    # leer una vez, y la fila
    .venv/bin/python pruebas/probar_respaldo.py      # llevarse todo y devolverlo
    .venv/bin/python pruebas/probar_demostracion.py  # el modo demostración
    .venv/bin/python pruebas/probar_exogena.py       # el lector de la exógena
    .venv/bin/python pruebas/probar_clasificacion.py # clasificar y aprender

Y para dejar un cliente cargado con todo y probarlo a mano:

    .venv/bin/python pruebas/cargar_para_probar.py

Le arma a un cliente una exógena inventada y un montón de documentos —unos
bien nombrados, otros con nombre de cámara, una foto, un escaneado sin texto
y un PDF con contraseña— y después imprime un paso a paso. Ningún dato es de
nadie. ESCRIBE en la base de este computador.

`probar_pantallas.py` abre Chromium de verdad y falla si el JavaScript revienta.
Hace falta porque un error de JavaScript no se ve desde el servidor: la página
carga con código 200 y el botón simplemente no hace nada.
