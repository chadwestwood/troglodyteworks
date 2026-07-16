(async function initCommunityInvitations() {
  const user = await requireCurrentUser();
  if (!user) {
    return;
  }

  const directForm = document.querySelector("[data-direct-invite-form]");
  const linkForm = document.querySelector("[data-link-invite-form]");
  const copyButton = document.querySelector("[data-copy-link]");

  let communityId;
  try {
    communityId = await findCohortsCommunityId();
    const data = await loadInvitationDashboard(communityId);
    configureRoleOptions(data.grantableRoles);
    renderInvitationDashboard(communityId, data);
  } catch (error) {
    showPageError(error.message);
    setFormDisabled(directForm, true);
    setFormDisabled(linkForm, true);
    return;
  }

  directForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();
    const formData = new FormData(directForm);
    if (!confirmElevatedRole(formData.get("initial_role"))) {
      return;
    }
    setFormDisabled(directForm, true);
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
      setDefaultRoles();
      showPageStatus(`Invitation sent to ${formData.get("email")}.`);
      await refreshInvitationDashboard(communityId);
    } catch (error) {
      showPageError(error.message);
    } finally {
      setFormDisabled(directForm, false);
    }
  });

  linkForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();
    const formData = new FormData(linkForm);
    if (!confirmElevatedRole(formData.get("initial_role"))) {
      return;
    }
    setFormDisabled(linkForm, true);
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
      showCreatedLink(`${window.location.origin}${data.invitation.url}`);
      showPageStatus("Signup link created.");
      await refreshInvitationDashboard(communityId);
    } catch (error) {
      showPageError(error.message);
    } finally {
      setFormDisabled(linkForm, false);
    }
  });

  copyButton?.addEventListener("click", copyCreatedLink);
})();

async function loadInvitationDashboard(communityId) {
  const [invitationData, approvalData] = await Promise.all([
    apiRequest(`/communities/${communityId}/invitations`),
    apiRequest(`/communities/${communityId}/invitation-redemptions/pending`),
  ]);
  return {
    invitations: invitationData.invitations,
    redemptions: approvalData.redemptions,
    grantableRoles: invitationData.grantable_roles,
  };
}

async function refreshInvitationDashboard(communityId) {
  const data = await loadInvitationDashboard(communityId);
  configureRoleOptions(data.grantableRoles);
  renderInvitationDashboard(communityId, data);
}

function renderInvitationDashboard(communityId, data) {
  renderMembershipRequests(communityId, data.redemptions);
  renderInvitations(communityId, data.invitations);
}

function renderMembershipRequests(communityId, redemptions) {
  const list = document.querySelector("[data-approval-list]");
  clearNode(list);
  if (!redemptions.length) {
    list?.appendChild(createResourceRow("No membership requests", "Requests that need review will appear here."));
    return;
  }

  redemptions.forEach((redemption) => {
    const name = redemption.user.display_name || redemption.user.email;
    const detail = `${redemption.user.email} · Requested ${roleLabel(redemption.initial_role)} · ${formatDate(redemption.redeemed_at)}`;
    const row = createResourceRow(name, detail);
    const actions = document.createElement("div");
    actions.className = "button-row";
    actions.appendChild(createDecisionButton("Approve", async () => {
      await decideRedemption(communityId, redemption.id, "approve");
    }));
    actions.appendChild(createDecisionButton("Deny", async () => {
      if (window.confirm(`Deny ${name}'s membership request?`)) {
        await decideRedemption(communityId, redemption.id, "deny");
      }
    }, true));
    row.appendChild(actions);
    list.appendChild(row);
  });
}

function renderInvitations(communityId, invitations) {
  const activeList = document.querySelector("[data-active-invitations-list]");
  const historyList = document.querySelector("[data-invitation-history-list]");
  clearNode(activeList);
  clearNode(historyList);
  const active = invitations.filter((invitation) => invitation.status === "pending");
  const history = invitations.filter((invitation) => invitation.status !== "pending");

  if (!active.length) {
    activeList?.appendChild(createResourceRow("No active invitations", "Create an account invitation or signup link above."));
  }
  active.forEach((invitation) => activeList?.appendChild(createInvitationRow(communityId, invitation, true)));

  if (!history.length) {
    historyList?.appendChild(createResourceRow("No invitation history", "Completed invitations will appear here."));
  }
  history.forEach((invitation) => historyList?.appendChild(createInvitationRow(communityId, invitation, false)));
}

