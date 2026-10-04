/* Album partagé : « +N » déplie la grille, visionneuse plein écran, envoi des photos dès qu'elles sont choisies. */
(function () {
  "use strict";
  var root = document.getElementById("album");
  if (!root) return;
  var d = root.dataset;
  var grid = document.getElementById("album-grid");
  var box = document.getElementById("lightbox");
  var big = box.querySelector("img");
  var current = -1;

  function tiles() { return grid ? Array.prototype.slice.call(grid.querySelectorAll(".album-tile")) : []; }

  function show(i) {
    var all = tiles();
    if (!all.length) return;
    current = (i + all.length) % all.length;
    big.src = all[current].dataset.full;
    box.hidden = false;
    document.body.style.overflow = "hidden";
    box.querySelector(".lightbox-close").focus();
  }
  function close() {
    box.hidden = true;
    big.removeAttribute("src");
    document.body.style.overflow = "";
    var all = tiles();
    if (all[current]) all[current].focus();
  }

  if (grid) {
    grid.addEventListener("click", function (ev) {
      var tile = ev.target.closest(".album-tile");
      if (!tile) return;
      var more = tile.querySelector("[data-more]");
      if (more) {
        // Premier clic sur « +N » : le reste de l'album apparaît
        more.remove();
        grid.querySelectorAll("[data-extra]").forEach(function (t) { t.hidden = false; });
        return;
      }
      show(tiles().indexOf(tile));
    });
  }

  box.addEventListener("click", function (ev) {
    var action = ev.target.closest("[data-lb]");
    if (action) {
      if (action.dataset.lb === "close") close();
      else show(current + (action.dataset.lb === "next" ? 1 : -1));
    } else if (ev.target === box) {
      close();
    }
  });
  document.addEventListener("keydown", function (ev) {
    if (box.hidden) return;
    if (ev.key === "Escape") close();
    else if (ev.key === "ArrowRight") show(current + 1);
    else if (ev.key === "ArrowLeft") show(current - 1);
  });

  var input = document.getElementById("photo-input");
  if (input) {
    input.addEventListener("change", function () {
      if (!input.files.length) return;
      document.getElementById("upload-label").textContent = d.labelSending;
      input.form.classList.add("is-sending");
      input.form.submit();
    });
  }
})();
