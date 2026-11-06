/* Remerciements (équipe) : envoi en un clic, aperçu du message. */
(function () {
  "use strict";
  var root = document.getElementById("thanks");
  if (!root) return;
  var d = root.dataset;
  var csrf = root.querySelector("[name=csrfmiddlewaretoken]").value;
  var flash = document.getElementById("thanks-flash");

  function say(ok, text) {
    flash.textContent = text;
    flash.classList.toggle("notice-success", ok);
    flash.classList.toggle("notice-danger", !ok);
    flash.hidden = false;
  }

  root.addEventListener("click", function (ev) {
    var preview = ev.target.closest("[data-preview]");
    if (preview) {
      root.querySelectorAll("[data-preview]").forEach(function (b) { b.classList.toggle("active", b === preview); });
      root.querySelectorAll("[data-pane]").forEach(function (p) { p.hidden = p.dataset.pane !== preview.dataset.preview; });
      return;
    }
    var one = ev.target.closest("[data-thanks]");
    if (!one) return;
    // Le lien WhatsApp s'ouvre normalement ; on enregistre l'envoi en même temps
    var isLink = one.tagName === "A";
    var url = d.sendUrl.replace("/0/envoyer/", "/" + one.dataset.thanks + "/envoyer/");
    if (!isLink) { one.disabled = true; say(true, d.msgSending); }
    fetch(url, { method: "POST", headers: { "X-CSRFToken": csrf, "X-Requested-With": "fetch" }, body: new URLSearchParams({}), keepalive: true })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, data: j }; }); })
      .then(function (res) {
        if (res.ok) {
          say(true, (res.data.channel === "email" ? d.msgSentEmail : d.msgSentWhatsapp) + " " + res.data.name + ".");
          setTimeout(function () { window.location.reload(); }, 1200);
        } else {
          say(false, res.data.error || d.msgError);
          one.disabled = false;
        }
      })
      .catch(function () { say(false, d.msgError); one.disabled = false; });
  });
})();
