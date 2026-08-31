/* ==========================================================
   Formulario 210 de un cliente.

   Esta pantalla es la plantilla de Excel abierta por dentro: se ve la
   hoja de captura tal como está en el archivo —con sus secciones, sus
   sangrías y sus fórmulas— y se escribe directamente en las casillas.

   Lo que se escribe se guarda para ESTE cliente. La plantilla no se toca
   nunca: el archivo de Excel se arma aparte, partiendo siempre de la
   plantilla limpia.

   Las fórmulas no se recalculan solas al escribir, porque eso se hace con
   LibreOffice y tarda unos segundos. Por eso las casillas cambiadas quedan
   marcadas como pendientes hasta que se aprieta "Actualizar totales".

   JavaScript plano, sin librerías, igual que el resto del programa.
   ========================================================== */

(function () {

const idCliente = new URLSearchParams(window.location.search).get("id");
if (!idCliente) return;

const avisoFormulario = document.getElementById("aviso-formulario");
const sinPlantilla = document.getElementById("sin-plantilla");
const motivoSinPlantilla = document.getElementById("motivo-sin-plantilla");
const bloque = document.getElementById("bloque-formulario");
const conteoFormulario = document.getElementById("conteo-formulario");

const filtroHoja = document.getElementById("filtro-hoja");
const soloConValor = document.getElementById("solo-con-valor");
const origenHoja = document.getElementById("origen-hoja");
const cuerpoHoja = document.getElementById("cuerpo-hoja");
const avisoPendientes = document.getElementById("aviso-pendientes");
const textoPendientes = document.getElementById("texto-pendientes");
const botonRecalcular = document.getElementById("boton-recalcular");

const listaValores = document.getElementById("lista-valores");
const conteoValores = document.getElementById("conteo-valores");
const cajaTotales = document.getElementById("caja-totales");

const botonGenerar = document.getElementById("boton-generar");
const enlaceArchivo = document.getElementById("enlace-formulario");
const progreso = document.getElementById("progreso-formulario");
const progresoTexto = document.getElementById("progreso-formulario-texto");
const resultado = document.getElementById("resultado-formulario");
const listaHistorial = document.getElementById("lista-historial");

const selectorPlantilla = document.getElementById("selector-plantilla");
const botonSubirPlantilla = document.getElementById("boton-subir-plantilla");
const botonSubirPlantilla1 = document.getElementById("boton-subir-plantilla-1");
const campoPlantilla = document.getElementById("campo-plantilla");
const avisoPlantilla = document.getElementById("aviso-plantilla");

/* Las columnas de valores de la hoja, en el orden en que se muestran. */
const COLUMNAS = ["G", "H", "I"];

/* Lo último que devolvió el servidor sobre la hoja. */
let hoja = null;
/* Los documentos del cliente, para decir de dónde salió cada dato. */
let documentosDelCliente = [];


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

function conSeparadores(numero) {
  if (numero === null || numero === undefined) return "";
  return numero.toLocaleString("es-CO", { maximumFractionDigits: 2 });
}

function comoNumero(texto) {
  if (texto === null || texto === undefined) return null;
  let limpio = String(texto).trim().replace(/[$\s]/g, "");
  if (limpio === "") return null;
  limpio = limpio.replace(/\./g, "").replace(",", ".");
  const numero = Number(limpio);
  if (!isFinite(numero)) return null;
  return numero;
}

/* "Alimentación" -> "alimentacion", para poder filtrar sin tildes. */
function sinTildes(texto) {
  return (texto || "").toLowerCase()
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}


/* ----------------------------------------------------------
   Pedirle cosas al servidor
   ---------------------------------------------------------- */

async function pedir(direccion, opciones) {
  const respuesta = await fetch(direccion, opciones);
  if (!respuesta.ok) {
    // textoDelError vive en comun.js. El texto de reserva lleva el
    // número del error, que es lo único útil cuando el servidor no
    // alcanzó ni a contestar en JSON.
    throw new Error(await textoDelError(
      respuesta,
      "No se pudo completar la operación (" + respuesta.status + ")."
    ));
  }
  if (respuesta.status === 204) return null;
  return respuesta.json();
}


/* ----------------------------------------------------------
   Pestañas
   ---------------------------------------------------------- */

function prepararPestanas() {
  const pestanas = document.querySelectorAll(".pestana");
  pestanas.forEach(function (pestana) {
    pestana.addEventListener("click", function () {
      pestanas.forEach(function (otra) {
        otra.classList.toggle("pestana-activa", otra === pestana);
        document.getElementById(otra.dataset.panel)
          .classList.toggle("oculto", otra !== pestana);
      });
    });
  });
}


/* ----------------------------------------------------------
   La hoja

   Se dibuja una fila por cada renglón de la plantilla, con su sangría y
   sus tres columnas de valores. Las casillas de fórmula se ven grises y
   no se pueden escribir; las de captura son campos de verdad.
   ---------------------------------------------------------- */

function celdaDeValor(fila, columna) {
  const casilla = document.createElement("td");
  casilla.className = "celda-valor";

  const datos = (fila.celdas || {})[columna];
  if (!datos) {
    casilla.classList.add("celda-fuera");
    return casilla;
  }

  /* --- Con fórmula: se muestra el resultado y no se deja escribir --- */
  if (datos.tipo === "formula") {
    casilla.classList.add("celda-formula");
    casilla.textContent = datos.valor === null ? "—" : conSeparadores(datos.valor);
    casilla.title = "La calcula la plantilla (" + datos.celda + ")";
    if (datos.valor === 0) casilla.classList.add("celda-cero");
    return casilla;
  }

  /* --- De captura: se puede escribir --- */
  if (!datos.editable) {
    casilla.classList.add("celda-fuera");
    return casilla;
  }

  const entrada = document.createElement("input");
  entrada.type = "text";
  entrada.className = "celda-campo";
  entrada.inputMode = "decimal";
  entrada.value = datos.valor === null ? "" : conSeparadores(datos.valor);
  entrada.title = datos.celda + (datos.documento ? " · " + datos.documento : "");
  entrada.setAttribute("aria-label", (fila.descripcion || datos.celda)
    + ", casilla " + datos.celda);
  if (datos.anotado) casilla.classList.add("celda-anotada");
  if (datos.pendiente) casilla.classList.add("celda-pendiente");
  if (!datos.anotado && datos.valor === 0) entrada.classList.add("celda-cero");

  let valorAlEntrar = entrada.value;

  entrada.addEventListener("focus", function () {
    valorAlEntrar = entrada.value;
    entrada.select();
  });

  entrada.addEventListener("keydown", function (evento) {
    if (evento.key === "Enter") entrada.blur();
    if (evento.key === "Escape") {
      entrada.value = valorAlEntrar;
      entrada.blur();
    }
  });

  entrada.addEventListener("blur", async function () {
    if (entrada.value.trim() === valorAlEntrar.trim()) return;

    /* Dejar la casilla vacía es quitar el valor: vuelve a lo que trae la
       plantilla. Para poner un cero hay que escribir 0. */
    if (entrada.value.trim() === "") {
      await quitarValor(datos.celda, entrada, valorAlEntrar);
      return;
    }

    const numero = comoNumero(entrada.value);
    if (numero === null) {
      avisar("«" + entrada.value + "» no es un número. La casilla se dejó"
             + " como estaba.", "error");
      entrada.value = valorAlEntrar;
      return;
    }
    await guardarValor(datos.celda, numero, entrada, casilla);
  });

  casilla.appendChild(entrada);
  return casilla;
}

async function guardarValor(celda, numero, entrada, casilla) {
  entrada.disabled = true;
  try {
    await pedir("/api/clientes/" + idCliente + "/formulario/valores", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        celda: celda,
        valor: numero,
        documento: "digitado por el contador"
      })
    });
    entrada.value = conSeparadores(numero);
    casilla.classList.add("celda-anotada", "celda-pendiente");
    marcarPendiente(celda, numero);
    cargarValores();
  } catch (error) {
    avisar(error.message, "error");
  } finally {
    entrada.disabled = false;
  }
}

