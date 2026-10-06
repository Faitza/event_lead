/* EventLead - petits détails du site (docs/details.md) : mode sombre, bandeau cookies, retour en haut,
   barre de progression, oeil du mot de passe, confirmation avant une action importante, impression, copier. */
(function () {
  "use strict";
  var root = document.documentElement;
  var lang = (root.getAttribute("lang") || "fr").slice(0, 2);
  var T = {
    fr: { show: "Afficher le mot de passe", hide: "Masquer le mot de passe", copied: "Copié",
          invalid: "Le formulaire n'a pas pu être envoyé. Corrigez les champs signalés en rouge." },
    en: { show: "Show password", hide: "Hide password", copied: "Copied",
          invalid: "The form could not be sent. Please fix the fields marked in red." },
    ht: { show: "Montre modpas la", hide: "Kache modpas la", copied: "Kopye",
          invalid: "Fòmilè a pa t ka pati. Korije chan ki make an wouj yo." }
  }[lang];
  if (!T) T = { show: "Afficher le mot de passe", hide: "Masquer le mot de passe", copied: "Copié",
                invalid: "Le formulaire n'a pas pu être envoyé. Corrigez les champs signalés en rouge." };

  function store(key, value) {
    try {
      if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
    } catch (e) { /* stockage bloqué (navigation privée) : le choix vaut pour la page seulement */ }
  }
  function read(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  // 01. Mode sombre : seulement quand le visiteur appuie sur le bouton (clair par défaut)
  var toggles = document.querySelectorAll("[data-theme-toggle]");
  function applyTheme(dark) {
    if (dark) {
      root.setAttribute("data-theme", "dark");
      root.setAttribute("data-bs-theme", "dark");
    } else {
      root.removeAttribute("data-theme");
      root.removeAttribute("data-bs-theme");
    }
    toggles.forEach(function (btn) {
      var label = dark ? btn.dataset.labelLight : btn.dataset.labelDark;
      btn.setAttribute("aria-pressed", dark ? "true" : "false");
      if (label) { btn.title = label; btn.setAttribute("aria-label", label); }
    });
  }
  applyTheme(root.getAttribute("data-theme") === "dark");
  toggles.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var dark = root.getAttribute("data-theme") !== "dark";
      applyTheme(dark);
      store("el-theme", dark ? "dark" : null);
    });
  });

  // 02. Bandeau cookies : une information, fermée une fois pour toutes
  var note = document.querySelector("[data-cookie-note]");
  if (note && read("el-cookies-ok") !== "1") {
    note.hidden = false;
    note.querySelector("[data-cookie-ok]").addEventListener("click", function () {
      note.hidden = true;
      store("el-cookies-ok", "1");
    });
  }

  // 04 / 08. Bouton retour en haut + barre de progression de la lecture
  var toTop = document.querySelector("[data-to-top]");
  var progress = document.querySelector("#el-progress span");
  if (toTop && document.querySelector(".fab-help")) toTop.classList.add("above-fab");
  var ticking = false;
  function onScroll() {
    ticking = false;
    var y = window.scrollY || root.scrollTop;
    var max = root.scrollHeight - window.innerHeight;
    if (progress) progress.style.transform = "scaleX(" + (max > 40 ? Math.min(1, y / max) : 0) + ")";
    if (toTop) toTop.hidden = y < 600;
  }
  window.addEventListener("scroll", function () {
    if (!ticking) { ticking = true; window.requestAnimationFrame(onScroll); }
  }, { passive: true });
  window.addEventListener("resize", onScroll);
  onScroll();
  if (toTop) {
    toTop.addEventListener("click", function () {
      window.scrollTo({ top: 0 });
      var target = document.getElementById("contenu");
      if (target) target.focus({ preventScroll: true });
    });
  }

  // 12. Lien « Aller au contenu » : si la page n'a pas de zone #contenu, il va au premier titre
  var skip = document.querySelector(".skip-link");
  if (skip && !document.getElementById("contenu")) {
    skip.addEventListener("click", function (e) {
      var target = document.querySelector("main, h1");
      if (!target) return;
      e.preventDefault();
      if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
      target.focus();
    });
  }

  // 13. Oeil pour voir le mot de passe (tous les champs mot de passe du site)
  document.querySelectorAll("input[type=password]:not([data-no-eye])").forEach(function (input) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pw-eye";
    btn.setAttribute("aria-label", T.show);
    btn.setAttribute("title", T.show);
    btn.setAttribute("aria-pressed", "false");
    if (input.id) btn.setAttribute("aria-controls", input.id);
    btn.innerHTML = '<i class="bi bi-eye" aria-hidden="true"></i>';
    var parent = input.parentNode;
    if (parent.classList.contains("input-group")) {
      btn.classList.add("btn", "btn-light", "in-group");
      parent.insertBefore(btn, input.nextSibling);
    } else {
      var wrap = document.createElement("span");
      wrap.className = "pw-field";
      parent.insertBefore(wrap, input);
      wrap.appendChild(input);
      wrap.appendChild(btn);
    }
    btn.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.innerHTML = '<i class="bi ' + (show ? "bi-eye-slash" : "bi-eye") + '" aria-hidden="true"></i>';
      btn.setAttribute("aria-label", show ? T.hide : T.show);
      btn.setAttribute("title", show ? T.hide : T.show);
      btn.setAttribute("aria-pressed", show ? "true" : "false");
      input.focus();
    });
  });
  // Le mot de passe repasse en points avant l'envoi (il n'est pas gardé en clair par le navigateur)
  document.addEventListener("submit", function (e) {
    e.target.querySelectorAll(".pw-eye[aria-pressed=true]").forEach(function (b) { b.click(); });
  }, true);

  // 17. Confirmation avant une action importante : data-confirm="Texte" sur un formulaire, un bouton ou un lien.
  // Écouté en phase de capture : passe avant la protection contre le double envoi (eventlead.js).
  document.addEventListener("submit", function (e) {
    var form = e.target;
    var submitter = e.submitter;
    var text = (submitter && submitter.getAttribute("data-confirm")) || form.getAttribute("data-confirm");
    if (text && !window.confirm(text)) { e.preventDefault(); e.stopImmediatePropagation(); }
  }, true);
  document.addEventListener("click", function (e) {
    var a = e.target.closest("a[data-confirm]");
    if (a && !window.confirm(a.getAttribute("data-confirm"))) { e.preventDefault(); e.stopImmediatePropagation(); }
  }, true);

  // 16. Formulaire refusé : un message en haut de l'écran et le curseur sur le premier champ à corriger
  // (si le serveur n'a pas déjà affiché un message d'erreur)
  var firstError = document.querySelector("form .errorlist, form .is-invalid, form .invalid-feedback.d-block");
  if (firstError && !document.querySelector(".toast-el.error")) {
    var stack = document.querySelector(".toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      stack.setAttribute("role", "alert");
      document.body.appendChild(stack);
    }
    var toast = document.createElement("div");
    toast.className = "toast-el error";
    toast.innerHTML = '<i class="bi bi-x-circle-fill text-danger"></i><div></div>';
    toast.querySelector("div").textContent = T.invalid;
    stack.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 8000);
  }
  if (firstError) {
    var field = firstError.closest(".mb-3, .form-group, div");
    var input = field && field.querySelector("input:not([type=hidden]), select, textarea");
    if (input) { input.setAttribute("aria-invalid", "true"); input.focus({ preventScroll: true }); input.scrollIntoView({ block: "center" }); }
  }

  // 10. Version imprimable : bouton [data-print]
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-print]")) { e.preventDefault(); window.print(); }
  });
  // Les questions de l'aide s'impriment ouvertes
  window.addEventListener("beforeprint", function () {
    document.querySelectorAll("details:not([open])").forEach(function (d) { d.setAttribute("open", ""); d.dataset.printOpened = "1"; });
  });
  window.addEventListener("afterprint", function () {
    document.querySelectorAll("details[data-print-opened]").forEach(function (d) { d.removeAttribute("open"); delete d.dataset.printOpened; });
  });

  // 09. Copier : le bouton annonce « Copié » aux lecteurs d'écran (l'action est dans eventlead.js)
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy]");
    if (!btn) return;
    var live = document.getElementById("el-net");
    if (live) {
      live.textContent = T.copied;
      live.classList.add("ok", "on");
      setTimeout(function () { live.classList.remove("on", "ok"); }, 1400);
    }
  });
})();
