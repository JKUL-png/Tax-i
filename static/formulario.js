/* ==========================================================
   Formulario 210 de un cliente.

   La plantilla de Excel es la misma para todos los clientes. Lo que se
   anota aquí es de este cliente: se guarda en la base de datos, y el
   archivo se arma aparte cada vez que se pide, partiendo siempre de la
   plantilla limpia.

   JavaScript plano, sin librerías, igual que el resto del programa.
   ========================================================== */

(function () {

const idCliente = new URLSearchParams(window.location.search).get("id");
if (!idCliente) return;

const seccion = document.getElementById("seccion-formulario");
const avisoFormulario = document.getElementById("aviso-formulario");
const sinPlantilla = document.getElementById("sin-plantilla");
const motivoSinPlantilla = document.getElementById("motivo-sin-plantilla");
const bloque = document.getElementById("bloque-formulario");
const conteoFormulario = document.getElementById("conteo-formulario");
const campoBuscar = document.getElementById("buscar-casilla");
const casillaTodas = document.getElementById("todas-casillas");
const resultados = document.getElementById("resultados-casillas");
const listaValores = document.getElementById("lista-valores");
const conteoValores = document.getElementById("conteo-valores");
const botonGenerar = document.getElementById("boton-generar");
const enlaceArchivo = document.getElementById("enlace-formulario");
const progreso = document.getElementById("progreso-formulario");
const progresoTexto = document.getElementById("progreso-formulario-texto");
const resultado = document.getElementById("resultado-formulario");
const historial = document.getElementById("historial");
const listaHistorial = document.getElementById("lista-historial");

/* Los documentos de este cliente, para poder decir de cuál salió cada dato. */
let documentosDelCliente = [];

/* Los valores ya anotados: {celda: {valor, documento, ...}} */
let valoresAnotados = {};


/* ----------------------------------------------------------
   Avisos
   ---------------------------------------------------------- */

let temporizador = null;

function avisar(texto, tipo) {
  avisoFormulario.textContent = texto;
  avisoFormulario.className = "aviso aviso-" + tipo;
  clearTimeout(temporizador);
  if (tipo === "exito") {
    temporizador = setTimeout(function () {
      avisoFormulario.className = "aviso oculto";
    }, 4000);
  }
}


/* ----------------------------------------------------------
   Números en pesos

   El contador escribe "1.500.000" o "1500000"; las dos formas valen.
   ---------------------------------------------------------- */

function enPesos(numero) {
  if (numero === null || numero === undefined) return "";
  return "$ " + numero.toLocaleString("es-CO", { maximumFractionDigits: 2 });
}

function comoNumero(texto) {
  if (texto === null || texto === undefined) return null;
  let limpio = String(texto).trim().replace(/[$\s]/g, "");
  if (limpio === "") return null;
  /* Puntos de miles fuera; la coma es el separador decimal. */
  limpio = limpio.replace(/\./g, "").replace(",", ".");
  const numero = Number(limpio);
  if (!isFinite(numero)) return null;
  return numero;
}


/* ----------------------------------------------------------
   Pedirle cosas al servidor
   ---------------------------------------------------------- */

async function textoDelError(respuesta) {
  try {
    const datos = await respuesta.json();
    if (datos && datos.detail) return datos.detail;
  } catch (error) { /* la respuesta no era JSON */ }
  return "No se pudo completar la operación (" + respuesta.status + ").";
}

async function pedir(direccion, opciones) {
  const respuesta = await fetch(direccion, opciones);
  if (!respuesta.ok) throw new Error(await textoDelError(respuesta));
  if (respuesta.status === 204) return null;
  return respuesta.json();
}


/* ----------------------------------------------------------
   Buscar casillas
   ---------------------------------------------------------- */

function chip(texto, clase) {
  const etiqueta = document.createElement("span");
  etiqueta.className = "etiqueta " + (clase || "etiqueta-neutra");
  etiqueta.textContent = texto;
  return etiqueta;
}

function dibujarCasilla(casilla) {
  const anotado = valoresAnotados[casilla.celda];

  const fila = document.createElement("div");
  fila.className = "casilla" + (anotado ? " casilla-anotada" : "");

  /* --- Lo que dice la plantilla --- */
  const datos = document.createElement("div");
  datos.className = "casilla-datos";

  /* El rastro de conceptos de arriba. Sin esto, veinte casillas dicen
     "Empresa xxx, NIT…" y no hay forma de saber cuál es cuál. */
  if (casilla.contexto) {
    const rastro = document.createElement("p");
    rastro.className = "casilla-rastro";
    rastro.textContent = casilla.contexto;
    datos.appendChild(rastro);
  }

  const titulo = document.createElement("p");
  titulo.className = "casilla-titulo";
  titulo.textContent = casilla.descripcion || "(sin descripción)";
  datos.appendChild(titulo);

  const marcas = document.createElement("div");
  marcas.className = "casilla-marcas";
  if (casilla.renglon) marcas.appendChild(chip("Renglón " + casilla.renglon));
  if (casilla.seccion) marcas.appendChild(chip(casilla.seccion));
  marcas.appendChild(chip(casilla.celda, "etiqueta-celda"));
  datos.appendChild(marcas);

  fila.appendChild(datos);

  /* --- Dónde se escribe el valor --- */
  const accion = document.createElement("div");
  accion.className = "casilla-accion";

  const entrada = document.createElement("input");
  entrada.type = "text";
  entrada.className = "campo-valor";
  entrada.inputMode = "decimal";
  entrada.placeholder = "0";
  entrada.setAttribute("aria-label", "Valor para " + casilla.celda);
  if (anotado) entrada.value = anotado.valor.toLocaleString("es-CO");

  const origen = document.createElement("select");
  origen.className = "selector-origen";
  origen.setAttribute("aria-label", "De dónde salió el dato");
  agregarOpciones(origen, anotado ? anotado.documento : "");

  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = "boton";
  boton.textContent = anotado ? "Actualizar" : "Guardar";

  async function guardar() {
    const numero = comoNumero(entrada.value);
    if (numero === null) {
      avisar("Escriba un número. Para dejar la casilla en cero, escriba 0.",
             "error");
      entrada.focus();
      return;
    }
    boton.disabled = true;
    try {
      await pedir("/api/clientes/" + idCliente + "/formulario/valores", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          celda: casilla.celda,
          valor: numero,
          documento: origen.value
        })
      });
      avisar("Guardado en " + casilla.celda + ".", "exito");
      await cargarValores();
      buscar();
    } catch (error) {
      avisar(error.message, "error");
    } finally {
      boton.disabled = false;
    }
  }

  boton.addEventListener("click", guardar);
  entrada.addEventListener("keydown", function (evento) {
    if (evento.key === "Enter") guardar();
  });

  accion.appendChild(entrada);
  accion.appendChild(origen);
  accion.appendChild(boton);
  fila.appendChild(accion);

  return fila;
}