async function quitarValor(celda, entrada, valorAlEntrar) {
  entrada.disabled = true;
  try {
    await pedir("/api/clientes/" + idCliente + "/formulario/valores/" + celda,
                { method: "DELETE" });
    marcarPendiente(celda, null);
    cargarValores();
  } catch (error) {
    /* Si no había nada guardado, no es un error que valga la pena mostrar. */
    entrada.value = valorAlEntrar;
  } finally {
    entrada.disabled = false;
  }
}

/* Anota en memoria que una casilla cambió y que los totales de al lado
   todavía no lo saben. */
function marcarPendiente(celda, valor) {
  if (!hoja) return;
  hoja.filas.forEach(function (fila) {
    const datos = (fila.celdas || {})[celda.charAt(0)];
    if (datos && datos.celda === celda) {
      datos.valor = valor;
      datos.anotado = valor !== null;
      datos.pendiente = true;
    }
  });
  hoja.pendientes = contarPendientes();
  mostrarPendientes();
}

function contarPendientes() {
  let cuantos = 0;
  (hoja ? hoja.filas : []).forEach(function (fila) {
    COLUMNAS.forEach(function (columna) {
      const datos = (fila.celdas || {})[columna];
      if (datos && datos.pendiente) cuantos += 1;
    });
  });
  return cuantos;
}

