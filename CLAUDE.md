# Convenciones del proyecto — Asistente de organización documental para renta

El brief completo está en `PROYECTO-ASISTENTE-RENTA.md`. Este archivo son las reglas de trabajo.
Ante cualquier duda de alcance, manda el brief.

**Qué es:** un archivador local que recibe documentos desordenados (PDF, fotos, XML, ZIP),
los identifica, dice cuáles faltan por cliente y genera un resumen. **No hace impuestos.**

---

## Stack

- **Backend:** Python 3.11+ con FastAPI
- **Base de datos:** SQLite (archivo local)
- **Frontend:** HTML + CSS + JavaScript plano. **Sin framework, sin build, sin npm.**
- **IA:** API de Groq (capa gratis), solo para documentos no estructurados.
  Se eligió sobre Gemini porque la capa gratis de Gemini usa lo que uno le manda
  para entrenar y revisores humanos pueden verlo. Groq no entrena ni retiene.
- **Corre en:** `http://localhost:8000`

Antes de agregar una dependencia nueva, preguntar. Cada librería es una cosa más que puede
fallar al instalar en el computador del contador.

---

## Estructura de carpetas

```
asistente-renta/
├── app/
│   ├── main.py           # servidor FastAPI
│   ├── db.py             # SQLite
│   ├── documentos.py     # clasificación y extracción
│   ├── checklist.py      # qué falta por cliente
│   ├── exportar.py       # resumen
│   ├── plantilla_210.py  # mapa de la plantilla de Excel
│   ├── escribir_210.py   # escritura quirúrgica sobre el .xlsx
│   ├── recalcular.py     # totales con LibreOffice
│   ├── formulario.py     # el Formulario 210 de cada cliente
│   └── rentai.py         # la asistente que conversa y propone
├── static/               # HTML, CSS, JS
├── plantillas/           # las plantillas de Excel del contador (NUNCA a git)
├── pruebas/              # programas que comprueban que todo siga funcionando
├── datos/                # NUNCA se sube a git
│   ├── archivos/         # documentos subidos, por cliente
│   ├── formularios/      # el Excel generado de cada cliente
│   └── base.db
├── .env                  # GROQ_API_KEY — NUNCA se sube a git
├── requirements.txt
├── iniciar.sh            # Mac
└── iniciar.bat           # Windows
```

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
- Las fechas de vencimiento se muestran como referencia verificable y son editables.
  No se inventan fechas: la tabla sale del calendario oficial.

### Privacidad

Los documentos son información tributaria confidencial de terceros que no dieron
consentimiento al desarrollador.

- Los archivos **nunca salen del computador**, salvo la página específica que se manda a la
  API para lectura.
- **Modo sin IA** (`SIN_IA=true` en `.env`): nada sale del equipo. Debe funcionar completo.
- Con la IA encendida sale: nombre del cliente, TEXTO de sus documentos, checklist y
  conversación. Los archivos nunca se mandan: de un PDF se manda el texto extraído aquí.
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
- Explicar cada paso en lenguaje claro, sin jerga.
- Reportar los resultados como son: si algo no se probó, decirlo.