function agregarOpciones(selector, seleccionado) {
  const manual = document.createElement("option");
  manual.value = "digitado por el contador";
  manual.textContent = "Digitado por usted";
  selector.appendChild(manual);

  documentosDelCliente.forEach(function (documento) {
    const opcion = document.createElement("option");
    opcion.value = documento.nombre_original;
    opcion.textContent = documento.nombre_original;
    selector.appendChild(opcion);
  });

  if (seleccionado) {
    const existe = Array.prototype.some.call(selector.options, function (o) {
      return o.value === seleccionado;
    });
    if (!existe) {
      const opcion = document.createElement("option");
      opcion.value = seleccionado;
      opcion.textContent = seleccionado;
      selector.appendChild(opcion);
    }
    selector.value = seleccionado;
  }
}

let temporizadorBusqueda = null;

function buscarConCalma() {
  clearTimeout(temporizadorBusqueda);
  temporizadorBusqueda = setTimeout(buscar, 250);
}

async function buscar() {
  const texto = campoBuscar.value.trim();
  const direccion = "/api/plantilla/celdas?buscar="
    + encodeURIComponent(texto)
    + (casillaTodas.checked ? "&todas=true" : "");

  try {
    const casillas = await pedir(direccion);
    resultados.textContent = "";

    if (casillas.length === 0) {
      const vacio = document.createElement("div");
      vacio.className = "vacio";
      vacio.textContent = texto
        ? "Ninguna casilla coincide con «" + texto + "»."
        : "No hay casillas para mostrar.";
      resultados.appendChild(vacio);
      return;
    }

    casillas.forEach(function (casilla) {
      resultados.appendChild(dibujarCasilla(casilla));
    });
  } catch (error) {
    avisar(error.message, "error");
  }
}


