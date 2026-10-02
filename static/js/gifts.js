/* Étape 3 du flux invité : sélection des cadeaux + verrouillage « temps réel »
   par rafraîchissement AJAX périodique (polling toutes les 5 secondes). */
(function () {
  "use strict";
  var root = document.getElementById("gift-selection");
  if (!root) return;
  var counter = document.getElementById("selected-count");
  var submit = document.getElementById("confirm-gifts");
  var liveNote = document.getElementById("live-note");

  function refreshCount() {
    var n = root.querySelectorAll(".gift-item input:checked:not(:disabled)").length;
    counter.textContent = n;
    submit.disabled = n === 0;
  }

  root.addEventListener("change", function (e) {
    var input = e.target;
    if (!input.matches("input[type=checkbox]")) return;
    input.closest(".gift-item").classList.toggle("is-checked", input.checked);
    refreshCount();
  });

  function lock(item, input) {
    var wasChecked = input.checked;
    input.checked = false;
    input.disabled = true;
    item.classList.remove("is-checked");
    item.classList.add("is-taken");
    item.querySelector(".gift-qty").textContent = "Déjà pris";
    if (wasChecked) {
      item.classList.add("just-locked");
      liveNote.textContent = "Un cadeau de votre sélection vient d'être choisi par un autre invité.";
      liveNote.parentElement.classList.remove("d-none");
    }
  }

  function poll() {
    fetch(root.dataset.pollUrl, { headers: { "X-Requested-With": "fetch" }, cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        data.gifts.forEach(function (g) {
          var item = root.querySelector('.gift-item[data-id="' + g.id + '"]');
          if (!item || g.mine) return;
          var input = item.querySelector("input");
          if (!g.available && !input.disabled) {
            lock(item, input);
          } else if (g.available) {
            item.querySelector(".gift-qty").textContent = g.remaining + (g.remaining > 1 ? " disponibles" : " disponible");
            if (input.disabled) {
              input.disabled = false;
              item.classList.remove("is-taken");
            }
          }
        });
        refreshCount();
      })
      .catch(function () { /* hors ligne : on réessaiera au prochain cycle */ });
  }

  refreshCount();
  setInterval(poll, parseInt(root.dataset.pollInterval || "5000", 10));
})();
