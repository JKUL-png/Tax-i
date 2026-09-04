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
const cajaCruce = document.getElementById("cruce");

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

  /* La casilla va PRIMERO, antes del renglón. El contador trabaja con
     la hoja de Excel abierta al lado: lo que busca es G132, no R33.
     R33 es la palabra de la DIAN —así viene escrita en la exógena— y
     por eso no se puede quitar; pero no es por donde él entra.

     Un renglón puede repartirse en varias casillas: R32 tiene nueve
     filas de detalle en la plantilla. Cuando son más de dos se dice
     cuántas en vez de listarlas, que ocuparía más que el nombre. */
  const casillas = (renglon.totales_por_casilla || [])
    .map(function (uno) { return uno.celda; })
    .filter(function (celda) { return !!celda; });

  const donde = document.createElement("span");
  donde.className = "propuesta-donde-va";
  if (casillas.length === 0) {
    donde.className = "propuesta-falta";
    donde.textContent = "sin casilla";
    donde.title = "Ninguno de sus valores tiene casilla escogida todavía."
                + " Ábralos abajo y escoja.";
  } else if (casillas.length <= 2) {
    donde.textContent = casillas.join(", ");
  } else {
    donde.textContent = casillas.length + " casillas";
    donde.title = casillas.join(", ");
  }
  titulo.appendChild(donde);

  const separador = document.createElement("span");
  separador.className = "propuesta-separador";
  separador.textContent = " · ";
  titulo.appendChild(separador);

  const cual = document.createElement("span");
  cual.className = "propuesta-renglon-nombre";
  cual.textContent = renglon.renglon + " — " + (renglon.nombre || "");
  titulo.appendChild(cual);

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

  /* Igual que arriba: primero dónde se escribe, después cuánto. */
  let casilla = document.createElement("span");
  if (componente.celda) {
    casilla.className = "propuesta-donde-va";
    casilla.textContent = componente.celda;
    casilla.title = componente.celda_motivo || "";
  } else if (componente.estado === "propuesto") {
    /* No es un rótulo: es un botón. Antes decía «escoja la casilla» y
       lo dejaba a uno buscando en la hoja de captura cuál era. Ahora
       abre la lista de las filas de ese renglón, con la etiqueta que
       trae cada una en la plantilla, que es lo que permite reconocerla. */
    casilla = document.createElement("button");
    casilla.type = "button";
    casilla.className = "propuesta-falta propuesta-escoger";
    casilla.textContent = "escoja la casilla";
    casilla.dataset.id = componente.id;
    casilla.dataset.renglon = componente.renglon;
    casilla.title = "Ese renglón tiene varias filas de detalle en su"
                  + " plantilla. Ábralo y escoja en cuál va.";
  } else {
    casilla.className = "propuesta-falta";
    casilla.textContent = "—";
  }
  linea.appendChild(casilla);

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
    await cargarElCruce();
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
    return valor.celda + "   " + pesos(valor.numero)
         + "   " + valor.renglon + " (nivel " + valor.nivel + ")";
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

/* ----------------------------------------------------------
   Escoger la casilla

   El renglón ya está decidido —lo decidió la DIAN en la exógena o lo
   escogió él—. Lo que falta es en cuál FILA de su hoja de trabajo va,
   y eso no es una decisión tributaria: se resuelve leyendo la etiqueta
   de la fila. El programa lo intenta solo; cuando dos filas empatan,
   pregunta, y lo que él escoja se recuerda para no volvérselo a
   preguntar.
   ---------------------------------------------------------- */

