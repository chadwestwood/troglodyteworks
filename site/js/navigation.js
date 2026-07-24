(async function initializeResponsiveNavigation() {
  let user = null;
  try {
    const response = await fetch("/api/v1/auth/me", { credentials: "include" });
    if (response.ok) user = (await response.json()).user;
  } catch (_error) {}

  document.querySelectorAll(".site-header, .app-header").forEach((header) => {
    const navigation = header.querySelector(".header-actions");
    if (!navigation) return;
    navigation.replaceChildren();
    if (user) {
      const communities = document.createElement("a");
      communities.className = "header-link";
      communities.href = "/communities/";
      communities.textContent = "My Communities";
      navigation.appendChild(communities);
      const menu = document.createElement("div");
      menu.className = "profile-menu";
      const trigger = document.createElement("button");
      trigger.className = "profile-trigger";
      trigger.type = "button";
      trigger.setAttribute("aria-label", "Open profile menu");
      trigger.setAttribute("aria-expanded", "false");
      if (user.profile_image_url) {
        const image = document.createElement("img");
        image.src = user.profile_image_url;
        image.alt = "";
        trigger.appendChild(image);
      } else {
        trigger.textContent = (user.display_name || "U").slice(0, 1).toUpperCase();
      }
      const popover = document.createElement("div");
      popover.className = "profile-popover";
      popover.hidden = true;
      popover.innerHTML = '<a href="/profile/">Profile</a><a href="/account/">Account &amp; plan</a>';
      const logout = document.createElement("button");
      logout.type = "button";
      logout.textContent = "Log out";
      logout.addEventListener("click", async () => {
        await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include", headers: {"X-TWE-CSRF":"1"} });
        window.location.href = "/";
      });
      popover.appendChild(logout);
      trigger.addEventListener("click", () => {
        popover.hidden = !popover.hidden;
        trigger.setAttribute("aria-expanded", String(!popover.hidden));
      });
      menu.append(trigger, popover);
      navigation.appendChild(menu);
    } else {
      [["Discover / Join","/explore/"],["Create","/onboarding/"],["Log in","/auth/sign-in.html"]].forEach(([label, href]) => {
        const link = document.createElement("a"); link.className = "header-link"; link.href = href; link.textContent = label; navigation.appendChild(link);
      });
    }
  });
  document.querySelectorAll(".breadcrumbs").forEach((breadcrumbs) => {
    if (breadcrumbs.querySelector("a")) return;
    const labels = breadcrumbs.textContent.split(">").map((part) => part.trim()).filter(Boolean);
    if (!labels.length) return;
    breadcrumbs.replaceChildren();
    labels.forEach((label, index) => {
      if (index) breadcrumbs.appendChild(document.createTextNode(" › "));
      if (index === labels.length - 1) {
        const current = document.createElement("span"); current.textContent = friendlyBreadcrumb(label); current.setAttribute("aria-current", "page"); breadcrumbs.appendChild(current);
      } else {
        const link = document.createElement("a"); link.textContent = friendlyBreadcrumb(label); link.href = breadcrumbHref(label); breadcrumbs.appendChild(link);
      }
    });
  });
  const compactNavigation = window.matchMedia("(max-width: 1080px)");

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

function friendlyBreadcrumb(label) {
  return ({ Operations: "My Communities", "Community workspace": "Community", "Connected Services": "Game Servers", "Service World": "Game Server" })[label] || label;
}

function breadcrumbHref(label) {
  if (label === "Home") return "/";
  if (["Operations", "My Communities"].includes(label)) return "/communities/";
  const parts = window.location.pathname.split("/").filter(Boolean);
  if (label === "Community workspace" || label === "Community") return parts[1] ? `/communities/${encodeURIComponent(parts[1])}/` : "/communities/";
  if (label === "Connected Services" || label === "Game Servers") return parts[1] && parts[3] ? `/communities/${encodeURIComponent(parts[1])}/game-servers/${encodeURIComponent(parts[3])}/` : "/communities/";
  return "/";
}
