const routes = {
  communities: "/communities/",
  community: "/communities/cohorts-in-the-wild/",
  explore: "/explore/",
  gameServer: "/communities/cohorts-in-the-wild/game-servers/ark-survival-ascended/",
  genesis: "/communities/cohorts-in-the-wild/game-servers/ark-survival-ascended/instances/genesis/",
};

async function initSignIn() {
  configureOAuthStartLinks();
  const form = document.querySelector("[data-sign-in-form]");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    try {
      await apiRequest("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: formData.get("email"),
          password: formData.get("password"),
        }),
      });
      window.location.href = pendingInvitePath() || routes.communities;
    } catch (error) {
      showError(error.message);
    }
  });
}

async function initRegister() {
  configureOAuthStartLinks();
  const form = document.querySelector("[data-register-form]");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    try {
      await apiRequest("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          display_name: formData.get("display_name"),
          email: formData.get("email"),
          password: formData.get("password"),
          password_confirmation: formData.get("password_confirmation"),
        }),
      });
      window.location.href = pendingInvitePath() || routes.communities;
    } catch (error) {
      showError(error.message);
    }
  });
}

async function initCommunities() {
  await requireCurrentUser();
  const list = document.querySelector("[data-communities-list]");
  const emptyState = document.querySelector("[data-empty-communities]");
  const data = await apiRequest("/communities");
  const pendingData = await apiRequest("/community-invitations/pending");
  clearNode(list);
  renderPendingInvitations(pendingData.invitations);
  if (data.communities.length === 0) {
    emptyState.hidden = false;
    return;
  }
  emptyState.hidden = true;
  data.communities.forEach((community) => {
    remember("twe.community_id", community.id);
    list.appendChild(createResourceRow(community.name, community.slug, community.role, { href: routes.community }));
  });
}

async function initAccount() {
  await requireCurrentUser();
  const data = await apiRequest("/account/identities");
  renderIdentities(data.identities);
  const adminEntry = document.querySelector("[data-admin-entry]");
  if (adminEntry) {
    adminEntry.hidden = !data.admin?.available;
  }
}

async function initAdmin() {
  await requireCurrentUser();
  const [overview, users, communities, discordAccess] = await Promise.all([
    apiRequest("/admin/overview"),
    apiRequest("/admin/users"),
    apiRequest("/admin/communities"),
    apiRequest("/admin/discord-access"),
  ]);
  const state = {
    overview: overview.overview,
    users: users.users,
    communities: communities.communities,
    discordAccess: discordAccess.discord_access,
    showTest: false,
    search: "",
  };
  const render = () => renderAdminDashboard(state);
  document.querySelector("[data-admin-show-test]")?.addEventListener("change", (event) => {
    state.showTest = event.target.checked;
    render();
  });
  document.querySelector("[data-admin-search]")?.addEventListener("input", (event) => {
    state.search = event.target.value.trim().toLowerCase();
    render();
  });
  render();
}

function renderAdminDashboard(state) {
  const visibleUsers = state.users.filter((user) => adminRecordVisible(user, state));
  const visibleCommunities = state.communities.filter((community) => adminRecordVisible(community, state));
  const visibleAccess = state.discordAccess.filter((request) => state.showTest || !request.is_test);
  renderAdminOverview(state.overview, state.showTest);
  renderAdminUsers(visibleUsers);
  renderAdminCommunities(visibleCommunities);
  renderAdminDiscordAccess(visibleAccess);
  setText("[data-admin-user-count]", visibleUsers.length);
  setText("[data-admin-community-count]", visibleCommunities.length);
  setText("[data-admin-access-count]", visibleAccess.length);
}

function adminRecordVisible(record, state) {
  if (!state.showTest && record.is_test) {
    return false;
  }
  if (!state.search) {
    return true;
  }
  return JSON.stringify(record).toLowerCase().includes(state.search);
}

