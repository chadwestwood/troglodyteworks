(function initializeResponsiveNavigation() {
  const compactNavigation = window.matchMedia("(max-width: 800px)");

  document.querySelectorAll(".site-header, .app-header").forEach((header, index) => {
    const navigation = header.querySelector(".header-actions");
    if (!navigation) {
      return;
    }

    if (!navigation.id) {
      navigation.id = `site-navigation-${index + 1}`;
    }

    const toggle = document.createElement("button");
    toggle.className = "nav-toggle";
    toggle.type = "button";
    toggle.textContent = "Menu";
    toggle.setAttribute("aria-controls", navigation.id);
    toggle.setAttribute("aria-expanded", "false");
    toggle.hidden = true;
    header.insertBefore(toggle, navigation);

    function setExpanded(expanded, restoreFocus = false) {
      toggle.setAttribute("aria-expanded", String(expanded));
      toggle.textContent = expanded ? "Close menu" : "Menu";
      navigation.hidden = compactNavigation.matches && !expanded;
      if (restoreFocus) {
        toggle.focus();
      }
    }

    function syncViewport() {
      if (compactNavigation.matches) {
        toggle.hidden = false;
        setExpanded(false);
      } else {
        toggle.hidden = true;
        navigation.hidden = false;
        toggle.setAttribute("aria-expanded", "false");
        toggle.textContent = "Menu";
      }
    }

    toggle.addEventListener("click", () => {
      setExpanded(toggle.getAttribute("aria-expanded") !== "true");
    });

    header.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        setExpanded(false, true);
      }
    });

    if (typeof compactNavigation.addEventListener === "function") {
      compactNavigation.addEventListener("change", syncViewport);
    } else {
      compactNavigation.addListener(syncViewport);
    }

    syncViewport();
  });
})();