/* ----------------------------------------------------------
   Los valores ya anotados de este cliente
   ---------------------------------------------------------- */

function dibujarValor(valor) {
  const fila = document.createElement("div");
  fila.className = "valor-anotado";

  const datos = document.createElement("div");
  datos.className = "valor-datos";

  if (valor.contexto) {
    const rastro = document.createElement("p");
    rastro.className = "casilla-rastro";
    rastro.textContent = valor.contexto;
    datos.appendChild(rastro);
  }

  const titulo = document.createElement("p");
  titulo.className = "valor-titulo";
  titulo.textContent = valor.descripcion || valor.celda;
  datos.appendChild(titulo);

  const detalle = document.createElement("p");
  detalle.className = "valor-detalle";
  const partes = [valor.celda];
  if (valor.renglon) partes.push("renglón " + valor.renglon);
  if (valor.documento) partes.push(valor.documento);
  detalle.textContent = partes.join(" · ");
  datos.appendChild(detalle);

  fila.appendChild(datos);

  const monto = document.createElement("p");
  monto.className = "valor-monto";
  monto.textContent = enPesos(valor.valor);
  fila.appendChild(monto);

  const quitar = document.createElement("button");
  quitar.type = "button";
  quitar.className = "boton-texto boton-texto-peligro";
  quitar.textContent = "Quitar";
  quitar.addEventListener("click", function () {
    quitarValor(valor);
  });
  fila.appendChild(quitar);

  return fila;
}

async function quitarValor(valor) {
  const seguro = window.confirm(
    "¿Quitar el valor de «" + (valor.descripcion || valor.celda) + "»?\n\n"
    + "La casilla vuelve a como viene en la plantilla. El movimiento queda"
    + " en el historial."
  );
  if (!seguro) return;

  try {
    await pedir("/api/clientes/" + idCliente + "/formulario/valores/"
                + encodeURIComponent(valor.celda), { method: "DELETE" });
    avisar("Valor quitado.", "exito");
    await cargarValores();
    buscar();
  } catch (error) {
    avisar(error.message, "error");
  }
}

async function cargarValores() {
  try {
    const datos = await pedir("/api/clientes/" + idCliente + "/formulario");

    valoresAnotados = {};
    datos.valores.forEach(function (valor) {
      valoresAnotados[valor.celda] = valor;
    });

    listaValores.textContent = "";
    if (datos.valores.length === 0) {
      const vacio = document.createElement("div");
      vacio.className = "vacio";
      vacio.textContent = "Todavía no hay ningún valor anotado para este"
        + " cliente. Búsquelo arriba y anótelo.";
      listaValores.appendChild(vacio);
    } else {
      datos.valores.forEach(function (valor) {
        listaValores.appendChild(dibujarValor(valor));
      });
    }

    const cuantos = datos.valores.length;
    conteoValores.textContent = cuantos === 0 ? "" : cuantos;
    conteoFormulario.textContent = cuantos === 0
      ? ""
      : cuantos + (cuantos === 1 ? " valor anotado" : " valores anotados");

    if (datos.estado.hay_archivo) {
      enlaceArchivo.classList.remove("oculto");
      enlaceArchivo.href = "/api/clientes/" + idCliente
        + "/formulario/archivo";
    }
  } catch (error) {
    avisar(error.message, "error");
  }
}


