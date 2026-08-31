/* ==========================================================
   Pantalla de agregar, importar y administrar clientes  (/clientes)

   Tres cosas, en este orden:

     1. Agregar un cliente a mano.
     2. Importar el Excel de la oficina, en dos pasos.
     3. Una tabla apretada para corregir la fecha o eliminar.

   Lo que YA NO está aquí
   ----------------------
   La lista de clientes con buscador, orden y filtros. Vivía en esta
   pantalla y era la forma de navegar el programa; desde que existe el
   riel —que está a la vista en todas las pantallas y además ordena por
   urgencia— era la misma lista dos veces, y la de aquí era la peor:
   había que llegar a esta página para usarla.

   Lo único que el riel no hace es corregir una fecha y eliminar un
   cliente. Eso es lo que quedó, y por eso quedó como tabla y no como
   tarjetas: es administración, no navegación.

   JavaScript plano, sin librerías: se abre y se entiende leyéndolo.
   ========================================================== */

const formulario = document.getElementById("formulario-cliente");
const campoNombre = document.getElementById("nombre");
const campoDigitos = document.getElementById("digitos");
const campoFecha = document.getElementById("fecha");
const cuerpoTabla = document.getElementById("tabla-clientes");
const conteoClientes = document.getElementById("conteo-clientes");
const aviso = document.getElementById("aviso");

/* Todos los clientes tal como llegaron. Los botones de lote de más
   abajo también lo usan para saber a cuántos les van a hacer algo. */
let todosLosClientes = [];


/* ----------------------------------------------------------
   Avisos arriba del formulario
   ---------------------------------------------------------- */

/* El cómo está en comun.js. Aquí solo se dice en cuál caja. */
function mostrarAviso(texto, tipo) { avisarEn(aviso, texto, tipo); }
function ocultarAviso() { ocultarAvisoEn(aviso); }


/* ----------------------------------------------------------
   La tabla de administración

   Ordenada por nombre, que es como se busca a alguien en una tabla de
   administración. La urgencia la ordena el riel; aquí lo que se quiere
   es encontrar a una persona concreta para corregirle algo.
   ---------------------------------------------------------- */

/* Compara nombres como los ordenaría una persona: sin importar tildes
   ni mayúsculas, y con la ñ en su sitio. */
function porNombre(a, b) {
  return a.nombre.localeCompare(b.nombre, "es", { sensitivity: "base" });
}

function celda(texto, clase) {
  const td = document.createElement("td");
  if (clase) td.className = clase;
  if (texto !== undefined) td.textContent = texto;
  return td;
}

function dibujarTabla() {
  cuerpoTabla.textContent = "";

  conteoClientes.textContent = todosLosClientes.length > 0
    ? "(" + todosLosClientes.length + ")"
    : "";

  if (todosLosClientes.length === 0) {
    const fila = document.createElement("tr");
    const hueco = celda(
      "Todavía no hay clientes. Agregue el primero con el formulario de arriba.",
      "vacio");
    hueco.colSpan = 5;
    fila.appendChild(hueco);
    cuerpoTabla.appendChild(fila);
    return;
  }

  todosLosClientes.slice().sort(porNombre).forEach(function (cliente) {
    cuerpoTabla.appendChild(dibujarFila(cliente));
  });
}

