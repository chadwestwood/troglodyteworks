(async function initDiscordAccessPage() {
  await requireCurrentUser();

  const form = document.querySelector("[data-discord-access-form]");
  const status = document.querySelector("[data-status]");
  const communitySelect = document.querySelector("[data-provider-community-select]");
  const instanceSelect = document.querySelector("[data-game-instance-select]");
  const discordGuildSelect = document.querySelector("[data-discord-guild-select]");
  const discordGuildHelp = document.querySelector("[data-discord-guild-help]");
  const refreshDiscordGuilds = document.querySelector("[data-refresh-discord-guilds]");
  const linkedDiscordSummary = document.querySelector("[data-linked-discord-summary]");
  const requestList = document.querySelector("[data-discord-access-requests]");
  const createShareButton = document.querySelector("[data-create-trog-share]");
  const shareResult = document.querySelector("[data-trog-share-result]");
  if (!form) {
    return;
  }
  const pageParameters = new URLSearchParams(window.location.search);
  const requestedCommunityId = pageParameters.get("community_id") || "";
  const requestedInstanceId = pageParameters.get("instance_id") || "";
  const setupReturnTo = requestedCommunityId && requestedInstanceId
    ? `/discord/request-access/?${new URLSearchParams({ community_id: requestedCommunityId, instance_id: requestedInstanceId })}`
    : "/discord/request-access/";
  const allowlist = document.querySelector("[data-channel-allowlist]");
  form.querySelectorAll('[name="channel_scope"]').forEach((radio) => radio.addEventListener("change", () => {
    allowlist.hidden = form.elements.channel_scope.value !== "allowlist";
  }));
  remember("twe.trog_return_to", setupReturnTo);
  const identities = await apiRequest("/account/identities");
  if (!identities.identities.discord.connected) {
    clearNode(status);
    const copy = document.createElement("span");
    copy.textContent = "Connect Discord before requesting Trog access so TWE can verify the Discord servers you manage.";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "primary-button";
    button.textContent = "Connect Discord";
    button.addEventListener("click", async () => {
      try {
        const data = await apiRequest("/account/identities/discord/connect", {
          method: "POST",
          body: JSON.stringify({ return_to: setupReturnTo }),
        });
        window.location.href = data.oauth.authorization_url;
      } catch (error) {
        showError(error.message);
      }
    });
    status.appendChild(copy);
    status.appendChild(document.createTextNode(" "));
    status.appendChild(button);
    form.hidden = true;
    return;
  }
  if (linkedDiscordSummary) {
    linkedDiscordSummary.textContent = `Discord connected: ${identities.identities.discord.provider_username || "linked account"}.`;
  }
  await populateManagedGuildChoices(discordGuildSelect, discordGuildHelp);
  refreshDiscordGuilds?.addEventListener("click", () => refreshManagedDiscordGuilds(refreshDiscordGuilds, setupReturnTo));
  await populateProviderChoices(
    communitySelect,
    instanceSelect,
    requestedCommunityId,
    requestedInstanceId,
  );
  if (requestedCommunityId && requestedInstanceId) {
    communitySelect.disabled = true;
    instanceSelect.disabled = true;
    status.textContent = "This setup is locked to the map or world you opened. Choose only the Discord server and channels where its Trog should answer.";
  }
  communitySelect?.addEventListener("change", () => populateInstanceChoices(communitySelect.value, instanceSelect));
  await renderAccessRequests(requestList);
  createShareButton?.addEventListener("click", async () => {
    if (!communitySelect.value || !instanceSelect.value) {
      showError("Choose a Community and hosted game first.");
      return;
    }
    createShareButton.disabled = true;
    try {
      const data = await apiRequest("/discord/trog-share-links", {
        method: "POST",
        body: JSON.stringify({
          provider_community_id: communitySelect.value,
          game_instance_id: instanceSelect.value,
        }),
      });
      clearNode(shareResult);
      shareResult.hidden = false;
      shareResult.append("Private link: ");
      const link = document.createElement("a");
      link.href = data.share.url;
      link.textContent = data.share.url;
      link.target = "_blank";
      link.rel = "noopener";
      shareResult.appendChild(link);
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "text-button";
      copy.textContent = "Copy link";
      copy.addEventListener("click", async () => {
        await navigator.clipboard.writeText(data.share.url);
        copy.textContent = "Copied";
      });
      shareResult.append(" ", copy);
    } catch (error) {
      showError(error.message);
    } finally {
      createShareButton.disabled = false;
    }
  });

  const callback = pageParameters;
  if (callback.get("discord_error")) {
    showError(callback.get("discord_error"));
  } else if (callback.get("verified") === "1" && callback.get("request")) {
    status.textContent = "Discord confirmed that you manage the selected server. Continue in Discord to install Trog.";
    await startDiscordAuthorization(callback.get("request"), "bot_install");
    return;
  } else if (callback.get("installed") === "1") {
    status.textContent = callback.get("status") === "active"
      ? "Trog is installed and this Community connection is active."
      : "Trog is installed. A Community owner or admin must approve access before its hosted game information becomes active.";
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const providerCommunityId = communitySelect.value.trim();
    const gameInstanceId = instanceSelect.value.trim();
    const discordGuildId = data.get("discord_guild_id").trim();
    const channelScope = data.get("channel_scope") || "all";
    const allowedChannelIds = [];

    try {
      const requestData = await apiRequest("/discord/instance-access-requests", {
        method: "POST",
        body: JSON.stringify({
          provider_community_id: providerCommunityId,
          game_instance_id: gameInstanceId,
          requested_capabilities: [
            "instance.status.read",
            "instance.players.count.read",
            "instance.players.names.read",
            "instance.mods.names.read",
          ],
          channel_scope: channelScope,
          allowed_channel_ids: allowedChannelIds,
        }),
      });

      const requestId = requestData.request.id;
      await startDiscordAuthorization(requestId, "guild_verification", discordGuildId);
    } catch (error) {
      showError(error.message);
    }
  });
})();

