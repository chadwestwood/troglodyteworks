(async function () {
  const grid = document.querySelector("[data-discord-matches]");
  try {
    let user = null;
    try {
      user = (await apiRequest("/auth/me")).user;
    } catch (_error) {}
    if (!user) {
      grid.replaceChildren(discoveryCard("Connect Discord", "Sign in or create an account to find Communities from Discord.", "/auth/sign-in.html?next=/explore/"));
      return;
    }
    const identities = await apiRequest("/account/identities");
    if (!identities.identities.discord.connected) {
      const card = discoveryCard("Connect Discord", "We use your Discord memberships to find relevant Communities.", "#");
      card.addEventListener("click", async (event) => {
        event.preventDefault();
        const data = await apiRequest("/account/identities/discord/connect", {method: "POST", body: JSON.stringify({return_to: "/explore/"})});
        window.location.href = data.oauth.authorization_url;
      });
      grid.replaceChildren(card);
      return;
    }
    const data = await apiRequest("/onboarding/discord-matches");
    const matches = data.communities || data.matches || [];
    if (!matches.length) {
      grid.replaceChildren(discoveryCard("No matches yet", "Ask a Discord admin to connect Trog, or use a private Community invite.", "/onboarding/?role=member"));
      return;
    }
    grid.replaceChildren(...matches.map((match) => {
      const card = discoveryCard(match.name, match.discord_guild_name || "Connected through Discord", "#");
      card.addEventListener("click", async (event) => {
        event.preventDefault();
        await apiRequest(`/onboarding/discord-matches/${match.id}/join`, {method: "POST"});
        window.location.href = `/communities/${encodeURIComponent(match.slug)}/`;
      });
      return card;
    }));
  } catch (error) {
    grid.replaceChildren(discoveryCard("Discord discovery unavailable", "You can still join with an invitation or create a Community.", "/communities/"));
  }

  function discoveryCard(title, detail, href) {
    const card = document.createElement("a");
    card.className = "app-tile app-tile--action";
    card.href = href;
    const icon = document.createElement("span");
    icon.textContent = "◎";
    const strong = document.createElement("strong");
    strong.textContent = title;
    const small = document.createElement("small");
    small.textContent = detail;
    card.append(icon, strong, small);
    return card;
  }
})();