function dibujarFila(cliente) {
  const fila = document.createElement("tr");

  /* --- Nombre: enlace de verdad a la pantalla del cliente --- */
  const tdNombre = celda();
  const enlace = document.createElement("a");
  enlace.href = "/cliente?id=" + cliente.id;
  enlace.textContent = cliente.nombre;
  tdNombre.appendChild(enlace);
  fila.appendChild(tdNombre);

  /* --- Los dos dígitos de la cédula --- */
  fila.appendChild(celda(cliente.dos_digitos, "cifra"));

  /* --- Cuánto le falta del checklist --- */
  const total = cliente.checklist_total || 0;
  const recibidos = cliente.checklist_recibidos || 0;
  const tdAvance = celda(
    total === 0 ? "sin lista" : recibidos + " de " + total,
    total === 0 ? "avance-neutro" : "cifra");
  fila.appendChild(tdAvance);

  /* --- La fecha, editable. Se guarda sola al cambiarla --- */
  const tdFecha = celda();
  const entrada = document.createElement("input");
  entrada.type = "date";
  entrada.value = cliente.fecha_vencimiento || "";
  entrada.setAttribute("aria-label", "Fecha de vencimiento de " + cliente.nombre);
  entrada.addEventListener("change", function () {
    guardarFecha(cliente.id, entrada.value);
  });

  const plazo = etiquetaDePlazo(cliente.fecha_vencimiento);
  const etiqueta = document.createElement("span");
  etiqueta.className = "etiqueta " + plazo.clase;
  etiqueta.textContent = plazo.texto;
  if (cliente.fecha_vencimiento) {
    etiqueta.title = fechaEnPalabras(cliente.fecha_vencimiento);
  }

  tdFecha.appendChild(entrada);
  tdFecha.appendChild(etiqueta);
  fila.appendChild(tdFecha);

  /* --- Eliminar --- */
  const tdBorrar = celda();
  const borrar = document.createElement("button");
  borrar.type = "button";
  borrar.className = "boton-texto boton-texto-peligro";
  borrar.textContent = "Eliminar";
  borrar.addEventListener("click", function () { eliminarCliente(cliente); });
  tdBorrar.appendChild(borrar);
  fila.appendChild(tdBorrar);

  return fila;
}


/* ----------------------------------------------------------
   Conversación con el servidor
   ---------------------------------------------------------- */

async function cargarClientes() {
  try {
    const respuesta = await fetch("/api/clientes");
    if (!respuesta.ok) throw new Error();
    todosLosClientes = await respuesta.json();
    dibujarTabla();
  } catch (e) {
    cuerpoTabla.textContent = "";
    const fila = document.createElement("tr");
    const hueco = celda(
      "No se pudo conectar con el servidor. Verifique que la aplicación " +
      "esté encendida.", "vacio");
    hueco.colSpan = 5;
    fila.appendChild(hueco);
    cuerpoTabla.appendChild(fila);
  }
}

/* Después de crear, cambiar o eliminar, el riel de la izquierda está
   mostrando lo de antes. Se le pide que se vuelva a cargar. */
function refrescarTodo() {
  cargarClientes();
  if (window.RielTaxi) window.RielTaxi.recargar();
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
  refrescarTodo();
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
  refrescarTodo();   // se redibuja para actualizar la etiqueta de plazo
}

async function eliminarCliente(cliente) {
  const seguro = confirm(
    "¿Eliminar a " + cliente.nombre + "?\n\n" +
    "Se borran también todos sus documentos del computador, y estos NO " +
    "van a la papelera. Esta acción no se puede deshacer."
  );
  if (!seguro) return;

  const respuesta = await fetch("/api/clientes/" + cliente.id, {
    method: "DELETE"
  });

  if (!respuesta.ok) {
    mostrarAviso(await textoDelError(respuesta), "error");
    return;
  }
  refrescarTodo();
}


/* ----------------------------------------------------------
   Arranque
   ---------------------------------------------------------- */

formulario.addEventListener("submit", agregarCliente);
cargarClientes();


/* ==========================================================
   Importar clientes desde un Excel o un CSV

   Son dos pasos, a propósito:
     1. Se manda el archivo y el servidor PROPONE una lista.
        Todavía no se guardó nada.
     2. El contador revisa y corrige en pantalla, y solo cuando
        aprieta "Crear" se guardan de verdad.
   ========================================================== */