async function startDiscordAuthorization(requestId, purpose, discordGuildId = null) {
  const oauth = await apiRequest(`/discord/instance-access-requests/${requestId}/oauth-state`, {
    method: "POST",
    body: JSON.stringify({ purpose, discord_guild_id: discordGuildId }),
  });
  window.location.href = oauth.oauth.authorization_url;
}

async function refreshManagedDiscordGuilds(button, returnTo = "/discord/request-access/") {
  button.disabled = true;
  button.textContent = "Opening Discord...";
  try {
    const data = await apiRequest("/account/identities/discord/connect", {
      method: "POST",
      body: JSON.stringify({ return_to: returnTo }),
    });
    window.location.href = data.oauth.authorization_url;
  } catch (error) {
    button.disabled = false;
    button.textContent = "Refresh Discord servers";
    showError(error.message);
  }
}

async function populateManagedGuildChoices(select, help) {
  if (!select) {
    return;
  }
  const data = await apiRequest("/discord/managed-guilds");
  clearNode(select);
  if (!data.guilds.length) {
    select.appendChild(new Option("Refresh Discord to find servers", ""));
    select.disabled = true;
    if (help) {
      help.textContent = "No verified manageable servers are available yet. Refresh Discord servers and authorize the guilds scope. If the list remains empty, ask a server owner to grant you Administrator or Manage Server permission, or have that administrator complete this setup.";
    }
    return;
  }
  select.disabled = false;
  select.appendChild(new Option("Choose a verified Discord server", ""));
  data.guilds.forEach((guild) => {
    const authority = guild.authority_source === "owner"
      ? "owner"
      : guild.authority_source === "administrator" ? "administrator" : "manage server";
    select.appendChild(new Option(`${guild.name} (${authority})`, guild.id));
  });
  if (help) {
    help.textContent = "Only servers Discord confirms you can manage are shown. TWE will verify the selected server again before installation.";
  }
}

