(async function initDiscordAccessPage() {
  await requireCurrentUser();

  const form = document.querySelector("[data-discord-access-form]");
  const status = document.querySelector("[data-status]");
  if (!form) {
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const providerCommunityId = data.get("provider_community_id").trim();
    const gameInstanceId = data.get("game_instance_id").trim();
    const discordUserId = data.get("discord_user_id").trim();
    const discordGuildId = data.get("discord_guild_id").trim();
    const permissions = data.get("permissions").trim();
    const allowedChannelIds = data.get("allowed_channel_ids")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);

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
          ],
          channel_scope: allowedChannelIds.length ? "allowlist" : "all",
        }),
      });

      const requestId = requestData.request.id;
      await apiRequest("/discord/identity/link", {
        method: "POST",
        body: JSON.stringify({ discord_user_id: discordUserId }),
      });
      const oauth = await apiRequest(`/discord/instance-access-requests/${requestId}/oauth-state`, {
        method: "POST",
        body: JSON.stringify({ purpose: "guild_verification" }),
      });
      await apiRequest(`/discord/instance-access-requests/${requestId}/discord-verification`, {
        method: "POST",
        body: JSON.stringify({
          state: oauth.oauth.state,
          discord_user_id: discordUserId,
          discord_guild_id: discordGuildId,
          discord_guild_name: "LizzLive",
          permissions,
        }),
      });

      await apiRequest(`/discord/instance-access-requests/${requestId}/bot-installation`, {
        method: "POST",
        body: JSON.stringify({ allowed_channel_ids: allowedChannelIds }),
      });

      status.textContent = "Request created and Discord side verified. A Cohorts owner still needs to approve the provider grant before it becomes active.";
    } catch (error) {
      showError(error.message);
    }
  });
})();
