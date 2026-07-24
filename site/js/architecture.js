(function initializeSystemMap() {
  const views = {
    overview: {
      eyebrow: "Current State",
      title: "The platform at one glance",
      description: "People use the website or Discord. TWE applies identity, routing, and permissions before reading from or acting through an approved provider.",
      type: "overview",
      zones: [
        { title: "People & surfaces", nodes: [
          ["Website", "Accounts, Communities, maps, hosting and approvals", "current"],
          ["Discord + Trog", "Conversation inside an approved channel", "current"]
        ] },
        { title: "Public edge", nodes: [
          ["Cloudflare", "DNS and public edge for troglodyteworks.com", "current"],
          ["Railway web", "Flask, Gunicorn and the browser API", "current"],
          ["Railway worker", "Persistent Discord Gateway connection", "current"]
        ] },
        { title: "Trust & memory", nodes: [
          ["Authorization", "Identity, Community role, map grant and capability", "current"],
          ["PostgreSQL", "Authoritative state, operations and audit history", "current"],
          ["MCP tool server", "One approved tool contract for every client", "planned"]
        ] },
        { title: "Connected services", nodes: [
          ["Nitrado", "Genesis status, players, mods and approved operations", "current"],
          ["CurseForge", "Minecraft modpack and mod metadata", "current"],
          ["Self-hosted agent", "Outbound-only reports and future execution", "building"],
          ["Railway Minecraft", "Managed server provisioning foundation", "building"]
        ] }
      ]
    },
    data: {
      eyebrow: "Data Rails",
      title: "How Trog learns what is true",
      description: "Each rail has a named source, a controlled collector, normalized storage, and an authorized consumer.",
      type: "rails",
      rails: [
        {
          name: "Discord context",
          note: "Routes a mention to the correct Community and game instance.",
          status: "current",
          steps: [
            ["Discord channel", "Mention and immutable Discord IDs"],
            ["Trog worker", "Deterministic intent recognition"],
            ["Routing + grants", "Guild, channel, instance and capability"],
            ["PostgreSQL", "Identity, membership and access records"],
            ["Trog response", "Only authorized instance context"]
          ]
        },
        {
          name: "Nitrado server truth",
          note: "Normalizes provider-specific information before the rest of TWE uses it.",
          status: "current",
          steps: [
            ["Nitrado API", "Service-scoped credential"],
            ["Provider adapter", "Status, players and mods"],
            ["Instance context", "Cohorts in the Wild — Genesis"],
            ["Operations + audit", "Recorded request and outcome"],
            ["Web + Discord", "One consistent answer"]
          ]
        },
        {
          name: "Managed Minecraft plan",
          note: "Pins a chosen CurseForge release before creating hosting resources.",
          status: "building",
          steps: [
            ["Member journey", "Choose Minecraft and a modpack"],
            ["CurseForge API", "Search and exact file selection"],
            ["Immutable plan", "Game, pack and version"],
            ["Railway provider", "Provision service and variables"],
            ["Game instance", "Track provisioning state"]
          ]
        },
        {
          name: "Self-hosted server",
          note: "Keeps household networks closed while reporting useful state outward.",
          status: "building",
          steps: [
            ["Host computer", "Game server process"],
            ["Trog Host Agent", "Outbound HTTPS only"],
            ["Pairing identity", "Revocable machine authorization"],
            ["PostgreSQL", "Provider resource and heartbeat"],
            ["Trog", "Provider-neutral server status"]
          ]
        }
      ]
    },
    actions: {
      eyebrow: "Action Rails",
      title: "How a request becomes controlled work",
      description: "A successful operation is defined by verified results—not merely by sending a command.",
      type: "rails",
      rails: [
        {
          name: "Discord server operation",
          note: "The same authorization boundary applies to a conversational command and a website button.",
          status: "current",
          steps: [
            ["@Trog request", "Natural-language command"],
            ["Intent", "Known capability and argument"],
            ["Authorization", "User + channel + map + grant"],
            ["Server operation", "Persist request and stage"],
            ["Provider adapter", "Execute and verify"],
            ["Discord update", "Report completion or failure"]
          ]
        },
        {
          name: "Cross-community Trog access",
          note: "A Discord owner may request access, but the map owner controls what that installation receives.",
          status: "current",
          steps: [
            ["Map share", "Owner creates scoped invitation"],
            ["Discord owner", "Redeems and proves guild authority"],
            ["Bot installation", "Trog joins the selected guild"],
            ["Provider approval", "Map owner approves capabilities"],
            ["Channel policy", "Bind a channel to one instance"],
            ["Read-only use", "Members inherit channel-safe commands"]
          ]
        },
        {
          name: "Future MCP workflow",
          note: "MCP will expose the same deterministic operation lifecycle to approved AI clients.",
          status: "planned",
          steps: [
            ["Conversation", "User describes a goal"],
            ["Agent", "Chooses a registered workflow"],
            ["MCP tool", "Validated structured request"],
            ["Authorization", "Server-side policy decision"],
            ["Operation", "Execute, verify and audit"],
            ["Explanation", "Plain-language result"]
          ]
        }
      ]
    },
    knowledge: {
      eyebrow: "Knowledge Rail",
      title: "How Trog will answer from TWE knowledge",
      description: "PostgreSQL already stores operational truth. pgvector will add semantic retrieval for documentation without replacing the relational database.",
      type: "rails",
      rails: [
        {
          name: "Current reference path",
          note: "The repository is the human-maintained source of truth today.",
          status: "current",
          steps: [
            ["Blueprints + docs", "Architecture, decisions and provider notes"],
            ["GitHub", "Versioned and reviewable"],
            ["Human lookup", "Owner or developer finds the reference"],
            ["Implementation", "Code and documentation change together"]
          ]
        },
        {
          name: "Planned RAG path",
          note: "Retrieval supplies relevant passages; it does not grant authority or execute actions.",
          status: "planned",
          steps: [
            ["Approved sources", "Docs, runbooks and provider references"],
            ["Chunk + embed", "Small searchable passages"],
            ["PostgreSQL + pgvector", "Embeddings beside source metadata"],
            ["Knowledge tool", "Tenant-safe semantic retrieval"],
            ["Trog context", "Relevant citations for reasoning"],
            ["Answer", "Grounded explanation, no direct action"]
          ]
        }
      ]
    },
    roadmap: {
      eyebrow: "Roadmap",
      title: "Build the rails in a deliberate order",
      description: "The map separates production truth from active foundations and future intent so the project stays understandable.",
      type: "roadmap",
      columns: [
        { title: "Working now", status: "current", items: [
          "Railway web and Trog worker", "Cloudflare custom domain", "PostgreSQL application state",
          "Google and Discord identity", "Community and map permissions", "Nitrado-connected Genesis",
          "Discord status, player, mod and operation flows", "CurseForge catalog access"
        ] },
        { title: "Build next", status: "building", items: [
          "Provider-neutral self-hosted reporting", "Managed Minecraft provisioning completion",
          "System-map maintenance checks", "MCP server with read-only tools first",
          "Unified operation service behind web, Discord and MCP", "Stronger runtime observability"
        ] },
        { title: "Add deliberately", status: "planned", items: [
          "PostgreSQL pgvector extension", "Document ingestion and source registry",
          "Citation-backed RAG retrieval", "Planning and diagnostic MCP tools",
          "Approved action-tool expansion", "Additional games and hosting providers",
          "Automated architecture discovery"
        ] }
      ]
    }
  };

  const title = document.querySelector("[data-view-title]");
  const eyebrow = document.querySelector("[data-view-eyebrow]");
  const description = document.querySelector("[data-view-description]");
  const content = document.querySelector("[data-map-content]");
  const tabs = Array.from(document.querySelectorAll("[data-map-view]"));

  function escapeText(value) {
    const element = document.createElement("span");
    element.textContent = value;
    return element.innerHTML;
  }

  function nodeTemplate(node) {
    const [name, detail, status = "current"] = node;
    return `<div class="map-node" data-status="${escapeText(status)}"><strong>${escapeText(name)}</strong><small>${escapeText(detail)}</small></div>`;
  }

  function renderOverview(view) {
    return `<div class="system-overview">${view.zones.map((zone) => `
      <section class="map-zone"><h3>${escapeText(zone.title)}</h3>${zone.nodes.map(nodeTemplate).join("")}</section>
    `).join("")}</div>`;
  }

  function renderRails(view) {
    return `<div class="rail-list">${view.rails.map((rail) => `
      <article class="system-rail">
        <header class="rail-header">
          <div><h3>${escapeText(rail.name)}</h3><p>${escapeText(rail.note)}</p></div>
          <span class="status-label" data-status="${escapeText(rail.status)}">${escapeText(rail.status)}</span>
        </header>
        <div class="rail-track" style="--rail-count:${rail.steps.length}">
          ${rail.steps.map((step) => `<div class="rail-step">${nodeTemplate([step[0], step[1], rail.status])}</div>`).join("")}
        </div>
      </article>`).join("")}</div>`;
  }

  function renderRoadmap(view) {
    return `<div class="roadmap-grid">${view.columns.map((column) => `
      <section class="roadmap-column">
        <div class="rail-header"><h3>${escapeText(column.title)}</h3><span class="status-label" data-status="${escapeText(column.status)}">${escapeText(column.status)}</span></div>
        <ul>${column.items.map((item) => `<li>${escapeText(item)}</li>`).join("")}</ul>
      </section>`).join("")}</div>`;
  }

  function render(name) {
    const view = views[name] || views.overview;
    eyebrow.textContent = view.eyebrow;
    title.textContent = view.title;
    description.textContent = view.description;
    content.innerHTML = view.type === "overview"
      ? renderOverview(view)
      : view.type === "roadmap" ? renderRoadmap(view) : renderRails(view);
    tabs.forEach((tab) => {
      const active = tab.dataset.mapView === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-pressed", String(active));
    });
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", `#${name}`);
    }
  }

  tabs.forEach((tab) => tab.addEventListener("click", () => render(tab.dataset.mapView)));
  const initialView = window.location.hash.replace("#", "");
  render(Object.hasOwn(views, initialView) ? initialView : "overview");
})();
