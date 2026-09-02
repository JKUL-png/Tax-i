/* ==========================================================
   La marca viva

   Dos cosas pequeñas y ninguna decorativa:

   1. El logo parpadea. Cada 6 a 10 segundos, 130 ms. El intervalo va
      salteado a propósito: un parpadeo cada 8 segundos exactos se siente
      mecánico, y lo que se busca es que parezca que hay alguien ahí, no
      que hay un reloj.

   2. La cabecera saca una raya de 1px cuando la página está desplazada,
      y ninguna cuando está arriba. La raya solo aparece cuando de verdad
      hace falta: para que el contenido no se le pegue por debajo.

   Las expresiones son las tres del logo, y cada una dice algo real:

      esperando  los dos ojos abiertos, las dos casillas vacías
      leyendo    los ojos entrecerrados, mientras se lee algo
      listo      el guiño, que es el visto: revisado

   Si el sistema pide menos movimiento, no parpadea nada.
   ========================================================== */

(function () {
  "use strict";

  /* Los tres gestos. Es el mismo trazo: solo cambian los dos huecos.
     Van escritos completos porque un SVG no sabe interpolar trozos. */
  var GESTOS = {
    esperando: "M6 3h13.5L29 12.5V26a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3Z" +
               "m3.2 9.9v5.2h4.4v-5.2H9.2Zm9.2 0v5.2h4.4v-5.2h-4.4Z",
    leyendo:   "M6 3h13.5L29 12.5V26a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3Z" +
               "m3.2 12v2.4h4.4V15H9.2Zm9.2 0v2.4h4.4V15h-4.4Z",
    listo:     "M6 3h13.5L29 12.5V26a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3Z" +
               "m3.2 9.9v5.2h4.4v-5.2H9.2Zm8.4 2.7-1.9 1.9 3.8 3.8 6-6.7-1.9-1.7-4.1 4.6-1.9-1.9Z"
  };

  var quietos = window.matchMedia &&
                window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Le pone un gesto a un logo. Se exporta porque inicio.js lo usa para
     la portada y porque el resto del programa puede pedirlo. */
  function gesto(svg, cual) {
    if (!svg) return;
    var cara = svg.querySelector(".marca-cara");
    if (cara && GESTOS[cual]) cara.setAttribute("d", GESTOS[cual]);
  }

  window.MarcaTaxi = { gesto: gesto, GESTOS: GESTOS };

  document.addEventListener("DOMContentLoaded", function () {

    /* ---------- La raya de la cabecera ---------- */
    /* Vale para las dos: la cabecera de la lista de clientes y la del
       panel de un cliente, que son la misma idea en dos sitios. */
    var cabecera = document.querySelector(".cabecera, .area-cabecera");
    if (cabecera) {
      var mirarDesplazamiento = function () {
        cabecera.classList.toggle("cabecera-desplazada", window.scrollY > 4);
      };
      mirarDesplazamiento();
      window.addEventListener("scroll", mirarDesplazamiento, { passive: true });
    }

    /* ---------- El parpadeo ---------- */
    if (quietos) return;

    /* Todos los logos de la página, no solo el primero. En la pantalla de
       inicio hay dos —el del riel y el grande de la portada— y con
       querySelector a secas parpadeaba el del riel mientras el grande,
       que es el que se está mirando, se quedaba tieso. Parpadean juntos:
       es la misma marca en dos tamaños, no dos dibujos. */
    /* Menos los que llevan data-gesto-propio: el botón de RentAI tiene
       sus propios gestos, y si parpadeara también con este reloj los dos
       se pisarían y el logo daría brincos. */
    var logos = document.querySelectorAll(".marca-logo:not([data-gesto-propio])");
    if (logos.length === 0) return;

    /* Los logos arrancan en "listo" (el guiño), que es como están
       dibujados en el HTML. Parpadear es pasar por "leyendo" un instante
       y volver. */
    function parpadear() {
      logos.forEach(function (logo) { gesto(logo, "leyendo"); });
      window.setTimeout(function () {
        logos.forEach(function (logo) { gesto(logo, "listo"); });
      }, 130);
      window.setTimeout(parpadear, 6000 + Math.random() * 4000);
    }

    window.setTimeout(parpadear, 3000 + Math.random() * 3000);
  });
})();