function mostrarPendientes() {
  const cuantos = hoja ? hoja.pendientes : 0;
  avisoPendientes.classList.toggle("oculto", cuantos === 0);
  textoPendientes.textContent = cuantos === 1
    ? "Hay 1 casilla cambiada. Los totales todavía no la incluyen."
    : "Hay " + cuantos + " casillas cambiadas. Los totales todavía no las"
      + " incluyen.";
}

function filaVisible(fila, texto, soloValor) {
  if (soloValor) {
    const tieneValor = COLUMNAS.some(function (columna) {
      const datos = (fila.celdas || {})[columna];
      return datos && datos.valor !== null && datos.valor !== 0;
    });
    if (!tieneValor) return false;
  }
  if (!texto) return true;
  return sinTildes(fila.descripcion).indexOf(texto) !== -1
    || fila.renglon === texto
    || sinTildes(fila.seccion).indexOf(texto) !== -1
    || COLUMNAS.some(function (columna) {
      const datos = (fila.celdas || {})[columna];
      return datos && datos.celda.toLowerCase() === texto;
    });
}

function dibujarHoja() {
  if (!hoja) return;

  const texto = sinTildes(filtroHoja.value.trim());
  const soloValor = soloConValor.checked;

  cuerpoHoja.textContent = "";
  let seccionAnterior = "";
  let mostradas = 0;

  hoja.filas.forEach(function (fila) {
    if (!filaVisible(fila, texto, soloValor)) return;

    /* Título de sección, como los bloques de la hoja de Excel. */
    if (fila.seccion && fila.seccion !== seccionAnterior) {
      seccionAnterior = fila.seccion;
      const cabecera = document.createElement("tr");
      cabecera.className = "fila-seccion";
      const celda = document.createElement("td");
      celda.colSpan = 5;
      celda.textContent = fila.seccion;
      cabecera.appendChild(celda);
      cuerpoHoja.appendChild(cabecera);
    }

    const linea = document.createElement("tr");
    linea.className = "fila-hoja";
    if (fila.es_nota) linea.classList.add("fila-nota");
    if (fila.renglon) linea.classList.add("fila-renglon");

    const numero = document.createElement("td");
    numero.className = "columna-renglon";
    if (fila.renglon) {
      const marca = document.createElement("span");
      marca.className = "etiqueta etiqueta-neutra";
      marca.textContent = fila.renglon;
      numero.appendChild(marca);
    }
    linea.appendChild(numero);

    const concepto = document.createElement("td");
    concepto.className = "columna-concepto";
    /* La sangría de la plantilla se respeta: es la que dice qué cuelga de
       qué. Se divide para que no se salga de la pantalla. */
    concepto.style.paddingLeft = (10 + Math.min(fila.sangria, 20) * 5) + "px";
    /* El texto va dentro de un div y no suelto en la celda: el recorte a
       dos líneas necesita un bloque propio, y aplicárselo a la celda de la
       tabla le rompe el ancho a toda la columna. */
    const textoConcepto = document.createElement("div");
    textoConcepto.className = "concepto-texto";
    textoConcepto.textContent = fila.descripcion;
    textoConcepto.title = fila.descripcion;
    concepto.appendChild(textoConcepto);
    linea.appendChild(concepto);

    COLUMNAS.forEach(function (columna) {
      linea.appendChild(celdaDeValor(fila, columna));
    });

    cuerpoHoja.appendChild(linea);
    mostradas += 1;
  });

  if (mostradas === 0) {
    const linea = document.createElement("tr");
    const celda = document.createElement("td");
    celda.colSpan = 5;
    celda.className = "vacio";
    celda.textContent = "Ninguna fila coincide con lo que buscó.";
    linea.appendChild(celda);
    cuerpoHoja.appendChild(linea);
  }

  origenHoja.textContent = hoja.origen === "archivo"
    ? "Los totales que se ven son los del último archivo generado."
    : "Todavía no se ha generado el archivo de este cliente: los totales que"
      + " se ven son los que trae la plantilla.";

  mostrarPendientes();
}

