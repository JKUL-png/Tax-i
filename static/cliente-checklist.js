/* ==========================================================
   Checklist: qué documentos se le pidieron al cliente
   y cuáles ya llegaron.

   La lista es del contador. Él agrega, quita y marca.
   El programa no decide qué documentos son obligatorios.
   ========================================================== */

const contenedorChecklist = document.getElementById("lista-checklist");
const avance = document.getElementById("avance");
const formularioRenglon = document.getElementById("formulario-renglon");
const campoTituloRenglon = document.getElementById("titulo-renglon");
const avisoChecklist = document.getElementById("aviso-checklist");

function mostrarAvisoChecklist(texto, tipo) {
  avisarEn(avisoChecklist, texto, tipo);
}


/* ----------------------------------------------------------
   Dibujar
   ---------------------------------------------------------- */

function dibujarChecklist(renglones) {
  contenedorChecklist.innerHTML = "";

  // Las cifras de la cabecera salen de aquí mismo: así el perfil de
  // arriba nunca queda diciendo algo distinto de lo que muestra la lista.
  pintarAvanceEnPerfil(renglones);

  const recibidos = renglones.filter(function (r) {
    return r.estado === "recibido";
  }).length;
  const faltan = renglones.length - recibidos;

  /* --- El resumen de arriba: lo primero que quiere ver el contador --- */
  if (renglones.length === 0) {
    avance.textContent = "";
  } else if (faltan === 0) {
    avance.textContent = "(completo: " + recibidos + " de " + renglones.length + ")";
  } else {
    avance.textContent =
      "(" + recibidos + " de " + renglones.length + " · falta" +
      (faltan === 1 ? " 1" : "n " + faltan) + ")";
  }

  if (renglones.length === 0) {
    const vacio = document.createElement("div");
    vacio.className = "vacio";

    const texto = document.createElement("p");
    texto.style.marginTop = "0";
    texto.textContent = "Este cliente todavía no tiene checklist.";
    vacio.appendChild(texto);

    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "boton";
    boton.textContent = "Usar la lista sugerida";
    boton.addEventListener("click", agregarListaBase);
    vacio.appendChild(boton);

    contenedorChecklist.appendChild(vacio);
    return;
  }

  renglones.forEach(function (renglon) {
    contenedorChecklist.appendChild(dibujarRenglon(renglon));
  });
}

function dibujarRenglon(renglon) {
  const fila = document.createElement("article");
  fila.className = "renglon";
  if (renglon.estado === "recibido") {
    fila.classList.add("renglon-recibido");
  }

  /* --- La casilla de "ya llegó" --- */
  const marca = document.createElement("input");
  marca.type = "checkbox";
  marca.className = "renglon-marca";
  marca.checked = renglon.estado === "recibido";
  marca.id = "renglon-" + renglon.id;
  marca.addEventListener("change", function () {
    guardarEstado(renglon.id, marca.checked ? "recibido" : "faltante");
  });

  /* --- El nombre del documento, editable ahí mismo --- */
  const titulo = document.createElement("input");
  titulo.type = "text";
  titulo.className = "renglon-titulo";
  titulo.value = renglon.titulo;
  titulo.maxLength = 200;
  titulo.setAttribute("aria-label", "Nombre del documento");
  // Se guarda al salir del campo, sin botón de guardar.
  titulo.addEventListener("change", function () {
    guardarTitulo(renglon, titulo);
  });

  /* --- Cuántos archivos tiene asignados este renglón --- */
  const archivos = document.createElement("span");
  archivos.className = "renglon-archivos";
  if (renglon.documentos > 0) {
    archivos.textContent = renglon.documentos === 1
      ? "1 archivo"
      : renglon.documentos + " archivos";
  }

  /* --- La etiqueta de estado --- */
  const etiqueta = document.createElement("span");
  if (renglon.estado === "recibido") {
    etiqueta.className = "etiqueta etiqueta-exito";
    etiqueta.textContent = "Recibido";
  } else {
    etiqueta.className = "etiqueta etiqueta-alerta";
    etiqueta.textContent = "Falta";
  }

  /* --- Quitar el renglón --- */
  const botonQuitar = document.createElement("button");
  botonQuitar.type = "button";
  botonQuitar.className = "boton-texto boton-texto-peligro";
  botonQuitar.textContent = "Quitar";
  botonQuitar.addEventListener("click", function () {
    quitarRenglon(renglon);
  });

  fila.appendChild(marca);
  fila.appendChild(titulo);
  fila.appendChild(archivos);
  fila.appendChild(etiqueta);
  fila.appendChild(botonQuitar);
  return fila;
}


