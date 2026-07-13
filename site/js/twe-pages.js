const routes = {
  communities: "/communities/",
  community: "/communities/cohorts-in-the-wild/",
  explore: "/explore/",
  gameServer: "/communities/cohorts-in-the-wild/game-servers/ark-survival-ascended/",
  genesis: "/communities/cohorts-in-the-wild/game-servers/ark-survival-ascended/instances/genesis/",
};

async function initSignIn() {
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
  list.innerHTML = "";
  if (data.communities.length === 0) {
    emptyState.hidden = false;
    return;
  }
  emptyState.hidden = true;
  data.communities.forEach((community) => {
    remember("twe.community_id", community.id);
    const item = document.createElement("a");
    item.className = "resource-row";
    item.href = routes.community;
    item.innerHTML = `<span><strong>${community.name}</strong><small>${community.slug}</small></span><span>${community.role}</span>`;
    list.appendChild(item);
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
  list.innerHTML = "";
  serversData.game_servers.forEach((server) => {
    remember("twe.game_server_id", server.id);
    const item = document.createElement("a");
    item.className = "resource-row";
    item.href = routes.gameServer;
    item.innerHTML = `<span><strong>${server.game_type}</strong><small>${server.name}</small></span><span>${server.status}</span>`;
    list.appendChild(item);
  });
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
  list.innerHTML = "";
  instancesData.instances.forEach((instance) => {
    remember("twe.instance_id", instance.id);
    const item = document.createElement("a");
    item.className = "resource-row";
    item.href = routes.genesis;
    item.innerHTML = `<span><strong>${instance.name}</strong><small>${instance.game_identifier}</small></span><span>${instance.status}</span>`;
    list.appendChild(item);
  });
}

async function initGenesis() {
  await requireCurrentUser();
  const instanceId = recall("twe.instance_id") || await findInstanceId();
  const [instanceData, healthData, capabilitiesData, operationsData] = await Promise.all([
    apiRequest(`/instances/${instanceId}`),
    apiRequest(`/instances/${instanceId}/health`),
    apiRequest(`/instances/${instanceId}/capabilities`),
    apiRequest(`/instances/${instanceId}/server-operations?limit=10`),
  ]);
  setText("[data-instance-name]", instanceData.instance.name);
  setText("[data-instance-type]", instanceData.instance.instance_type);
  setText("[data-instance-status]", instanceData.instance.status);
  setText("[data-health-status]", healthData.health.overall_status);
  renderChecks(healthData.health.checks);
  renderCapabilities(instanceId, capabilitiesData.capabilities);
  renderOperations(operationsData.server_operations);
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
  list.innerHTML = "";
  op.checks.forEach((check) => {
    const row = document.createElement("div");
    row.className = "resource-row";
    row.innerHTML = `<span><strong>${check.name}</strong><small>${check.result_message || ""}</small></span><span>${check.status}</span>`;
    list.appendChild(row);
  });
}

function renderChecks(checks) {
  const list = document.querySelector("[data-health-checks]");
  list.innerHTML = "";
  checks.forEach((check) => {
    const row = document.createElement("div");
    row.className = "resource-row";
    row.innerHTML = `<span><strong>${check.name}</strong><small>${check.message}</small></span><span>${check.status}</span>`;
    list.appendChild(row);
  });
}

function renderCapabilities(instanceId, capabilities) {
  const list = document.querySelector("[data-capabilities]");
  list.innerHTML = "";
  capabilities.forEach((capability) => {
    const row = document.createElement("div");
    row.className = "resource-row";
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
    row.innerHTML = `<span><strong>${capability.key}</strong><small>${capability.available ? capability.description : capability.unavailable_reason}</small></span>`;
    row.appendChild(button);
    list.appendChild(row);
  });
}

function renderOperations(operations) {
  const list = document.querySelector("[data-operations]");
  list.innerHTML = "";
  operations.forEach((operation) => {
    const item = document.createElement("a");
    item.className = "resource-row";
    item.href = `/server-operations/?id=${operation.id}`;
    item.innerHTML = `<span><strong>${operation.capability}</strong><small>${operation.requested_at}</small></span><span>${operation.status}</span>`;
    list.appendChild(item);
  });
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
