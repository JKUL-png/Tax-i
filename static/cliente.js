/* ==========================================================
   Pantalla de un cliente: subir y ver sus documentos.

   El id del cliente viene en la dirección: /cliente?id=3

   JavaScript plano, sin librerías.
   ========================================================== */

const idCliente = new URLSearchParams(window.location.search).get("id");

const tituloNombre = document.getElementById("nombre-cliente");
const lineaDatos = document.getElementById("datos-cliente");
const zonaArrastre = document.getElementById("zona-arrastre");
const campoArchivos = document.getElementById("campo-archivos");
const campoCarpeta = document.getElementById("campo-carpeta");
const botonArchivos = document.getElementById("boton-archivos");
const botonCarpeta = document.getElementById("boton-carpeta");
const contenedorLista = document.getElementById("lista-documentos");
const conteo = document.getElementById("conteo");
const progreso = document.getElementById("progreso");
const progresoTexto = document.getElementById("progreso-texto");
const informe = document.getElementById("informe");
const aviso = document.getElementById("aviso");

/* De a cuántos archivos se manda cada tanda. Se parte en tandas para que
   subir 200 fotos no sea una sola petición gigante que se pueda caer. */
const ARCHIVOS_POR_TANDA = 20;
const PESO_POR_TANDA = 40 * 1024 * 1024;   // 40 MB


/* ----------------------------------------------------------
   Avisos
   ---------------------------------------------------------- */

let temporizadorAviso = null;

function mostrarAviso(texto, tipo) {
  aviso.textContent = texto;
  aviso.className = "aviso aviso-" + tipo;
  clearTimeout(temporizadorAviso);
  if (tipo === "exito") {
    temporizadorAviso = setTimeout(ocultarAviso, 4000);
  }
}

function ocultarAviso() {
  aviso.className = "aviso oculto";
  aviso.textContent = "";
}


/* ----------------------------------------------------------
   Formatos
   ---------------------------------------------------------- */

/* 1536000 -> "1,5 MB" */
function pesoEnPalabras(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1).replace(".", ",") + " MB";
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


/* ----------------------------------------------------------
   Dibujar
   ---------------------------------------------------------- */

/* Los renglones del checklist del cliente. Se guardan aquí porque la
   lista de documentos los necesita para armar el selector de asignación. */
let renglonesDelCliente = [];

function dibujarDocumentos(documentos) {
  contenedorLista.innerHTML = "";
  conteo.textContent = documentos.length > 0 ? "(" + documentos.length + ")" : "";

  if (documentos.length === 0) {
    const vacio = document.createElement("div");
    vacio.className = "vacio";
    vacio.textContent =
      "Todavía no hay documentos de este cliente. Suba los primeros arriba.";
    contenedorLista.appendChild(vacio);
    return;
  }

  documentos.forEach(function (documento) {
    contenedorLista.appendChild(dibujarDocumento(documento));
  });
}

