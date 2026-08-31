# Asistente de organización documental para renta — Prototipo local

> **Para el asistente que lea esto:** este documento tiene todo el contexto necesario.
> No hace falta preguntar por antecedentes. Las decisiones marcadas como cerradas no se re-discuten
> salvo que aparezca información técnica nueva.

---

## 1. Qué es esto

Un prototipo **local** (corre en el computador, no en internet) que ayuda a un contador
a organizar los documentos que le mandan sus clientes para la declaración de renta.

**Hace tres cosas:**
1. Recibe archivos desordenados (PDF, fotos, XML, ZIP) y los identifica.
2. Dice qué documentos ya llegaron y **cuáles faltan** por cliente.
3. Genera un resumen imprimible/exportable por cliente.

**No hace impuestos.** No calcula, no deduce, no aconseja. Organiza y reporta.

---

## 2. Contexto real

- **Usuario:** un contador público en Colombia. Trabaja con
  **personas naturales** (declaración de renta, Formulario 210).
- **Temporada activa:** los vencimientos de renta AG 2025 corren del **12 de agosto al 26 de octubre de 2026**,
  escalonados por los dos últimos dígitos del NIT/cédula. Hay plazos especiales para
  contribuyentes de zonas afectadas por el sismo del 10 de agosto de 2026.
- **El dolor concreto:** cada cliente debe entregar entre 8 y 12 documentos. Llegan por
  WhatsApp, correo, fotos, PDFs, capturas de pantalla — "mezcla de todo". El contador
  pierde horas persiguiendo gente y averiguando qué falta.
- **Objetivo del prototipo:** que el contador lo use durante esta temporada y diga si sirve.
  No es un producto comercial todavía.

### Sobre el desarrollador
- JKUL. Sin formación formal en programación; construye con asistencia de IA.
- **Necesita explicaciones claras y pasos concretos, no jerga.** Es la razón de
  que el código de este repositorio esté comentado como está: en español, y
  explicando el porqué de cada decisión, no solo el qué.

---

## 3. Decisiones cerradas (no re-discutir)

| Decisión | Razón |
|---|---|
| **Aplicación web local**, no software instalable empaquetado | Ya sabe hacer web; funciona igual en Windows y Mac; después se despliega sin reescribir |
| **No se automatiza el portal de la DIAN** | Requeriría credenciales ajenas de un portal del Estado; frágil; y no hace falta |
| **Sin login, sin pagos, sin planes** | Es un prototipo para una persona |
| **Sin cálculo de impuestos ni asesoría** | Línea legal innegociable — ver sección 6 |
| **Los archivos se procesan localmente** | Son datos tributarios confidenciales de terceros |
| **Primero la versión sin IA, después el chat** | Si se arranca por el chat, se quema la semana en prompts |

---

## 4. Arquitectura

### Stack
- **Backend:** Python 3.11+ con FastAPI
- **Base de datos:** SQLite (archivo local, sin instalar nada)
- **Frontend:** HTML + CSS + JavaScript plano, sin framework
- **IA:** API de Anthropic, solo para leer documentos no estructurados
- **Corre en:** `http://localhost:8000`

### Estructura de carpetas propuesta
```
asistente-renta/
├── app/
│   ├── main.py           # servidor FastAPI
│   ├── db.py             # SQLite
│   ├── documentos.py     # clasificación y extracción
│   ├── checklist.py      # qué falta por cliente
│   └── exportar.py       # resumen
├── static/               # HTML, CSS, JS
├── datos/
│   ├── archivos/         # documentos subidos, por cliente
│   └── base.db
├── .env                  # ANTHROPIC_API_KEY
├── requirements.txt
└── iniciar.bat / iniciar.sh
```

---

## 5. Qué usa IA y qué no

**Regla central: el código maneja los datos, la IA maneja lo desordenado.**
Un modelo puede equivocarse sumando. El código no. Nunca se le pide a la IA que calcule.

### NO usa IA (código normal, exacto, gratis)
- Leer XML de factura electrónica (formato UBL 2.1 — ya viene con los campos separados)
- Descomprimir ZIP
- Calcular la fecha de vencimiento a partir de los dos últimos dígitos de la cédula
- Ordenar, renombrar y guardar archivos
- Detectar duplicados (comparar CUFE o hash del archivo)
- Armar el checklist de completitud
- Generar el resumen y el export

### SÍ usa IA
- **Clasificar el documento:** dado un PDF o una foto, decir de qué tipo es
  (certificado de ingresos y retenciones, certificado bancario, certificado de pensión
  voluntaria, medicina prepagada, intereses de vivienda, etc.)