function renderAdminOverview(overview, showTest) {
  const list = document.querySelector("[data-admin-overview]");
  clearNode(list);
  const people = overview.people + (showTest ? overview.test_accounts : 0);
  const communities = overview.communities + (showTest ? overview.test_communities : 0);
  const servers = overview.game_servers + (showTest ? overview.test_game_servers : 0);
  list.appendChild(createAdminStat("People", people, `${overview.test_accounts} automated test account(s) ${showTest ? "included" : "hidden"}`));
  list.appendChild(createAdminStat("Communities", communities, `${overview.test_communities} test communit${overview.test_communities === 1 ? "y" : "ies"} ${showTest ? "included" : "hidden"}`));
  list.appendChild(createAdminStat("Game servers", servers, `${overview.online_instances} production instance(s) online`));
  list.appendChild(createAdminStat("Trog access", overview.active_trog_grants, overview.pending_trog_requests ? `${overview.pending_trog_requests} request(s) need attention` : "No requests waiting"));
}

function renderAdminUsers(users) {
  const list = document.querySelector("[data-admin-users]");
  clearNode(list);
  if (!users.length) {
    list.appendChild(createResourceRow("No users found.", "Accounts will appear here after registration."));
    return;
  }
  users.forEach((user) => {
    const memberships = user.memberships.length
      ? user.memberships.map((membership) => `${membership.name} (${membership.role})`).join(" · ")
      : "No Community membership";
    const methods = user.authentication_methods.length ? user.authentication_methods.join(" + ") : "no sign-in method";
    const activity = user.last_active_at ? `Active ${formatAdminDate(user.last_active_at)}` : "No active session";
    list.appendChild(createAdminRecord(user.display_name, user.email, [memberships, `${methods} · ${activity}`], user.is_test ? "Test" : null));
  });
}

function renderAdminCommunities(communities) {
  const list = document.querySelector("[data-admin-communities]");
  clearNode(list);
  if (!communities.length) {
    list.appendChild(createResourceRow("No communities found.", "Community spaces will appear here after creation."));
    return;
  }
  communities.forEach((community) => {
    const managers = community.managers.length
      ? community.managers.map((manager) => `${manager.display_name || manager.email} (${manager.role})`).join(" · ")
      : community.created_by_name || community.created_by_email || "No owner recorded";
    const servers = community.game_servers.length
      ? community.game_servers.map((server) => `${server.name}: ${server.status}`).join(" · ")
      : "No game servers connected";
    const trog = community.active_trog_grants || community.pending_trog_requests
      ? `Trog: ${community.active_trog_grants} active · ${community.pending_trog_requests} pending`
      : "No Trog access grants";
    list.appendChild(createAdminRecord(
      community.name,
      `Owned/administered by ${managers}`,
      [
        `${community.member_count} member(s) · ${community.game_server_count} server(s) · ${community.instance_count} instance(s)`,
        `${servers} · ${trog}`,
      ],
      community.is_test ? "Test" : null,
    ));
  });
}

function renderAdminDiscordAccess(requests) {
  const list = document.querySelector("[data-admin-discord-access]");
  clearNode(list);
  if (!requests.length) {
    list.appendChild(createAdminRecord("No Trog access requests", "External Discord access requests will appear here.", []));
    return;
  }
  requests.forEach((request) => {
    const guild = request.consumer_discord_guild_name || request.consumer_discord_guild_id || "Discord server not verified";
    const requester = request.requested_by_name || request.requested_by_email || "Unknown requester";
    list.appendChild(createAdminRecord(
      `${request.provider_community_name} - ${request.instance_name}`,
      guild,
      [`Requested by ${requester} · ${formatAdminDate(request.created_at)}`],
      request.status.replaceAll("_", " "),
      request.status.startsWith("pending_") ? "attention" : request.status,
    ));
  });
}

function createAdminStat(label, value, detail) {
  const stat = document.createElement("div");
  stat.className = "admin-stat";
  stat.appendChild(createTextElement("span", label, "admin-stat-label"));
  stat.appendChild(createTextElement("strong", value, "admin-stat-value"));
  stat.appendChild(createTextElement("small", detail));
  return stat;
}

function createAdminRecord(title, subtitle, details, badge = null, badgeTone = "") {
  const record = document.createElement("article");
  record.className = "admin-record";
  const heading = document.createElement("div");
  heading.className = "admin-record-heading";
  heading.appendChild(createTextElement("strong", title));
  if (badge) {
    heading.appendChild(createTextElement("span", badge, `admin-badge ${badgeTone}`.trim()));
  }
  record.appendChild(heading);
  if (subtitle) {
    record.appendChild(createTextElement("p", subtitle, "admin-record-subtitle"));
  }
  details.forEach((detail) => record.appendChild(createTextElement("small", detail)));
  return record;
}