/* ----------------------------------------------------------
   Generar el archivo
   ---------------------------------------------------------- */

function lineaResultado(texto, clase) {
  const parrafo = document.createElement("p");
  parrafo.className = clase || "";
  parrafo.textContent = texto;
  return parrafo;
}

function dibujarTotales(totales) {
  const caja = document.createElement("details");
  caja.className = "totales";
  caja.open = true;

  const titulo = document.createElement("summary");
  titulo.textContent = "Totales que calculó la plantilla (" + totales.length + ")";
  caja.appendChild(titulo);

  const nota = document.createElement("p");
  nota.className = "ayuda";
  nota.textContent = "Estos números los calculó su plantilla de Excel, no"
    + " este programa. Están aquí para que los revise; los definitivos son"
    + " los del archivo. Los renglones de la liquidación (impuesto y saldos)"
    + " no se muestran aquí: ábralos en Excel.";
  caja.appendChild(nota);

  /* Casi todos los renglones están en cero. Se pueden esconder para dejar
     a la vista solo lo que este cliente sí tiene. */
  const conCeros = totales.filter(function (t) { return t.valor === 0; }).length;
  const opcion = document.createElement("label");
  opcion.className = "opcion-linea";
  const marca = document.createElement("input");
  marca.type = "checkbox";
  marca.checked = true;
  opcion.appendChild(marca);
  opcion.appendChild(document.createTextNode(
    "Esconder los " + conCeros + " renglones que están en cero"
  ));
  caja.appendChild(opcion);

  let seccionAnterior = "";
  const lista = document.createElement("div");
  lista.className = "lista-totales sin-ceros";
  marca.addEventListener("change", function () {
    lista.classList.toggle("sin-ceros", marca.checked);
  });

  totales.forEach(function (total) {
    if (total.seccion && total.seccion !== seccionAnterior) {
      seccionAnterior = total.seccion;
      const cabecera = document.createElement("p");
      /* Si toda la sección está en cero, su título se esconde con ella. */
      const todaEnCero = totales.every(function (otro) {
        return otro.seccion !== total.seccion || otro.valor === 0;
      });
      cabecera.className = "total-seccion" + (todaEnCero ? " total-en-cero" : "");
      cabecera.textContent = total.seccion;
      lista.appendChild(cabecera);
    }

    const fila = document.createElement("div");
    fila.className = "total" + (total.valor === 0 ? " total-en-cero" : "");

    const numero = document.createElement("span");
    numero.className = "etiqueta etiqueta-neutra total-renglon";
    numero.textContent = total.renglon;
    fila.appendChild(numero);

    const descripcion = document.createElement("span");
    descripcion.className = "total-descripcion";
    descripcion.textContent = total.descripcion;
    fila.appendChild(descripcion);

    const monto = document.createElement("span");
    monto.className = "total-monto" + (total.valor === 0 ? " total-cero" : "");
    monto.textContent = enPesos(total.valor);
    fila.appendChild(monto);

    lista.appendChild(fila);
  });

  caja.appendChild(lista);
  return caja;
}

