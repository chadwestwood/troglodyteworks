(function () {
  const choices = document.querySelectorAll("[data-hosting-choice]");
  const nitrado = document.querySelector("[data-connection-panel]");
  const selfHosted = document.querySelector("[data-host-agent-panel]");
  if (!choices.length || !nitrado || !selfHosted) return;

  function showChoice(choice) {
    nitrado.hidden = choice !== "nitrado";
    selfHosted.hidden = choice !== "self";
    choices.forEach((button) => button.classList.toggle("is-selected", button.dataset.hostingChoice === choice));
    (choice === "nitrado" ? nitrado : selfHosted).scrollIntoView({behavior: "smooth", block: "start"});
  }

  choices.forEach((button) => button.addEventListener("click", () => showChoice(button.dataset.hostingChoice)));
  const requested = new URLSearchParams(window.location.search).get("path");
  if (["nitrado", "self"].includes(requested)) showChoice(requested);
})();
