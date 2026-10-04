/* EventLead - interactions communes (JavaScript vanilla, sans dépendance). */
(function () {
  "use strict";

  // Effet ripple au clic sur les boutons
  document.addEventListener("pointerdown", function (e) {
    var btn = e.target.closest(".btn");
    if (!btn || btn.disabled || btn.classList.contains("disabled")) return;
    var rect = btn.getBoundingClientRect();
    var size = Math.max(rect.width, rect.height);
    var ripple = document.createElement("span");
    ripple.className = "ripple";
    ripple.style.width = ripple.style.height = size + "px";
    ripple.style.left = e.clientX - rect.left - size / 2 + "px";
    ripple.style.top = e.clientY - rect.top - size / 2 + "px";
    btn.appendChild(ripple);
    setTimeout(function () { ripple.remove(); }, 320);
  });

  // Apparition progressive des sections au défilement
  var reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && reveals.length) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add("visible"); });
  }

  // Ombre de la barre de navigation au défilement
  var nav = document.querySelector(".el-nav");
  if (nav) {
    var onScroll = function () { nav.classList.toggle("scrolled", window.scrollY > 8); };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // Fermeture automatique des messages flash
  document.querySelectorAll(".toast-el").forEach(function (toast) {
    var close = function () {
      toast.style.transition = "opacity .25s ease, transform .25s ease";
      toast.style.opacity = "0";
      toast.style.transform = "translateX(12px)";
      setTimeout(function () { toast.remove(); }, 260);
    };
    var btn = toast.querySelector(".btn-close");
    if (btn) btn.addEventListener("click", close);
    setTimeout(close, 6000);
  });

  // Copier dans le presse-papiers
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy]");
    if (!btn) return;
    e.preventDefault();
    var text = btn.getAttribute("data-copy");
    var done = function () {
      var icon = btn.querySelector("i");
      var previous = icon ? icon.className : null;
      if (icon) icon.className = "bi bi-check2";
      btn.classList.add("btn-success");
      setTimeout(function () {
        if (icon) icon.className = previous;
        btn.classList.remove("btn-success");
      }, 1400);
    };
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(done);
    } else {
      var tmp = document.createElement("textarea");
      tmp.value = text; document.body.appendChild(tmp); tmp.select();
      document.execCommand("copy"); tmp.remove(); done();
    }
  });


  // Sidebar du tableau de bord (mobile)
  var burger = document.querySelector(".dash-burger");
  var sidebar = document.querySelector(".dash-sidebar");
  if (burger && sidebar) {
    burger.addEventListener("click", function () { sidebar.classList.toggle("open"); });
  }

  // Compteur +/- (accompagnants, billets)
  document.querySelectorAll(".counter").forEach(function (counter) {
    var input = counter.querySelector("input");
    counter.querySelectorAll("button[data-step]").forEach(function (b) {
      b.addEventListener("click", function () {
        var min = parseInt(input.min || "0", 10);
        var max = parseInt(input.max || "999", 10);
        var v = (parseInt(input.value || "0", 10) || 0) + parseInt(b.dataset.step, 10);
        input.value = Math.max(min, Math.min(max, v));
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });
  });
})();

/* Solidité (docs/solidite.md) : chargement visible, pas de double envoi, requêtes qui échouent ou traînent,
   erreurs du navigateur gardées dans le journal du serveur. */
