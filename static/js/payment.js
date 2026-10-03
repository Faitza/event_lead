/* Modal de paiement : MonCash, NatCash, Stripe, PayPal (flux simulés en V1). */
(function () {
  "use strict";
  var modalEl = document.getElementById("paymentModal");
  if (!modalEl) return;
  var form = document.getElementById("payment-form");
  var methodInput = form.querySelector("input[name=method]");
  var title = document.getElementById("pay-title");
  var back = document.getElementById("pay-back");
  var modal = bootstrap.Modal.getOrCreateInstance(modalEl);

  // Les titres traduits viennent de data-title sur chaque étape ; le français sert de repli.
  var TITLES = { choose: "Choisissez votre mode de paiement", moncash: "Payer avec MonCash",
    natcash: "Payer avec NatCash", stripe: "Payer par carte bancaire", paypal: "Payer avec PayPal",
    processing: "Traitement en cours" };

  function show(step) {
    modalEl.querySelectorAll(".pay-step").forEach(function (s) {
      s.classList.toggle("active", s.dataset.step === step);
    });
    var stepEl = modalEl.querySelector('.pay-step[data-step="' + step + '"]');
    title.textContent = (stepEl && stepEl.dataset.title) || TITLES[step] || "";
    back.classList.toggle("d-none", step === "choose" || step === "processing");
    if (["moncash", "natcash", "stripe", "paypal"].indexOf(step) >= 0) methodInput.value = step;
  }

  modalEl.addEventListener("show.bs.modal", function () { if (!modalEl.dataset.keep) show("choose"); delete modalEl.dataset.keep; });
  modalEl.querySelectorAll("[data-method]").forEach(function (b) {
    b.addEventListener("click", function () { show(b.dataset.method); });
  });
  back.addEventListener("click", function () { show("choose"); });

  // Quantité de billets -> montant affiché
  // Séparateurs de milliers et de décimales selon la langue de la page (le créole garde le format français)
  var numLocale = (document.documentElement.lang || "fr").slice(0, 2) === "en" ? "en-US" : "fr-FR";
  var qty = document.getElementById("id_quantity_visible");
  var hiddenQty = form.querySelector("input[name=quantity]");
  function syncAmount() {
    var n = qty ? Math.max(1, parseInt(qty.value || "1", 10)) : 1;
    if (hiddenQty) hiddenQty.value = n;
    var htg = parseFloat(form.dataset.unitHtg) * n;
    var usd = parseFloat(form.dataset.unitUsd) * n;
    document.querySelectorAll("[data-amount-htg]").forEach(function (el) {
      el.textContent = htg.toLocaleString(numLocale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " HTG";
    });
    document.querySelectorAll("[data-amount-usd]").forEach(function (el) {
      el.textContent = usd.toLocaleString(numLocale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " USD";
    });
  }
  if (qty) qty.addEventListener("input", syncAmount);
  syncAmount();

  // MonCash : numéro -> code OTP -> confirmation
  var sendOtp = document.getElementById("moncash-send-otp");
  if (sendOtp) sendOtp.addEventListener("click", function () {
    var phone = document.getElementById("mc-phone");
    if (!/^(\+?509)?\s?[2-5]\d{3}\s?-?\d{4}$/.test(phone.value.trim())) {
      phone.classList.add("is-invalid"); phone.focus(); return;
    }
    phone.classList.remove("is-invalid");
    sendOtp.disabled = true;
    sendOtp.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>';
    sendOtp.appendChild(document.createTextNode(sendOtp.dataset.sendingLabel || "Envoi du code..."));
    setTimeout(function () {
      document.getElementById("moncash-otp-block").classList.remove("d-none");
      sendOtp.classList.add("d-none");
      document.getElementById("mc-otp").focus();
    }, 900);
  });

  // Aperçu de carte en direct (Stripe)
  function fmtCard(v) { return v.replace(/\D/g, "").slice(0, 19).replace(/(.{4})/g, "$1 ").trim(); }
  var cn = document.getElementById("card-number"), ce = document.getElementById("card-expiry"),
      cnm = document.getElementById("card-name");
  var pvExpiry = document.getElementById("pv-expiry"), pvName = document.getElementById("pv-name");
  var expiryHint = (pvExpiry && pvExpiry.dataset.placeholder) || "MM/AA";
  var nameHint = (pvName && pvName.dataset.placeholder) || "NOM DU TITULAIRE";
  if (cn) {
    cn.addEventListener("input", function () {
      cn.value = fmtCard(cn.value);
      document.getElementById("pv-number").textContent = cn.value || "•••• •••• •••• ••••";
    });
    ce.addEventListener("input", function () {
      var v = ce.value.replace(/\D/g, "").slice(0, 4);
      ce.value = v.length > 2 ? v.slice(0, 2) + "/" + v.slice(2) : v;
      pvExpiry.textContent = ce.value || expiryHint;
    });
    cnm.addEventListener("input", function () {
      pvName.textContent = cnm.value.toUpperCase() || nameHint;
    });
  }

  // Soumission : délai artificiel puis envoi au serveur
  form.addEventListener("submit", function (e) {
    if (form.dataset.sending) return;
    e.preventDefault();
    var active = modalEl.querySelector(".pay-step.active");
    var invalid = false;
    active.querySelectorAll("input[required]").forEach(function (i) {
      var bad = !i.value.trim() || (i.pattern && !new RegExp("^(?:" + i.pattern + ")$").test(i.value.trim()));
      i.classList.toggle("is-invalid", bad);
      if (bad) invalid = true;
    });
    if (invalid) return;
    // Seuls les champs de la méthode choisie sont envoyés
    modalEl.querySelectorAll(".pay-step").forEach(function (s) {
      if (s !== active) s.querySelectorAll("input").forEach(function (i) { i.disabled = true; });
    });
    show("processing");
    form.dataset.sending = "1";
    setTimeout(function () { form.submit(); }, 1600);
  });

  // Réouverture automatique après une erreur serveur
  if (form.dataset.reopen) {
    modalEl.dataset.keep = "1";
    show(form.dataset.reopen);
    modal.show();
  }
})();