- **Extraer campos visibles:** quién lo emite, a qué periodo corresponde, cifras clave.
  Estos datos se muestran al contador **para que él los verifique**, nunca se usan para calcular nada.
- **Búsqueda en lenguaje natural** (fase 2): "muéstrame los certificados bancarios que faltan"

### Sobre el modelo
- Usar un modelo pequeño y barato para clasificar (es una tarea simple y de alto volumen).
- Usar uno más capaz solo para extracción de documentos difíciles o escaneos malos.
- **Importante:** si el documento es un XML, no se manda a la IA. Se parsea y listo.

---

## 6. Línea legal — innegociable

El prototipo **jamás**:
- Calcula el impuesto a cargo ni el saldo a favor
- Dice qué es deducible y qué no
- Sugiere cómo declarar
- Afirma que un cliente está o no obligado a declarar

El prototipo **sí**:
- Dice qué documentos llegaron y cuáles faltan
- Muestra lo que dice cada documento, marcando que es lectura automática sujeta a verificación
- Organiza y exporta

**Todo dato extraído por IA debe mostrarse marcado como "lectura automática — verificar"
junto a un enlace para abrir el documento original.** El contador es el profesional; el
software es un archivador, no un asesor.

El checklist de documentos debe ser **editable por el contador**. Él decide qué necesita
cada cliente, no el software.

---

## 7. Privacidad — obligatorio

Los documentos son información tributaria confidencial de terceros que no dieron consentimiento
al desarrollador.

1. **Decirle al contador explícitamente** que es un prototipo y qué pasa con los archivos.
2. **Para las primeras pruebas, usar documentos ficticios o del propio contador**, no de clientes reales.
3. Los archivos **nunca salen del computador**, salvo la página específica que se manda a la
   API para lectura.
4. Incluir un **modo sin IA** (`SIN_IA=true` en `.env`) donde nada sale del equipo. Sirve para
   demostrar el flujo sin exponer nada.
5. No registrar contenido de documentos en logs.

---

## 8. Versión 1 — lo que se construye esta semana

**Objetivo: que exista y funcione, no que esté bonito.**

1. **Clientes.** Crear cliente con nombre y dos últimos dígitos de cédula.
   El sistema calcula y muestra la fecha de vencimiento.
2. **Subir archivos.** Arrastrar varios archivos a la vez, o una carpeta completa.
3. **Clasificación.** El sistema identifica cada documento y lo asigna a una casilla del checklist.
   Si no está seguro, lo deja como "sin clasificar" para que el contador lo asigne a mano.
4. **Checklist por cliente.** Lista de documentos esperados, marcados como recibido / faltante.
   El contador puede agregar o quitar renglones.
5. **Exportar.** Dos salidas: el resumen del cliente, y **el mensaje de "esto es lo que me falta"**
   listo para copiar y mandar por WhatsApp.

### Lo que NO va en la versión 1
- Chat con IA
- Calendario de otros impuestos (predial, vehicular, ICA)
- Múltiples usuarios
- Nube, login, pagos
- Recordatorios automáticos

---

## 9. Checklist base sugerido (editable)

Punto de partida para renta de persona natural. **El contador lo ajusta.**

- Certificado de ingresos y retenciones (uno por empleador)
- Certificados bancarios: saldos a 31 de diciembre, intereses, GMF
- Certificado de aportes a pensión voluntaria / AFC
- Certificado de medicina prepagada
- Certificado de intereses de crédito de vivienda
- Certificado de dependientes
- Certificados de inversiones o acciones
- Soportes de bienes inmuebles
- Soportes de vehículos
- Certificados de retención por honorarios
- Otros ingresos y soportes varios

---

## 10. Criterio de éxito

Al terminar la semana, el contador debe poder responder:

1. ¿Le ahorró tiempo real, o fue igual de rápido hacerlo como siempre?
2. ¿La clasificación automática acertó lo suficiente como para confiar en ella?
3. ¿Usaría el mensaje de "esto es lo que falta" con sus clientes?
4. ¿Qué es lo primero que le agregaría?

**Si la respuesta a la 1 es "fue igual", el prototipo falló y eso también es un resultado válido.**
Se descubrió en una semana en vez de en seis meses.

---

## 11. Cómo debe trabajar el asistente

- Construir **primero el flujo sin IA**: subir archivos, checklist manual, exportar. Que eso funcione completo.
- Después agregar clasificación automática.
- Explicar cada paso en lenguaje claro; el desarrollador no tiene formación formal en programación.
- Escribir los comentarios del código en español.
- No agregar funciones que no estén en la sección 8, por buenas que parezcan.
- Si algo de la sección 6 o 7 se ve comprometido por una decisión técnica, decirlo antes de implementarlo.
