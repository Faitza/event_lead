/* Cartes Leaflet + OpenStreetMap (sans clé API). */
(function () {
  "use strict";
  var PIN = null;
  function pin() {
    if (PIN) return PIN;
    PIN = L.divIcon({
      className: "",
      html: '<div style="width:34px;height:34px;border-radius:50% 50% 50% 0;background:#45065C;transform:rotate(-45deg);display:flex;align-items:center;justify-content:center;box-shadow:0 4px 10px rgba(44,3,59,.35);border:2px solid #D4AF37"><i class="bi bi-stars" style="transform:rotate(45deg);color:#D4AF37;font-size:14px"></i></div>',
      iconSize: [34, 34], iconAnchor: [17, 34]
    });
    return PIN;
  }
  function baseMap(el, lat, lng, zoom) {
    var map = L.map(el, { scrollWheelZoom: false }).setView([lat, lng], zoom);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap"
    }).addTo(map);
    return map;
  }

  // Carte en lecture seule : <div class="map-box" data-map data-lat data-lng data-label>
  document.querySelectorAll("[data-map]").forEach(function (el) {
    var lat = parseFloat(el.dataset.lat), lng = parseFloat(el.dataset.lng);
    if (isNaN(lat) || isNaN(lng)) return;
    var map = baseMap(el, lat, lng, 15);
    var m = L.marker([lat, lng], { icon: pin() }).addTo(map);
    if (el.dataset.label) m.bindPopup(el.dataset.label);
  });

  // Carte d'édition (formulaire événement) : repère déplaçable + géocodage serveur
  var editor = document.querySelector("[data-map-editor]");
  if (editor) {
    var latInput = document.getElementById(editor.dataset.latInput);
    var lngInput = document.getElementById(editor.dataset.lngInput);
    var venueInput = document.getElementById(editor.dataset.venueInput);
    var status = document.getElementById("geocode-status");
    var lat = parseFloat(latInput.value), lng = parseFloat(lngInput.value);
    var has = !isNaN(lat) && !isNaN(lng);
    var map = baseMap(editor, has ? lat : 18.5392, has ? lng : -72.3364, has ? 15 : 11); // Port-au-Prince
    var marker = null;
    function place(la, ln, pan) {
      latInput.value = la.toFixed(6); lngInput.value = ln.toFixed(6);
      if (!marker) {
        marker = L.marker([la, ln], { icon: pin(), draggable: true }).addTo(map);
        marker.on("dragend", function () { var p = marker.getLatLng(); place(p.lat, p.lng, false); });
      } else { marker.setLatLng([la, ln]); }
      if (pan) map.setView([la, ln], 15);
    }
    if (has) place(lat, lng, false);
    map.on("click", function (e) { place(e.latlng.lat, e.latlng.lng, false); });
    var btn = document.getElementById("geocode-btn");
    if (btn) btn.addEventListener("click", function () {
      var q = venueInput.value.trim();
      if (!q) { venueInput.focus(); return; }
      status.textContent = editor.dataset.msgSearching || "Recherche de l'adresse...";
      fetch(editor.dataset.geocodeUrl + "?q=" + encodeURIComponent(q), { headers: { "X-Requested-With": "fetch" } })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.found) { place(d.lat, d.lng, true); status.textContent = editor.dataset.msgFound || "Adresse localisée. Ajustez le repère si nécessaire."; }
          else { status.textContent = editor.dataset.msgNotfound || "Adresse introuvable. Cliquez sur la carte pour placer le repère."; }
        })
        .catch(function () { status.textContent = editor.dataset.msgUnavailable || "Service de géocodage indisponible. Cliquez sur la carte pour placer le repère."; });
    });
  }
})();
