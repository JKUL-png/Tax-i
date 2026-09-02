/* ==========================================================
   La franja del modo demostración.

   Cuando el modo está prendido hay clientes INVENTADOS cargados. Eso
   tiene que ser evidente en TODAS las pantallas, no solo en la de
   Cuenta: si alguien graba un video o le pasa el computador a un colega,
   nadie puede confundir un cliente de ejemplo con uno de verdad.

   Este archivo se carga en todas las pantallas y no hace nada mientras
   el modo esté apagado.
   ========================================================== */

(function () {
  "use strict";

  fetch("/api/demostracion")
    .then(function (respuesta) {
      return respuesta.ok ? respuesta.json() : null;
    })
    .then(function (estado) {
      if (!estado || !estado.activo) return;

      var franja = document.createElement("div");
      franja.className = "franja-demo";
      franja.setAttribute("role", "status");

      var fuerte = document.createElement("strong");
      fuerte.textContent = "MODO DEMOSTRACIÓN PRENDIDO. ";
      franja.appendChild(fuerte);

      franja.appendChild(document.createTextNode(
        "Los clientes marcados con " + (estado.marca || "(EJEMPLO FICTICIO)")
        + " son inventados. Se apaga en Cuenta y ajustes."
      ));

      document.body.insertBefore(franja, document.body.firstChild);
    })
    .catch(function () {
      // Si no se puede preguntar, la pantalla funciona igual. La franja
      // es un aviso, no una parte del programa.
    });
})();