function dibujarDocumento(documento) {
  const tarjeta = document.createElement("article");
  tarjeta.className = "documento";

  /* --- Etiqueta del tipo (PDF, Foto, XML) --- */
  const tipo = document.createElement("span");
  tipo.className = "documento-tipo";
  tipo.textContent = documento.tipo;

  /* --- Nombre y detalles --- */
  const datos = document.createElement("div");
  datos.className = "documento-datos";

  const nombre = document.createElement("p");
  nombre.className = "documento-nombre";
  // textContent y no innerHTML: si el archivo se llama "<script>.pdf",
  // se muestra como texto y no se ejecuta nada.
  nombre.textContent = documento.nombre_original;

  const detalle = document.createElement("p");
  detalle.className = "documento-detalle";
  let texto = pesoEnPalabras(documento.tamano) + " · " +
              fechaHoraEnPalabras(documento.subido_en);
  if (documento.venia_en_zip) {
    texto += " · venía en " + documento.venia_en_zip;
  }
  detalle.textContent = texto;

  datos.appendChild(nombre);
  datos.appendChild(detalle);

  /* --- A qué renglón del checklist pertenece --- */
  const asignacion = document.createElement("div");
  asignacion.className = "documento-asignacion";

  const selector = document.createElement("select");
  selector.className = "selector-renglon";
  selector.setAttribute("aria-label", "Asignar a un renglón del checklist");

  const vacia = document.createElement("option");
  vacia.value = "";
  vacia.textContent = "— sin asignar —";
  selector.appendChild(vacia);

  renglonesDelCliente.forEach(function (renglon) {
    const opcion = document.createElement("option");
    opcion.value = renglon.id;
    opcion.textContent = renglon.titulo;
    selector.appendChild(opcion);
  });

  selector.value = documento.renglon_id || "";
  selector.addEventListener("change", function () {
    asignarDocumento(documento.id, selector.value || null);
  });

  asignacion.appendChild(selector);

  // Si el programa cree saber a qué renglón va, lo propone. La sugerencia
  // sale del nombre del archivo, con código: no la hizo ninguna IA.
  if (!documento.renglon_id && documento.sugerencia) {
    const sugerido = renglonesDelCliente.find(function (r) {
      return r.id === documento.sugerencia;
    });
    if (sugerido) {
      const propuesta = document.createElement("button");
      propuesta.type = "button";
      propuesta.className = "sugerencia";
      propuesta.textContent = "¿Es \"" + sugerido.titulo + "\"?";
      propuesta.title = "Sugerencia por el nombre del archivo. Confirme usted.";
      propuesta.addEventListener("click", function () {
        asignarDocumento(documento.id, sugerido.id);
      });
      asignacion.appendChild(propuesta);
    }
  }

  /* --- Acciones --- */
  const acciones = document.createElement("div");
  acciones.className = "documento-acciones";

  const botonVer = document.createElement("button");
  botonVer.type = "button";
  botonVer.className = "boton-texto";
  botonVer.textContent = "Ver";
  botonVer.addEventListener("click", function () {
    abrirVisor(documento);
  });

  const botonEliminar = document.createElement("button");
  botonEliminar.type = "button";
  botonEliminar.className = "boton-texto boton-texto-peligro";
  botonEliminar.textContent = "Eliminar";
  botonEliminar.addEventListener("click", function () {
    eliminarDocumento(documento);
  });

  acciones.appendChild(botonVer);
  acciones.appendChild(botonEliminar);

  const arriba = document.createElement("div");
  arriba.className = "documento-arriba";
  arriba.appendChild(tipo);
  arriba.appendChild(datos);
  arriba.appendChild(acciones);

  tarjeta.appendChild(arriba);
  tarjeta.appendChild(asignacion);
  return tarjeta;
}

/* Muestra el resumen de lo que se subió y lo que quedó por fuera. */
function mostrarInforme(guardados, ignorados) {
  informe.innerHTML = "";

  if (guardados === 0 && ignorados.length === 0) {
    informe.className = "informe oculto";
    return;
  }

  const resumen = document.createElement("p");
  resumen.className = "informe-resumen";
  if (guardados === 1) {
    resumen.textContent = "Se guardó 1 documento.";
  } else {
    resumen.textContent = "Se guardaron " + guardados + " documentos.";
  }
  informe.appendChild(resumen);

  if (ignorados.length > 0) {
    const titulo = document.createElement("p");
    titulo.className = "informe-titulo";
    titulo.textContent = ignorados.length === 1
      ? "1 archivo quedó por fuera:"
      : ignorados.length + " archivos quedaron por fuera:";
    informe.appendChild(titulo);

    const lista = document.createElement("ul");
    lista.className = "informe-lista";
    ignorados.forEach(function (motivo) {
      const renglon = document.createElement("li");
      renglon.textContent = motivo;
      lista.appendChild(renglon);
    });
    informe.appendChild(lista);
  }

  informe.className = "informe";
}


/* ----------------------------------------------------------
   Arrastrar y soltar
   ---------------------------------------------------------- */

/* Recorre una entrada del arrastre. Si es carpeta, entra y saca todo
   lo que hay adentro, incluidas las subcarpetas. */
function recorrerEntrada(entrada, acumulador) {
  return new Promise(function (terminar) {
    if (entrada.isFile) {
      entrada.file(
        function (archivo) { acumulador.push(archivo); terminar(); },
        function () { terminar(); }
      );
      return;
    }

    if (entrada.isDirectory) {
      const lector = entrada.createReader();
      // readEntries devuelve máximo 100 de una vez: hay que volver a
      // preguntar hasta que conteste con una lista vacía.
      const leerTanda = function () {
        lector.readEntries(
          function (entradas) {
            if (entradas.length === 0) { terminar(); return; }
            const pendientes = entradas.map(function (hija) {
              return recorrerEntrada(hija, acumulador);
            });
            Promise.all(pendientes).then(leerTanda);
          },
          function () { terminar(); }
        );
      };
      leerTanda();
      return;
    }

    terminar();
  });
}

