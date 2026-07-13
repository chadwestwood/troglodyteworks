(async function initCommunityInvitations() {
  await requireCurrentUser();
  const communityId = recall("twe.community_id") || await findCommunityId();
  const directForm = document.querySelector("[data-direct-invite-form]");
  const linkForm = document.querySelector("[data-link-invite-form]");
  const createdLink = document.querySelector("[data-created-link]");

  directForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(directForm);
    try {
      await apiRequest(`/communities/${communityId}/invitations`, {
        method: "POST",
        body: JSON.stringify({
          invitation_type: "direct",
          email: formData.get("email"),
          initial_role: formData.get("initial_role"),
        }),
      });
      directForm.reset();
      await renderInvitations(communityId);
    } catch (error) {
      showError(error.message);
    }
  });

  linkForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(linkForm);
    try {
      const data = await apiRequest(`/communities/${communityId}/invitations`, {
        method: "POST",
        body: JSON.stringify({
          invitation_type: "link",
          initial_role: formData.get("initial_role"),
          maximum_uses: formData.get("maximum_uses"),
          expires_in_hours: formData.get("expires_in_hours"),
          requires_approval: formData.get("requires_approval") === "on",
        }),
      });
      const url = `${window.location.origin}${data.invitation.url}`;
      createdLink.textContent = url;
      createdLink.hidden = false;
      await navigator.clipboard?.writeText(url).catch(() => {});
      await renderInvitations(communityId);
    } catch (error) {
      showError(error.message);
    }
  });

  await renderInvitations(communityId);
})();

async function renderInvitations(communityId) {
  const list = document.querySelector("[data-invitations-list]");
  if (!list) {
    return;
  }
  const data = await apiRequest(`/communities/${communityId}/invitations`);
  list.innerHTML = "";
  data.invitations.forEach((invitation) => {
    const row = document.createElement("div");
    row.className = "resource-row";
    const label = invitation.invited_user?.display_name || invitation.invitation_type;
    row.innerHTML = `<span><strong>${label}</strong><small>${invitation.initial_role} - ${invitation.status} - ${invitation.remaining_uses} use(s) left</small></span>`;
    if (invitation.status === "pending") {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Revoke";
      button.addEventListener("click", async () => {
        try {
          await apiRequest(`/communities/${communityId}/invitations/${invitation.id}/revoke`, { method: "POST" });
          await renderInvitations(communityId);
        } catch (error) {
          showError(error.message);
        }
      });
      row.appendChild(button);
    }
    list.appendChild(row);
  });
}

async function findCommunityId() {
  const data = await apiRequest("/communities");
  const community = data.communities.find((item) => item.slug === "cohorts-in-the-wild") || data.communities[0];
  remember("twe.community_id", community?.id);
  return community?.id;
}
