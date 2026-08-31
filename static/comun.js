/* ==========================================================
   Lo que usan todas las pantallas.

   Antes cada archivo tenía su propia copia de esto: mostrarAviso estaba
   escrita cinco veces, y las fechas y los pesos, una vez por pantalla.
   Cuando había que corregir algo, se corregía en un sitio y seguía mal
   en los otros cuatro.

   Este archivo se carga ANTES que los demás en cada página, con su
   propia etiqueta <script>. Sin build, sin npm: las funciones quedan
   disponibles para los archivos que van después.
   ========================================================== */


/* ----------------------------------------------------------
   Avisos
   ---------------------------------------------------------- */

/* Cada caja de aviso lleva su propio reloj, para que un aviso que se
   apaga en una sección no apague el de otra. */
const relojesDeAviso = new WeakMap();

/* Muestra un aviso en una caja. `tipo` es "exito", "error" o "info".
   Los de éxito se van solos; los de error se quedan hasta que el
   contador haga algo al respecto. */
function avisarEn(caja, texto, tipo) {
  if (!caja) return;
  caja.textContent = texto;
  caja.className = "aviso aviso-" + tipo;
  clearTimeout(relojesDeAviso.get(caja));
  if (tipo === "exito") {
    relojesDeAviso.set(caja, setTimeout(function () {
      ocultarAvisoEn(caja);
    }, 4000));
  }
}

function ocultarAvisoEn(caja) {
  if (!caja) return;
  clearTimeout(relojesDeAviso.get(caja));
  caja.className = "aviso oculto";
  caja.textContent = "";
}


/* ----------------------------------------------------------
   Errores del servidor
   ---------------------------------------------------------- */

/* Saca el texto del error que mandó el servidor.

   El servidor contesta siempre igual: {"detail": "una frase en español"}.
   Esas frases están escritas para que las lea el contador, así que se
   muestran tal cual. Si la respuesta no era JSON —porque se cayó la
   conexión a mitad, por ejemplo— se usa el texto de reserva. */
async function textoDelError(respuesta, porDefecto) {
  try {
    const cuerpo = await respuesta.json();
    if (typeof cuerpo.detail === "string") return cuerpo.detail;
  } catch (e) {
    // No era JSON. Se usa el texto de reserva.
  }
  return porDefecto || "No se pudo completar la operación.";
}


/* ----------------------------------------------------------
   Fechas y plazos
   ---------------------------------------------------------- */

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
               "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

/* "2026-10-14" -> "14 de octubre de 2026" */
function fechaEnPalabras(texto) {
  if (!texto) return "";
  const [anio, mes, dia] = texto.split("-").map(Number);
  if (!anio || !mes || !dia) return texto;
  return dia + " de " + MESES[mes - 1] + " de " + anio;
}

/* "2026-08-26T14:03:00" -> "26/08/2026, 2:03 p. m." */
function fechaHoraEnPalabras(texto) {
  const fecha = new Date(texto);
  if (isNaN(fecha)) return texto;
  return fecha.toLocaleString("es-CO", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "numeric", minute: "2-digit"
  });
}

/* Cuántos días faltan. Compara solo fechas, sin horas. */
function diasQueFaltan(texto) {
  const [anio, mes, dia] = texto.split("-").map(Number);
  const vencimiento = new Date(anio, mes - 1, dia);
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  return Math.round((vencimiento - hoy) / 86400000);
}

/* Devuelve el texto y el color de la etiqueta de plazo.

   Es la misma en la lista de clientes y en el perfil de cada uno: el
   contador ve la misma frase y el mismo color en los dos sitios, que es
   justamente lo que hace que se pueda confiar en el color. */
function etiquetaDePlazo(fecha) {
  if (!fecha) {
    return { texto: "Sin fecha", clase: "etiqueta-neutra", dias: null };
  }

  const dias = diasQueFaltan(fecha);

  if (dias < 0) {
    const pasados = Math.abs(dias);
    return {
      texto: "Venció hace " + pasados + (pasados === 1 ? " día" : " días"),
      clase: "etiqueta-error",
      dias: dias
    };
  }
  if (dias === 0) {
    return { texto: "Vence hoy", clase: "etiqueta-error", dias: 0 };
  }
  if (dias <= 15) {
    return {
      texto: "Faltan " + dias + (dias === 1 ? " día" : " días"),
      clase: "etiqueta-alerta",
      dias: dias
    };
  }
  return {
    texto: "Faltan " + dias + " días",
    clase: "etiqueta-exito",
    dias: dias
  };
}


/* ----------------------------------------------------------
   Tamaños
   ---------------------------------------------------------- */

/* 1536000 -> "1,5 MB" */
function pesoEnPalabras(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1).replace(".", ",") + " MB";
}


/* ----------------------------------------------------------
   Contar cosas en español
   ---------------------------------------------------------- */

/* 1 -> "1 documento",  3 -> "3 documentos".
   Sirve para no escribir el (n === 1 ? "" : "s") en veinte sitios. */
function contar(cantidad, singular, plural) {
  return cantidad + " " + (cantidad === 1 ? singular : plural);
}