/* Saca la lista de archivos de lo que se soltó en la zona. */
async function archivosDelArrastre(transferencia) {
  const entradas = [];

  // Ojo: webkitGetAsEntry hay que llamarlo de una, antes de cualquier
  // espera, porque el navegador vacía la lista apenas termina el evento.
  if (transferencia.items) {
    for (let i = 0; i < transferencia.items.length; i++) {
      const item = transferencia.items[i];
      if (item.kind !== "file") continue;
      const entrada = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
      if (entrada) entradas.push(entrada);
    }
  }

  // Navegador que no soporta carpetas: al menos los archivos sueltos.
  if (entradas.length === 0) {
    return Array.from(transferencia.files || []);
  }

  const acumulador = [];
  for (const entrada of entradas) {
    await recorrerEntrada(entrada, acumulador);
  }
  return acumulador;
}

zonaArrastre.addEventListener("dragover", function (evento) {
  evento.preventDefault();
  zonaArrastre.classList.add("zona-activa");
});

zonaArrastre.addEventListener("dragleave", function (evento) {
  // Solo se apaga cuando el puntero sale de verdad de la zona, no cuando
  // pasa por encima de un hijo.
  if (!zonaArrastre.contains(evento.relatedTarget)) {
    zonaArrastre.classList.remove("zona-activa");
  }
});

zonaArrastre.addEventListener("drop", async function (evento) {
  evento.preventDefault();
  zonaArrastre.classList.remove("zona-activa");
  const archivos = await archivosDelArrastre(evento.dataTransfer);
  subirArchivos(archivos);
});

// Si se sueltan archivos fuera de la zona, el navegador los abriría en
// una pestaña y se perdería la página. Esto lo evita.
window.addEventListener("dragover", function (e) { e.preventDefault(); });
window.addEventListener("drop", function (e) { e.preventDefault(); });

botonArchivos.addEventListener("click", function () { campoArchivos.click(); });
botonCarpeta.addEventListener("click", function () { campoCarpeta.click(); });

campoArchivos.addEventListener("change", function () {
  subirArchivos(Array.from(campoArchivos.files));
  campoArchivos.value = "";   // permite volver a elegir el mismo archivo
});

campoCarpeta.addEventListener("change", function () {
  subirArchivos(Array.from(campoCarpeta.files));
  campoCarpeta.value = "";
});


/* ----------------------------------------------------------
   Conversación con el servidor
   ---------------------------------------------------------- */

async function textoDelError(respuesta) {
  try {
    const cuerpo = await respuesta.json();
    if (typeof cuerpo.detail === "string") return cuerpo.detail;
    if (Array.isArray(cuerpo.detail) && cuerpo.detail.length > 0) {
      return cuerpo.detail[0].msg.replace("Value error, ", "");
    }
  } catch (e) {
    // Si no era JSON se usa el mensaje de abajo.
  }
  return "No se pudo completar la operación.";
}

async function cargarCliente() {
  try {
    const respuesta = await fetch("/api/clientes/" + idCliente);
    if (!respuesta.ok) throw new Error();
    const cliente = await respuesta.json();
    tituloNombre.textContent = cliente.nombre;
    document.title = cliente.nombre + " · Tax-i";

    let texto = "Cédula termina en " + cliente.dos_digitos;
    if (cliente.fecha_vencimiento) {
      texto += " · vence el " + cliente.fecha_vencimiento;
    } else {
      texto += " · sin fecha de vencimiento";
    }
    lineaDatos.textContent = texto;
  } catch (e) {
    tituloNombre.textContent = "No se encontró el cliente";
    lineaDatos.textContent = "";
  }
}

async function cargarDocumentos() {
  try {
    const respuesta = await fetch("/api/clientes/" + idCliente + "/documentos");
    if (!respuesta.ok) throw new Error();
    dibujarDocumentos(await respuesta.json());
  } catch (e) {
    contenedorLista.innerHTML =
      '<div class="vacio">No se pudieron cargar los documentos.</div>';
  }
}