function formatAdminDate(value) {
  if (!value) {
    return "unknown date";
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function renderIdentities(identities) {
  const list = document.querySelector("[data-identities-list]");
  if (!list) {
    return;
  }
  clearNode(list);
  [
    ["local", "Local password", "Use your email and password to sign in."],
    ["google", "Google", "Use Google to sign in to this same TWE account."],
    ["discord", "Discord", "Verify the Discord servers you manage and configure Trog."],
  ].forEach(([provider, label, description]) => {
    const identity = identities[provider];
    const detail = identity.connected
      ? identity.provider_username || identity.provider_email || "Connected"
      : identity.configured === false ? "Provider setup required" : "Not connected";
    const row = createResourceRow(label, `${description} ${detail}`);
    const button = document.createElement("button");
    button.type = "button";
    if (provider === "local") {
      button.textContent = identity.connected ? "Connected" : "Unavailable";
      button.className = "identity-status-button";
      button.disabled = true;
    } else {
      if (identity.connected) {
        button.textContent = "Disconnect";
        button.disabled = !identity.can_unlink;
        button.addEventListener("click", async () => {
          try {
            await apiRequest(`/account/identities/${provider}`, { method: "DELETE" });
            window.location.reload();
          } catch (error) {
            showError(error.message);
          }
        });
      } else {
        button.textContent = identity.configured === false ? "Setup required" : `Connect ${label}`;
        button.disabled = identity.configured === false;
        button.addEventListener("click", async () => {
          try {
            const data = await apiRequest(`/account/identities/${provider}/connect`, {
              method: "POST",
              body: JSON.stringify({ return_to: recall("twe.trog_return_to") || "/account/" }),
            });
            window.location.href = data.oauth.authorization_url;
          } catch (error) {
            showError(error.message);
          }
        });
      }
    }
    row.appendChild(button);
    list.appendChild(row);
  });
}

function configureOAuthStartLinks() {
  const next = pendingInvitePath() || recall("twe.trog_return_to") || routes.communities;
  document.querySelectorAll("[data-oauth-start]").forEach((link) => {
    const provider = link.dataset.oauthStart;
    link.href = `/api/v1/auth/${provider}/start?next=${encodeURIComponent(next)}`;
  });
}

function renderPendingInvitations(invitations) {
  const list = document.querySelector("[data-pending-invitations]");
  const section = document.querySelector("[data-pending-invitations-section]");
  if (!list) {
    return;
  }
  clearNode(list);
  if (!invitations.length) {
    if (section) {
      section.hidden = true;
    }
    return;
  }
  if (section) {
    section.hidden = false;
  }
  invitations.forEach((invitation) => {
    const row = createResourceRow(invitation.community.name, `Invited as ${invitation.initial_role}`);
    const accept = document.createElement("button");
    accept.type = "button";
    accept.textContent = "Accept";
    accept.addEventListener("click", async () => {
      try {
        await apiRequest(`/community-invitations/direct/${invitation.id}/accept`, { method: "POST" });
        remember("twe.community_id", invitation.community.id);
        window.location.reload();
      } catch (error) {
        showError(error.message);
      }
    });
    const decline = document.createElement("button");
    decline.type = "button";
    decline.textContent = "Decline";
    decline.addEventListener("click", async () => {
      try {
        await apiRequest(`/community-invitations/direct/${invitation.id}/decline`, { method: "POST" });
        window.location.reload();
      } catch (error) {
        showError(error.message);
      }
    });
    row.appendChild(accept);
    row.appendChild(decline);
    list.appendChild(row);
  });
}

async function initCommunity() {
  await requireCurrentUser();
  const communityId = recall("twe.community_id") || await findCommunityId();
  const communityData = await apiRequest(`/communities/${communityId}`);
  const serversData = await apiRequest(`/communities/${communityId}/game-servers`);
  setText("[data-community-name]", communityData.community.name);
  setText("[data-community-role]", communityData.community.current_user_role);
  const list = document.querySelector("[data-game-servers-list]");
  renderCommunityServers(list, serversData.game_servers);
  await initHostGame(communityId, communityData.community.current_user_role);
  await initMembershipApprovals(communityId, communityData.community.current_user_role);
}

function renderCommunityServers(list, servers) {
  clearNode(list);
  servers.forEach((server) => {
    remember("twe.game_server_id", server.id);
    list.appendChild(createResourceRow(server.game_type, server.name, server.status, { href: routes.gameServer }));
  });
}

async function initHostGame(communityId, role) {
  const panel = document.querySelector("[data-host-game-panel]");
  const form = document.querySelector("[data-host-game-form]");
  if (!panel || !form) {
    return;
  }
  if (role !== "owner") {
    panel.hidden = false;
    setText("[data-host-game-note]", "Only Community owners can provision new game Instances.");
    form.hidden = true;
    return;
  }
  panel.hidden = false;
  form.hidden = false;
  const gameSelect = document.querySelector("[data-host-game-select]");
  const mapSelect = document.querySelector("[data-host-map-select]");
  const status = document.querySelector("[data-host-status]");
  const details = document.querySelector("[data-host-details]");
  const catalog = await apiRequest("/game-catalog");
  populateGameCatalog(gameSelect, mapSelect, catalog.games || []);
  await resumeProvisioningStatus(communityId, status, details);
  gameSelect?.addEventListener("change", () => {
    const game = (catalog.games || []).find((item) => item.key === gameSelect.value);
    populateMapOptions(mapSelect, game?.maps || []);
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const gameKey = gameSelect?.value;
    const mapKey = mapSelect?.value;
    if (!gameKey || !mapKey) {
      showError("Select a supported game and map first.");
      return;
    }
    if (!window.confirm("Provision this new game Instance now?")) {
      return;
    }
    const submitButton = form.querySelector("button[type='submit']");
    if (submitButton) {
      submitButton.disabled = true;
    }
    status.hidden = false;
    status.textContent = "Submitting provisioning request...";
    details.hidden = false;
    details.textContent = "TWE is creating the Instance and Server Operation.";
    try {
      const idempotencyKey = createIdempotencyKey();
      const data = await apiRequest(`/communities/${communityId}/instances`, {
        method: "POST",
        body: JSON.stringify({
          game_key: gameKey,
          map_key: mapKey,
          idempotency_key: idempotencyKey,
        }),
      });
      remember("twe.instance_id", data.instance.id);
      remember("twe.operation_id", data.server_operation.id);
      status.textContent = "Provisioning requested.";
      details.textContent = "Waiting for the hosting provider to finish provisioning.";
      await trackProvisioningProgress(communityId, data.instance.id, data.server_operation.id, status, details);
    } catch (error) {
      showError(error.message);
      status.textContent = "Provisioning request failed.";
      details.textContent = error.message;
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
      }
    }
  });
}

async function resumeProvisioningStatus(communityId, statusNode, detailNode) {
  const instanceId = recall("twe.instance_id");
  const operationId = recall("twe.operation_id");
  if (!instanceId || !operationId || !statusNode || !detailNode) {
    return;
  }
  try {
    const operationData = await apiRequest(`/server-operations/${operationId}`);
    const operation = operationData.server_operation;
    if (["completed", "failed", "cancelled"].includes(operation.status)) {
      statusNode.hidden = false;
      detailNode.hidden = false;
      statusNode.textContent = `Previous provisioning: ${humanizeKey(operation.status)}`;
      detailNode.textContent = operation.result_message || "Provisioning has finished.";
      return;
    }
    statusNode.hidden = false;
    detailNode.hidden = false;
    statusNode.textContent = "Resuming provisioning monitor...";
    detailNode.textContent = "Tracking the active server operation after refresh.";
    await trackProvisioningProgress(communityId, instanceId, operationId, statusNode, detailNode);
  } catch (_error) {
    // Ignore stale localStorage values.
  }
}

function populateGameCatalog(gameSelect, mapSelect, games) {
  clearNode(gameSelect);
  if (!games.length) {
    gameSelect?.appendChild(new Option("No supported games", ""));
    populateMapOptions(mapSelect, []);
    return;
  }
  games.forEach((game) => {
    gameSelect?.appendChild(new Option(game.name, game.key));
  });
  populateMapOptions(mapSelect, games[0].maps || []);
}

function populateMapOptions(mapSelect, maps) {
  clearNode(mapSelect);
  if (!maps.length) {
    mapSelect?.appendChild(new Option("No supported maps", ""));
    return;
  }
  maps.forEach((map) => {
    mapSelect?.appendChild(new Option(map.name, map.key));
  });
}

async function trackProvisioningProgress(communityId, instanceId, operationId, statusNode, detailNode) {
  const terminal = new Set(["completed", "failed", "cancelled"]);
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const [instanceData, operationData, serversData] = await Promise.all([
      apiRequest(`/instances/${instanceId}`),
      apiRequest(`/server-operations/${operationId}`),
      apiRequest(`/communities/${communityId}/game-servers`),
    ]);
    const operation = operationData.server_operation;
    const instance = instanceData.instance;
    renderCommunityServers(document.querySelector("[data-game-servers-list]"), serversData.game_servers);
    statusNode.textContent = `Provisioning status: ${humanizeKey(operation.status)}`;
    detailNode.textContent = operation.result_message || `Current stage: ${humanizeKey(operation.current_stage)}`;
    if (terminal.has(operation.status)) {
      if (operation.status === "completed") {
        statusNode.textContent = "Provisioning complete.";
        detailNode.textContent = `Instance ${instance.name} is ready.`;
      }
      if (operation.status === "failed") {
        statusNode.textContent = "Provisioning failed.";
        detailNode.textContent = operation.result_message || instance.provisioning_error || "Provider reported a failure.";
      }
      return;
    }
    await delay(3000);
  }
  statusNode.textContent = "Provisioning still in progress.";
  detailNode.textContent = "Refresh this page to continue monitoring progress.";
}

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function createIdempotencyKey() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `provision-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function initGameServer() {
  await requireCurrentUser();
  const gameServerId = recall("twe.game_server_id") || await findGameServerId();
  const serverData = await apiRequest(`/game-servers/${gameServerId}`);
  const instancesData = await apiRequest(`/game-servers/${gameServerId}/instances`);
  setText("[data-server-name]", serverData.game_server.name);
  setText("[data-server-game-type]", serverData.game_server.game_type);
  setText("[data-server-status]", serverData.game_server.status);
  const list = document.querySelector("[data-instances-list]");
  clearNode(list);
  instancesData.instances.forEach((instance) => {
    remember("twe.instance_id", instance.id);
    list.appendChild(createResourceRow(instance.name, instance.game_identifier, instance.status, { href: routes.genesis }));
  });
}

async function initGenesis() {
  await requireCurrentUser();
  const instanceId = recall("twe.instance_id") || await findInstanceId();
  const communityId = recall("twe.community_id") || await findCommunityId();
  const [instanceData, healthData, capabilitiesData, communityData] = await Promise.all([
    apiRequest(`/instances/${instanceId}`),
    apiRequest(`/instances/${instanceId}/health`),
    apiRequest(`/instances/${instanceId}/capabilities`),
    apiRequest(`/communities/${communityId}`),
  ]);
  const visibleCapabilities = capabilitiesData.capabilities.filter(
    (capability) => capability.available || capability.unavailable_reason !== "Your Community role cannot request this Capability."
  );
  const hasOperatorAccess = visibleCapabilities.length > 0;
  setText("[data-instance-name]", instanceData.instance.name);
  setText("[data-instance-summary]", "ARK: Survival Ascended · Genesis map");
  renderGenesisHealth(healthData.health, hasOperatorAccess);
  configureGenesisAccessView(hasOperatorAccess);
  if (hasOperatorAccess) {
    const operationsData = await apiRequest(`/instances/${instanceId}/server-operations?limit=10`);
    renderCapabilities(instanceId, visibleCapabilities);
    renderOperations(operationsData.server_operations);
  }
  await initMembershipApprovals(communityId, communityData.community.current_user_role);
}

function configureGenesisAccessView(hasOperatorAccess) {
  const readOnlyPanel = document.querySelector("[data-read-only-panel]");
  const capabilitiesPanel = document.querySelector("[data-capabilities-panel]");
  const operationsPanel = document.querySelector("[data-operations-panel]");
  if (readOnlyPanel) {
    readOnlyPanel.hidden = hasOperatorAccess;
  }
  if (capabilitiesPanel) {
    capabilitiesPanel.hidden = !hasOperatorAccess;
  }
  if (operationsPanel) {
    operationsPanel.hidden = !hasOperatorAccess;
  }
}

async function initMembershipApprovals(communityId, currentRole = null) {
  const panel = document.querySelector("[data-membership-approvals-panel]");
  if (!panel || !communityId) {
    return;
  }
  let role = currentRole;
  if (!role) {
    const communityData = await apiRequest(`/communities/${communityId}`);
    role = communityData.community.current_user_role;
  }
  if (!["owner", "admin", "moderator"].includes(role)) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  await refreshMembershipApprovals(communityId);
}

async function refreshMembershipApprovals(communityId) {
  const data = await apiRequest(`/communities/${communityId}/invitation-redemptions/pending`);
  const list = document.querySelector("[data-membership-approval-list]");
  const count = document.querySelector("[data-membership-approval-count]");
  clearNode(list);
  if (count) {
    count.textContent = data.redemptions.length ? `(${data.redemptions.length})` : "";
  }
  if (!data.redemptions.length) {
    list?.appendChild(createResourceRow("No pending requests", "New requests will appear here after someone submits an approval-required link."));
    return;
  }
  data.redemptions.forEach((redemption) => {
    const name = redemption.user.display_name || redemption.user.email;
    const detail = `${redemption.user.email} · Requested ${communityRoleLabel(redemption.initial_role)} · ${formatDashboardDate(redemption.redeemed_at)}`;
    const row = createResourceRow(name, detail);
    const actions = document.createElement("div");
    actions.className = "button-row";
    actions.appendChild(createMembershipDecisionButton("Approve", communityId, redemption.id, "approve", name));
    actions.appendChild(createMembershipDecisionButton("Deny", communityId, redemption.id, "deny", name, true));
    row.appendChild(actions);
    list?.appendChild(row);
  });
}

function createMembershipDecisionButton(label, communityId, redemptionId, decision, name, secondary = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.className = secondary ? "secondary-action" : "primary-button";
  button.addEventListener("click", async () => {
    if (decision === "deny" && !window.confirm(`Deny ${name}'s membership request?`)) {
      return;
    }
    const row = button.closest(".resource-row");
    row?.querySelectorAll("button").forEach((control) => { control.disabled = true; });
    try {
      await apiRequest(`/communities/${communityId}/invitation-redemptions/${redemptionId}/${decision}`, { method: "POST" });
      const status = document.querySelector("[data-membership-approval-status]");
      if (status) {
        status.textContent = decision === "approve" ? `${name} is now a Community member.` : `${name}'s request was denied.`;
        status.hidden = false;
      }
      await refreshMembershipApprovals(communityId);
    } catch (error) {
      showError(error.message);
      row?.querySelectorAll("button").forEach((control) => { control.disabled = false; });
    }
  });
  return button;
}

