(async function initTrogShare() {
  const token = location.pathname.split("/").filter(Boolean).at(-1);
  const heading = document.querySelector("[data-share-heading]");
  const copy = document.querySelector("[data-share-copy]");
  const errorNode = document.querySelector("[data-error]");
  const button = document.querySelector("[data-redeem]");
  try {
    const data = await apiRequest(`/discord/trog-share-links/${encodeURIComponent(token)}`);
    heading.textContent = `${data.share.community} is sharing ${data.share.instance}`;
    copy.textContent = `Add this Trog connection to a Discord server you manage. It provides approved read-only information for ${data.share.game_server} - ${data.share.instance}; it does not make you a member or give you control of the hosted game.`;
    button.hidden = false;
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await requireCurrentUser();
        const redeemed = await apiRequest(`/discord/trog-share-links/${encodeURIComponent(token)}/redeem`, { method: "POST" });
        location.href = redeemed.continue_to;
      } catch (error) {
        if (error.status === 401) {
          remember("twe.trog_return_to", location.pathname);
          location.href = "/auth/sign-in.html";
          return;
        }
        errorNode.textContent = error.message;
        errorNode.hidden = false;
        button.disabled = false;
      }
    });
  } catch (error) {
    heading.textContent = "This invitation is unavailable";
    copy.textContent = "Ask the game owner for a new private Trog invitation.";
    errorNode.textContent = error.message;
    errorNode.hidden = false;
  }
}());