function createInvitationRow(communityId, invitation, active) {
  const direct = invitation.invitation_type === "direct";
  const label = direct
    ? invitation.invited_user?.display_name || invitation.invited_user?.email || "TWE member"
    : "Shareable signup link";
  const details = [];
  if (direct && invitation.invited_user?.email && invitation.invited_user.email !== label) {
    details.push(invitation.invited_user.email);
  }
  details.push(roleLabel(invitation.initial_role));
  if (!direct) {
    details.push(`${invitation.remaining_uses} of ${invitation.maximum_uses} uses left`);
  }
  details.push(invitation.requires_approval ? "Leader review required" : "Joins immediately");
  details.push(`Expires ${formatDate(invitation.expires_at)}`);
  if (!active) {
    details.push(statusLabel(invitation.status));
  }

  const row = createResourceRow(label, details.join(" · "));
  if (active) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Revoke";
    button.className = "secondary-action";
    button.addEventListener("click", async () => {
      if (!window.confirm(`Revoke this invitation for ${label}?`)) {
        return;
      }
      button.disabled = true;
      clearMessages();
      try {
        await apiRequest(`/communities/${communityId}/invitations/${invitation.id}/revoke`, { method: "POST" });
        showPageStatus("Invitation revoked.");
        await refreshInvitationDashboard(communityId);
      } catch (error) {
        showPageError(error.message);
        button.disabled = false;
      }
    });
    row.appendChild(button);
  }
  return row;
}

function createDecisionButton(label, callback, secondary = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  if (secondary) {
    button.className = "secondary-action";
  }
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await callback();
    } catch (error) {
      showPageError(error.message);
      button.disabled = false;
    }
  });
  return button;
}

async function decideRedemption(communityId, redemptionId, decision) {
  clearMessages();
  await apiRequest(`/communities/${communityId}/invitation-redemptions/${redemptionId}/${decision}`, { method: "POST" });
  showPageStatus(decision === "approve" ? "Membership request approved." : "Membership request denied.");
  await refreshInvitationDashboard(communityId);
}

async function findCohortsCommunityId() {
  const data = await apiRequest("/communities");
  const community = data.communities.find((item) => item.slug === "cohorts-in-the-wild");
  if (!community) {
    throw new Error("Cohorts in the Wild is not available to this account. No other Community was selected.");
  }
  remember("twe.community_id", community.id);
  return community.id;
}

function configureRoleOptions(roles) {
  document.querySelectorAll("select[name='initial_role']").forEach((select) => {
    const currentValue = select.value;
    clearNode(select);
    roles.forEach((role) => {
      const option = document.createElement("option");
      option.value = role;
      option.textContent = roleLabel(role);
      select.appendChild(option);
    });
    select.value = roles.includes(currentValue) ? currentValue : roles[0];
    updateRoleDescription(select);
    select.onchange = () => updateRoleDescription(select);
  });
}

function updateRoleDescription(select) {
  const description = select.closest("form")?.querySelector("[data-role-description]");
  const descriptions = {
    member: "Members can participate in the Community but cannot manage invitations.",
    moderator: "Moderators can manage members and invite people as Members.",
    admin: "Administrators can manage the Community and assign Moderator or Member roles.",
  };
  if (description) {
    description.textContent = descriptions[select.value] || "";
  }
}

function setDefaultRoles() {
  document.querySelectorAll("select[name='initial_role']").forEach((select) => {
    if ([...select.options].some((option) => option.value === "member")) {
      select.value = "member";
      updateRoleDescription(select);
    }
  });
}

function confirmElevatedRole(role) {
  if (role !== "admin") {
    return true;
  }
  return window.confirm("Administrators can manage this Community and invite other leaders. Create this Administrator invitation?");
}

function showCreatedLink(url) {
  const container = document.querySelector("[data-created-link]");
  const input = document.querySelector("[data-created-link-value]");
  const copyStatus = document.querySelector("[data-copy-status]");
  if (input) {
    input.value = url;
  }
  if (copyStatus) {
    copyStatus.textContent = "";
  }
  if (container) {
    container.hidden = false;
  }
}

async function copyCreatedLink() {
  const input = document.querySelector("[data-created-link-value]");
  const status = document.querySelector("[data-copy-status]");
  if (!input?.value) {
    return;
  }
  try {
    await navigator.clipboard.writeText(input.value);
    status.textContent = "Copied to clipboard.";
  } catch (error) {
    input.focus();
    input.select();
    status.textContent = "Clipboard access was unavailable. The full link is selected for copying.";
  }
}

function setFormDisabled(form, disabled) {
  form?.querySelectorAll("input, select, button").forEach((control) => {
    control.disabled = disabled;
  });
}

function clearMessages() {
  const error = document.querySelector("[data-error]");
  const status = document.querySelector("[data-status]");
  if (error) {
    error.hidden = true;
    error.textContent = "";
  }
  if (status) {
    status.hidden = true;
    status.textContent = "";
  }
}

function showPageError(message) {
  clearMessages();
  showError(message);
}

function showPageStatus(message) {
  const node = document.querySelector("[data-status]");
  if (node) {
    node.textContent = message;
    node.hidden = false;
  }
}

function roleLabel(role) {
  return ({ member: "Member", moderator: "Moderator", admin: "Administrator" })[role] || role;
}

function statusLabel(status) {
  return status ? `${status.charAt(0).toUpperCase()}${status.slice(1)}` : "Unknown";
}

function formatDate(value) {
  if (!value) {
    return "never";
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