function communityRoleLabel(role) {
  return ({ member: "Member", moderator: "Moderator", admin: "Administrator" })[role] || role;
}

function formatDashboardDate(value) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

async function initOperation() {
  await requireCurrentUser();
  const params = new URLSearchParams(window.location.search);
  const operationId = params.get("id") || recall("twe.operation_id");
  if (!operationId) {
    showError("No Server Operation selected.");
    return;
  }
  const data = await apiRequest(`/server-operations/${operationId}`);
  const op = data.server_operation;
  setText("[data-operation-capability]", op.capability);
  setText("[data-operation-status]", op.status);
  setText("[data-operation-stage]", op.current_stage || "none");
  setText("[data-operation-result]", op.result_message || "Pending");
  const list = document.querySelector("[data-operation-checks]");
  clearNode(list);
  op.checks.forEach((check) => {
    list.appendChild(createResourceRow(check.name, check.result_message || "", check.status));
  });
}

function renderGenesisHealth(health, showDetails) {
  const status = genesisStatusPresentation(health.overall_status);
  setText("[data-health-status]", status.label);
  setText("[data-health-summary]", status.summary);
  const list = document.querySelector("[data-health-checks]");
  clearNode(list);
  if (!showDetails) {
    return;
  }
  health.checks.forEach((check) => {
    list.appendChild(createResourceRow(healthCheckLabel(check.name), check.message, checkStatusLabel(check.status)));
  });
}

