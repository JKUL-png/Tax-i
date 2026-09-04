/* ==========================================================
   La propuesta del formulario

   Una sola llamada al modelo con la exógena y todos los documentos del
   cliente adentro, y sale el Formulario 210 propuesto entero.

   Lo que esta pantalla tiene que dejar clarísimo, en este orden:

     1. Es una PROPUESTA. Nada entró al formulario todavía.
     2. Dónde mirar primero. Los de nivel C van en amarillo porque los
        interpretó el modelo; los A y B se pueden aceptar en bloque.
     3. De dónde salió cada cifra, con la frase del papel a la vista y
        el documento a un clic.

   El nivel NO filtra ni bloquea nada: todo llega lleno. Solo dice
   dónde mirar primero.
   ========================================================== */

(function () {

const panel = document.getElementById("panel-propuesta");
if (!panel) return;

const cajaAviso = document.getElementById("propuesta-aviso");
const cajaSinIa = document.getElementById("propuesta-sin-ia");
const textoMotivo = document.getElementById("propuesta-motivo");
const cajaArrancar = document.getElementById("propuesta-arrancar");
const textoEstimado = document.getElementById("propuesta-estimado");
const botonProponer = document.getElementById("boton-proponer");
const cajaResultado = document.getElementById("propuesta-resultado");
const textoConteo = document.getElementById("propuesta-conteo");
const textoFicha = document.getElementById("propuesta-ficha");
const botonBloque = document.getElementById("boton-aprobar-bloque");
const botonReproponer = document.getElementById("boton-reproponer");
const lista = document.getElementById("propuesta-lista");
const conteoPestana = document.getElementById("conteo-propuesta");
const botonComparar = document.getElementById("boton-comparar");
const campoComparar = document.getElementById("campo-comparar");
const cajaComparacion = document.getElementById("comparacion-resultado");

let cliente = null;
let ultimo = null;

/* Cómo se lee cada nivel. El texto es el que ve el contador al pasar el
   cursor, y es lo que hace que la letra signifique algo. */
const NIVELES = {
  A: {
    marca: "",
    titulo: "Dato directo: la propia fuente dice a qué renglón va."
  },
  B: {
    marca: "◆",
    titulo: "Regla de la DIAN aplicada: el «Uso declaración Sugerida»"
          + " traía una condición y se cumple."
  },
  C: {
    marca: "",
    titulo: "Lo interpretó el modelo. Revíselo."
  }
};


/* ----------------------------------------------------------
   Pedirle cosas al servidor
   ---------------------------------------------------------- */

async function pedir(camino, opciones) {
  const respuesta = await fetch("/api/clientes/" + cliente + camino,
                                opciones || {});
  if (!respuesta.ok) throw new Error(await textoDelError(respuesta));
  return respuesta.json();
}

function avisar(texto, tipo) {
  avisarEn(cajaAviso, texto, tipo || "error");
}


/* ----------------------------------------------------------
   Dibujar
   ---------------------------------------------------------- */

function pesos(valor) {
  if (valor === null || valor === undefined) return "—";
  return "$" + Math.round(valor).toLocaleString("es-CO");
}

function mostrar(informe) {
  ultimo = informe;

  cajaSinIa.classList.toggle("oculto", !!informe.ia_disponible);
  if (!informe.ia_disponible) {
    textoMotivo.textContent = informe.motivo || "";
  }

  const hay = informe.hay_pasada && informe.renglones.length > 0;
  cajaArrancar.classList.toggle("oculto", !informe.ia_disponible || hay);
  cajaResultado.classList.toggle("oculto", !hay);

  if (conteoPestana) {
    conteoPestana.textContent = hay ? String(informe.propuestos) : "";
  }
  if (!hay) {
    if (informe.ia_disponible) pedirElEstimado();
    return;
  }

  /* El contador de arriba, que es lo primero que se lee. */
  const partes = [
    contar(informe.propuestos, "valor propuesto", "valores propuestos")
  ];
  if (informe.para_revisar) {
    partes.push(informe.para_revisar + " requieren su revisión");
  }
  if (informe.en_revision_manual) {
    partes.push(contar(informe.en_revision_manual,
                       "quedó para revisión manual",
                       "quedaron para revisión manual"));
  }
  if (informe.sin_casilla) {
    partes.push(contar(informe.sin_casilla,
                       "sin casilla escogida", "sin casilla escogida"));
  }
  textoConteo.textContent = partes.join(" — ");

  const pasada = informe.pasada || {};
  const fichas = [];
  if (pasada.modelo) fichas.push("Propuesto por " + pasada.modelo);
  if (pasada.tokens_entrada) {
    fichas.push((pasada.tokens_entrada + pasada.tokens_salida)
                .toLocaleString("es-CO") + " tokens");
  }
  if (pasada.costo_usd) {
    fichas.push("≈ US$" + pasada.costo_usd.toFixed(3) + " (aproximado)");
  }
  if (pasada.estado === "parcial") {
    fichas.push("Quedó incompleta: " + (pasada.motivo || ""));
  }
  textoFicha.textContent = fichas.join(" · ");

  lista.innerHTML = "";
  informe.renglones.forEach(function (renglon) {
    lista.appendChild(dibujarRenglon(renglon));
  });
}

function dibujarRenglon(renglon) {
  const caja = document.createElement("div");
  caja.className = "propuesta-renglon nivel-" + renglon.nivel;
  if (renglon.conflicto) caja.classList.add("propuesta-conflicto");

  const cabecera = document.createElement("div");
  cabecera.className = "propuesta-cabecera";

  const titulo = document.createElement("div");
  titulo.className = "propuesta-titulo";
  const ficha = NIVELES[renglon.nivel] || NIVELES.C;
  titulo.textContent = renglon.renglon + " — " + (renglon.nombre || "");
  if (ficha.marca) {
    const marca = document.createElement("span");
    marca.className = "propuesta-marca";
    marca.textContent = " " + ficha.marca;
    marca.title = ficha.titulo;
    titulo.appendChild(marca);
  }
  if (renglon.nivel === "C") {
    const etiqueta = document.createElement("span");
    etiqueta.className = "etiqueta etiqueta-revisar";
    etiqueta.textContent = "Revisar";
    etiqueta.title = ficha.titulo;
    titulo.appendChild(etiqueta);
  }
  cabecera.appendChild(titulo);

  const total = document.createElement("div");
  total.className = "propuesta-total cifra";
  total.textContent = pesos(renglon.total);
  cabecera.appendChild(total);
  caja.appendChild(cabecera);

  if (renglon.conflicto) {
    const aviso = document.createElement("p");
    aviso.className = "propuesta-conflicto-texto";
    aviso.textContent = "Dos bloques de documentos propusieron cosas"
                      + " distintas para este renglón. Revíselos juntos.";
    caja.appendChild(aviso);
  }

  renglon.componentes.forEach(function (componente) {
    caja.appendChild(dibujarComponente(componente));
  });
  return caja;
}

function dibujarComponente(componente) {
  const fila = document.createElement("div");
  fila.className = "propuesta-componente estado-" + componente.estado;

  const linea = document.createElement("div");
  linea.className = "propuesta-linea";

  if (componente.estado === "propuesto") {
    const marca = document.createElement("input");
    marca.type = "checkbox";
    marca.className = "propuesta-marcar";
    marca.dataset.id = componente.id;
    marca.disabled = !componente.verificada || !componente.celda;
    linea.appendChild(marca);
  }

  const cifra = document.createElement("span");
  cifra.className = "cifra propuesta-cifra";
  cifra.textContent = componente.numero === null
    ? (componente.valor || "—") : pesos(componente.numero);
  linea.appendChild(cifra);

  const donde = document.createElement("span");
  donde.className = "propuesta-donde";
  if (componente.fuente === "documento") {
    const enlace = document.createElement("a");
    enlace.href = "/api/documentos/" + componente.documento_id + "/archivo";
    enlace.target = "_blank";
    enlace.rel = "noopener";
    enlace.textContent = componente.nombre_original || componente.referencia;
    donde.appendChild(enlace);
  } else {
    donde.textContent = "Exógena, registro " + componente.referencia.slice(1);
  }
  linea.appendChild(donde);

  if (componente.celda) {
    const casilla = document.createElement("span");
    casilla.className = "propuesta-casilla";
    casilla.textContent = "→ " + componente.celda;
    casilla.title = componente.celda_motivo || "";
    linea.appendChild(casilla);
  } else if (componente.estado === "propuesto") {
    const falta = document.createElement("span");
    falta.className = "propuesta-casilla propuesta-falta";
    falta.textContent = "→ escoja la casilla";
    falta.title = "Ese renglón tiene varias filas de detalle y ninguna"
                + " gana claramente. La escoge usted, en la hoja de captura.";
    linea.appendChild(falta);
  }

  if (componente.estado === "aprobado") {
    const marca = document.createElement("span");
    marca.className = "etiqueta etiqueta-exito";
    marca.textContent = "Anotado";
    linea.appendChild(marca);
  }
  fila.appendChild(linea);

  /* La cita, que es lo que hace verificable la cifra. */
  if (componente.cita) {
    const cita = document.createElement("p");
    cita.className = "propuesta-cita";
    cita.textContent = "«" + componente.cita + "»";
    fila.appendChild(cita);
  }
  if (componente.nota) {
    const nota = document.createElement("p");
    nota.className = "propuesta-nota";
    nota.textContent = componente.nota;
    fila.appendChild(nota);
  }
  if (componente.motivo) {
    const motivo = document.createElement("p");
    motivo.className = "propuesta-motivo";
    motivo.textContent = componente.motivo;
    fila.appendChild(motivo);
  }
  return fila;
}


/* ----------------------------------------------------------
   Correr la pasada
   ---------------------------------------------------------- */

async function pedirElEstimado() {
  try {
    const datos = await pedir("/pasada/estimado");
    if (!datos.ia_disponible) return;
    const partes = [
      contar(datos.documentos, "documento con texto",
             "documentos con texto"),
      contar(datos.filas_exogena, "registro de exógena",
             "registros de exógena")
    ];
    if (datos.bloques > 1) {
      partes.push("se manda en " + datos.bloques + " bloques");
    }
    let texto = partes.join(" · ") + ". Cuesta unos "
              + datos.tokens_estimados.toLocaleString("es-CO")
              + " tokens";
    if (datos.costo_estimado) {
      texto += ", más o menos US$" + datos.costo_estimado.toFixed(3);
    }
    texto += ".";
    if (datos.sin_texto.length) {
      texto += " " + contar(datos.sin_texto.length,
                            "documento no tiene texto legible y no se manda",
                            "documentos no tienen texto legible y no se mandan")
             + ".";
    }
    textoEstimado.textContent = texto;
  } catch (e) {
    textoEstimado.textContent = "";
  }
}

async function proponer() {
  botonProponer.disabled = true;
  if (botonReproponer) botonReproponer.disabled = true;
  const antes = botonProponer.textContent;
  botonProponer.textContent = "Leyendo todo y proponiendo…";
  try {
    const informe = await pedir("/pasada", { method: "POST" });
    mostrar(informe);
    avisar("Listo. Nada entró al formulario todavía: revise y apruebe.",
           "exito");
  } catch (e) {
    avisar(e.message || "No se pudo proponer el formulario.");
  } finally {
    botonProponer.disabled = false;
    botonProponer.textContent = antes;
    if (botonReproponer) botonReproponer.disabled = false;
  }
}


/* ----------------------------------------------------------
   Aprobar

   En bloque solo los de nivel A y B, y SIEMPRE mostrando la lista
   completa antes de confirmar. Los de nivel C, uno por uno.
   ---------------------------------------------------------- */

async function aprobarEnBloque() {
  let datos;
  try {
    datos = await pedir("/pasada/en-bloque");
  } catch (e) {
    avisar(e.message || "No se pudo armar la lista.");
    return;
  }
  if (!datos.cuantos) {
    avisar("No hay ninguna propuesta de nivel A o B lista para aceptar.",
           "aviso");
    return;
  }

  const nombres = datos.valores.map(function (valor) {
    return valor.renglon + " → " + valor.celda + "   "
         + pesos(valor.numero) + "   (nivel " + valor.nivel + ")";
  });
  const seguro = await preguntar({
    titulo: "Aceptar " + datos.cuantos + " valores",
    frase: "Se van a anotar en el Formulario 210 de este cliente. Los de"
         + " nivel C no se tocan: esos se revisan uno por uno.",
    nombres: nombres,
    maximo: nombres.length,
    nota: "Después de aprobar puede cambiar cualquier valor en la hoja"
        + " de captura."
  });
  if (!seguro) return;

  await aprobar(datos.valores.map(function (valor) { return valor.id; }));
}

async function aprobar(ids) {
  try {
    const respuesta = await pedir("/pasada/aprobar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: ids })
    });
    mostrar(respuesta.pasada);
    avisar(contar(respuesta.aprobados, "valor anotado", "valores anotados")
           + " en el Formulario 210.", "exito");
    /* La hoja de captura y la lista de valores se refrescan solas. */
    document.dispatchEvent(new CustomEvent("valor-anotado"));
  } catch (e) {
    avisar(e.message || "No se pudieron anotar los valores.");
  }
}

function marcados() {
  return Array.from(lista.querySelectorAll(".propuesta-marcar:checked"))
              .map(function (marca) { return Number(marca.dataset.id); });
}

lista.addEventListener("change", function (evento) {
  if (!evento.target.classList.contains("propuesta-marcar")) return;
  const cuantos = marcados().length;
  botonBloque.textContent = cuantos
    ? "Aceptar los " + cuantos + " marcados"
    : "Aceptar los de nivel A y B";
});


/* ----------------------------------------------------------
   Modo comparación
   ---------------------------------------------------------- */

function dibujarComparacion(informe) {
  cajaComparacion.classList.remove("oculto");
  cajaComparacion.innerHTML = "";

  const resumen = document.createElement("div");
  resumen.className = "tarjeta comparacion-resumen";
  const titular = document.createElement("p");
  titular.className = "propuesta-conteo";
  titular.textContent = "De lo que Tax-i propuso, coincidió en "
                      + informe.acierto + "%";
  resumen.appendChild(titular);

  const detalle = document.createElement("p");
  detalle.className = "ayuda";
  detalle.textContent =
      informe.coinciden + " coinciden · "
    + informe.difieren + " difieren · "
    + informe.solo_taxi + " los propuso Tax-i y usted los dejó vacíos · "
    + informe.solo_contador + " los llenó usted y Tax-i no los propuso";
  resumen.appendChild(detalle);

  const porNivel = document.createElement("p");
  porNivel.className = "ayuda";
  porNivel.textContent = ["A", "B", "C"].map(function (nivel) {
    const fila = (informe.por_nivel || {})[nivel] || {};
    return "Nivel " + nivel + ": " + (fila.coincide || 0) + " bien / "
         + ((fila.difiere || 0) + (fila.solo_taxi || 0)) + " mal";
  }).join(" · ");
  resumen.appendChild(porNivel);
  cajaComparacion.appendChild(resumen);

  const tabla = document.createElement("div");
  tabla.className = "comparacion-lista";
  (informe.renglones || []).forEach(function (fila) {
    const linea = document.createElement("div");
    linea.className = "comparacion-fila comparacion-" + fila.estado;
    linea.innerHTML = "";
    const nombre = document.createElement("span");
    nombre.className = "comparacion-nombre";
    nombre.textContent = fila.renglon + " " + (fila.nombre || "");
    const nuestro = document.createElement("span");
    nuestro.className = "cifra";
    nuestro.textContent = pesos(fila.taxi);
    const suyo = document.createElement("span");
    suyo.className = "cifra";
    suyo.textContent = pesos(fila.contador);
    const diferencia = document.createElement("span");
    diferencia.className = "cifra comparacion-diferencia";
    diferencia.textContent = fila.estado === "coincide"
      ? "igual" : pesos(fila.diferencia);
    [nombre, nuestro, suyo, diferencia].forEach(function (parte) {
      linea.appendChild(parte);
    });
    tabla.appendChild(linea);
  });
  cajaComparacion.appendChild(tabla);
}

async function comparar(archivo) {
  if (!archivo) return;
  const cuerpo = new FormData();
  cuerpo.append("archivo", archivo);
  try {
    const informe = await pedir("/comparacion", {
      method: "POST", body: cuerpo
    });
    dibujarComparacion(informe);
  } catch (e) {
    avisar(e.message || "No se pudo comparar ese archivo.");
  }
}


/* ----------------------------------------------------------
   Encender
   ---------------------------------------------------------- */

async function cargar() {
  try {
    mostrar(await pedir("/pasada"));
  } catch (e) {
    avisar(e.message || "No se pudo cargar la propuesta.");
  }
  try {
    const guardada = await pedir("/comparacion");
    if (guardada && guardada.renglones) dibujarComparacion(guardada);
  } catch (e) {
    /* Nunca se ha comparado: no hay nada que mostrar y no es un error. */
  }
}

botonProponer.addEventListener("click", proponer);
botonReproponer.addEventListener("click", proponer);
botonBloque.addEventListener("click", function () {
  const escogidos = marcados();
  if (escogidos.length) {
    aprobar(escogidos);
    return;
  }
  aprobarEnBloque();
});
botonComparar.addEventListener("click", function () { campoComparar.click(); });
campoComparar.addEventListener("change", function () {
  comparar(campoComparar.files[0]);
  campoComparar.value = "";
});

window.PasadaTaxi = {
  encender: function (id) {
    cliente = id;
    cargar();
  }
};

})();
