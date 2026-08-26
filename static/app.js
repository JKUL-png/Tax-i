/* ==========================================================
   Pantalla de clientes.

   Habla con el servidor por /api/clientes y dibuja la lista.
   JavaScript plano, sin librerías: se abre y se entiende leyéndolo.
   ========================================================== */

const formulario = document.getElementById("formulario-cliente");
const campoNombre = document.getElementById("nombre");
const campoDigitos = document.getElementById("digitos");
const campoFecha = document.getElementById("fecha");
const contenedorLista = document.getElementById("lista-clientes");
const aviso = document.getElementById("aviso");


/* ----------------------------------------------------------
   Avisos arriba del formulario
   ---------------------------------------------------------- */

let temporizadorAviso = null;

function mostrarAviso(texto, tipo) {
  aviso.textContent = texto;
  aviso.className = "aviso aviso-" + tipo;
  clearTimeout(temporizadorAviso);
  // Los mensajes de éxito se van solos; los de error se quedan.
  if (tipo === "exito") {
    temporizadorAviso = setTimeout(ocultarAviso, 4000);
  }
}

function ocultarAviso() {
  aviso.className = "aviso oculto";
  aviso.textContent = "";
}


/* ----------------------------------------------------------
   Fechas
   ---------------------------------------------------------- */

/* Convierte "2026-10-14" en "14 de octubre de 2026". */
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
               "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

function fechaEnPalabras(texto) {
  const [anio, mes, dia] = texto.split("-").map(Number);
  return dia + " de " + MESES[mes - 1] + " de " + anio;
}

/* Cuántos días faltan. Compara solo fechas, sin horas. */
function diasQueFaltan(texto) {
  const [anio, mes, dia] = texto.split("-").map(Number);
  const vencimiento = new Date(anio, mes - 1, dia);
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  return Math.round((vencimiento - hoy) / 86400000);
}

/* Devuelve el texto y el color de la etiqueta de plazo. */
function etiquetaDePlazo(fecha) {
  if (!fecha) {
    return { texto: "Sin fecha", clase: "etiqueta-neutra" };
  }

  const dias = diasQueFaltan(fecha);

  if (dias < 0) {
    const pasados = Math.abs(dias);
    return {
      texto: "Venció hace " + pasados + (pasados === 1 ? " día" : " días"),
      clase: "etiqueta-error"
    };
  }
  if (dias === 0) {
    return { texto: "Vence hoy", clase: "etiqueta-error" };
  }
  if (dias <= 15) {
    return {
      texto: "Faltan " + dias + (dias === 1 ? " día" : " días"),
      clase: "etiqueta-alerta"
    };
  }
  return { texto: "Faltan " + dias + " días", clase: "etiqueta-exito" };
}


/* ----------------------------------------------------------
   Dibujar la lista
   ---------------------------------------------------------- */

function dibujarLista(clientes) {
  contenedorLista.innerHTML = "";

  if (clientes.length === 0) {
    const vacio = document.createElement("div");
    vacio.className = "vacio";
    vacio.textContent = "Todavía no hay clientes. Agregue el primero arriba.";
    contenedorLista.appendChild(vacio);
    return;
  }

  clientes.forEach(function (cliente) {
    contenedorLista.appendChild(dibujarCliente(cliente));
  });
}