function genesisStatusPresentation(status) {
  const presentations = {
    ready: { label: "Online", summary: "Genesis is running and responding normally." },
    degraded: { label: "Needs attention", summary: "Genesis is reachable, but one or more checks need attention." },
    offline: { label: "Offline", summary: "Genesis is not currently available." },
    unavailable: { label: "Offline", summary: "Genesis is not currently available." },
  };
  return presentations[status] || { label: "Status unavailable", summary: "TWE could not confirm the current Genesis status." };
}

function healthCheckLabel(name) {
  return ({
    process_running: "Server process",
    port_reachable: "Network connection",
    broadcasting: "Game response",
    management_adapter: "Server connection",
  })[name] || humanizeKey(name);
}

function checkStatusLabel(status) {
  return ({ passed: "Passed", failed: "Failed", not_configured: "Not configured", unknown: "Unknown" })[status] || humanizeKey(status);
}

function renderCapabilities(instanceId, capabilities) {
  const list = document.querySelector("[data-capabilities]");
  clearNode(list);
  capabilities.forEach((capability) => {
    const row = createResourceRow(
      capability.name,
      capability.available ? capability.description : capability.unavailable_reason,
    );
    const button = document.createElement("button");
    button.textContent = capability.name;
    button.disabled = !capability.available;
    button.addEventListener("click", async () => {
      const confirmed = !capability.requires_confirmation || window.confirm(`Create ${capability.name} Server Operation?`);
      if (!confirmed) {
        return;
      }
      try {
        const data = await apiRequest(`/instances/${instanceId}/server-operations`, {
          method: "POST",
          body: JSON.stringify({ capability: capability.key, confirmed }),
        });
        remember("twe.operation_id", data.server_operation.id);
        window.location.href = `/server-operations/?id=${data.server_operation.id}`;
      } catch (error) {
        showError(error.message);
      }
    });
    row.appendChild(button);
    list.appendChild(row);
  });
}

