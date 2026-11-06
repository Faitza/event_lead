/* Relances des invités sans réponse : envoi en un clic, filtres, aperçu du message, suivi en direct. */
(function () {
  "use strict";
  var root = document.getElementById("reminders");
  if (!root) return;
  var d = root.dataset;
  var csrf = root.querySelector("[name=csrfmiddlewaretoken]").value;
  var flash = document.getElementById("remind-flash");
  var slots = {
    action: document.getElementById("action-slot"),
    stats: document.getElementById("stats-slot"),
    table: document.getElementById("table-slot"),
  };
  var filter = "all";
  var busy = false;

  function post(url) {
    return fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": csrf, "X-Requested-With": "fetch" },
      body: new URLSearchParams({}),
      keepalive: true,
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, data: j }; }); });
  }

  function say(ok, text) {
    flash.textContent = text;
    flash.classList.toggle("notice-success", ok);
    flash.classList.toggle("notice-danger", !ok);
    flash.hidden = false;
  }

  function applyFilter() {
    var rows = slots.table.querySelectorAll("tbody tr");
    var shown = 0;
    rows.forEach(function (tr) {
      var show = filter === "all" ||
        (filter === "never" && tr.dataset.never === "1") ||
        (filter === "3" ? Number(tr.dataset.count) >= 3 : tr.dataset.count === filter);
      tr.hidden = !show;
      if (show) shown++;
    });
    slots.table.querySelectorAll("[data-filter]").forEach(function (b) {
      b.classList.toggle("active", b.dataset.filter === filter);
    });
    var empty = slots.table.querySelector(".empty-filter");
    if (empty) empty.hidden = shown > 0 || !rows.length;
  }

  function refresh() {
    return fetch(d.liveUrl, { headers: { "X-Requested-With": "fetch" }, cache: "no-store" })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        if (!html) return;
        var doc = new DOMParser().parseFromString(html, "text/html");
        Object.keys(slots).forEach(function (k) {
          var s = doc.querySelector("[data-slot=" + k + "]");
          if (s) slots[k].innerHTML = s.innerHTML;
        });
        applyFilter();
      })
      .catch(function () {});
  }
  setInterval(function () { if (!document.hidden && !busy) refresh(); }, 5000);

  root.addEventListener("click", function (ev) {
    var tab = ev.target.closest("[data-filter]");
    if (tab) { filter = tab.dataset.filter; applyFilter(); return; }

    var preview = ev.target.closest("[data-preview]");
    if (preview) {
      root.querySelectorAll("[data-preview]").forEach(function (b) { b.classList.toggle("active", b === preview); });
      root.querySelectorAll("[data-pane]").forEach(function (p) { p.hidden = p.dataset.pane !== preview.dataset.preview; });
      return;
    }

    var one = ev.target.closest("[data-remind]");
    if (one) {
      // Le lien WhatsApp s'ouvre normalement ; on enregistre la relance en même temps
      var isLink = one.tagName === "A";
      var url = d.sendUrl.replace("/0/envoyer/", "/" + one.dataset.remind + "/envoyer/");
      if (!isLink) { one.disabled = true; say(true, d.msgSending); }
      busy = true;
      post(url).then(function (res) {
        if (res.ok) say(true, (res.data.channel === "email" ? d.msgSentEmail : d.msgSentWhatsapp) + " " + res.data.name + ".");
        else say(false, res.data.error || d.msgError);
      }).catch(function () { say(false, d.msgError); }).then(function () { busy = false; return refresh(); });
      return;
    }

    var due = ev.target.closest("#send-due");
    if (due && !due.disabled) {
      if (Number(due.dataset.email) > 0 && !window.confirm(d.msgConfirm)) return;
      due.disabled = true;
      busy = true;
      say(true, d.msgSending);
      post(d.sendDueUrl).then(function (res) {
        say(!!res.data.ok, res.data.message || d.msgError);
      }).catch(function () { say(false, d.msgError); }).then(function () { busy = false; return refresh(); });
    }
  });
})();
