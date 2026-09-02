/* ==========================================================
   El respaldo de TODO el programa.

   No es de un cliente: es de todos. Un archivo con la base entera y los
   documentos, para llevárselo a un disco externo.

   Es lo más importante de esta pantalla. Si se le daña el disco al
   contador en octubre, sin esto pierde el trabajo de la temporada.

   Restaurar va en dos pasos a propósito: primero se mira qué trae el
   archivo y se le dice al contador, y solo después de que confirme se
   toca algo. Restaurar encima del trabajo de una temporada no puede ser
   un solo clic.
   ========================================================== */

const botonRespaldo = document.getElementById("boton-respaldo");
const progresoRespaldo = document.getElementById("progreso-respaldo");
const progresoRespaldoTexto = document.getElementById("progreso-respaldo-texto");

const botonRestaurar = document.getElementById("boton-restaurar");
const campoRespaldo = document.getElementById("campo-respaldo");
const revisionRespaldo = document.getElementById("revision-respaldo");
const avisoRespaldo = document.getElementById("aviso-respaldo");

function avisarRespaldo(texto, tipo) {
  avisarEn(avisoRespaldo, texto, tipo);
}

/* ----------------------------------------------------------
   Llevarse todo
   ---------------------------------------------------------- */

if (botonRespaldo) {
  botonRespaldo.addEventListener("click", async function () {
    botonRespaldo.disabled = true;
    progresoRespaldo.classList.remove("oculto");
    ocultarAvisoEn(avisoRespaldo);

    // Armar el ZIP con doscientos documentos escaneados tarda. El reloj
    // dice que sigue vivo y cuánto lleva. Vive en comun.js.
    const reloj = relojDeProgreso(progresoRespaldoTexto);
    reloj.paso("Empacando la base de datos y todos los documentos…");

    try {
      const respuesta = await fetch("/api/respaldo");
      if (!respuesta.ok) {
        throw new Error(await textoDelError(
          respuesta, "No se pudo armar el respaldo."
        ));
      }

      // El navegador no puede guardar por su cuenta: se arma un enlace
      // invisible y se le da clic. El nombre lo manda el servidor.
      const paquete = await respuesta.blob();
      const direccion = URL.createObjectURL(paquete);
      const enlace = document.createElement("a");
      enlace.href = direccion;
      enlace.download = nombreDelRespaldo(respuesta);
      document.body.appendChild(enlace);
      enlace.click();
      document.body.removeChild(enlace);
      URL.revokeObjectURL(direccion);

      avisarRespaldo(
        "Respaldo listo (" + pesoEnPalabras(paquete.size) + "). Guárdelo en"
        + " un disco externo o en una memoria USB.",
        "exito"
      );
    } catch (error) {
      avisarRespaldo(error.message || "No se pudo armar el respaldo.", "error");
    } finally {
      reloj.detener();
      progresoRespaldo.classList.add("oculto");
      botonRespaldo.disabled = false;
    }
  });
}

/* El nombre que mandó el servidor en la cabecera, o uno de reserva. */
function nombreDelRespaldo(respuesta) {
  const cabecera = respuesta.headers.get("Content-Disposition") || "";
  const encontrado = cabecera.match(/filename\*=UTF-8''([^;]+)/);
  if (encontrado) {
    try {
      return decodeURIComponent(encontrado[1]);
    } catch (e) {
      // Si viene mal codificado se usa el de reserva.
    }
  }
  return "Tax-i respaldo.zip";
}

/* ----------------------------------------------------------
   Restaurar: primero mirar, después confirmar
   ---------------------------------------------------------- */

if (botonRestaurar) {
  botonRestaurar.addEventListener("click", function () {
    campoRespaldo.click();
  });
}

if (campoRespaldo) {
  campoRespaldo.addEventListener("change", async function () {
    const archivo = campoRespaldo.files[0];
    if (!archivo) return;

    ocultarAvisoEn(avisoRespaldo);
    revisionRespaldo.classList.add("oculto");
    revisionRespaldo.textContent = "";

    try {
      const cuerpo = new FormData();
      cuerpo.append("archivo", archivo, archivo.name);
      const respuesta = await fetch("/api/respaldo/revisar", {
        method: "POST", body: cuerpo
      });
      if (!respuesta.ok) {
        throw new Error(await textoDelError(
          respuesta, "No se pudo leer ese archivo."
        ));
      }
      mostrarQueTrae(await respuesta.json(), archivo);
    } catch (error) {
      avisarRespaldo(error.message || "No se pudo leer ese archivo.", "error");
    } finally {
      // Se limpia para que escoger el MISMO archivo otra vez vuelva a
      // disparar el change.
      campoRespaldo.value = "";
    }
  });
}

/* Le dice al contador qué trae el archivo y qué va a pasar, y le pone el
   botón para confirmar. Nada se toca hasta que apriete ese botón. */
function mostrarQueTrae(informacion, archivo) {
  revisionRespaldo.textContent = "";

  const titulo = document.createElement("p");
  titulo.className = "resultado-bien";
  titulo.textContent = "Ese archivo es un respaldo de Tax-i. Trae "
    + contar(informacion.documentos, "documento", "documentos")
    + " y " + pesoEnPalabras(informacion.tamano) + ".";
  revisionRespaldo.appendChild(titulo);

  const aviso = document.createElement("p");
  aviso.className = "resultado-aviso";
  aviso.textContent = "Al restaurar, este respaldo REEMPLAZA lo que hay"
    + " ahora en el programa. Lo que hay ahora no se borra: queda guardado"
    + " en una carpeta dentro de datos/, con la fecha en el nombre.";
  revisionRespaldo.appendChild(aviso);

  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = "boton";
  boton.textContent = "Sí, restaurar este respaldo";
  boton.addEventListener("click", function () {
    restaurarDeVerdad(archivo, boton);
  });
  revisionRespaldo.appendChild(boton);

  revisionRespaldo.classList.remove("oculto");
}

async function restaurarDeVerdad(archivo, boton) {
  boton.disabled = true;
  boton.textContent = "Restaurando…";
  try {
    const cuerpo = new FormData();
    cuerpo.append("archivo", archivo, archivo.name);
    const respuesta = await fetch("/api/respaldo/restaurar", {
      method: "POST", body: cuerpo
    });
    if (!respuesta.ok) {
      throw new Error(await textoDelError(
        respuesta, "No se pudo restaurar el respaldo."
      ));
    }
    const informe = await respuesta.json();

    revisionRespaldo.textContent = "";
    const listo = document.createElement("p");
    listo.className = "resultado-bien";
    listo.textContent = "Restaurado: "
      + contar(informe.clientes, "cliente", "clientes") + " y "
      + contar(informe.documentos, "documento", "documentos") + "."
      + (informe.copia_de_seguridad
          ? " Lo que había antes quedó guardado en "
            + informe.copia_de_seguridad + "."
          : "");
    revisionRespaldo.appendChild(listo);

    const nota = document.createElement("p");
    nota.className = "ayuda";
    nota.textContent = "Vuelva a la lista de clientes para verlos. Si usaba"
      + " IA, la llave hay que escribirla otra vez en Cuenta: el respaldo"
      + " no la lleva.";
    revisionRespaldo.appendChild(nota);
  } catch (error) {
    avisarRespaldo(error.message || "No se pudo restaurar el respaldo.",
                   "error");
    boton.disabled = false;
    boton.textContent = "Sí, restaurar este respaldo";
  }
}
