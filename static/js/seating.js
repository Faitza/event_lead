/* Plan de table : glisser les invités sur les tables, choisir une table dans la liste, tables à créer ou modifier. */
(function () {
  "use strict";
  var root = document.getElementById("seating");
  if (!root) return;
  var d = root.dataset;
  var csrf = root.querySelector("[name=csrfmiddlewaretoken]").value;
  var board = document.getElementById("board");
  var flash = document.getElementById("seat-flash");
  var dragging = false, busy = false, term = "";

  function say(ok, text) {
    if (!text) { flash.hidden = true; return; }
    flash.textContent = text;
    flash.classList.toggle("notice-success", ok);
    flash.classList.toggle("notice-danger", !ok);
    flash.hidden = false;
  }

  function render(html) {
    board.innerHTML = html;
    var box = document.getElementById("seat-search");
    if (box) { box.value = term; filter(); }
  }

  function filter() {
    var q = term.trim().toLowerCase();
    var shown = 0, items = board.querySelectorAll("#seat-pool-list .seat-guest");
    items.forEach(function (li) {
      var show = !q || li.dataset.name.indexOf(q) !== -1;
      li.hidden = !show;
      if (show) shown++;
    });
    var none = board.querySelector(".seat-none");
    if (none) none.hidden = shown > 0 || !items.length;
  }

  function post(url, data) {
    busy = true;
    return fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": csrf, "X-Requested-With": "fetch" },
      body: new URLSearchParams(data || {}),
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, data: j }; }); })
      .then(function (res) {
        busy = false;
        if (res.data.html) render(res.data.html);
        say(res.ok, res.ok ? res.data.message : res.data.error);
        return res;
      })
      .catch(function () { busy = false; say(false, d.msgError); return { ok: false, data: {} }; });
  }

  function seat(guest, table) { return post(d.seatUrl, { guest: guest, table: table }); }

  /* ---- suivi en direct (sans casser un glisser-déposer ou un menu ouvert) ---- */
  function modalOpen() { return !!document.querySelector(".modal.show"); }
  function refresh() {
    if (dragging || busy || modalOpen()) return;
    var active = document.activeElement;
    if (active && (active.matches(".seat-pick") || active.id === "seat-search" && active.value)) return;
    fetch(d.liveUrl, { headers: { "X-Requested-With": "fetch" }, cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j && j.html && !dragging && !busy && !modalOpen()) render(j.html); })
      .catch(function () {});
  }
  setInterval(function () { if (!document.hidden) refresh(); }, 8000);

  /* ---- glisser-déposer ---- */
  root.addEventListener("dragstart", function (ev) {
    var li = ev.target.closest && ev.target.closest(".seat-guest");
    if (!li) return;
    dragging = true;
    ev.dataTransfer.setData("text/plain", li.dataset.guest);
    ev.dataTransfer.effectAllowed = "move";
    li.classList.add("is-dragging");
  });
  root.addEventListener("dragend", function () {
    dragging = false;
    root.querySelectorAll(".is-dragging, .drop-over").forEach(function (e) { e.classList.remove("is-dragging", "drop-over"); });
  });
  root.addEventListener("dragover", function (ev) {
    var zone = ev.target.closest && ev.target.closest("[data-drop-table]");
    if (!zone || !dragging) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
    zone.classList.add("drop-over");
  });
  root.addEventListener("dragleave", function (ev) {
    var zone = ev.target.closest && ev.target.closest("[data-drop-table]");
    if (zone && !zone.contains(ev.relatedTarget)) zone.classList.remove("drop-over");
  });
  root.addEventListener("drop", function (ev) {
    var zone = ev.target.closest && ev.target.closest("[data-drop-table]");
    if (!zone) return;
    ev.preventDefault();
    var guest = ev.dataTransfer.getData("text/plain");
    dragging = false;
    zone.classList.remove("drop-over");
    if (guest) seat(guest, zone.dataset.dropTable);
  });

  /* ---- clics ---- */
  root.addEventListener("click", function (ev) {
    var out = ev.target.closest("[data-unseat]");
    if (out) { seat(out.dataset.unseat, ""); return; }
    var edit = ev.target.closest("[data-edit-table]");
    if (edit) {
      document.getElementById("edit-id").value = edit.dataset.editTable;
      document.getElementById("edit-name").value = edit.dataset.name;
      document.getElementById("edit-capacity").value = edit.dataset.capacity;
      document.getElementById("edit-error").hidden = true;
      window.bootstrap.Modal.getOrCreateInstance(document.getElementById("edit-table-modal")).show();
      return;
    }
    if (ev.target.closest("#auto-place")) { say(true, ""); post(d.autoUrl); }
  });

  root.addEventListener("change", function (ev) {
    var pick = ev.target.closest("[data-pick]");
    if (pick && pick.value) seat(pick.dataset.pick, pick.value);
  });
  root.addEventListener("input", function (ev) {
    if (ev.target.id === "seat-search") { term = ev.target.value; filter(); }
  });

  /* ---- formulaires : ajout, modification, suppression, création en série ---- */
  function form(el) { return Object.fromEntries(new FormData(el).entries()); }
  function hide(id) { window.bootstrap.Modal.getOrCreateInstance(document.getElementById(id)).hide(); }

  document.getElementById("add-table-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var f = ev.target;
    post(d.addUrl, form(f)).then(function (res) { if (res.ok) { hide("add-table-modal"); f.elements.name.value = ""; } });
  });
  document.getElementById("edit-table-form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var data = form(ev.target), err = document.getElementById("edit-error");
    post(d.updateUrl.replace("/0/modifier/", "/" + data.table + "/modifier/"), data).then(function (res) {
      if (res.ok) { err.hidden = true; hide("edit-table-modal"); }
      else { err.textContent = res.data.error || d.msgError; err.hidden = false; }
    });
  });
  document.getElementById("edit-delete").addEventListener("click", function () {
    var id = document.getElementById("edit-id").value;
    if (!window.confirm(d.msgConfirmDelete)) return;
    post(d.deleteUrl.replace("/0/supprimer/", "/" + id + "/supprimer/")).then(function () { hide("edit-table-modal"); });
  });
  root.addEventListener("submit", function (ev) {
    if (ev.target.id !== "bulk-form") return;
    ev.preventDefault();
    post(d.bulkUrl, form(ev.target));
  });
})();
