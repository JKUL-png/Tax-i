/* ==========================================================
   La pantalla de inicio

   Lo único que necesita: decir cuántos clientes hay cargados, para que
   la portada no sea un folleto sino el estado real del programa. Si
   todavía no hay ninguno, lo dice y el botón de al lado es lo que hay
   que hacer.

   Todo lo demás de esta pantalla es texto fijo en el HTML.
   ========================================================== */

(function () {
  "use strict";

  var caja = document.getElementById("inicio-cuenta");
  if (!caja) return;

  fetch("/api/clientes")
    .then(function (respuesta) {
      if (!respuesta.ok) throw new Error();
      return respuesta.json();
    })
    .then(function (clientes) {
      if (clientes.length === 0) {
        caja.textContent = "Todavía no hay ningún cliente cargado.";
        return;
      }

      /* Cuántos tienen algo pendiente. Es la pregunta de la temporada, y
         la cuenta es la misma que hace el riel: total menos recibidos. */
      var pendientes = clientes.filter(function (c) {
        var total = c.checklist_total || 0;
        return total === 0 || (c.checklist_recibidos || 0) < total;
      }).length;

      caja.textContent =
        contar(clientes.length, "cliente cargado", "clientes cargados") +
        (pendientes > 0
          ? " · " + contar(pendientes, "con algo pendiente", "con algo pendiente")
          : " · ninguno con pendientes");
    })
    .catch(function () {
      /* Sin servidor no se pone nada: la portada se lee igual, y el
         riel de al lado ya avisa que no se pudo conectar. */
    });
})();