/* Parte la lista en tandas para no mandar todo en una sola petición. */
function armarTandas(archivos) {
  const tandas = [];
  let tanda = [];
  let peso = 0;

  archivos.forEach(function (archivo) {
    if (tanda.length > 0 &&
        (tanda.length >= ARCHIVOS_POR_TANDA || peso + archivo.size > PESO_POR_TANDA)) {
      tandas.push(tanda);
      tanda = [];
      peso = 0;
    }
    tanda.push(archivo);
    peso += archivo.size;
  });

  if (tanda.length > 0) tandas.push(tanda);
  return tandas;
}

let subiendo = false;

async function subirArchivos(archivos) {
  if (subiendo) {
    mostrarAviso("Espere a que termine la subida anterior.", "error");
    return;
  }
  if (!archivos || archivos.length === 0) return;

  ocultarAviso();
  informe.className = "informe oculto";
  subiendo = true;
  progreso.className = "progreso";

  const tandas = armarTandas(archivos);
  let guardados = 0;
  let ignorados = [];
  let enviados = 0;

  try {
    for (const tanda of tandas) {
      progresoTexto.textContent =
        "Subiendo " + (enviados + 1) + " de " + archivos.length + "…";

      const formulario = new FormData();
      tanda.forEach(function (archivo) {
        // El tercer argumento es el nombre: si el archivo vino de una
        // carpeta, se manda la ruta relativa para no perder el contexto.
        formulario.append("archivos", archivo,
                          archivo.webkitRelativePath || archivo.name);
      });

      const respuesta = await fetch("/api/clientes/" + idCliente + "/documentos", {
        method: "POST",
        body: formulario
      });

      if (!respuesta.ok) {
        mostrarAviso(await textoDelError(respuesta), "error");
        break;
      }

      const resultado = await respuesta.json();
      guardados += resultado.guardados.length;
      ignorados = ignorados.concat(resultado.ignorados);
      enviados += tanda.length;
    }
  } catch (e) {
    mostrarAviso("Se perdió la conexión con el servidor durante la subida.", "error");
  }

  subiendo = false;
  progreso.className = "progreso oculto";
  mostrarInforme(guardados, ignorados);
  cargarDocumentos();
}

async function eliminarDocumento(documento) {
  const seguro = confirm(
    "¿Eliminar \"" + documento.nombre_original + "\"?\n\n" +
    "Se borra el archivo del computador y no se puede deshacer."
  );
  if (!seguro) return;

  const respuesta = await fetch("/api/documentos/" + documento.id, {
    method: "DELETE"
  });

  if (!respuesta.ok) {
    mostrarAviso(await textoDelError(respuesta), "error");
    return;
  }
  cargarDocumentos();
}


/* ----------------------------------------------------------
   Arranque
   ---------------------------------------------------------- */

if (!idCliente) {
  tituloNombre.textContent = "Falta el cliente";
  lineaDatos.textContent = "Vuelva a la lista y entre a un cliente.";
} else {
  cargarCliente();
  // Los documentos se cargan más abajo, después del checklist: cada
  // documento necesita la lista de renglones para armar su selector.
}


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

let temporizadorChecklist = null;

function mostrarAvisoChecklist(texto, tipo) {
  avisoChecklist.textContent = texto;
  avisoChecklist.className = "aviso aviso-" + tipo;
  clearTimeout(temporizadorChecklist);
  if (tipo === "exito") {
    temporizadorChecklist = setTimeout(function () {
      avisoChecklist.className = "aviso oculto";
      avisoChecklist.textContent = "";
    }, 4000);
  }
}


/* ----------------------------------------------------------
   Dibujar
   ---------------------------------------------------------- */

function dibujarChecklist(renglones) {
  contenedorChecklist.innerHTML = "";

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
  refrescarMensaje();
}

async function quitarRenglon(renglon) {
  let advertencia = "¿Quitar \"" + renglon.titulo +
                   "\" del checklist de este cliente?";
  if (renglon.documentos > 0) {
    advertencia += "\n\nLos " + renglon.documentos +
      " archivo(s) asignados NO se borran: quedan sin asignar.";
  }
  const seguro = confirm(advertencia);
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
  refrescarMensaje();
}