async function cargarHoja() {
  try {
    hoja = await pedir("/api/clientes/" + idCliente + "/formulario/hoja");
    dibujarHoja();
  } catch (error) {
    avisar(error.message, "error");
  }
}


/* ----------------------------------------------------------
   Los valores anotados (pestaña "Resultado")
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

  if (valor.otra_plantilla) {
    const alerta = document.createElement("p");
    alerta.className = "valor-alerta";
    alerta.textContent = "Se anotó con otra plantilla. Revise que la casilla"
      + " signifique lo mismo en la de ahora.";
    datos.appendChild(alerta);
  }

  fila.appendChild(datos);

  const monto = document.createElement("p");
  monto.className = "valor-monto";
  monto.textContent = enPesos(valor.valor);
  fila.appendChild(monto);

  const quitar = document.createElement("button");
  quitar.type = "button";
  quitar.className = "boton-texto boton-texto-peligro";
  quitar.textContent = "Quitar";
  quitar.addEventListener("click", async function () {
    const seguro = window.confirm(
      "¿Quitar el valor de «" + (valor.descripcion || valor.celda) + "»?\n\n"
      + "La casilla vuelve a como viene en la plantilla. El movimiento queda"
      + " en el historial."
    );
    if (!seguro) return;
    try {
      await pedir("/api/clientes/" + idCliente + "/formulario/valores/"
                  + valor.celda, { method: "DELETE" });
      avisar("Valor quitado.", "exito");
      await cargarValores();
      await cargarHoja();
    } catch (error) {
      avisar(error.message, "error");
    }
  });
  fila.appendChild(quitar);

  return fila;
}

async function cargarValores() {
  try {
    const datos = await pedir("/api/clientes/" + idCliente + "/formulario");

    listaValores.textContent = "";
    if (datos.valores.length === 0) {
      const vacio = document.createElement("div");
      vacio.className = "vacio";
      vacio.textContent = "Todavía no hay ningún valor anotado para este"
        + " cliente. Escríbalos en la hoja de captura.";
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
      enlaceArchivo.href = "/api/clientes/" + idCliente + "/formulario/archivo";
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
  cajaTotales.textContent = "";

  const nota = document.createElement("p");
  nota.className = "ayuda";
  nota.textContent = "Estos números los calculó su plantilla de Excel, no"
    + " este programa. Están aquí para que los revise; los definitivos son"
    + " los del archivo. Los renglones de la liquidación (impuesto y saldos)"
    + " no se muestran aquí: ábralos en Excel.";
  cajaTotales.appendChild(nota);

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
  cajaTotales.appendChild(opcion);

  const lista = document.createElement("div");
  lista.className = "lista-totales sin-ceros";
  marca.addEventListener("change", function () {
    lista.classList.toggle("sin-ceros", marca.checked);
  });

  let seccionAnterior = "";
  totales.forEach(function (total) {
    if (total.seccion && total.seccion !== seccionAnterior) {
      seccionAnterior = total.seccion;
      const cabecera = document.createElement("p");
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

  cajaTotales.appendChild(lista);
}

async function generar(desdeLaHoja) {
  botonGenerar.disabled = true;
  botonRecalcular.disabled = true;
  progreso.classList.remove("oculto");
  progresoTexto.textContent = "Armando el archivo y revisando las fórmulas…"
    + " Puede tardar unos segundos.";
  if (desdeLaHoja) {
    textoPendientes.textContent = "Calculando los totales…";
  }
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

    if (informe.recalculo) {
      resultado.appendChild(lineaResultado(
        informe.recalculo.motivo,
        informe.recalculo.recalculado ? "ayuda" : "resultado-aviso"
      ));
    }

    if (informe.totales && informe.totales.length > 0) {
      dibujarTotales(informe.totales);
    }

    resultado.classList.remove("oculto");
    enlaceArchivo.classList.remove("oculto");
    enlaceArchivo.href = "/api/clientes/" + idCliente + "/formulario/archivo";
    avisar("Totales actualizados. El archivo quedó listo para descargar.",
           "exito");

    await cargarHoja();
    cargarHistorial();
  } catch (error) {
    avisar(error.message, "error");
    resultado.textContent = "";
    resultado.appendChild(lineaResultado(error.message, "resultado-mal"));
    resultado.classList.remove("oculto");
    enlaceArchivo.classList.add("oculto");
  } finally {
    botonGenerar.disabled = false;
    botonRecalcular.disabled = false;
    progreso.classList.add("oculto");
  }
}


/* ----------------------------------------------------------
   Historial
   ---------------------------------------------------------- */

