(function () {
  "use strict";

  let communityId = null;
  let connection = null;
  let gameServers = [];

  const errorNode = document.querySelector("[data-error]");
  const statusNode = document.querySelector("[data-status]");
  const tokenForm = document.querySelector("[data-token-form]");
  const tokenInput = document.querySelector("[data-token-input]");
  const connectButton = document.querySelector("[data-connect-button]");
  const discoverButton = document.querySelector("[data-discover-button]");
  const disconnectButton = document.querySelector("[data-disconnect-button]");
  const resourcesPanel = document.querySelector("[data-resources-panel]");
  const resourcesList = document.querySelector("[data-resources-list]");

  function setBusy(isBusy) {
    connectButton.disabled = isBusy;
    discoverButton.disabled = isBusy;
    disconnectButton.disabled = isBusy;
    tokenInput.disabled = isBusy;
  }

  function showStatus(message) {
    statusNode.textContent = message;
    statusNode.hidden = false;
  }

  function showProblem(error) {
    errorNode.textContent = error.message || "The hosting request failed.";
    errorNode.hidden = false;
  }

  function clearMessages() {
    errorNode.hidden = true;
    errorNode.textContent = "";
    statusNode.hidden = true;
    statusNode.textContent = "";
  }

  function humanize(value) {
    if (!value) return "Unknown";
    const words = String(value).replaceAll("_", " ");
    return words.charAt(0).toUpperCase() + words.slice(1);
  }

  function formatDate(value) {
    if (!value) return "Not yet verified";
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  }

  function compatibleGameServers() {
    return gameServers.filter((server) => {
      const gameType = String(server.game_type || "").toLowerCase();
      return gameType.includes("ark") && gameType.includes("survival ascended");
    });
  }

  function resourceDetail(resource) {
    const details = [
      `Service ${resource.service_id}`,
      humanize(resource.status),
      resource.available ? "Available" : "Unavailable",
    ];
    if (!resource.supported) details.push("Unsupported game");
    if (resource.metadata?.slots) details.push(`${resource.metadata.slots} slots`);
    return details.join(" · ");
  }

  function createResourceRow(resource) {
    const row = document.createElement("div");
    row.className = "resource-row";
    const description = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = resource.name;
    const detail = document.createElement("small");
    detail.textContent = resourceDetail(resource);
    description.append(name, detail);
    row.appendChild(description);

    if (resource.binding) {
      const binding = document.createElement("span");
      binding.textContent = `Connected to ${resource.binding.game_server_name}`;
      row.appendChild(binding);
      return row;
    }

    const servers = compatibleGameServers();
    if (!resource.supported || !resource.available || connection.status !== "active" || !servers.length) {
      const state = document.createElement("span");
      state.textContent = !servers.length && resource.supported ? "No compatible Game Server" : "Not selectable";
      row.appendChild(state);
      return row;
    }

    const actions = document.createElement("div");
    actions.className = "button-row";
    const select = document.createElement("select");
    select.setAttribute("aria-label", `Game Server for ${resource.name}`);
    servers.forEach((server) => select.appendChild(new Option(server.name, server.id)));
    const button = document.createElement("button");
    button.type = "button";
    button.className = "primary-button";
    button.textContent = "Connect service";
    button.addEventListener("click", () => selectResource(resource, select.value, button));
    actions.append(select, button);
    row.appendChild(actions);
    return row;
  }

  function render(data) {
    connection = data.connection;
    resourcesList.replaceChildren();
    discoverButton.hidden = !connection;
    disconnectButton.hidden = !connection || connection.status === "revoked";
    document.querySelector("[data-revocation-note]").hidden = !connection || connection.status === "revoked";
    document.querySelector("[data-connection-heading]").textContent = connection ? "Replace connected token" : "Connect hosting";
    connectButton.textContent = connection ? "Validate and replace token" : "Validate and connect";
    const summary = document.querySelector("[data-connection-summary]");
    summary.hidden = !connection;
    summary.textContent = connection
      ? `Status: ${humanize(connection.status)} · Scope: ${connection.granted_scopes.join(", ") || "None"} · Last verified: ${formatDate(connection.last_verified_at)}`
      : "";

    const resources = data.resources || data.discovery?.resources || [];
    resourcesPanel.hidden = !connection;
    if (!resources.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No game services were discovered. Refresh services after confirming the token has the service scope.";
      resourcesList.appendChild(empty);
      return;
    }
    resources.forEach((resource) => resourcesList.appendChild(createResourceRow(resource)));
  }

  async function selectResource(resource, gameServerId, button) {
    clearMessages();
    button.disabled = true;
    try {
      const data = await apiRequest(
        `/communities/${communityId}/hosting-connections/${connection.id}/resources/${resource.id}/select`,
        { method: "POST", body: JSON.stringify({ game_server_id: gameServerId }) },
      );
      showStatus(data.binding.already_bound ? "That service was already connected." : "The hosting service is connected.");
      await loadConnection();
    } catch (error) {
      showProblem(error);
    } finally {
      button.disabled = false;
    }
  }

  async function loadConnection() {
    const data = await apiRequest(`/communities/${communityId}/hosting-connections/nitrado`);
    render(data);
  }

  tokenForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();
    setBusy(true);
    let token = tokenInput.value;
    tokenInput.value = "";
    try {
      const data = await apiRequest(`/communities/${communityId}/hosting-connections/nitrado`, {
        method: "POST",
        body: JSON.stringify({ token }),
      });
      token = "";
      render(data);
      showStatus("Nitrado is connected and its services were refreshed.");
    } catch (error) {
      token = "";
      showProblem(error);
    } finally {
      setBusy(false);
    }
  });

  discoverButton.addEventListener("click", async () => {
    clearMessages();
    setBusy(true);
    try {
      const data = await apiRequest(`/communities/${communityId}/hosting-connections/${connection.id}/discover`, { method: "POST" });
      render(data);
      showStatus("Nitrado services were refreshed.");
    } catch (error) {
      showProblem(error);
      await loadConnection().catch(() => {});
    } finally {
      setBusy(false);
    }
  });

  disconnectButton.addEventListener("click", async () => {
    if (!window.confirm("Disconnect Nitrado locally? This removes the stored credential and service bindings. You must revoke the token separately in Nitrado.")) {
      return;
    }
    clearMessages();
    setBusy(true);
    try {
      const result = await apiRequest(`/communities/${communityId}/hosting-connections/${connection.id}`, { method: "DELETE" });
      await loadConnection();
      const unbound = result.disconnected.unbound_game_servers;
      showStatus(`Nitrado was disconnected locally${unbound ? ` and ${unbound} Game Server binding${unbound === 1 ? "" : "s"} was removed` : ""}. Revoke the token separately in Nitrado.`);
    } catch (error) {
      showProblem(error);
    } finally {
      setBusy(false);
    }
  });

  async function initialize() {
    await requireCurrentUser();
    const communities = await apiRequest("/communities");
    const community = communities.communities.find((item) => item.slug === "cohorts-in-the-wild") || communities.communities[0];
    if (!community) throw new Error("No Community is available.");
    communityId = community.id;
    document.querySelector("[data-community-name]").textContent = community.name;
    const [communityData, serversData] = await Promise.all([
      apiRequest(`/communities/${communityId}`),
      apiRequest(`/communities/${communityId}/game-servers`),
    ]);
    if (communityData.community.current_user_role !== "owner") {
      tokenForm.hidden = true;
      throw new Error("Only a Community Owner can connect hosting.");
    }
    gameServers = serversData.game_servers;
    await loadConnection();
  }

  initialize().catch(showProblem);
}());