function dibujarCliente(cliente) {
  const tarjeta = document.createElement("article");
  tarjeta.className = "cliente";

  /* --- Nombre y cédula --- */
  const datos = document.createElement("div");
  datos.className = "cliente-datos";

  const nombre = document.createElement("h3");
  nombre.className = "cliente-nombre";
  nombre.textContent = cliente.nombre;

  const cedula = document.createElement("p");
  cedula.className = "cliente-cedula";
  cedula.textContent = "Cédula termina en " + cliente.dos_digitos;

  datos.appendChild(nombre);
  datos.appendChild(cedula);

  /* --- Fecha de vencimiento, editable --- */
  const bloqueFecha = document.createElement("div");
  bloqueFecha.className = "cliente-fecha";

  const etiquetaCampo = document.createElement("label");
  etiquetaCampo.textContent = "Fecha de vencimiento";
  etiquetaCampo.setAttribute("for", "fecha-" + cliente.id);

  const entradaFecha = document.createElement("input");
  entradaFecha.type = "date";
  entradaFecha.id = "fecha-" + cliente.id;
  entradaFecha.value = cliente.fecha_vencimiento || "";

  const plazo = etiquetaDePlazo(cliente.fecha_vencimiento);
  const etiqueta = document.createElement("span");
  etiqueta.className = "etiqueta " + plazo.clase;
  etiqueta.textContent = plazo.texto;
  if (cliente.fecha_vencimiento) {
    etiqueta.title = fechaEnPalabras(cliente.fecha_vencimiento);
  }

  // Al cambiar la fecha se guarda sola, sin botón de guardar.
  entradaFecha.addEventListener("change", function () {
    guardarFecha(cliente.id, entradaFecha.value);
  });

  bloqueFecha.appendChild(etiquetaCampo);
  bloqueFecha.appendChild(entradaFecha);
  bloqueFecha.appendChild(etiqueta);

  /* --- Eliminar --- */
  const acciones = document.createElement("div");
  acciones.className = "cliente-acciones";

  const botonEliminar = document.createElement("button");
  botonEliminar.type = "button";
  botonEliminar.className = "boton-texto";
  botonEliminar.textContent = "Eliminar";
  botonEliminar.addEventListener("click", function () {
    eliminarCliente(cliente);
  });

  acciones.appendChild(botonEliminar);

  tarjeta.appendChild(datos);
  tarjeta.appendChild(bloqueFecha);
  tarjeta.appendChild(acciones);
  return tarjeta;
}


/* ----------------------------------------------------------
   Conversación con el servidor
   ---------------------------------------------------------- */

/* Saca el mensaje de error que manda el servidor, en lenguaje entendible. */
async function textoDelError(respuesta) {
  try {
    const cuerpo = await respuesta.json();
    if (typeof cuerpo.detail === "string") {
      return cuerpo.detail;
    }
    // Errores de validación: FastAPI los manda como lista.
    if (Array.isArray(cuerpo.detail) && cuerpo.detail.length > 0) {
      return cuerpo.detail[0].msg.replace("Value error, ", "");
    }
  } catch (e) {
    // Si la respuesta no era JSON, se usa el mensaje genérico de abajo.
  }
  return "No se pudo completar la operación.";
}

async function cargarClientes() {
  try {
    const respuesta = await fetch("/api/clientes");
    if (!respuesta.ok) throw new Error();
    dibujarLista(await respuesta.json());
  } catch (e) {
    contenedorLista.innerHTML =
      '<div class="vacio">No se pudo conectar con el servidor. ' +
      "Verifique que la aplicación esté encendida.</div>";
  }
}

async function agregarCliente(evento) {
  evento.preventDefault();
  ocultarAviso();

  const respuesta = await fetch("/api/clientes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      nombre: campoNombre.value,
      dos_digitos: campoDigitos.value,
      fecha_vencimiento: campoFecha.value || null
    })
  });

  if (!respuesta.ok) {
    mostrarAviso(await textoDelError(respuesta), "error");
    return;
  }

  const cliente = await respuesta.json();
  mostrarAviso("Se agregó a " + cliente.nombre + ".", "exito");

  formulario.reset();
  campoNombre.focus();   // listo para escribir el siguiente
  cargarClientes();
}

async function guardarFecha(idCliente, fecha) {
  const respuesta = await fetch("/api/clientes/" + idCliente, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fecha_vencimiento: fecha || null })
  });

  if (!respuesta.ok) {
    mostrarAviso(await textoDelError(respuesta), "error");
    return;
  }
  cargarClientes();   // se redibuja para actualizar la etiqueta de plazo
}

async function eliminarCliente(cliente) {
  const seguro = confirm(
    "¿Eliminar a " + cliente.nombre + "?\n\nEsta acción no se puede deshacer."
  );
  if (!seguro) return;

  const respuesta = await fetch("/api/clientes/" + cliente.id, {
    method: "DELETE"
  });

  if (!respuesta.ok) {
    mostrarAviso(await textoDelError(respuesta), "error");
    return;
  }
  cargarClientes();
}


/* ----------------------------------------------------------
   Arranque
   ---------------------------------------------------------- */

formulario.addEventListener("submit", agregarCliente);
cargarClientes();