/* ----------------------------------------------------------
   Conversación con el servidor
   ---------------------------------------------------------- */

async function cargarChecklist() {
  try {
    const respuesta = await fetch("/api/clientes/" + idCliente + "/checklist");
    if (!respuesta.ok) throw new Error();
    renglonesDelCliente = await respuesta.json();
    dibujarChecklist(renglonesDelCliente);
  } catch (e) {
    contenedorChecklist.innerHTML =
      '<div class="vacio">No se pudo cargar el checklist.</div>';
  }
}

async function guardarEstado(idRenglon, estado) {
  const respuesta = await fetch("/api/checklist/" + idRenglon, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ estado: estado })
  });

  if (!respuesta.ok) {
    mostrarAvisoChecklist(await textoDelError(respuesta), "error");
  }
  cargarChecklist();   // se redibuja para actualizar el resumen de arriba
  refrescarMensaje();
}

async function guardarTitulo(renglon, entrada) {
  const nuevo = entrada.value.trim();

  if (nuevo === renglon.titulo) return;   // no cambió nada

  const respuesta = await fetch("/api/checklist/" + renglon.id, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ titulo: nuevo })
  });

  if (!respuesta.ok) {
    mostrarAvisoChecklist(await textoDelError(respuesta), "error");
    entrada.value = renglon.titulo;   // se devuelve a como estaba
    return;
  }
  cargarChecklist();
  cargarDocumentos();
  cargarHistorial();
  refrescarMensaje();
}

async function agregarRenglon(evento) {
  evento.preventDefault();

  const respuesta = await fetch("/api/clientes/" + idCliente + "/checklist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ titulo: campoTituloRenglon.value })
  });

  if (!respuesta.ok) {
    mostrarAvisoChecklist(await textoDelError(respuesta), "error");
    return;
  }

  campoTituloRenglon.value = "";
  campoTituloRenglon.focus();   // listo para escribir el siguiente
  cargarChecklist();
  cargarDocumentos();
  cargarHistorial();
  refrescarMensaje();
}

async function agregarListaBase() {
  const respuesta = await fetch(
    "/api/clientes/" + idCliente + "/checklist/base",
    { method: "POST" }
  );

  if (!respuesta.ok) {
    mostrarAvisoChecklist(await textoDelError(respuesta), "error");
    return;
  }
  cargarChecklist();
  cargarDocumentos();
  cargarHistorial();
  refrescarMensaje();
}

async function quitarRenglon(renglon) {
  const quien = clienteActual ? clienteActual.nombre : "este cliente";
  let nota = "El renglón desaparece del checklist. Queda anotado en el " +
             "historial del cliente.";
  if (renglon.documentos > 0) {
    nota = "Los " + contar(renglon.documentos, "archivo asignado", "archivos asignados") +
           " NO se borran: quedan sin asignar. " + nota;
  }

  const seguro = await preguntar({
    titulo: "Quitar un renglón del checklist",
    frase: "Se va a quitar del checklist:",
    cliente: "Del checklist de " + quien,
    nombres: [renglon.titulo],
    nota: nota
  });
  if (!seguro) return;

  const respuesta = await fetch("/api/checklist/" + renglon.id, {
    method: "DELETE"
  });

  if (!respuesta.ok) {
    mostrarAvisoChecklist(await textoDelError(respuesta), "error");
    return;
  }
  cargarChecklist();
  cargarDocumentos();
  cargarHistorial();
  refrescarMensaje();
}

formularioRenglon.addEventListener("submit", agregarRenglon);
