/* Contribution en argent : montants, mode de paiement, petit mot ; la fenêtre de paiement s'ouvre sur le mode choisi. */
(function () {
  "use strict";
  var root = document.getElementById("contribution");
  if (!root) return;
  var d = root.dataset;
  var rate = parseFloat(d.rate), min = parseInt(d.min, 10), max = parseInt(d.max, 10);
  var numLocale = (document.documentElement.lang || "fr").slice(0, 2) === "en" ? "en-US" : "fr-FR";
  var chips = root.querySelectorAll(".amount-chip");
  var choices = root.querySelectorAll(".pay-choice");
  var other = document.getElementById("other-amount");
  var hint = document.getElementById("usd-hint");
  var label = document.getElementById("contribute-label");
  var error = document.getElementById("amount-error");
  var message = document.getElementById("contribution-message");
  var button = document.getElementById("contribute-btn");
  var modalEl = document.getElementById("paymentModal");
  var amount = NaN;

  function parse(raw) {
    var digits = String(raw || "").replace(/[\s.,  ]/g, "");
    return /^\d+$/.test(digits) ? parseInt(digits, 10) : NaN;
  }
  function fmt(n, digits) {
    return n.toLocaleString(numLocale, { minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0 }).replace(/\u202f/g, "\u00a0");
  }
  function render() {
    if (isNaN(amount) || amount <= 0) { hint.textContent = ""; label.textContent = d.labelPay.replace("{amount}", "..."); return; }
    hint.textContent = fmt(amount) + " HTG ≈ " + fmt(amount * rate, 2) + " USD";
    label.textContent = d.labelPay.replace("{amount}", fmt(amount));
  }
  function showError(text) { error.textContent = text || ""; error.hidden = !text; }

  chips.forEach(function (chip) {
    if (chip.classList.contains("active")) amount = parseInt(chip.dataset.amount, 10);
    chip.addEventListener("click", function () {
      chips.forEach(function (c) {
        var on = c === chip;
        c.classList.toggle("active", on);
        c.setAttribute("aria-checked", on ? "true" : "false");
      });
      other.value = "";
      amount = parseInt(chip.dataset.amount, 10);
      showError("");
      render();
    });
  });
  if (isNaN(amount)) amount = parse(other.value);
  other.addEventListener("input", function () {
    chips.forEach(function (c) { c.classList.remove("active"); c.setAttribute("aria-checked", "false"); });
    amount = parse(other.value);
    showError("");
    render();
  });
  render();

  function method() {
    var on = root.querySelector(".pay-choice.active");
    return on ? on.dataset.method : "moncash";
  }
  choices.forEach(function (c) {
    c.addEventListener("click", function () {
      choices.forEach(function (o) {
        var on = o === c;
        o.classList.toggle("active", on);
        o.setAttribute("aria-checked", on ? "true" : "false");
      });
    });
  });

  button.addEventListener("click", function () {
    if (isNaN(amount)) { showError(d.msgInvalid); other.focus(); return; }
    if (amount < min) { showError(d.msgMin); other.focus(); return; }
    if (amount > max) { showError(d.msgMax); other.focus(); return; }
    showError("");
    var form = document.getElementById("payment-form");
    document.getElementById("pay-amount").value = amount;
    document.getElementById("pay-message").value = message.value;
    form.dataset.unitHtg = String(amount);
    form.dataset.unitUsd = String(amount * rate);
    form.dispatchEvent(new Event("el:amount"));
    // On ouvre directement le mode choisi ; le bouton « retour » de la fenêtre permet d'en changer
    modalEl.querySelector('[data-method="' + method() + '"]').click();
    modalEl.dataset.keep = "1";
    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
  });
})();