const botonImportar = document.getElementById("boton-importar");
const campoImportar = document.getElementById("campo-importar");
const avisoImportar = document.getElementById("aviso-importar");
const revision = document.getElementById("revision");
const revisionResumen = document.getElementById("revision-resumen");
const revisionColumnas = document.getElementById("revision-columnas");
const revisionFilas = document.getElementById("revision-filas");
const botonConfirmar = document.getElementById("boton-confirmar");
const botonCancelar = document.getElementById("boton-cancelar");

/* Cómo se llama cada campo en pantalla. */
const NOMBRES_DE_CAMPO = {
  nombre: "Nombre",
  cedula: "Cédula",
  dos_digitos: "Dos dígitos",
  fecha_vencimiento: "Fecha de vencimiento"
};


function mostrarAvisoImportar(texto, tipo) { avisarEn(avisoImportar, texto, tipo); }
function ocultarAvisoImportar() { ocultarAvisoEn(avisoImportar); }

function cerrarRevision() {
  revision.className = "revision oculto";
  revisionFilas.innerHTML = "";
}


/* ----------------------------------------------------------
   Dibujar la tabla de revisión
   ---------------------------------------------------------- */

/* Crea una casilla de la tabla con un campo de texto adentro. */
function casillaEditable(valor, clase, maximo) {
  const casilla = document.createElement("td");
  const entrada = document.createElement("input");
  entrada.type = "text";
  entrada.value = valor || "";
  entrada.className = clase || "";
  if (maximo) entrada.maxLength = maximo;
  casilla.appendChild(entrada);
  return casilla;
}

function dibujarRevision(datos) {
  revisionFilas.innerHTML = "";

  const total = datos.propuestas.length;
  const marcados = datos.propuestas.filter(function (p) { return p.incluir; }).length;

  revisionResumen.textContent =
    "Se leyeron " + total + (total === 1 ? " fila" : " filas") + ". " +
    marcados + " están listas para crear. " +
    "Nada se ha guardado todavía: revise y corrija lo que haga falta.";

  /* --- Qué columnas se reconocieron y cuáles no --- */
  revisionColumnas.innerHTML = "";

  const reconocidas = Object.keys(datos.columnas_reconocidas)
    .map(function (campo) { return NOMBRES_DE_CAMPO[campo] || campo; });

  const linea = document.createElement("p");
  linea.style.margin = "0 0 4px";
  linea.textContent = "Columnas reconocidas: " + reconocidas.join(", ") + ".";
  revisionColumnas.appendChild(linea);

  // Aviso sobre el orden de las fechas, cuando el archivo no dejaba claro
  // si estaban escritas día/mes o mes/día.
  if (datos.aviso_fechas) {
    const alerta = document.createElement("p");
    alerta.className = "aviso aviso-fechas";
    alerta.textContent = datos.aviso_fechas;
    revisionColumnas.appendChild(alerta);
  }

  if (datos.columnas_ignoradas.length > 0) {
    const otra = document.createElement("p");
    otra.style.margin = "0 0 16px";
    otra.textContent =
      "El resto del archivo (" + datos.columnas_ignoradas.join(", ") +
      ") se guarda como notas del cliente.";
    revisionColumnas.appendChild(otra);
  }

  /* --- Una fila por cliente propuesto --- */
  datos.propuestas.forEach(function (propuesta) {
    const fila = document.createElement("tr");
    if (propuesta.avisos.length > 0) fila.className = "fila-revisar";

    /* Casilla de "crear sí o no" */
    const casillaMarca = document.createElement("td");
    const marca = document.createElement("input");
    marca.type = "checkbox";
    marca.checked = propuesta.incluir;
    marca.className = "marca-crear";
    casillaMarca.appendChild(marca);
    fila.appendChild(casillaMarca);

    /* Nombre, dígitos y fecha: todos editables aquí mismo */
    fila.appendChild(casillaEditable(propuesta.nombre, "campo-nombre", 120));
    fila.appendChild(casillaEditable(propuesta.dos_digitos, "campo-digitos", 2));

    const casillaFecha = document.createElement("td");
    const entradaFecha = document.createElement("input");
    entradaFecha.type = "date";
    entradaFecha.value = propuesta.fecha_vencimiento || "";
    entradaFecha.className = "campo-fecha";
    casillaFecha.appendChild(entradaFecha);
    fila.appendChild(casillaFecha);

    /* Avisos */
    const casillaAvisos = document.createElement("td");
    casillaAvisos.className = "casilla-avisos";
    casillaAvisos.textContent = propuesta.avisos.join(" · ");
    fila.appendChild(casillaAvisos);

    // Las notas no se muestran en la tabla para no volverla ilegible,
    // pero viajan con la fila y se guardan con el cliente.
    fila.dataset.notas = propuesta.notas || "";

    revisionFilas.appendChild(fila);
  });

  revision.className = "revision";
}


