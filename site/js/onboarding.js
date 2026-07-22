(async function initOnboarding() {
  "use strict";
  await requireCurrentUser();
  const choice = document.querySelector("[data-onboarding-choice]");
  const manager = document.querySelector("[data-manager-flow]");
  const member = document.querySelector("[data-member-flow]");
  const error = document.querySelector("[data-error]");
  const guildSelect = document.querySelector("[data-managed-guild]");
  let activePath = "manager";

  function showPath(path) {
    activePath = path;
    choice.hidden = true;
    manager.hidden = !["manager", "host"].includes(path);
    member.hidden = path !== "member";
    if (["manager", "host"].includes(path)) {
      const heading = manager.querySelector("h1");
      const button = manager.querySelector("[data-create-workspace]");
      heading.textContent = path === "host" ? "Choose the Discord server for your new game" : "Choose the Discord server you manage";
      button.textContent = path === "host" ? "Create this Community and choose Minecraft" : "Create this Community and continue to Nitrado";
      loadManager().catch(showError);
    }
    if (path === "member") loadMember().catch(showError);
  }
  function showError(problem) {
    error.textContent = problem.message || String(problem);
    error.hidden = false;
    choice.hidden = false;
  }
  async function connectDiscord(returnTo) {
    const data = await apiRequest("/account/identities/discord/connect", {
      method: "POST", body: JSON.stringify({ return_to: returnTo }),
    });
    window.location.href = data.oauth.authorization_url;
  }
  function connectButton(node, text, returnTo) {
    node.replaceChildren();
    const button = document.createElement("button");
    button.className = "primary-button";
    button.type = "button";
    button.textContent = text;
    button.addEventListener("click", () => connectDiscord(returnTo).catch(showError));
    node.appendChild(button);
  }
  async function loadManager() {
    const [data, communityData] = await Promise.all([
      apiRequest("/discord/managed-guilds"),
      apiRequest("/communities"),
    ]);
    const existingOption = document.querySelector("[data-existing-community-option]");
    if (existingOption) existingOption.hidden = !(communityData.communities || []).length;
    guildSelect.replaceChildren(new Option("Choose your Discord server", ""));
    data.guilds.forEach((guild) => guildSelect.appendChild(new Option(guild.name, guild.id)));
    const connect = document.querySelector("[data-discord-connect]");
    if (!data.discord_connected || !data.guilds.length) {
      connectButton(connect, data.discord_connected ? "Reconnect Discord to refresh servers" : "Connect Discord", `/onboarding/?path=${activePath}`);
    } else {
      connect.textContent = "Discord is connected. Only servers you can manage appear below.";
    }
  }
  async function loadMember() {
    const data = await apiRequest("/onboarding/discord-matches");
    const connect = document.querySelector("[data-member-connect]");
    const matches = document.querySelector("[data-matches]");
    matches.replaceChildren();
    if (!data.discord_connected) {
      connectButton(connect, "Connect Discord and find my servers", "/onboarding/?path=member");
      return;
    }
    connectButton(connect, "Refresh my Discord servers", "/onboarding/?path=member");
    if (!data.matches.length) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "None of your Discord servers are using Trog yet.";
      matches.appendChild(p);
      return;
    }
    data.matches.forEach((match) => {
      const row = document.createElement("div");
      row.className = "resource-row";
      const label = document.createElement("span");
      label.innerHTML = `<strong></strong><small>Discord confirmed you belong to this server.</small>`;
      label.querySelector("strong").textContent = match.discord_guild_name || match.name;
      const button = document.createElement("button");
      button.className = "primary-button";
      button.textContent = "Join on Trog";
      button.addEventListener("click", async () => {
        await apiRequest(`/onboarding/discord-matches/${match.id}/join`, { method: "POST" });
        remember("twe.community_id", match.id);
        window.location.href = "/communities/";
      });
      row.append(label, button);
      matches.appendChild(row);
    });
  }

  document.querySelectorAll("[data-path]").forEach((button) => button.addEventListener("click", () => showPath(button.dataset.path)));
  document.querySelectorAll("[data-back]").forEach((button) => button.addEventListener("click", () => {
    choice.hidden = false; manager.hidden = true; member.hidden = true;
  }));
  document.querySelector("[data-refresh-discord]")?.addEventListener("click", () => connectDiscord(`/onboarding/?path=${activePath}`).catch(showError));
  document.querySelector("[data-create-workspace]")?.addEventListener("click", async () => {
    if (!guildSelect.value) return showError(new Error("Choose the Discord server you manage."));
    const data = await apiRequest("/onboarding/discord-workspace", {
      method: "POST", body: JSON.stringify({
        discord_guild_id: guildSelect.value,
        setup_intent: activePath === "host" ? "minecraft_hosting" : "nitrado_connection",
      }),
    });
    remember("twe.community_id", data.workspace.id);
    window.location.href = activePath === "host"
      ? `/hosting/new/?community_id=${encodeURIComponent(data.workspace.id)}`
      : `/communities/${encodeURIComponent(data.workspace.slug)}/hosting/?setup=1`;
  });
  document.querySelector("[data-copy-message]")?.addEventListener("click", async (event) => {
    const message = document.querySelector("[data-share-message]").value;
    await navigator.clipboard.writeText(message);
    event.currentTarget.textContent = "Copied — paste it in Discord";
  });

  const initialPath = new URLSearchParams(window.location.search).get("path");
  if (["manager", "member", "host"].includes(initialPath)) showPath(initialPath);
})().catch((error) => {
  const node = document.querySelector("[data-error]");
  if (node) { node.textContent = error.message; node.hidden = false; }
});