formularioRenglon.addEventListener("submit", agregarRenglon);

if (idCliente) {
  // Primero el checklist y DESPUÉS los documentos: el selector de cada
  // documento se arma con los renglones, así que tienen que existir ya.
  cargarChecklist().then(cargarDocumentos);
}


/* ==========================================================
   Exportar: el mensaje para el cliente y el resumen.

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


/* ==========================================================
   Asignar un documento a un renglón del checklist
   ========================================================== */

async function asignarDocumento(idDocumento, idRenglon) {
  const respuesta = await fetch("/api/documentos/" + idDocumento, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      renglon_id: idRenglon ? Number(idRenglon) : null
    })
  });

  if (!respuesta.ok) {
    mostrarAviso(await textoDelError(respuesta), "error");
    cargarDocumentos();   // se devuelve a como estaba
    return;
  }

  // Asignar un documento marca su renglón como recibido, así que hay
  // que recargar las dos listas y rehacer el mensaje.
  await cargarChecklist();
  cargarDocumentos();
  refrescarMensaje();
}


/* ==========================================================
   Visor de documentos

   Abre el archivo encima de la pantalla, sin salir del cliente.
   Cada tipo se muestra a su manera: los PDF y las fotos los dibuja
   el navegador, el XML y los Excel los prepara el servidor.
   ========================================================== */

const visor = document.getElementById("visor");
const visorTitulo = document.getElementById("visor-titulo");
const visorContenido = document.getElementById("visor-contenido");
const visorAbrir = document.getElementById("visor-abrir");
const visorCerrar = document.getElementById("visor-cerrar");

function cerrarVisor() {
  visor.className = "visor oculto";
  visorContenido.innerHTML = "";   // suelta el PDF o la imagen de la memoria
}

visorCerrar.addEventListener("click", cerrarVisor);

// Clic en el fondo oscuro: cierra. Clic dentro de la caja: no.
visor.addEventListener("click", function (evento) {
  if (evento.target === visor) cerrarVisor();
});

document.addEventListener("keydown", function (evento) {
  if (evento.key === "Escape" && !visor.classList.contains("oculto")) {
    cerrarVisor();
  }
});

/* Dibuja un mensaje simple dentro del visor. */
function mensajeEnVisor(texto) {
  const parrafo = document.createElement("p");
  parrafo.className = "visor-mensaje";
  parrafo.textContent = texto;
  return parrafo;
}

/* Los campos que el código sacó de un XML de factura electrónica. */
function bloqueDeLectura(leido) {
  const caja = document.createElement("div");
  caja.className = "lectura-xml";

  const titulo = document.createElement("p");
  titulo.className = "lectura-titulo";
  titulo.textContent = "Leído del archivo (exacto, sin IA)";
  caja.appendChild(titulo);

  const NOMBRES = {
    numero: "Número", fecha: "Fecha", cufe: "CUFE",
    emisor: "Emisor", nit_emisor: "NIT del emisor",
    receptor: "Receptor", total: "Total", moneda: "Moneda"
  };

  const lista = document.createElement("dl");
  lista.className = "lectura-campos";
  Object.keys(leido).forEach(function (campo) {
    const nombre = document.createElement("dt");
    nombre.textContent = NOMBRES[campo] || campo;
    const valor = document.createElement("dd");
    valor.textContent = leido[campo];
    lista.appendChild(nombre);
    lista.appendChild(valor);
  });
  caja.appendChild(lista);
  return caja;
}

