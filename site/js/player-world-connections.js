(function () {
  "use strict";

  let currentUser = null;
  let community = null;
  let selectedConnection = null;

  const form = document.querySelector("[data-connection-form]");
  const nameInput = document.querySelector("[data-display-name]");
  const createButton = document.querySelector("[data-create-button]");
  const list = document.querySelector("[data-connections-list]");
  const pairingPanel = document.querySelector("[data-pairing-panel]");
  const pairingToken = document.querySelector("[data-pairing-token]");
  const pairingExpiry = document.querySelector("[data-pairing-expiry]");
  const copyButton = document.querySelector("[data-copy-token]");
  const discordPanel = document.querySelector("[data-discord-panel]");
  const discordGuild = document.querySelector("[data-discord-guild]");
  const discordButton = document.querySelector("[data-enable-discord]");
  const discordBindings = document.querySelector("[data-discord-bindings]");
  const errorNode = document.querySelector("[data-error]");
  const statusNode = document.querySelector("[data-status]");

  function showProblem(error) {
    errorNode.textContent = error.message || "The world connection request failed.";
    errorNode.hidden = false;
  }

  function showStatus(message) {
    statusNode.textContent = message;
    statusNode.hidden = false;
  }

  function clearMessages() {
    errorNode.hidden = true;
    errorNode.textContent = "";
    statusNode.hidden = true;
    statusNode.textContent = "";
  }

  function humanizeStatus(value) {
    return {
      unpaired: "Waiting to pair",
      offline: "Client offline",
      ready: "Client ready",
      in_world: "Playing now",
      revoked: "Revoked",
    }[value] || "Unknown";
  }

  function formatDate(value) {
    if (!value) return "Never seen";
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  }

  function connectionRow(connection) {
    const row = document.createElement("div");
    row.className = "resource-row";

    const description = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = connection.display_name;
    const detail = document.createElement("small");
    detail.textContent = `${connection.owner_display_name || "Community member"} · ${humanizeStatus(connection.status)} · Last seen ${formatDate(connection.last_seen_at)}`;
    description.append(title, detail);
    row.appendChild(description);

    if (connection.owner_user_id === currentUser.id && connection.status !== "revoked") {
      const actions = document.createElement("div");
      actions.className = "button-row";
      const pairButton = document.createElement("button");
      pairButton.type = "button";
      pairButton.className = "primary-button secondary";
      pairButton.textContent = "New pairing code";
      pairButton.addEventListener("click", () => createPairingToken(connection.id, pairButton));
      const revokeButton = document.createElement("button");
      revokeButton.type = "button";
      revokeButton.className = "text-button";
      revokeButton.textContent = "Revoke";
      revokeButton.addEventListener("click", () => revokeConnection(connection, revokeButton));
      actions.append(pairButton, revokeButton);
      row.appendChild(actions);
    } else {
      const state = document.createElement("span");
      state.textContent = connection.discord_sharing_enabled ? "Discord sharing approved" : "Discord sharing off";
      row.appendChild(state);
    }
    return row;
  }

  function renderConnections(connections) {
    list.replaceChildren();
    if (!connections.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No player-owned worlds are connected yet.";
      list.appendChild(empty);
      return;
    }
    connections.forEach((connection) => list.appendChild(connectionRow(connection)));
    selectedConnection = connections.find((connection) =>
      connection.owner_user_id === currentUser.id && connection.status !== "revoked"
    ) || null;
    discordPanel.hidden = !selectedConnection;
    if (selectedConnection) {
      loadDiscordBindings().catch(showProblem);
    }
  }

  function renderDiscordGuilds(guilds) {
    discordGuild.replaceChildren();
    discordBindings.replaceChildren();
    const installed = guilds.filter((guild) => guild.trog_installed_for_community);
    if (!installed.length) {
      discordGuild.appendChild(new Option("No verified Trog installation is available", ""));
      discordGuild.disabled = true;
      discordButton.disabled = true;
    } else {
      discordGuild.disabled = false;
      discordButton.disabled = false;
      installed.forEach((guild) => discordGuild.appendChild(new Option(guild.name, guild.id)));
    }

    const active = guilds.filter((guild) => guild.sharing_active);
    if (!active.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Minecraft presence is not shared with Discord yet.";
      discordBindings.appendChild(empty);
      return;
    }
    active.forEach((guild) => {
      const row = document.createElement("div");
      row.className = "resource-row";
      const description = document.createElement("span");
      const title = document.createElement("strong");
      title.textContent = guild.name;
      const detail = document.createElement("small");
      detail.textContent = "Trog may answer read-only Minecraft presence questions in admin-enabled channels.";
      description.append(title, detail);
      const revoke = document.createElement("button");
      revoke.type = "button";
      revoke.className = "text-button";
      revoke.textContent = "Stop sharing";
      revoke.addEventListener("click", () => revokeDiscordBinding(guild, revoke));
      row.append(description, revoke);
      discordBindings.appendChild(row);
    });
  }

  async function loadDiscordBindings() {
    if (!selectedConnection) return;
    const data = await apiRequest(`/player-world-connections/${selectedConnection.id}/discord-bindings`);
    renderDiscordGuilds(data.discord_guilds);
  }

  function showPairing(pairing) {
    pairingToken.textContent = pairing.token;
    pairingExpiry.textContent = `Expires in ${Math.round(pairing.expires_in_seconds / 60)} minutes`;
    pairingPanel.hidden = false;
    pairingPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function loadConnections() {
    const data = await apiRequest(`/communities/${community.id}/player-world-connections`);
    renderConnections(data.player_world_connections);
  }

  async function createPairingToken(connectionId, button) {
    clearMessages();
    button.disabled = true;
    try {
      const data = await apiRequest(`/player-world-connections/${connectionId}/pairing-token`, { method: "POST" });
      showPairing(data.pairing);
      showStatus("A new one-time pairing code is ready.");
    } catch (error) {
      showProblem(error);
    } finally {
      button.disabled = false;
    }
  }

  async function revokeConnection(connection, button) {
    if (!window.confirm(`Revoke your Trog connection to ${connection.display_name}? The paired mod will stop reporting.`)) {
      return;
    }
    clearMessages();
    button.disabled = true;
    try {
      await apiRequest(`/player-world-connections/${connection.id}`, { method: "DELETE" });
      pairingPanel.hidden = true;
      showStatus(`${connection.display_name} was revoked.`);
      await loadConnections();
    } catch (error) {
      showProblem(error);
    } finally {
      button.disabled = false;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();
    createButton.disabled = true;
    try {
      const data = await apiRequest(`/communities/${community.id}/player-world-connections`, {
        method: "POST",
        body: JSON.stringify({ display_name: nameInput.value, game_type: "minecraft" }),
      });
      showPairing(data.player_world_connection.pairing);
      showStatus(`${data.player_world_connection.display_name} is ready to pair.`);
      await loadConnections();
    } catch (error) {
      showProblem(error);
    } finally {
      createButton.disabled = false;
    }
  });

  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(pairingToken.textContent);
      showStatus("Pairing code copied. It is still shown only on this page and expires in 15 minutes.");
    } catch (error) {
      showProblem(new Error("The browser could not copy the pairing code. Select and copy it manually."));
    }
  });

  discordButton.addEventListener("click", async () => {
    if (!selectedConnection || !discordGuild.value) return;
    clearMessages();
    discordButton.disabled = true;
    try {
      await apiRequest(`/player-world-connections/${selectedConnection.id}/discord-bindings`, {
        method: "POST",
        body: JSON.stringify({ discord_guild_id: discordGuild.value }),
      });
      showStatus("Trog may now answer read-only Minecraft presence questions in that Discord server.");
      await Promise.all([loadConnections(), loadDiscordBindings()]);
    } catch (error) {
      showProblem(error);
    } finally {
      discordButton.disabled = false;
    }
  });

  async function revokeDiscordBinding(guild, button) {
    clearMessages();
    button.disabled = true;
    try {
      await apiRequest(
        `/player-world-connections/${selectedConnection.id}/discord-bindings/${guild.binding_id}`,
        { method: "DELETE" },
      );
      showStatus(`Minecraft presence is no longer shared with ${guild.name}.`);
      await Promise.all([loadConnections(), loadDiscordBindings()]);
    } catch (error) {
      showProblem(error);
    } finally {
      button.disabled = false;
    }
  }

  async function initialize() {
    currentUser = await requireCurrentUser();
    const communities = await apiRequest("/communities");
    const pathParts = window.location.pathname.split("/").filter(Boolean);
    const communitySlug = decodeURIComponent(pathParts[1] || "");
    community = communities.communities.find((item) => item.slug === communitySlug);
    if (!community) throw new Error("No Community is available.");
    document.querySelector("[data-community-name]").textContent = community.name;
    document.querySelectorAll("[data-community-link]").forEach((link) => {
      link.href = `/communities/${encodeURIComponent(community.slug)}/`;
    });
    document.querySelectorAll("[data-community-members-link]").forEach((link) => {
      link.href = `/communities/${encodeURIComponent(community.slug)}/invitations/`;
    });
    await loadConnections();
  }

  initialize().catch(showProblem);
}());
