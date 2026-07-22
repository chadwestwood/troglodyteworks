(function initializeProducts() {
  const products = [
    {
      slug: "free", name: "Free", price: 0, step: "See it", promise: "Know what is happening on your server.",
      example: "@Trog who is online?", question: "Server answers", headline: "The answers your community needs.",
      intro: "Give players and administrators a dependable place to check the server without opening a control panel.",
      summary: ["Natural read-only requests", "Status, players, mods, and rates", "Guided Discord and server setup"],
      bestFor: ["Trying Trog for the first time", "Community self-service", "Essential server visibility"],
      examples: [
        ["Is the server up?", "Trog checks the routed game instance and reports whether it is ready for players."],
        ["Who is online?", "Trog returns the current player information available from the hosting provider."],
        ["What mods are installed?", "Trog lists configured mods by name using the shared mod catalog."]
      ],
      included: [["See live state", "Check health, players, versions, rates, and supported server information."], ["Share one answer", "Everyone permitted in an approved Discord channel can use its allowed read-only requests."], ["Stay safely read-only", "Free never changes the game server."]],
      boundary: "Free answers questions naturally, but it never performs an operation that changes your server."
    },
    {
      slug: "control", name: "Control", price: 5, step: "Control it", promise: "Run routine server operations from Discord.",
      example: "@Trog restart the server", question: "Routine operations", headline: "Essential server controls, inside Discord.",
      intro: "For owners and named operators who want safe, deterministic control without opening a hosting panel.",
      summary: ["Everything in Free", "Start, stop, restart, save, and update", "Named operator permissions and action history"],
      bestFor: ["Hands-on server owners", "Trusted server operators", "Routine maintenance"],
      examples: [["Restart the server.", "Trog checks your individual authority, confirms the request, warns the channel, and reports when the server is ready."], ["Stop the server.", "Trog confirms the disruptive action and records who requested it."], ["Update the server tonight.", "Trog prepares the supported maintenance operation with clear timing and status reporting."]],
      included: [["Operate", "Start, stop, restart, save, update, and run supported maintenance operations."], ["Authorize individuals", "Give selected people operational access without upgrading everyone in the channel."], ["Stay accountable", "Use owner limits, confirmations, verification, and an action history."]],
      boundary: "Control performs supported routine operations. It does not design configuration changes or manage mods.", next: "assist"
    },
    {
      slug: "assist", name: "Assist", price: 8, step: "Ask for it", promise: "Let Trog gather the missing details.",
      example: "@Trog restart before tonight's event", question: "Context and follow-up", headline: "Ask once. Let Trog clarify the details.",
      intro: "Trog understands context, identifies the intended supported operation, and asks short questions when timing or scope is missing.",
      summary: ["Everything in Control", "Context-aware requests", "Clarifying questions and guided execution"],
      bestFor: ["Busy community administrators", "Teams with several moderators", "People who want guided operations"],
      examples: [["Restart before tonight's event.", "Trog asks for the event time, proposes warning intervals, and prepares the restart."], ["Do maintenance when the server is empty.", "Trog clarifies the maintenance window and watches the available player state."], ["Use the same restart plan as last Friday.", "Trog finds the relevant recorded operation and presents it for review."]],
      included: [["Understand context", "Connect references, timing, and the routed instance without making unsafe guesses."], ["Ask concise questions", "Collect only the details required before an operation can proceed."], ["Guide execution", "Turn the completed request into the same deterministic, audited operation used by Control."]],
      boundary: "Assist helps form an operational request. It does not independently design server configuration.", next: "admin"
    },
    {
      slug: "admin", name: "Admin", price: 10, step: "Configure it", promise: "Configure your server conversationally.",
      example: "@Trog make breeding faster without breaking imprinting", question: "Configuration goals", headline: "Configure the experience—not the files.",
      intro: "Describe the change you want. Trog identifies relevant settings, explains tradeoffs, and prepares a reviewable change.",
      summary: ["Everything in Assist", "Configuration and mod management", "Team permission delegation and rollback"],
      bestFor: ["Owners who want less configuration-file work", "Administrators tuning progression", "Teams with delegated power users"],
      examples: [["Make breeding faster without breaking imprinting.", "Trog coordinates related values and previews every exact change."], ["Install mod 930381.", "Trog resolves its name, checks compatibility, previews the change, and verifies the saved provider configuration."], ["Let Lizz restart and install mods.", "Trog grants only the requested rights within your subscription and the instance owner's delegation ceiling."]],
      included: [["Translate goals", "Turn configuration requests into exact validated settings."], ["Manage mods safely", "Resolve, install, remove, reconcile, and report mods using provider verification."], ["Delegate a team", "Let authorized managers assign a limited subset of their rights to named linked users."]],
      boundary: "Admin can configure and delegate only within the exact authority granted by the game-instance owner.", next: "pro"
    },
    {
      slug: "pro", name: "Pro", price: 15, step: "Delegate outcomes", promise: "Set the goal. Trog coordinates the details.",
      example: "@Trog plan a balanced breeding event", question: "Desired outcomes", headline: "Your server-management partner.",
      intro: "Give Trog the outcome. It investigates, recommends a plan, gets approval, carries it out, and follows up.",
      summary: ["Everything in Admin", "Plans, polls, events, and recommendations", "Execution, monitoring, and follow-up"],
      bestFor: ["Active gaming communities", "Complex events and changes", "Owners who want a proactive partner"],
      examples: [["Plan a breeding event for next weekend.", "Trog proposes rates, timing, announcements, safeguards, rollout, rollback, and a post-event check."], ["Players say gathering is too grindy.", "Trog reviews current settings, recommends options, and prepares a community poll."], ["Prepare us for a new map launch.", "Trog coordinates settings, mods, backups, communications, timing, and verification."]],
      included: [["Recommend", "Evaluate current state and present understandable options and tradeoffs."], ["Coordinate", "Prepare polls, events, announcements, configuration packages, mod changes, and schedules."], ["Follow through", "Execute approved plans, verify outcomes, monitor afterward, and recommend the next step."]],
      boundary: "Pro is powerful but accountable. Consequential plans remain visible, permission-limited, and approval-based."
    }
  ];

  const money = (product) => product.price === 0 ? "Free forever" : `$${product.price} / managed server / month`;
  const card = (product) => `<article class="product-card ${product.slug === "assist" ? "is-featured" : ""}">
    ${product.slug === "assist" ? '<span class="product-badge">Most popular</span>' : ""}
    <p class="eyebrow">${product.step}</p><h3>Trog ${product.name}</h3><p class="product-price">${money(product)}</p><p>${product.promise}</p>
    <div class="product-example"><small>You say</small><strong>“${product.example}”</strong></div>
    <ul>${product.summary.map((item) => `<li>${item}</li>`).join("")}</ul>
    <a class="primary-button ${product.slug === "assist" ? "" : "secondary"}" href="/products/${product.slug}/">Explore ${product.name}</a>
  </article>`;

  const grid = document.querySelector("[data-product-grid]");
  if (grid) grid.innerHTML = products.map(card).join("");

  const chooser = document.querySelector("[data-product-chooser]");
  if (chooser) chooser.innerHTML = products.map((product, index) => `<a href="/products/${product.slug}/"><span>0${index + 1}</span><strong>${product.question}</strong><em>Trog ${product.name}</em></a>`).join("");

  const detail = document.querySelector("[data-product-detail]");
  if (!detail) return;
  const slug = window.location.pathname.split("/").filter(Boolean).pop();
  const product = products.find((item) => item.slug === slug);
  if (!product) { window.location.replace("/products/"); return; }
  document.title = `Trog ${product.name} | Troglodyte Works`;
  detail.innerHTML = `
    <a class="product-back" href="/products/">← All products</a>
    <section class="detail-hero"><div><p class="eyebrow">Trog ${product.name} · ${money(product)}</p><h1>${product.headline}</h1><p class="subtitle">${product.intro}</p><div class="button-row"><a class="primary-button" href="/onboarding/">${product.price === 0 ? "Start free" : `Choose ${product.name}`}</a><a class="primary-button secondary" href="/auth/sign-in.html">Sign in first</a></div></div><aside><p class="eyebrow">Best for</p>${product.bestFor.map((item) => `<p>${item}</p>`).join("")}</aside></section>
    <section class="owner-rule"><p class="eyebrow">Authority rule</p><h2>Your product is not a permission bypass.</h2><p>Trog ${product.name} makes these features available to you. On a server owned by somebody else, you can use only the subset its owner has granted specifically to your linked identity and approved Discord route.</p></section>
    <section class="product-section"><div class="product-heading"><div><p class="eyebrow">See it in action</p><h2>What ${product.name} feels like.</h2></div><p>These examples demonstrate capability and context, not rigid phrases you must memorize.</p></div><div class="conversation-grid">${product.examples.map((example, index) => `<article><span>0${index + 1}</span><p><small>You</small>“${example[0]}”</p><p><small>Trog</small>${example[1]}</p></article>`).join("")}</div></section>
    <section class="included-section"><div><p class="eyebrow">Included</p><h2>More capability.<br>The same clear control.</h2></div><div>${product.included.map((item) => `<article><h3>${item[0]}</h3><p>${item[1]}</p></article>`).join("")}</div></section>
    <section class="product-boundary"><div><p class="eyebrow">Know the fit</p><h2>Where ${product.name} draws the line.</h2></div><p>${product.boundary}</p>${product.next ? `<a class="header-link" href="/products/${product.next}/">Compare Trog ${products.find((item) => item.slug === product.next).name} →</a>` : ""}</section>
    <section class="product-cta"><div><p class="eyebrow">Trog ${product.name}</p><h2>Ready to put Trog to work?</h2><p>Sign in or create an account, then choose the exact community, game instance, Discord server, and channel.</p></div><a class="primary-button" href="/onboarding/">Continue to guided setup</a></section>`;
})();
