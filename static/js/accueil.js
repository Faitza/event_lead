/* Accueil seulement : apparition des éléments un par un, comme une présentation.
   Les éléments [data-anim] qui arrivent ensemble à l'écran se montrent l'un après
   l'autre, dans l'ordre de la page. [data-anim-step] (en secondes) règle l'écart. */
(function () {
  "use strict";
  var root = document.documentElement;
  if (!root.classList.contains("anim-on")) return;
  if (!("IntersectionObserver" in window)) { root.classList.remove("anim-on"); return; }

  // Un élément déjà apparu retrouve ses propres styles (survol des tuiles, etc.)
  function done(el) {
    el.classList.remove("is-in");
    el.removeAttribute("data-anim");
    el.style.removeProperty("--anim-delay");
  }

  function show(el, delay) {
    el.style.setProperty("--anim-delay", delay + "s");
    el.classList.add("is-in");
    setTimeout(function () { done(el); }, (delay + 0.8) * 1000);
  }

  var io = new IntersectionObserver(function (entries) {
    var batch = entries.filter(function (e) { return e.isIntersecting; }).map(function (e) { return e.target; });
    batch.sort(function (a, b) { return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1; });
    var delay = 0;
    batch.forEach(function (el, i) {
      io.unobserve(el);
      var holder = el.closest("[data-anim-step]");
      var step = holder ? parseFloat(holder.getAttribute("data-anim-step")) : 0.12;
      if (i > 0) delay = Math.min(delay + step, 1.6);
      show(el, delay);
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
  document.querySelectorAll("[data-anim]").forEach(function (el) { io.observe(el); });
})();
