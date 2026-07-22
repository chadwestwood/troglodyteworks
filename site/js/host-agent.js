(async function initHostAgent() {
  await requireCurrentUser();
  const communities = await apiRequest("/communities");
  const community = communities.communities.find((item) => item.id === recall("twe.community_id")) || communities.communities[0];
  if (!community || community.role !== "owner") {
    document.querySelector("[data-host-agent-panel]")?.remove();
    return;
  }
  const pairingButton = document.querySelector("[data-create-pairing]");
  const result = document.querySelector("[data-pairing-result]");
  const list = document.querySelector("[data-host-agents]");

  async function render() {
    const data = await apiRequest(`/communities/${community.id}/host-agents`);
    clearNode(list);
    if (!data.agents.length) {
      list.appendChild(createResourceRow("No paired computers yet", "Create a pairing command to begin."));
      return;
    }
    data.agents.forEach((agent) => {
      list.appendChild(createResourceRow(agent.name, `${agent.status} · last report ${agent.last_seen_at || "never"}`));
      agent.resources.forEach((resource) => {
        const row = createResourceRow(resource.name, `${resource.game_key.replaceAll("_", " ")} · ${resource.status}`,
          resource.bound_game_server_id ? "Connected" : null);
        if (!resource.bound_game_server_id) {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = "Connect to this Community";
          button.addEventListener("click", async () => {
            button.disabled = true;
            try {
              await apiRequest(`/communities/${community.id}/host-agents/resources/${resource.id}/connect`, { method: "POST" });
              await render();
            } catch (error) {
              showError(error.message);
              button.disabled = false;
            }
          });
          row.appendChild(button);
        }
        list.appendChild(row);
      });
    });
  }

  pairingButton.addEventListener("click", async () => {
    pairingButton.disabled = true;
    try {
      const data = await apiRequest(`/communities/${community.id}/host-agents/pairings`, { method: "POST" });
      result.hidden = false;
      clearNode(result);
      result.append("Run this within 30 minutes: ", createTextElement("code", data.pairing.command));
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "text-button";
      copy.textContent = "Copy command";
      copy.addEventListener("click", async () => {
        await navigator.clipboard.writeText(data.pairing.command);
        copy.textContent = "Copied";
      });
      result.append(" ", copy);
    } catch (error) {
      showError(error.message);
    } finally {
      pairingButton.disabled = false;
    }
  });
  await render();
}()).catch((error) => showError(error.message));