async function abrirLasCasillas(boton) {
  /* Si ya estaba abierto, se cierra: el mismo clic sirve para las dos. */
  const abierta = boton.parentElement.parentElement
                       .querySelector(".propuesta-casillas");
  if (abierta) {
    abierta.remove();
    boton.classList.remove("propuesta-escoger-abierto");
    return;
  }

  boton.disabled = true;
  let datos;
  try {
    datos = await pedir("/pasada/casillas?renglon="
                        + encodeURIComponent(boton.dataset.renglon));
  } catch (e) {
    avisar(e.message || "No se pudieron cargar las casillas.");
    boton.disabled = false;
    return;
  }
  boton.disabled = false;
  boton.classList.add("propuesta-escoger-abierto");

  const caja = document.createElement("div");
  caja.className = "propuesta-casillas";

  const titulo = document.createElement("p");
  titulo.className = "propuesta-casillas-titulo";
  titulo.textContent = datos.casillas.length
    ? "¿En cuál fila de " + datos.renglon + " va esta cifra?"
    : (datos.motivo || "Ese renglón no tiene casillas en esta plantilla.");
  caja.appendChild(titulo);

  datos.casillas.forEach(function (una) {
    const opcion = document.createElement("button");
    opcion.type = "button";
    opcion.className = "propuesta-casilla-opcion";
    opcion.dataset.id = boton.dataset.id;
    opcion.dataset.celda = una.celda;

    const codigo = document.createElement("span");
    codigo.className = "propuesta-donde-va";
    codigo.textContent = una.celda;
    opcion.appendChild(codigo);

    const que = document.createElement("span");
    que.className = "propuesta-casilla-que";
    que.textContent = una.descripcion || "(la plantilla no le puso nombre)";
    opcion.appendChild(que);

    const fila = document.createElement("span");
    fila.className = "propuesta-casilla-fila";
    fila.textContent = "fila " + una.fila;
    opcion.appendChild(fila);

    if (una.celda === datos.recordada) {
      const marca = document.createElement("span");
      marca.className = "etiqueta etiqueta-exito";
      marca.textContent = "la que usó antes";
      opcion.appendChild(marca);
    }
    caja.appendChild(opcion);
  });

  boton.parentElement.parentElement.appendChild(caja);
}

async function guardarLaCasilla(id, celda) {
  try {
    mostrar(await pedir("/pasada/casilla", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: Number(id), celda: celda })
    }));
    avisar("Queda en " + celda + ". El programa se acuerda para la"
           + " próxima vez que aparezca ese renglón.", "exito");
  } catch (e) {
    avisar(e.message || "No se pudo guardar la casilla.");
  }
}

lista.addEventListener("click", function (evento) {
  const escoger = evento.target.closest(".propuesta-escoger");
  if (escoger) {
    abrirLasCasillas(escoger);
    return;
  }
  const opcion = evento.target.closest(".propuesta-casilla-opcion");
  if (opcion) {
    guardarLaCasilla(opcion.dataset.id, opcion.dataset.celda);
  }
});


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
   El cruce: sus papeles contra lo que reportó la DIAN

   Sin IA y sin costo: dos listas de números que ya están en la base y
   una resta. Va arriba de la propuesta porque es lo primero que él
   mira cuando ya tiene las dos cosas cargadas.

   «Diferencia» significa REVÍSELO. Nunca «está mal» ni «hay un error»:
   la cifra de la DIAN puede estar desactualizada —ella misma lo
   advierte— y el certificado puede estar incompleto. Quién tiene la
   razón lo decide él.
   ---------------------------------------------------------- */

const CRUCE = {
  diferencia: {
    etiqueta: "Diferencia",
    frase: function (h) {
      return "La DIAN reporta " + pesos(h.dian) + " y sus documentos dicen "
           + pesos(h.papeles) + ". Se diferencian en "
           + pesos(Math.abs(h.diferencia)) + ".";
    }
  },
  sin_soporte: {
    etiqueta: "Sin soporte",
    frase: function (h) {
      return "La DIAN reporta " + pesos(h.dian)
           + " y todavía no hay ningún documento que lo respalde.";
    }
  },
  sin_reportar: {
    etiqueta: "Sin reportar",
    frase: function (h) {
      return "Sus documentos dicen " + pesos(h.papeles)
           + " y ningún tercero le reportó eso a la DIAN. Es normal: no"
           + " todo se reporta.";
    }
  },
  coincide: {
    etiqueta: "Coincide",
    frase: function (h) {
      return "La DIAN y sus documentos dicen lo mismo: " + pesos(h.dian) + ".";
    }
  }
};

/* Qué se muestra abierto de entrada. Lo que coincide no: son las que no
   hay que mirar, y ocuparían la pantalla entera. */
const CRUCE_A_LA_VISTA = ["diferencia", "sin_soporte", "sin_reportar"];