/* ----------------------------------------------------------
   Conversación con el servidor
   ---------------------------------------------------------- */

async function analizarArchivo(archivo) {
  ocultarAvisoImportar();
  cerrarRevision();
  mostrarAvisoImportar("Leyendo el archivo…", "exito");

  const formulario = new FormData();
  formulario.append("archivo", archivo, archivo.name);

  let respuesta;
  try {
    respuesta = await fetch("/api/importar/analizar", {
      method: "POST",
      body: formulario
    });
  } catch (e) {
    mostrarAvisoImportar("No se pudo conectar con el servidor.", "error");
    return;
  }

  if (!respuesta.ok) {
    mostrarAvisoImportar(await textoDelError(respuesta), "error");
    return;
  }

  ocultarAvisoImportar();
  dibujarRevision(await respuesta.json());
}

async function confirmarImportacion() {
  const seleccionados = [];

  Array.from(revisionFilas.children).forEach(function (fila) {
    if (!fila.querySelector(".marca-crear").checked) return;
    seleccionados.push({
      nombre: fila.querySelector(".campo-nombre").value,
      dos_digitos: fila.querySelector(".campo-digitos").value,
      fecha_vencimiento: fila.querySelector(".campo-fecha").value || null,
      notas: fila.dataset.notas || null
    });
  });

  if (seleccionados.length === 0) {
    mostrarAvisoImportar("No hay ninguna fila marcada para crear.", "error");
    return;
  }

  botonConfirmar.disabled = true;

  const respuesta = await fetch("/api/importar/confirmar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(seleccionados)
  });

  botonConfirmar.disabled = false;

  if (!respuesta.ok) {
    mostrarAvisoImportar(await textoDelError(respuesta), "error");
    return;
  }

  const resultado = await respuesta.json();

  let texto = resultado.creados === 1
    ? "Se creó 1 cliente."
    : "Se crearon " + resultado.creados + " clientes.";
  if (resultado.errores.length > 0) {
    texto += " " + resultado.errores.length + " fila(s) no se pudieron crear: " +
             resultado.errores.join(" | ");
  }

  mostrarAvisoImportar(texto, resultado.errores.length > 0 ? "error" : "exito");
  cerrarRevision();
  refrescarTodo();
}


/* ----------------------------------------------------------
   Botones
   ---------------------------------------------------------- */

botonImportar.addEventListener("click", function () { campoImportar.click(); });

campoImportar.addEventListener("change", function () {
  if (campoImportar.files.length > 0) {
    analizarArchivo(campoImportar.files[0]);
  }
  campoImportar.value = "";   // permite volver a elegir el mismo archivo
});

botonConfirmar.addEventListener("click", confirmarImportacion);

botonCancelar.addEventListener("click", function () {
  cerrarRevision();
  ocultarAvisoImportar();
});


/* ----------------------------------------------------------
   Acciones sobre todos los clientes de una vez

   Después de importar 150 clientes de un Excel, dejarlos en el punto de
   partida uno por uno son 150 visitas. Estos dos botones lo hacen de un
   golpe, y los dos respetan lo que el contador ya haya puesto a mano.
   ---------------------------------------------------------- */

