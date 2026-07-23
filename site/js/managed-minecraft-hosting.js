(async function initManagedMinecraftHosting() {
  "use strict";
  await requireCurrentUser();
  const state = { community: null, modpack: null, file: null, capabilities: null, plan: null };
  const errorNode = document.querySelector("[data-error]");

  function fail(error) {
    errorNode.textContent = error.message || String(error);
    errorNode.hidden = false;
    errorNode.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function clearError() { errorNode.hidden = true; errorNode.textContent = ""; }
  function showStep(number) {
    clearError();
    document.querySelectorAll("[data-step]").forEach((node) => { node.hidden = Number(node.dataset.step) !== number; });
    document.querySelectorAll("[data-progress]").forEach((node) => { node.classList.toggle("is-active", Number(node.dataset.progress) <= number); });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function requireStep(number) {
    if (number === 2) {
      const select = document.querySelector("[data-community]");
      if (!select.value) throw new Error("Choose a Community you own first.");
      state.community = select.value;
    }
    if (number === 4) {
      const select = document.querySelector("[data-file]");
      if (!state.modpack || !select.value) throw new Error("Choose a modpack and version first.");
      state.file = JSON.parse(select.selectedOptions[0].dataset.file);
      updateReview();
    }
    showStep(number);
  }

  const [communityData, capabilities] = await Promise.all([
    apiRequest("/communities"), apiRequest("/hosting/capabilities"),
  ]);
  state.capabilities = capabilities;
  const communitySelect = document.querySelector("[data-community]");
  const owned = (communityData.communities || []).filter((community) => community.role === "owner");
  communitySelect.replaceChildren(new Option("Choose a Community you own", ""));
  owned.forEach((community) => {
    const option = new Option(community.name, community.id);
    if (new URLSearchParams(window.location.search).get("community_id") === community.id) option.selected = true;
    communitySelect.appendChild(option);
  });
  document.querySelector("[data-no-community]").hidden = owned.length > 0;

  async function resumeExistingPlan(communityId) {
    if (!communityId) return false;
    const data = await apiRequest(`/communities/${communityId}/managed-hosting-plans`);
    const plan = (data.plans || []).find((item) => !["cancelled"].includes(item.status));
    if (!plan) return false;
    state.community = communityId;
    state.plan = plan;
    document.querySelector("[data-result-title]").textContent = plan.status === "online" ? "Your Minecraft server is online" : "Continue your Minecraft installation";
    document.querySelector("[data-result-message]").textContent = `Plan: ${plan.server_name} · ${plan.modpack_name} · ${plan.modpack_version}`;
    const canInstall = state.capabilities.railway_installation && ["awaiting_installation", "awaiting_platform_configuration", "failed"].includes(plan.status);
    document.querySelector("[data-final-charge]").hidden = !canInstall;
    document.querySelector("[data-install-actions]").hidden = !canInstall;
    showStep(5);
    if (["provisioning", "online"].includes(plan.status)) await pollPlan();
    return true;
  }

  async function search() {
    clearError();
    const query = document.querySelector("[data-search]").value.trim();
    if (!capabilities.curseforge_search) throw new Error("CurseForge search is not enabled on TWE yet. An administrator needs to add the CurseForge API key.");
    const data = await apiRequest(`/hosting/curseforge/modpacks?query=${encodeURIComponent(query)}`);
    const results = document.querySelector("[data-results]");
    results.replaceChildren();
    if (!data.modpacks.length) results.append(createTextElement("p", "No matching modpacks found.", "muted"));
    data.modpacks.forEach((modpack) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "resource-row resource-button";
      const content = document.createElement("span");
      content.append(createTextElement("strong", modpack.name), createTextElement("small", modpack.summary || "CurseForge Minecraft modpack"));
      row.append(content, createTextElement("span", "Choose"));
      row.addEventListener("click", () => chooseModpack(modpack).catch(fail));
      results.appendChild(row);
    });
  }
  async function chooseModpack(modpack) {
    clearError(); state.modpack = modpack;
    const data = await apiRequest(`/hosting/curseforge/modpacks/${modpack.id}/files`);
    const fileSelect = document.querySelector("[data-file]");
    fileSelect.replaceChildren(new Option(`Choose a ${modpack.name} version`, ""));
    data.files.forEach((file) => {
      const versions = file.game_versions.filter((value) => /^1\./.test(value)).slice(0, 3).join(", ");
      const option = new Option(`${file.display_name}${versions ? ` — Minecraft ${versions}` : ""}`, String(file.id));
      option.dataset.file = JSON.stringify(file);
      fileSelect.appendChild(option);
    });
    document.querySelector("[data-file-picker]").hidden = false;
    document.querySelector("[data-file-picker]").scrollIntoView({ behavior: "smooth" });
  }
  function selectedCost() {
    const memory = Number(document.querySelector("[data-memory]").value);
    return state.capabilities.memory_options.find((option) => option.memory_mb === memory);
  }
  function updateReview() {
    const memory = Number(document.querySelector("[data-memory]").value);
    const cost = selectedCost();
    document.querySelector("[data-review-pack]").textContent = state.modpack.name;
    document.querySelector("[data-review-version]").textContent = state.file.display_name;
    document.querySelector("[data-review-memory]").textContent = `${memory / 1024} GB`;
    document.querySelector("[data-cost]").innerHTML = `<strong>Estimated Railway usage: $${cost.estimated_monthly_min}–$${cost.estimated_monthly_max} per month.</strong> Actual cost varies with memory, CPU, storage, uptime, and network traffic. Modded Minecraft generally needs at least 4 GB.`;
  }
  async function submit() {
    clearError();
    if (!state.community || !state.modpack || !state.file) throw new Error("Complete the earlier steps first.");
    const payload = {
      server_name: document.querySelector("[data-server-name]").value.trim(),
      modpack_project_id: state.modpack.id,
      modpack_file_id: state.file.id,
      memory_mb: Number(document.querySelector("[data-memory]").value),
      accept_eula: document.querySelector("[data-accept-eula]").checked,
      accept_estimated_cost: document.querySelector("[data-accept-cost]").checked,
      accept_beta: document.querySelector("[data-accept-beta]").checked,
    };
    const data = await apiRequest(`/communities/${state.community}/managed-hosting-plans`, { method: "POST", body: JSON.stringify(payload) });
    state.plan = data.plan;
    document.querySelector("[data-result-title]").textContent = data.installation_available ? "Your server is approved for installation" : "Your exact server plan is saved";
    document.querySelector("[data-result-message]").textContent = data.next_step;
    document.querySelector("[data-final-charge]").hidden = !data.installation_available;
    document.querySelector("[data-install-actions]").hidden = !data.installation_available;
    showStep(5);
  }

  async function install() {
    clearError();
    if (!state.plan) throw new Error("Save an installation plan first.");
    const button = document.querySelector("[data-install]");
    button.disabled = true;
    const status = document.querySelector("[data-install-status]");
    status.hidden = false;
    status.textContent = "Creating persistent storage and installing your CurseForge modpack…";
    try {
      await apiRequest(`/communities/${state.community}/managed-hosting-plans/${state.plan.id}/install`, { method: "POST", body: "{}" });
      document.querySelector("[data-install-actions]").hidden = true;
      await pollPlan();
    } catch (error) {
      button.disabled = false;
      throw error;
    }
  }

  async function pollPlan() {
    const status = document.querySelector("[data-install-status]");
    for (let attempt = 0; attempt < 90; attempt += 1) {
      const data = await apiRequest(`/communities/${state.community}/managed-hosting-plans/${state.plan.id}`);
      state.plan = data.plan;
      if (data.plan.status === "online") {
        status.textContent = "Installation complete. Your world is ready for players.";
        document.querySelector("[data-player-address]").textContent = data.plan.public_endpoint;
        document.querySelector("[data-world-link]").href = data.plan.world_url;
        document.querySelector("[data-online-result]").hidden = false;
        return;
      }
      if (data.plan.status === "failed") {
        status.textContent = data.plan.last_error || "Installation stopped before the server came online.";
        document.querySelector("[data-install-actions]").hidden = false;
        document.querySelector("[data-install]").disabled = false;
        return;
      }
      status.textContent = `Minecraft installation is ${String(data.plan.status).replaceAll("_", " ")}. Large modpacks can take several minutes.`;
      await new Promise((resolve) => window.setTimeout(resolve, 5000));
    }
    status.textContent = "Installation is still running. You can safely leave this page and return later.";
  }

  document.querySelectorAll("[data-next]").forEach((button) => button.addEventListener("click", () => { try { requireStep(Number(button.dataset.next)); } catch (error) { fail(error); } }));
  document.querySelectorAll("[data-back]").forEach((button) => button.addEventListener("click", () => showStep(Number(button.dataset.back))));
  document.querySelector("[data-search-button]").addEventListener("click", () => search().catch(fail));
  document.querySelector("[data-search]").addEventListener("keydown", (event) => { if (event.key === "Enter") search().catch(fail); });
  document.querySelector("[data-memory]").addEventListener("change", updateReview);
  communitySelect.addEventListener("change", () => resumeExistingPlan(communitySelect.value).catch(fail));
  document.querySelector("[data-submit]").addEventListener("click", () => submit().catch(fail));
  document.querySelector("[data-install]").addEventListener("click", () => install().catch(fail));
  if (!(await resumeExistingPlan(communitySelect.value))) showStep(1);
})().catch((error) => showError(error.message));
