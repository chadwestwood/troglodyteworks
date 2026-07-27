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
  return ({ Operations: "My Communities", "Community workspace": "Community", "Connected Services": "Worlds", "Game Servers": "Worlds", "Service World": "World" })[label] || label;
}

function breadcrumbHref(label) {
  if (label === "Home") return "/";
  if (["Operations", "My Communities"].includes(label)) return "/communities/";
  const parts = window.location.pathname.split("/").filter(Boolean);
  if (label === "Community workspace" || label === "Community") return parts[1] ? `/communities/${encodeURIComponent(parts[1])}/` : "/communities/";
  if (["Connected Services", "Game Servers", "Worlds"].includes(label)) return parts[1] ? `/communities/${encodeURIComponent(parts[1])}/` : "/communities/";
  return "/";
}

/*
 * A desktop screen is a finite presentation surface. When an existing screen
 * contains more top-level tasks than the viewport can hold, present those
 * tasks as linked screens instead of requiring vertical scrolling.
 *
 * This is a safety net for ordinary app screens. Purpose-built dashboards use
 * their own fixed layouts above it.
 */
function initializeViewportScreens() {
  const desktop = window.matchMedia("(min-width: 961px)");
  const purposeBuilt = ".communities-screen, .community-dashboard";
  let observer;

  function paginate() {
    if (observer) observer.disconnect();
    document.querySelectorAll(".app-shell > main, main.app-shell").forEach((main) => {
      if (!desktop.matches || main.matches(purposeBuilt)) return;
      main.classList.add("viewport-screen");
      const existing = main.querySelector(":scope > .screen-pagination");
      if (existing) existing.remove();
      const fixedHeight = main.matches("main.app-shell")
        ? [...main.children]
          .filter((child) => child.matches("header, .breadcrumbs"))
          .reduce((total, child) => total + outerHeight(child), 0)
        : 0;
      const available = Math.max(220, main.clientHeight - fixedHeight - 56);
      const roots = [...main.children].filter((child) =>
        !child.matches("header, .breadcrumbs, dialog, script, .screen-pagination")
      );
      const children = roots.flatMap((child) => expandScreenCandidate(child, available));
      children.forEach((child) => { child.hidden = false; });
      if (!children.length) return;

      const groups = [];
      let group = [];
      let used = 0;
      children.forEach((child) => {
        const height = Math.min(available, outerHeight(child));
        if (group.length && used + height > available) {
          groups.push(group);
          group = [];
          used = 0;
        }
        group.push(child);
        used += height;
      });
      if (group.length) groups.push(group);
      if (groups.length < 2) return;

      const params = new URLSearchParams(window.location.search);
      const selected = Math.min(
        groups.length - 1,
        Math.max(0, Number(params.get("screen") || 1) - 1)
      );
      children.forEach((child) => { child.hidden = true; });
      groups[selected].forEach((child) => { child.hidden = false; });
      main.querySelectorAll("[data-screen-container]").forEach((container) => {
        const visibleChild = [...container.children].some((child) =>
          !child.matches("dialog, script") && !child.hidden
        );
        container.hidden = !visibleChild;
      });
      groups[selected].forEach((child) => {
        let parent = child.parentElement;
        while (parent && parent !== main) {
          if (parent.hasAttribute("data-screen-container")) parent.hidden = false;
          parent = parent.parentElement;
        }
      });

      const nav = document.createElement("nav");
      nav.className = "screen-pagination";
      nav.setAttribute("aria-label", "More on this page");
      const status = document.createElement("span");
      status.className = "screen-pagination__status";
      status.textContent = `Screen ${selected + 1} of ${groups.length}`;
      nav.appendChild(status);
      if (selected > 0) nav.appendChild(screenLink("Back", selected));
      if (selected < groups.length - 1) nav.appendChild(screenLink("Next", selected + 2));
      main.appendChild(nav);
    });
    document.querySelectorAll(".app-shell > main, main.app-shell").forEach((main) => {
      observer.observe(main, { childList: true, subtree: true });
    });
  }

  function expandScreenCandidate(element, available, depth = 0) {
    element.hidden = false;
    const height = outerHeight(element);
    const children = [...element.children].filter((child) =>
      !child.matches("header, .breadcrumbs, dialog, script, .screen-pagination, [data-error]")
    );
    if (height <= available || children.length < 2 || depth >= 3) return [element];
    element.dataset.screenContainer = "";
    return children.flatMap((child) => expandScreenCandidate(child, available, depth + 1));
  }

  function outerHeight(element) {
    const style = getComputedStyle(element);
    return element.getBoundingClientRect().height
      + parseFloat(style.marginTop || 0)
      + parseFloat(style.marginBottom || 0);
  }

  function screenLink(label, screen) {
    const link = document.createElement("a");
    const url = new URL(window.location.href);
    url.searchParams.set("screen", screen);
    link.href = `${url.pathname}${url.search}${url.hash}`;
    link.textContent = label;
    return link;
  }

  const schedule = () => {
    window.clearTimeout(schedule.timer);
    schedule.timer = window.setTimeout(paginate, 80);
  };
  window.addEventListener("load", schedule);
  window.addEventListener("resize", schedule);
  observer = new MutationObserver(schedule);
  schedule();
}

initializeViewportScreens();