async function generar() {
  botonGenerar.disabled = true;
  progreso.classList.remove("oculto");
  progresoTexto.textContent = "Armando el archivo y revisando las fórmulas…"
    + " Puede tardar unos segundos.";
  resultado.classList.add("oculto");
  resultado.textContent = "";

  try {
    const informe = await pedir(
      "/api/clientes/" + idCliente + "/formulario/generar",
      { method: "POST" }
    );

    resultado.textContent = "";

    const verificacion = informe.verificacion;
    resultado.appendChild(lineaResultado(
      "Listo. Se escribieron " + informe.valores_escritos
      + (informe.valores_escritos === 1 ? " valor" : " valores")
      + " y se revisaron las " + verificacion.formulas_comparadas
      + " fórmulas del libro: ninguna cambió.",
      "resultado-bien"
    ));

    if (informe.recalculo && informe.recalculo.recalculado) {
      resultado.appendChild(lineaResultado(
        informe.recalculo.motivo, "ayuda"
      ));
    } else if (informe.recalculo) {
      resultado.appendChild(lineaResultado(
        informe.recalculo.motivo, "resultado-aviso"
      ));
    }

    if (informe.totales && informe.totales.length > 0) {
      resultado.appendChild(dibujarTotales(informe.totales));
    }

    resultado.classList.remove("oculto");
    enlaceArchivo.classList.remove("oculto");
    enlaceArchivo.href = "/api/clientes/" + idCliente + "/formulario/archivo";
    avisar("El archivo quedó listo para descargar.", "exito");
    cargarHistorial();
  } catch (error) {
    avisar(error.message, "error");
    resultado.textContent = "";
    resultado.appendChild(lineaResultado(error.message, "resultado-mal"));
    resultado.classList.remove("oculto");
    enlaceArchivo.classList.add("oculto");
  } finally {
    botonGenerar.disabled = false;
    progreso.classList.add("oculto");
  }
}


/* ----------------------------------------------------------
   Historial
   ---------------------------------------------------------- */

async function cargarHistorial() {
  try {
    const movimientos = await pedir(
      "/api/clientes/" + idCliente + "/formulario/bitacora"
    );

    listaHistorial.textContent = "";
    if (movimientos.length === 0) {
      const vacio = document.createElement("p");
      vacio.className = "ayuda";
      vacio.textContent = "Todavía no hay movimientos.";
      listaHistorial.appendChild(vacio);
      return;
    }

    movimientos.forEach(function (movimiento) {
      const fila = document.createElement("p");
      fila.className = "movimiento";
      const antes = movimiento.valor_anterior === null
        ? "vacío" : enPesos(movimiento.valor_anterior);
      const despues = movimiento.valor_nuevo === null
        ? "se quitó" : enPesos(movimiento.valor_nuevo);
      fila.textContent = fechaCorta(movimiento.fecha_hora) + " · "
        + movimiento.celda + ": " + antes + " → " + despues
        + (movimiento.documento ? " · " + movimiento.documento : "");
      listaHistorial.appendChild(fila);
    });
  } catch (error) {
    /* El historial es un extra: si falla, no vale la pena molestar. */
  }
}

function fechaCorta(texto) {
  const fecha = new Date(texto);
  if (isNaN(fecha)) return texto;
  return fecha.toLocaleString("es-CO", {
    day: "2-digit", month: "2-digit",
    hour: "numeric", minute: "2-digit"
  });
}


/* ----------------------------------------------------------
   Arranque
   ---------------------------------------------------------- */

async function arrancar() {
  let plantilla;
  try {
    plantilla = await pedir("/api/plantilla");
  } catch (error) {
    avisar(error.message, "error");
    return;
  }

  if (!plantilla.hay_plantilla) {
    motivoSinPlantilla.textContent = plantilla.motivo;
    sinPlantilla.classList.remove("oculto");
    return;
  }

  bloque.classList.remove("oculto");

  if (!plantilla.libreoffice) {
    avisar("LibreOffice no está instalado en este computador, así que los"
      + " totales no se pueden calcular aquí. El archivo se genera igual y"
      + " los totales aparecen al abrirlo en Excel.", "fechas");
  }

  try {
    documentosDelCliente = await pedir(
      "/api/clientes/" + idCliente + "/documentos"
    );
  } catch (error) {
    documentosDelCliente = [];
  }

  await cargarValores();
  await buscar();
  cargarHistorial();
}

campoBuscar.addEventListener("input", buscarConCalma);
casillaTodas.addEventListener("change", buscar);
botonGenerar.addEventListener("click", generar);

arrancar();

})();