function fechaCorta(texto) {
  const fecha = new Date(texto);
  if (isNaN(fecha)) return texto;
  return fecha.toLocaleString("es-CO", {
    day: "2-digit", month: "2-digit", hour: "numeric", minute: "2-digit"
  });
}

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


/* ----------------------------------------------------------
   La plantilla: cuál se usa y cómo subir otra
   ---------------------------------------------------------- */

function avisarPlantilla(texto, tipo) {
  avisoPlantilla.textContent = texto;
  avisoPlantilla.className = "aviso aviso-" + tipo;
}

function dibujarSelectorPlantillas(plantilla) {
  selectorPlantilla.textContent = "";
  (plantilla.disponibles || []).forEach(function (nombre) {
    const opcion = document.createElement("option");
    opcion.value = nombre;
    opcion.textContent = nombre;
    selectorPlantilla.appendChild(opcion);
  });
  selectorPlantilla.value = plantilla.archivo;
}

async function cambiarPlantilla() {
  try {
    await pedir("/api/plantilla/activa", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre: selectorPlantilla.value })
    });
    avisarPlantilla("Ahora se usa «" + selectorPlantilla.value + "». Revise"
      + " los valores ya anotados: las casillas de una plantilla no tienen"
      + " por qué significar lo mismo en otra.", "fechas");
    await cargarValores();
    await cargarHoja();
  } catch (error) {
    avisarPlantilla(error.message, "error");
  }
}

async function subirPlantilla(archivo) {
  if (!archivo) return;
  avisarPlantilla("Revisando «" + archivo.name + "»…", "fechas");

  const paquete = new FormData();
  paquete.append("archivo", archivo);

  try {
    const plantilla = await pedir("/api/plantilla", {
      method: "POST", body: paquete
    });
    dibujarSelectorPlantillas(plantilla);
    avisarPlantilla("Listo: ahora se usa «" + plantilla.guardada + "». Tiene "
      + plantilla.celdas_de_captura + " casillas para capturar.", "exito");
    sinPlantilla.classList.add("oculto");
    bloque.classList.remove("oculto");
    await cargarValores();
    await cargarHoja();
  } catch (error) {
    avisarPlantilla(error.message, "error");
  }
}


/* ----------------------------------------------------------
   Arranque

   La hoja no se carga hasta que el contador abre la sección: son 562
   filas y no vale la pena traerlas si no las va a mirar.
   ---------------------------------------------------------- */

let hojaPedida = false;

async function arrancar() {
  prepararPestanas();

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
  dibujarSelectorPlantillas(plantilla);

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
  cargarHistorial();
}

const plegable = document.getElementById("plegable-formulario");
plegable.addEventListener("toggle", function () {
  if (plegable.open && !hojaPedida) {
    hojaPedida = true;
    cargarHoja();
  }
});

/* Cuando RentAI anota una propuesta, la hoja y la lista se refrescan
   solas: el contador no tiene por qué recargar la página. */
document.addEventListener("valor-anotado", async function () {
  await cargarValores();
  if (hojaPedida) await cargarHoja();
});

filtroHoja.addEventListener("input", dibujarHoja);
soloConValor.addEventListener("change", dibujarHoja);
botonRecalcular.addEventListener("click", function () { generar(true); });
botonGenerar.addEventListener("click", function () { generar(false); });
selectorPlantilla.addEventListener("change", cambiarPlantilla);
botonSubirPlantilla.addEventListener("click", function () {
  campoPlantilla.click();
});
if (botonSubirPlantilla1) {
  botonSubirPlantilla1.addEventListener("click", function () {
    campoPlantilla.click();
  });
}
campoPlantilla.addEventListener("change", function () {
  subirPlantilla(campoPlantilla.files[0]);
  campoPlantilla.value = "";
});

arrancar();

})();