async function abrirVisor(documento) {
  visorTitulo.textContent = documento.nombre_original;
  visorAbrir.href = "/api/documentos/" + documento.id + "/archivo";
  visorContenido.innerHTML = "";
  visorContenido.appendChild(mensajeEnVisor("Cargando…"));
  visor.className = "visor";

  let datos;
  try {
    const respuesta = await fetch("/api/documentos/" + documento.id + "/vista");
    if (!respuesta.ok) throw new Error();
    datos = await respuesta.json();
  } catch (e) {
    visorContenido.innerHTML = "";
    visorContenido.appendChild(
      mensajeEnVisor("No se pudo cargar la vista del documento.")
    );
    return;
  }

  visorContenido.innerHTML = "";

  if (datos.vista === "pdf") {
    // El navegador trae su propio lector de PDF.
    const marco = document.createElement("iframe");
    marco.className = "visor-pdf";
    marco.src = datos.url;
    marco.title = documento.nombre_original;
    visorContenido.appendChild(marco);

  } else if (datos.vista === "imagen") {
    const imagen = document.createElement("img");
    imagen.className = "visor-imagen";
    imagen.src = datos.url;
    imagen.alt = documento.nombre_original;
    visorContenido.appendChild(imagen);

  } else if (datos.vista === "tabla") {
    if (datos.recortado) {
      visorContenido.appendChild(mensajeEnVisor(
        "Mostrando las primeras " + datos.filas.length + " filas de " +
        datos.total_filas + ". Para verlo completo, abra el archivo aparte."
      ));
    }
    const envoltura = document.createElement("div");
    envoltura.className = "tabla-envoltura";
    const tabla = document.createElement("table");
    tabla.className = "tabla-vista";

    datos.filas.forEach(function (fila, numero) {
      const renglon = document.createElement("tr");
      fila.forEach(function (casilla) {
        // La primera fila se dibuja como encabezado.
        const celda = document.createElement(numero === 0 ? "th" : "td");
        celda.textContent = casilla;
        renglon.appendChild(celda);
      });
      tabla.appendChild(renglon);
    });

    envoltura.appendChild(tabla);
    visorContenido.appendChild(envoltura);

  } else if (datos.vista === "texto") {
    if (datos.leido) {
      visorContenido.appendChild(bloqueDeLectura(datos.leido));
    }
    if (datos.recortado) {
      visorContenido.appendChild(mensajeEnVisor(
        "El archivo es largo: se muestra solo el comienzo."
      ));
    }
    const bloque = document.createElement("pre");
    bloque.className = "visor-texto";
    bloque.textContent = datos.texto;
    visorContenido.appendChild(bloque);

  } else {
    visorContenido.appendChild(mensajeEnVisor(
      datos.motivo || "Este archivo no se puede ver aquí."
    ));
    const enlace = document.createElement("a");
    enlace.className = "boton";
    enlace.href = datos.url;
    enlace.target = "_blank";
    enlace.rel = "noopener";
    enlace.textContent = "Abrir el archivo aparte";
    visorContenido.appendChild(enlace);
  }
}


/* ==========================================================
   Aviso de cómo está configurado el programa
   ========================================================== */

async function cargarConfiguracion() {
  const caja = document.getElementById("aviso-modo");
  try {
    const respuesta = await fetch("/api/configuracion");
    if (!respuesta.ok) return;
    const config = await respuesta.json();

    caja.textContent = config.motivo;
    caja.className = config.ia_disponible
      ? "aviso-modo aviso-modo-ia"
      : "aviso-modo";
  } catch (e) {
    // Si no se puede leer, no se muestra nada. No es crítico.
  }
}

cargarConfiguracion();


/* ----------------------------------------------------------
   Recordar qué secciones quedaron abiertas

   La pantalla es larga, así que las secciones se pliegan. Si el contador
   deja abierta la de documentos, la próxima vez que entre a un cliente
   debería encontrarla abierta: no tiene por qué volver a abrirla cada vez.

   Se guarda en el navegador (localStorage), que es de este computador y
   no sale de aquí. Solo se guarda cuál sección está abierta: ningún dato
   de ningún cliente.
   ---------------------------------------------------------- */

function recordarPlegables() {
  const plegables = document.querySelectorAll(".plegable");

  plegables.forEach(function (plegable) {
    const llave = "abierto:" + plegable.id;

    /* Lo guardado manda sobre lo que diga el HTML. */
    let guardado = null;
    try {
      guardado = window.localStorage.getItem(llave);
    } catch (error) {
      /* Hay navegadores que no dejan guardar nada (modo privado). Se
         sigue sin recordar, que no es grave. */
    }
    if (guardado === "si") plegable.open = true;
    if (guardado === "no") plegable.open = false;

    plegable.addEventListener("toggle", function () {
      try {
        window.localStorage.setItem(llave, plegable.open ? "si" : "no");
      } catch (error) { /* igual que arriba */ }
    });
  });
}

recordarPlegables();
