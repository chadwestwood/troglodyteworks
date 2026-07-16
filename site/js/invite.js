(async function initInviteLanding() {
  const token = invitationTokenFromPath();
  if (!token) {
    showError("Invitation token is missing.");
    return;
  }
  remember("twe.pending_invite_token", token);
  configureInviteOAuthLinks(token);

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
    invitation.requires_approval
      ? `Request the ${invitation.initial_role} role. A Community leader must approve you before you join. This does not grant server operation, Genesis, or Discord installation access.`
      : `This invitation grants the ${invitation.initial_role} role. It does not grant server operation, Genesis, or Discord installation access.`
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

  const memberActions = document.querySelector("[data-member-actions]");
  const acceptButton = document.querySelector("[data-accept-invite]");
  memberActions.hidden = false;
  if (invitation.requires_approval && acceptButton) {
    acceptButton.textContent = "Request to Join";
  }
  acceptButton?.addEventListener("click", async () => {
    try {
      const data = await apiRequest(`/community-invitations/${token}/accept`, { method: "POST" });
      window.localStorage.removeItem("twe.pending_invite_token");
      if (data.redemption.status === "pending_approval") {
        memberActions.hidden = true;
        const status = document.querySelector("[data-invite-status]");
        status.textContent = "Request sent. A Cohorts in the Wild leader can now approve your membership.";
        status.hidden = false;
      } else {
        window.location.href = "/communities/";
      }
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

function configureInviteOAuthLinks(token) {
  const next = `/invite/${token}/`;
  document.querySelectorAll("[data-oauth-start]").forEach((link) => {
    const provider = link.dataset.oauthStart;
    link.href = `/api/v1/auth/${provider}/start?next=${encodeURIComponent(next)}`;
  });
}
