/* Page publicité : compte à rebours fluide avant d'autoriser « Passer ». */
(function () {
  "use strict";
  var bar = document.getElementById("countdown-fill");
  var skip = document.getElementById("skip-btn");
  var label = document.getElementById("skip-label");
  if (!bar || !skip) return;
  var total = parseInt(skip.dataset.seconds || "5", 10) * 1000;
  var start = null;

  function frame(ts) {
    if (start === null) start = ts;
    var elapsed = ts - start;
    var ratio = Math.min(elapsed / total, 1);
    bar.style.width = (ratio * 100).toFixed(2) + "%";
    var remaining = Math.ceil((total - elapsed) / 1000);
    if (ratio < 1) {
      label.textContent = "Passer dans " + remaining + " s";
      requestAnimationFrame(frame);
    } else {
      skip.classList.remove("disabled");
      skip.removeAttribute("aria-disabled");
      skip.removeAttribute("tabindex");
      label.textContent = "Passer";
    }
  }
  if (total <= 0) { bar.style.width = "100%"; skip.classList.remove("disabled"); label.textContent = "Passer"; return; }
  skip.addEventListener("click", function (e) { if (skip.classList.contains("disabled")) e.preventDefault(); });
  requestAnimationFrame(frame);
})();
