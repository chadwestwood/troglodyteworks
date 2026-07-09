const journeyDetails = {
  join: {
    question: "Do you already have an invite?",
    copy:
      "Invitation links will eventually bring visitors straight into the right community. For now, this path defines the shape of that future onboarding flow.",
  },
  servers: {
    question: "Are you starting fresh or managing an existing server?",
    copy:
      "Troglodyte Works will support hosted and external servers, so the next step should begin with where your world already lives.",
  },
  explore: {
    question: "Would you rather see communities, servers, or automation first?",
    copy:
      "Exploration should stay practical: show one useful example at a time without asking visitors to learn the whole platform first.",
  },
};

const journeyCards = document.querySelectorAll("[data-journey]");
const summary = document.querySelector("#journey-summary");
const nextStep = document.querySelector("#next-step");
const nextStepTitle = document.querySelector("#next-step-title");
const nextStepCopy = document.querySelector("#next-step-copy");
const resetJourney = document.querySelector("#reset-journey");

function selectJourney(journey) {
  const detail = journeyDetails[journey];

  if (!detail) {
    return;
  }

  journeyCards.forEach((card) => {
    card.classList.toggle("is-selected", card.dataset.journey === journey);
  });

  summary.textContent = "Good. We can narrow the path from there.";
  nextStepTitle.textContent = detail.question;
  nextStepCopy.textContent = detail.copy;
  nextStep.hidden = false;
}

function resetSelection() {
  journeyCards.forEach((card) => card.classList.remove("is-selected"));
  summary.textContent =
    "Choose the path closest to your goal. We will only show the next useful step.";
  nextStep.hidden = true;
}

journeyCards.forEach((card) => {
  card.addEventListener("click", () => selectJourney(card.dataset.journey));
});

resetJourney?.addEventListener("click", resetSelection);
