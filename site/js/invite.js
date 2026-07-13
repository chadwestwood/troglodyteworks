(async function initInviteLanding() {
  const token = invitationTokenFromPath();
  if (!token) {
    showError("Invitation token is missing.");
    return;
  }
  remember("twe.pending_invite_token", token);

  let invitation;
  try {
    const data = await apiRequest(`/community-invitations/${token}`, { method: "GET" });
    invitation = data.invitation;
  } catch (error) {
    showError(error.message);
    return;
  }

  setText("[data-invite-community]", invitation.community.name);
  setText(
    "[data-invite-details]",
    `This invitation grants the ${invitation.initial_role} role. It does not grant server operation, Genesis, or Discord installation access.`
  );

  let user = null;
  try {
    const data = await apiRequest("/auth/me");
    user = data.user;
  } catch (_error) {
    document.querySelector("[data-auth-actions]").hidden = false;
    return;
  }

  if (!user) {
    document.querySelector("[data-auth-actions]").hidden = false;
    return;
  }

  document.querySelector("[data-member-actions]").hidden = false;
  document.querySelector("[data-accept-invite]")?.addEventListener("click", async () => {
    try {
      await apiRequest(`/community-invitations/${token}/accept`, { method: "POST" });
      window.localStorage.removeItem("twe.pending_invite_token");
      window.location.href = "/communities/";
    } catch (error) {
      showError(error.message);
    }
  });
  document.querySelector("[data-decline-invite]")?.addEventListener("click", async () => {
    try {
      await apiRequest(`/community-invitations/${token}/decline`, { method: "POST" });
      window.localStorage.removeItem("twe.pending_invite_token");
      window.location.href = "/";
    } catch (error) {
      showError(error.message);
    }
  });
})();

function invitationTokenFromPath() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[0] === "invite" ? parts[1] : null;
}