function renderOperations(operations) {
  const list = document.querySelector("[data-operations]");
  clearNode(list);
  if (!operations.length) {
    list?.appendChild(createResourceRow("No recent activity", "Server actions will appear here after an operator runs them."));
    return;
  }
  operations.forEach((operation) => {
    list.appendChild(createResourceRow(
      capabilityLabel(operation.capability),
      formatDashboardDate(operation.requested_at),
      humanizeKey(operation.status),
      { href: `/server-operations/?id=${operation.id}` },
    ));
  });
}

function capabilityLabel(capability) {
  return ({
    "instance.status": "Status check",
    "instance.players.list": "Player list",
    "instance.save": "World save",
    "instance.restart": "Instance restart",
  })[capability] || humanizeKey(capability);
}

function humanizeKey(value) {
  if (!value) {
    return "Unknown";
  }
  const words = String(value).replaceAll(".", " ").replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

async function findCommunityId() {
  const data = await apiRequest("/communities");
  const community = data.communities.find((item) => item.slug === "cohorts-in-the-wild") || data.communities[0];
  remember("twe.community_id", community?.id);
  return community?.id;
}

async function findGameServerId() {
  const communityId = recall("twe.community_id") || await findCommunityId();
  const data = await apiRequest(`/communities/${communityId}/game-servers`);
  const server = data.game_servers.find((item) => item.slug === "ark-survival-ascended") || data.game_servers[0];
  remember("twe.game_server_id", server?.id);
  return server?.id;
}

async function findInstanceId() {
  const gameServerId = recall("twe.game_server_id") || await findGameServerId();
  const data = await apiRequest(`/game-servers/${gameServerId}/instances`);
  const instance = data.instances.find((item) => item.slug === "genesis") || data.instances[0];
  remember("twe.instance_id", instance?.id);
  return instance?.id;
}

const page = document.body.dataset.page;
const initializers = {
  signIn: initSignIn,
  register: initRegister,
  account: initAccount,
  admin: initAdmin,
  communities: initCommunities,
  community: initCommunity,
  gameServer: initGameServer,
  genesis: initGenesis,
  operation: initOperation,
};

initializers[page]?.().catch((error) => showError(error.message));

function pendingInvitePath() {
  const token = recall("twe.pending_invite_token");
  return token ? `/invite/${token}/` : null;
}