(function () {
  "use strict";
  var body = document.body;
  var MSG = {
    failed: body.dataset.msgNetFailed || "La connexion a échoué. Vérifiez votre réseau, la page réessaie toute seule.",
    slow: body.dataset.msgNetSlow || "Le serveur met trop de temps à répondre. Réessayez dans un instant.",
    busy: body.dataset.msgNetBusy || "Trop de demandes en peu de temps. Patientez une minute.",
    back: body.dataset.msgNetBack || "Connexion rétablie."
  };
  var FETCH_TIMEOUT_MS = 20000;
  var SEND_RELEASE_MS = 15000;

  // 05. Barre de chargement : visible si la page suivante tarde un peu (pas de clignotement si elle est rapide)
  var bar = document.getElementById("el-loading");
  var barTimer = null, barStop = null;
  function loading(on) {
    if (!bar) return;
    clearTimeout(barTimer);
    clearTimeout(barStop);
    if (on) {
      barTimer = setTimeout(function () { bar.classList.add("on"); }, 150);
      // La page n'a pas changé (téléchargement, réseau coupé) : la barre s'efface d'elle-même
      barStop = setTimeout(function () { bar.classList.remove("on"); }, SEND_RELEASE_MS);
    } else {
      bar.classList.remove("on");
    }
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest("a[href]");
    if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var href = a.getAttribute("href");
    if (!href || href.charAt(0) === "#" || a.target === "_blank" || a.hasAttribute("download") ||
        a.hasAttribute("data-bs-toggle") || /^(javascript|mailto|tel|https?:\/\/wa\.me)/i.test(href)) return;
    if (a.origin && a.origin !== location.origin) return;
    if (a.pathname === location.pathname && a.search === location.search && a.hash) return;
    if (/\.(csv|pdf|zip|png)(\?|$)/i.test(a.pathname)) return;  // téléchargements : la page ne change pas
    loading(true);
  });

  // 09. Un formulaire envoyé ne peut pas repartir une deuxième fois (double clic, impatience)
  function release(form) {
    delete form.dataset.elSending;
    form.querySelectorAll(".is-sending").forEach(function (b) {
      b.classList.remove("is-sending");
      b.removeAttribute("aria-disabled");
      var spin = b.querySelector(".el-spin");
      if (spin) spin.remove();
    });
  }
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (e.defaultPrevented || form.hasAttribute("data-no-guard")) return;  // formulaire géré par un autre script
    if ((form.getAttribute("method") || "get").toLowerCase() !== "post") { loading(true); return; }
    if (form.dataset.elSending) { e.preventDefault(); return; }
    form.dataset.elSending = "1";
    // Le bouton n'est pas désactivé (son nom serait perdu dans l'envoi) : il est simplement rendu inactif
    var btn = e.submitter || form.querySelector("[type=submit]");
    if (btn && !btn.classList.contains("is-sending")) {
      btn.classList.add("is-sending");
      btn.setAttribute("aria-disabled", "true");
      var spin = document.createElement("span");
      spin.className = "spinner-border spinner-border-sm me-2 el-spin";
      spin.setAttribute("aria-hidden", "true");
      btn.insertBefore(spin, btn.firstChild);
    }
    loading(true);
    // La page n'a pas changé (téléchargement, réseau coupé) : on rend la main au bout de quelques secondes
    setTimeout(function () { release(form); }, SEND_RELEASE_MS);
  });
  // Retour arrière : la page revient du cache du navigateur, on remet les boutons en état
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    loading(false);
    document.querySelectorAll("form[data-el-sending]").forEach(release);
  });

  // 07 / 08. Requêtes en arrière-plan (suivi en direct, pointage, plan de table...) : délai maximum,
  // et un bandeau clair quand elles échouent, qui disparaît dès que le réseau revient.
  var net = document.getElementById("el-net");
  var netTimer = null, netDown = false;
  function netNotice(text) {
    if (!net) return;
    clearTimeout(netTimer);
    if (text) {
      netDown = true;
      net.textContent = text;
      net.classList.remove("ok");
      net.classList.add("on");
    } else if (netDown) {
      netDown = false;
      net.textContent = MSG.back;
      net.classList.add("ok", "on");
      netTimer = setTimeout(function () { net.classList.remove("on"); }, 2500);
    }
  }
  if (window.fetch && window.AbortController) {
    var nativeFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      init = init || {};
      var timer = null;
      if (!init.signal && !init.keepalive) {
        var ctrl = new AbortController();
        init.signal = ctrl.signal;
        timer = setTimeout(function () { ctrl.abort(); }, FETCH_TIMEOUT_MS);
      }
      return nativeFetch(input, init).then(function (r) {
        clearTimeout(timer);
        if (r.status === 429) netNotice(MSG.busy);
        else if (r.status >= 500) netNotice(MSG.failed);
        else netNotice(null);
        return r;
      }, function (err) {
        clearTimeout(timer);
        netNotice(err && err.name === "AbortError" ? MSG.slow : MSG.failed);
        throw err;
      });
    };
  }
  window.addEventListener("offline", function () { netNotice(MSG.failed); });
  window.addEventListener("online", function () { netNotice(null); });

  // 18. Erreur JavaScript chez un visiteur : envoyée au journal du serveur (5 au plus par page)
  var errorUrl = body.dataset.errorUrl, sent = 0;
  function report(message, source, line) {
    if (!errorUrl || !navigator.sendBeacon || sent >= 5) return;
    sent++;
    try {
      navigator.sendBeacon(errorUrl, JSON.stringify({
        message: String(message || "").slice(0, 300), source: String(source || "").slice(0, 200), line: line || 0,
        page: location.pathname, agent: navigator.userAgent.slice(0, 160)
      }));
    } catch (e) { /* rien : le signalement ne doit jamais gêner la page */ }
  }
  window.addEventListener("error", function (e) { report(e.message, e.filename, e.lineno); });
  window.addEventListener("unhandledrejection", function (e) {
    var r = e.reason;
    if (r && r.name === "AbortError") return;  // délai dépassé : déjà affiché dans le bandeau
    report(r && r.message ? r.message : r, "promise", 0);
  });
})();
