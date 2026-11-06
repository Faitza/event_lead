// « Y aller ensemble » : les fenêtres « Proposer » et « Signaler » reçoivent la personne du bouton qui les ouvre.
(function () {
  document.addEventListener("show.bs.modal", function (event) {
    var button = event.relatedTarget;
    if (!button || !button.getAttribute("data-ya-url")) return;
    var modal = event.target;
    var form = modal.querySelector("form[data-ya-form]");
    if (form) form.setAttribute("action", button.getAttribute("data-ya-url"));
    modal.querySelectorAll("[data-ya-fill]").forEach(function (el) {
      el.textContent = button.getAttribute("data-ya-" + el.getAttribute("data-ya-fill")) || "";
    });
    var eventField = modal.querySelector("input[name=event]");
    if (eventField) eventField.value = button.getAttribute("data-ya-event") || "";
  });
  // Conversation : on arrive sur le dernier message.
  var chat = document.querySelector(".ya-chat");
  if (chat) chat.scrollTop = chat.scrollHeight;
})();
