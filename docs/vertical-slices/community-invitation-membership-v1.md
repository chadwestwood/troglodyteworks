# Vertical Slice: Community Invitation and Membership Entry (V1)

## Purpose

This slice lets a Community leader invite people into a TWE Community without manual database work.

Concrete target:

```text
Community: Cohorts in the Wild
Community leader: Chad
Invitee: Mattertrala
Result: Mattertrala becomes a basic Cohorts member
```

The invitation establishes only Community Membership. It does not grant Genesis access, Trog installation approval, restart, save, mods, configuration, ownership, or platform administration.

## Included Flows

Direct invitation:

1. A Community owner, admin, or moderator identifies an existing TWE user by exact safe identifier.
2. TWE creates a pending direct Community Invitation.
3. The invited TWE user accepts or declines.
4. Acceptance creates a Community Membership with the approved initial role.

Shareable link:

1. A Community owner, admin, or moderator creates an Invite Link.
2. TWE returns the plaintext token once.
3. Chad sends the link to Mattertrala.
4. Mattertrala opens `/invite/{token}/`.
5. If unauthenticated, the invite token is preserved through sign-in or account creation.
6. Mattertrala accepts or declines.
7. Acceptance creates basic Community Membership unless leader approval is required.

Approval-required flow:

1. Redemption creates a pending membership request.
2. An authorized Community leader approves or denies it.
3. Approval creates the membership.

## Domain Model

```text
Community
has
Community Invitations
redeemed by
TWE Users
creating
Community Memberships
```

Terms:

- Community Invitation
- Invitation Token
- Invited TWE User
- Invite Link
- Community Membership
- Membership Request
- Inviting User
- Initial Community Role

This slice is separate from Discord guild installation and Instance Access Grants.

## Authorization

Community owners, admins, and moderators may manage invitations.

Role safety:

- owner may invite `admin`, `moderator`, or `member`;
- admin may invite `moderator` or `member`;
- moderator may invite `member`;
- no one may invite another user into an equal or higher role through this slice;
- `owner` is never assignable through invitations.

The current server-operation capability grant model is intentionally not reused for Community invitation management because it is scoped to Game Server and Game Instance operations. A future Community capability-grant model may replace this role check.

## Schema

Migration:

```text
backend/genesis/migrations/0006_community_invitations.sql
```

Tables:

- `community_invitations`
- `community_invitation_redemptions`

Important rules:

- share-link tokens are cryptographically random;
- only token hashes are stored;
- plaintext tokens are returned only at creation;
- duplicate pending direct invitations are prevented;
- existing membership duplication is prevented by `community_memberships`;
- maximum-use limits are enforced atomically during redemption;
- revoked, expired, accepted, and declined invitations cannot be reused.

## API

Implemented endpoints:

```text
POST /api/v1/communities/{community_id}/invitations
GET  /api/v1/communities/{community_id}/invitations
POST /api/v1/communities/{community_id}/invitations/{invitation_id}/revoke
GET  /api/v1/community-invitations/{token}
POST /api/v1/community-invitations/{token}/accept
POST /api/v1/community-invitations/{token}/decline
POST /api/v1/community-invitations/direct/{invitation_id}/accept
POST /api/v1/community-invitations/direct/{invitation_id}/decline
POST /api/v1/communities/{community_id}/invitation-redemptions/{redemption_id}/approve
POST /api/v1/communities/{community_id}/invitation-redemptions/{redemption_id}/deny
```

The token hash is never returned.

## UI

Leader page:

```text
/communities/cohorts-in-the-wild/invitations/
```

Invite landing page:

```text
/invite/{token}/
```

The landing page preserves `twe.pending_invite_token` through sign-in and account creation.

## Mattertrala Path

1. Chad signs in.
2. Chad opens the Cohorts invitations page.
3. Chad creates a one-use or limited-use link with initial role `member`.
4. Chad sends the link to Mattertrala.
5. Mattertrala opens the link.
6. Mattertrala creates or signs into a TWE account.
7. Mattertrala accepts.
8. Mattertrala becomes a basic Cohorts member.
9. Mattertrala can then start the separate Cohorts -> Genesis -> LizzLive Trog access request.

Mattertrala still cannot approve his own provider-side Instance Access Grant unless he separately has the required Cohorts authorization.

## Follow-Ups

- Add rate limiting for invitation creation and redemption.
- Add formal Community-scoped capability grants if the platform needs non-role invitation permissions.
- Replace exact-email direct lookup with verified username or privacy-preserving search if account identity expands.
- Add a polished Members page after this slice.