async function renderAccessRequests(list) {
  if (!list) {
    return;
  }
  const data = await apiRequest("/discord/installations");
  clearNode(list);
  if (!data.installations.length) {
    list.appendChild(createResourceRow("No Trog access requests yet.", "Create a request above to begin."));
    return;
  }
  data.installations.forEach((request) => {
    const guild = request.consumer_discord_guild_name || request.consumer_discord_guild_id || "Discord verification pending";
    const channels = request.requested_channel_ids.length
      ? `${request.requested_channel_ids.length} allowed channel(s)`
      : "all visible channels";
    const row = createResourceRow(
      `${request.provider_community_name} - ${request.instance_name}`,
      `${guild} · ${request.status.replaceAll("_", " ")} · ${channels}`,
    );
    if (request.is_requester && !request.discord_approved_at && !["denied", "revoked"].includes(request.status)) {
      const verify = document.createElement("button");
      verify.type = "button";
      verify.textContent = "Verify Discord server";
      verify.addEventListener("click", () => {
        const selectedGuildId = document.querySelector("[data-discord-guild-select]")?.value;
        if (!selectedGuildId) {
          showError("Choose a verified Discord server above, then try again.");
          return;
        }
        startDiscordAuthorization(request.id, "guild_verification", selectedGuildId)
          .catch((error) => showError(error.message));
      });
      row.appendChild(verify);
    }
    if (request.is_requester && request.discord_approved_at && !request.installed_at && !["denied", "revoked"].includes(request.status)) {
      const install = document.createElement("button");
      install.type = "button";
      install.textContent = "Install Trog";
      install.addEventListener("click", () => startDiscordAuthorization(request.id, "bot_install").catch((error) => showError(error.message)));
      row.appendChild(install);
    }
    if (request.can_manage_provider && request.discord_approved_at && !request.provider_approved_at && !["denied", "revoked"].includes(request.status)) {
      const approve = document.createElement("button");
      approve.type = "button";
      approve.textContent = "Approve Read Access";
      approve.addEventListener("click", async () => {
        try {
          await apiRequest(`/discord/instance-access-requests/${request.id}/provider-approval`, {
            method: "POST",
            body: JSON.stringify({
              approved_capabilities: request.capabilities,
              channel_scope: request.channel_scope,
            }),
          });
          await renderAccessRequests(list);
        } catch (error) {
          showError(error.message);
        }
      });
      row.appendChild(approve);
    }
    if (request.can_manage_provider && !request.provider_approved_at && !["denied", "revoked"].includes(request.status)) {
      const deny = document.createElement("button");
      deny.type = "button";
      deny.textContent = "Deny";
      deny.addEventListener("click", async () => {
        if (!window.confirm(`Deny Trog access for ${guild}?`)) {
          return;
        }
        try {
          await apiRequest(`/discord/instance-access-requests/${request.id}/provider-denial`, { method: "POST" });
          await renderAccessRequests(list);
        } catch (error) {
          showError(error.message);
        }
      });
      row.appendChild(deny);
    }
    if (request.can_manage_provider && request.status === "active") {
      const revoke = document.createElement("button");
      revoke.type = "button";
      revoke.textContent = "Revoke";
      revoke.addEventListener("click", async () => {
        if (!window.confirm(`Revoke Trog read access for ${guild}?`)) {
          return;
        }
        try {
          await apiRequest(`/discord/instance-access-grants/${request.id}/revoke`, { method: "POST" });
          await renderAccessRequests(list);
        } catch (error) {
          showError(error.message);
        }
      });
      row.appendChild(revoke);
    }
    if (request.can_delegate_operator && request.status === "active" && request.requested_by) {
      const operator = document.createElement("button");
      operator.type = "button";
      operator.className = "secondary-action";
      operator.textContent = request.operator_rights
        ? `Remove ${request.requester_name}'s Trog operator rights`
        : `Grant ${request.requester_name} Trog operator rights`;
      operator.addEventListener("click", async () => {
        const enabling = !request.operator_rights;
        const warning = enabling
          ? `Allow ${request.requester_name} to add mods and restart only ${request.instance_name}?`
          : `Remove ${request.requester_name}'s mod and restart rights for ${request.instance_name}?`;
        if (!window.confirm(warning)) {
          return;
        }
        operator.disabled = true;
        try {
          await apiRequest(`/discord/instance-access-grants/${request.id}/operator-rights`, {
            method: "PATCH",
            body: JSON.stringify({ enabled: enabling }),
          });
          await renderAccessRequests(list);
        } catch (error) {
          showError(error.message);
          operator.disabled = false;
        }
      });
      row.appendChild(operator);
    }
    if (request.can_manage_discord && request.status === "active") {
      const route = document.createElement("button");
      route.type = "button";
      route.className = "secondary-action";
      route.textContent = "Choose Discord channels";
      route.addEventListener("click", () => renderChannelRouteEditor(row, request, route));
      row.appendChild(route);
    }
    list.appendChild(row);
  });
}

