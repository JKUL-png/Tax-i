/* ==========================================================
   Exportar: el mensaje para el cliente y el resumen imprimible.

   El mensaje se muestra en un campo editable a propósito: es un
   borrador, no algo que el programa manda solo. El contador lo lee,
   lo ajusta a su manera de hablar, y él decide cuándo mandarlo.
   ========================================================== */

const campoMensaje = document.getElementById("mensaje");
const botonCopiar = document.getElementById("boton-copiar");
const botonRehacer = document.getElementById("boton-rehacer");
const enlaceImprimir = document.getElementById("enlace-imprimir");
const enlaceTxt = document.getElementById("enlace-txt");


/* Se vuelve true en cuanto el contador escribe algo en el mensaje.
   A partir de ahí el programa deja de reescribírselo. */
let mensajeEditado = false;

async function cargarMensaje() {
  try {
    const respuesta = await fetch("/api/clientes/" + idCliente + "/mensaje");
    if (!respuesta.ok) throw new Error();
    const datos = await respuesta.json();
    campoMensaje.value = datos.texto;
    mensajeEditado = false;
  } catch (e) {
    campoMensaje.value = "No se pudo armar el mensaje.";
  }
}

/* Se llama cada vez que cambia el checklist.

   Si el mensaje sigue siendo el borrador automático, se rehace para que
   no quede diciendo que falta algo que ya llegó. Si el contador ya lo
   escribió a su manera, no se le toca: se le avisa y él decide. */
function refrescarMensaje() {
  if (!campoMensaje) return;
  if (!mensajeEditado) {
    cargarMensaje();
    return;
  }
  mostrarAvisoChecklist(
    "El checklist cambió. El mensaje de abajo lo escribió usted, así que no"
    + " se tocó: si quiere el borrador nuevo, use \"Volver al borrador\".",
    "exito"
  );
}

async function copiarMensaje() {
  const texto = campoMensaje.value;

  try {
    // La forma moderna. Funciona en localhost, que el navegador
    // considera un sitio seguro.
    await navigator.clipboard.writeText(texto);
  } catch (e) {
    // Si el navegador no la deja, se hace a la antigua: se selecciona
    // el texto del campo y se copia.
    campoMensaje.select();
    try {
      document.execCommand("copy");
    } catch (otro) {
      mostrarAviso(
        "No se pudo copiar solo. Seleccione el texto y use Control+C.",
        "error"
      );
      return;
    }
  }

  // Confirmación en el mismo botón: el contador ve que sí pasó algo.
  const original = botonCopiar.textContent;
  botonCopiar.textContent = "¡Copiado!";
  setTimeout(function () { botonCopiar.textContent = original; }, 2000);
}

campoMensaje.addEventListener("input", function () {
  mensajeEditado = true;
});

botonCopiar.addEventListener("click", copiarMensaje);

botonRehacer.addEventListener("click", function () {
  const seguro = confirm(
    "¿Volver al borrador?\n\nSe pierden los cambios que le hizo al mensaje."
  );
  if (seguro) cargarMensaje();
});

if (idCliente) {
  enlaceImprimir.href = "/resumen?id=" + idCliente;
  enlaceTxt.href = "/api/clientes/" + idCliente + "/resumen.txt";
  cargarMensaje();
}
