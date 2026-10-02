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