function dibujarCruce(informe) {
  cajaCruce.innerHTML = "";
  if (!informe || !informe.hay_exogena) {
    cajaCruce.classList.add("oculto");
    return;
  }
  cajaCruce.classList.remove("oculto");

  const caja = document.createElement("div");
  caja.className = "tarjeta";

  const titulo = document.createElement("p");
  titulo.className = "propuesta-conteo";
  if (!informe.hay_propuesta) {
    titulo.textContent = "Sus papeles contra lo que reportó la DIAN";
    caja.appendChild(titulo);
    const espera = document.createElement("p");
    espera.className = "ayuda";
    espera.textContent = "La exógena ya está cargada. Pida la propuesta del"
                       + " formulario y aquí aparece, renglón por renglón,"
                       + " en qué se diferencian sus documentos de lo que"
                       + " los terceros le reportaron a la DIAN.";
    caja.appendChild(espera);
    cajaCruce.appendChild(caja);
    return;
  }

  const partes = [];
  if (informe.diferencias) {
    partes.push(contar(informe.diferencias, "renglón se diferencia",
                       "renglones se diferencian"));
  }
  if (informe.sin_soporte) {
    partes.push(contar(informe.sin_soporte, "sin soporte", "sin soporte"));
  }
  if (informe.sin_reportar) {
    partes.push(contar(informe.sin_reportar, "que nadie reportó",
                       "que nadie reportó"));
  }
  titulo.textContent = partes.length
    ? "Sus papeles y la DIAN: " + partes.join(" · ")
    : "Sus papeles y la DIAN dicen lo mismo en todos los renglones.";
  caja.appendChild(titulo);

  const explica = document.createElement("p");
  explica.className = "ayuda";
  explica.textContent = "Se compara por renglón, que es lo único que se puede"
                      + " afirmar sin suponer cuál fila de la exógena"
                      + " corresponde a cuál papel. Una diferencia no dice"
                      + " quién tiene la razón: dice que hay que mirarla.";
  caja.appendChild(explica);

  const lista = document.createElement("div");
  lista.className = "cruce-lista";
  informe.hallazgos
    .filter(function (h) { return CRUCE_A_LA_VISTA.indexOf(h.estado) !== -1; })
    .forEach(function (h) { lista.appendChild(dibujarHallazgo(h)); });
  if (lista.children.length) caja.appendChild(lista);

  if (informe.requieren_decision.length) {
    const aparte = document.createElement("p");
    aparte.className = "ayuda";
    aparte.textContent = contar(informe.requieren_decision.length,
      "registro de la exógena no entra en el cruce",
      "registros de la exógena no entran en el cruce")
      + " porque la DIAN propone más de un renglón para ellos. Elegir es"
      + " criterio suyo: están en la pestaña Exógena.";
    caja.appendChild(aparte);
  }

  cajaCruce.appendChild(caja);
}

function dibujarHallazgo(h) {
  const fila = document.createElement("div");
  fila.className = "cruce-fila cruce-" + h.estado;

  const cabecera = document.createElement("div");
  cabecera.className = "cruce-cabecera";

  const etiqueta = document.createElement("span");
  etiqueta.className = "etiqueta cruce-etiqueta-" + h.estado;
  etiqueta.textContent = CRUCE[h.estado].etiqueta;
  cabecera.appendChild(etiqueta);

  const cual = document.createElement("span");
  cual.className = "cruce-renglon";
  cual.textContent = h.renglon + (h.nombre ? " — " + h.nombre : "");
  cabecera.appendChild(cual);
  fila.appendChild(cabecera);

  const frase = document.createElement("p");
  frase.className = "cruce-frase";
  frase.textContent = CRUCE[h.estado].frase(h);
  fila.appendChild(frase);

  /* Quién reportó qué, y con cuál papel. Sin esto el aviso obliga a
     irse a otra pestaña a averiguar de dónde salió cada lado. */
  if (h.filas.length) {
    fila.appendChild(dibujarLado("La DIAN", h.filas.map(function (f) {
      return pesos(f.valor) + "  " + (f.tercero || "") + " — " + f.detalle;
    })));
  }
  if (h.documentos.length) {
    fila.appendChild(dibujarLado("Sus documentos",
      h.documentos.map(function (d) {
        return pesos(d.valor) + "  " + (d.nombre || "");
      })));
  }
  return fila;
}

function dibujarLado(quien, lineas) {
  const caja = document.createElement("div");
  caja.className = "cruce-lado";
  const nombre = document.createElement("span");
  nombre.className = "cruce-quien";
  nombre.textContent = quien + ":";
  caja.appendChild(nombre);
  const lista = document.createElement("ul");
  lineas.forEach(function (texto) {
    const uno = document.createElement("li");
    uno.textContent = texto;
    lista.appendChild(uno);
  });
  caja.appendChild(lista);
  return caja;
}


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

async function cargarElCruce() {
  try {
    dibujarCruce(await pedir("/cruce"));
  } catch (e) {
    /* Sin exógena no hay nada que cruzar, y eso no es un error. */
  }
}

async function cargar() {
  try {
    mostrar(await pedir("/pasada"));
  } catch (e) {
    avisar(e.message || "No se pudo cargar la propuesta.");
  }
  await cargarElCruce();
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