async function renderChannelRouteEditor(row, request, button) {
  button.disabled = true;
  try {
    const data = await apiRequest(`/discord/installations/${request.consumer_discord_guild_id}/channels`);
    const panel = document.createElement("fieldset");
    panel.className = "content-stack";
    const legend = document.createElement("legend");
    legend.textContent = `Channels that should use ${request.provider_community_name} - ${request.instance_name}`;
    panel.appendChild(legend);
    const selected = new Set(request.requested_channel_ids || []);
    data.channels.forEach((channel) => {
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = channel.id;
      checkbox.checked = selected.has(channel.id);
      label.append(checkbox, document.createTextNode(` #${channel.name}`));
      panel.appendChild(label);
    });
    const save = document.createElement("button");
    save.type = "button";
    save.className = "primary-button";
    save.textContent = "Save channel routing";
    save.addEventListener("click", async () => {
      const channelIds = [...panel.querySelectorAll('input[type="checkbox"]:checked')]
        .map((checkbox) => checkbox.value);
      if (!channelIds.length) {
        showError("Choose at least one Discord channel.");
        return;
      }
      save.disabled = true;
      try {
        await apiRequest(`/discord/instance-access-grants/${request.id}/channels`, {
          method: "PATCH",
          body: JSON.stringify({ channel_ids: channelIds }),
        });
        await renderAccessRequests(document.querySelector("[data-discord-access-requests]"));
      } catch (error) {
        showError(error.message);
        save.disabled = false;
      }
    });
    panel.appendChild(save);
    row.appendChild(panel);
    button.remove();
  } catch (error) {
    showError(error.message);
    button.disabled = false;
  }
}

async function populateProviderChoices(
  communitySelect,
  instanceSelect,
  preferredCommunityId = "",
  preferredInstanceId = "",
) {
  if (!communitySelect || !instanceSelect) {
    return;
  }
  const data = await apiRequest("/communities");
  clearNode(communitySelect);
  if (!data.communities.length) {
    communitySelect.appendChild(new Option("Join a provider Community first", ""));
    instanceSelect.appendChild(new Option("No Communities available", ""));
    return;
  }
  data.communities.forEach((community) => {
    communitySelect.appendChild(new Option(`${community.name} (${community.role})`, community.id));
  });
  const selectedCommunity = preferredCommunityId || recall("twe.community_id");
  if (selectedCommunity && data.communities.some((community) => community.id === selectedCommunity)) {
    communitySelect.value = selectedCommunity;
  }
  await populateInstanceChoices(communitySelect.value, instanceSelect, preferredInstanceId);
}

async function populateInstanceChoices(communityId, instanceSelect, preferredInstanceId = "") {
  clearNode(instanceSelect);
  if (!communityId) {
    instanceSelect.appendChild(new Option("Choose a Community first", ""));
    return;
  }
  remember("twe.community_id", communityId);
  const serversData = await apiRequest(`/communities/${communityId}/game-servers`);
  const options = [];
  for (const server of serversData.game_servers) {
    const instancesData = await apiRequest(`/game-servers/${server.id}/instances`);
    instancesData.instances.forEach((instance) => {
      options.push({ server, instance });
    });
  }
  if (!options.length) {
    instanceSelect.appendChild(new Option("No Instances found for this Community", ""));
    return;
  }
  options.forEach(({ server, instance }) => {
    instanceSelect.appendChild(new Option(`${server.name} - ${instance.name}`, instance.id));
  });
  const selectedInstance = preferredInstanceId || recall("twe.instance_id");
  if (selectedInstance && options.some(({ instance }) => instance.id === selectedInstance)) {
    instanceSelect.value = selectedInstance;
  }
}
