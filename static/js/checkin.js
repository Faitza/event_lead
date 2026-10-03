/* Pointage de l'entrée : lecture du QR code par la caméra, recherche, ajout sur place, suivi en direct. */
(function () {
  "use strict";
  var root = document.getElementById("checkin");
  if (!root) return;
  var d = root.dataset;
  var csrf = root.querySelector("[name=csrfmiddlewaretoken]").value;
  var statsSlot = document.getElementById("stats-slot");
  var recentSlot = document.getElementById("recent-slot");
  var resultBox = document.getElementById("scan-result");
  var hint = document.getElementById("scan-hint");
  var box = document.getElementById("scan-box");
  var toggle = document.getElementById("scan-toggle");
  var video = document.getElementById("scan-video");
  var filter = "all";
  var stream = null, detector = null, timer = null, lastCode = "", lastAt = 0, audio = null;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function post(url, data) {
    return fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": csrf, "X-Requested-With": "fetch" },
      body: new URLSearchParams(data || {}),
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, data: j }; }); });
  }

  /* ---- suivi en direct ---- */
  function applyFilter() {
    var rows = recentSlot.querySelectorAll("tr[data-result]");
    var shown = 0;
    rows.forEach(function (tr) {
      var show = filter === "all" || (filter === "refused" && tr.dataset.refused === "1") || (filter === "walk_in" && tr.dataset.result === "walk_in");
      tr.hidden = !show;
      if (show) shown++;
    });
    recentSlot.querySelectorAll("[data-filter]").forEach(function (b) { b.classList.toggle("active", b.dataset.filter === filter); });
    var empty = recentSlot.querySelector(".empty-filter");
    if (empty) empty.hidden = shown > 0 || !rows.length;
  }

  function refresh() {
    fetch(d.liveUrl, { headers: { "X-Requested-With": "fetch" }, cache: "no-store" })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        if (!html) return;
        var doc = new DOMParser().parseFromString(html, "text/html");
        var s = doc.querySelector("[data-slot=stats]"), r = doc.querySelector("[data-slot=recent]");
        if (s) statsSlot.innerHTML = s.innerHTML;
        if (r) recentSlot.innerHTML = r.innerHTML;
        applyFilter();
      })
      .catch(function () {});
  }
  setInterval(function () { if (!document.hidden) refresh(); }, 5000);

  recentSlot.addEventListener("click", function (ev) {
    var tab = ev.target.closest("[data-filter]");
    if (tab) { filter = tab.dataset.filter; applyFilter(); return; }
    var cancel = ev.target.closest("[data-cancel]");
    if (cancel && window.confirm(d.msgConfirmCancel)) {
      post(d.cancelUrl.replace("/0/annuler/", "/" + cancel.dataset.cancel + "/annuler/")).then(function (res) {
        if (res.ok) { showMessage("muted", d.msgCancelled, res.data.name); refresh(); }
      });
    }
  });
  applyFilter();

  /* ---- résultat affiché sous la caméra ---- */
  function beep(tone) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      var osc = audio.createOscillator(), gain = audio.createGain();
      osc.frequency.value = tone === "success" ? 880 : 220;
      gain.gain.value = 0.08;
      osc.connect(gain); gain.connect(audio.destination);
      osc.start(); osc.stop(audio.currentTime + (tone === "success" ? 0.12 : 0.3));
    } catch (e) {}
    if (navigator.vibrate) navigator.vibrate(tone === "success" ? 60 : [120, 60, 120]);
  }

  function showMessage(tone, title, name, detail, note, time) {
    resultBox.hidden = false;
    resultBox.className = "scan-result tone-" + tone;
    resultBox.textContent = "";
    var head = el("div", "scan-result-title", title + (time ? " · " + time : ""));
    resultBox.appendChild(head);
    if (name) resultBox.appendChild(el("div", "scan-result-name", name));
    if (detail) resultBox.appendChild(el("div", "scan-result-detail", detail));
    if (note) resultBox.appendChild(el("div", "scan-result-note", note));
  }

  function show(r) {
    showMessage(r.tone, r.title, r.name, r.detail, r.note, r.time);
    beep(r.tone);
  }

  /* ---- caméra ---- */
  function say(text) { hint.textContent = text; }

  function handle(code) {
    var now = Date.now();
    if (code === lastCode && now - lastAt < 4000) return;
    lastCode = code; lastAt = now;
    post(d.scanUrl, { code: code }).then(function (res) { show(res.data); refresh(); })
      .catch(function () { showMessage("danger", d.msgError); });
  }

  function tick() {
    if (!stream) return;
    if (video.readyState >= 2) {
      if (detector) {
        detector.detect(video).then(function (codes) { if (codes.length) handle(codes[0].rawValue); }).catch(function () {});
      } else if (window.jsQR) {
        var canvas = tick.canvas || (tick.canvas = document.createElement("canvas"));
        canvas.width = video.videoWidth; canvas.height = video.videoHeight;
        var ctx = canvas.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(video, 0, 0);
        var img = ctx.getImageData(0, 0, canvas.width, canvas.height);
        var found = window.jsQR(img.data, img.width, img.height);
        if (found && found.data) handle(found.data);
      }
    }
    timer = setTimeout(tick, 250);
  }

  function stop() {
    if (timer) clearTimeout(timer);
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null; timer = null;
    video.srcObject = null;
    box.classList.remove("on");
    toggle.textContent = d.msgStart;
  }

  function start() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { say(d.msgUnsupported); return; }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then(function (s) {
        stream = s; video.srcObject = s;
        return video.play();
      })
      .then(function () {
        box.classList.add("on");
        toggle.textContent = d.msgStop;
        detector = "BarcodeDetector" in window ? new window.BarcodeDetector({ formats: ["qr_code"] }) : null;
        tick();
      })
      .catch(function () { stop(); say(d.msgDenied); });
  }
  toggle.addEventListener("click", function () { if (stream) stop(); else start(); });
  window.addEventListener("pagehide", stop);

  /* ---- recherche d'un invité ---- */
  var input = document.getElementById("guest-search");
  var list = document.getElementById("search-results");
  var typing = null;

  function renderResults(items) {
    list.textContent = "";
    if (!items.length) { list.appendChild(el("li", "text-muted small py-2", d.msgNone)); return; }
    items.forEach(function (g) {
      var li = el("li", "search-row");
      var who = el("div", "flex-grow-1");
      who.appendChild(el("strong", "", g.name + (g.party > 1 ? " +" + (g.party - 1) : "")));
      who.appendChild(el("div", "small text-muted", g.status + " · " + g.code));
      li.appendChild(who);
      if (g.arrived) {
        li.appendChild(el("span", "badge-el badge-success", d.msgArrived + " " + g.arrived_at));
      } else {
        var b = el("button", "btn btn-sm btn-primary", d.msgCheck);
        b.type = "button";
        b.addEventListener("click", function () {
          b.disabled = true;
          post(d.manualUrl, { guest: g.id }).then(function (res) { show(res.data); refresh(); runSearch(); });
        });
        li.appendChild(b);
      }
      list.appendChild(li);
    });
  }

  function runSearch() {
    var q = input.value.trim();
    if (q.length < 2) { list.textContent = ""; return; }
    fetch(d.searchUrl + "?q=" + encodeURIComponent(q), { headers: { "X-Requested-With": "fetch" }, cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (j) { renderResults(j.results); })
      .catch(function () {});
  }
  input.addEventListener("input", function () { clearTimeout(typing); typing = setTimeout(runSearch, 250); });

  /* ---- invité arrivé sans être sur la liste ---- */
  var form = document.getElementById("walk-in-form");
  var errorBox = document.getElementById("walk-error");
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    errorBox.hidden = true;
    post(d.walkInUrl, {
      name: form.elements.name.value, companions: form.elements.companions.value, phone: form.elements.phone.value,
    }).then(function (res) {
      if (!res.ok) { errorBox.textContent = res.data.error || d.msgError; errorBox.hidden = false; return; }
      show(res.data);
      form.reset();
      var modal = window.bootstrap && window.bootstrap.Modal.getInstance(document.getElementById("walk-in-modal"));
      if (modal) modal.hide();
      refresh();
    }).catch(function () { errorBox.textContent = d.msgError; errorBox.hidden = false; });
  });

  /* ---- plein écran (tablette ou téléphone posé à l'entrée) ---- */
  var full = document.getElementById("fullscreen-toggle");
  if (full && document.documentElement.requestFullscreen) {
    full.hidden = false;
    full.addEventListener("click", function () {
      if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen();
    });
  }
})();
