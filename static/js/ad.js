/* Publicité plein écran après la réponse d'un invité.
   La barre du haut avance pendant la durée de la pub (15 s au plus) ; à la fin, on passe tout seul à la confirmation.
   « Passer » marche tout de suite. Le son est coupé au départ ; l'icône le remet. */
(function () {
  "use strict";
  var story = document.querySelector(".story");
  if (!story) return;
  var fill = document.getElementById("story-fill");
  var video = document.getElementById("story-video");
  var embed = document.getElementById("story-embed");
  var sound = document.getElementById("story-sound");
  var next = story.dataset.next;
  var limit = (parseInt(story.dataset.seconds, 10) || 15) * 1000;
  var started = null;
  var paused = false;
  var pausedAt = 0;
  var done = false;

  function leave() {
    if (done) return;
    done = true;
    window.location.href = next;
  }

  function duration() {
    // Une vidéo plus courte que la limite finit à sa propre fin
    if (video && isFinite(video.duration) && video.duration > 0) return Math.min(video.duration * 1000, limit);
    return limit;
  }

  function elapsed(now) {
    if (video && !video.paused && isFinite(video.duration) && video.currentTime > 0) return video.currentTime * 1000;
    return paused ? pausedAt : now - started;
  }

  function frame(now) {
    if (started === null) started = now;
    var spent = elapsed(now);
    var ratio = Math.min(spent / duration(), 1);
    if (fill) fill.style.width = (ratio * 100).toFixed(2) + "%";
    if (ratio >= 1) { leave(); return; }
    requestAnimationFrame(frame);
  }

  if (video) {
    video.addEventListener("ended", leave);
    // Lecture automatique refusée (économie de données...) : le temps avance quand même
    var tryPlay = video.play && video.play();
    if (tryPlay && tryPlay.catch) tryPlay.catch(function () {});
  }

  // Quand l'invité ouvre « En savoir plus » dans un autre onglet, la pub attend son retour
  document.addEventListener("visibilitychange", function () {
    var now = performance.now();
    if (document.hidden) {
      paused = true; pausedAt = now - started;
      if (video) video.pause();
    } else if (paused) {
      paused = false; started = now - pausedAt;
      if (video) video.play().catch(function () {});
    }
  });

  if (sound) {
    sound.addEventListener("click", function () {
      var on = sound.getAttribute("aria-pressed") !== "true";
      sound.setAttribute("aria-pressed", on ? "true" : "false");
      sound.setAttribute("aria-label", on ? sound.dataset.labelOn : sound.dataset.labelOff);
      var icon = sound.querySelector("i");
      if (icon) icon.className = "bi " + (on ? "bi-volume-up-fill" : "bi-volume-mute-fill");
      if (video) { video.muted = !on; if (on) video.play().catch(function () {}); }
      if (embed && embed.contentWindow) {
        embed.contentWindow.postMessage(JSON.stringify({ event: "command", func: on ? "unMute" : "mute", args: [] }), "*");
      }
    });
  }

  requestAnimationFrame(frame);
})();