const avisoLote = document.getElementById("aviso-lote");
const botonListaBase = document.getElementById("boton-lista-base");
const botonVencimientos = document.getElementById("boton-vencimientos");

botonListaBase.addEventListener("click", async function () {
  const sinChecklist = todosLosClientes.filter(function (c) {
    return (c.checklist_total || 0) === 0;
  }).length;

  if (sinChecklist === 0) {
    avisarEn(avisoLote, "Todos los clientes ya tienen checklist.", "exito");
    return;
  }

  const seguro = confirm(
    "Se le va a poner la lista base del checklist a " +
    contar(sinChecklist, "cliente", "clientes") + ".\n\n" +
    "A los que ya tienen checklist no se les toca nada."
  );
  if (!seguro) return;

  this.disabled = true;
  try {
    const respuesta = await fetch("/api/clientes/lote/checklist-base", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    if (!respuesta.ok) {
      avisarEn(avisoLote, await textoDelError(respuesta), "error");
      return;
    }
    const r = await respuesta.json();
    avisarEn(avisoLote,
      "Listo: " + contar(r.puestos, "cliente quedó", "clientes quedaron") +
      " con la lista base de " + r.renglones + " renglones." +
      (r.saltados > 0
        ? " " + contar(r.saltados, "ya tenía", "ya tenían") + " checklist y no se tocaron."
        : ""),
      "exito");
    refrescarTodo();
  } catch (e) {
    avisarEn(avisoLote, "No se pudo conectar con el servidor.", "error");
  } finally {
    this.disabled = false;
  }
});

botonVencimientos.addEventListener("click", async function () {
  const sinFecha = todosLosClientes.filter(function (c) {
    return !c.fecha_vencimiento;
  }).length;

  const seguro = confirm(
    "Se le va a poner la fecha del calendario oficial a " +
    contar(sinFecha, "cliente", "clientes") + " que no tiene fecha.\n\n" +
    "La fecha sale de la tabla del calendario que está cargada en el " +
    "programa, según los dos últimos dígitos de la cédula.\n\n" +
    "A los que ya tienen fecha no se les toca: esa la puso usted."
  );
  if (!seguro) return;

  this.disabled = true;
  try {
    const respuesta = await fetch("/api/clientes/lote/vencimientos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    if (!respuesta.ok) {
      avisarEn(avisoLote, await textoDelError(respuesta), "error");
      return;
    }
    const r = await respuesta.json();
    let texto = "Listo: " + contar(r.puestas, "fecha puesta", "fechas puestas") +
                " del calendario del año gravable " + r.anio + ".";
    if (r.respetadas > 0) {
      texto += " " + contar(r.respetadas, "cliente ya tenía", "clientes ya tenían") +
               " su fecha y no se tocaron.";
    }
    if (r.sin_fecha > 0) {
      texto += " " + contar(r.sin_fecha, "cliente no está", "clientes no están") +
               " en la tabla.";
    }
    avisarEn(avisoLote, texto, "exito");
    refrescarTodo();
  } catch (e) {
    avisarEn(avisoLote, "No se pudo conectar con el servidor.", "error");
  } finally {
    this.disabled = false;
  }
});

/* El botón de vencimientos solo aparece si hay tabla cargada. Sin ella
   no haría nada, y un botón que no hace nada es peor que no tenerlo. */
(async function mirarSiHayTabla() {
  try {
    const respuesta = await fetch("/api/vencimientos");
    if (!respuesta.ok) return;
    const datos = await respuesta.json();
    if (datos.hay_tabla) {
      botonVencimientos.classList.remove("oculto");
      botonVencimientos.textContent =
        "Poner los vencimientos del calendario " + datos.anio;
    }
  } catch (e) {
    // Sin respuesta, el botón se queda escondido. No es crítico.
  }
})();
