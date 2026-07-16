# Vertical Slice: Multi-Provider Authentication and Account Linking (V1)

## Purpose

This slice makes the TWE User the canonical account while allowing multiple authentication methods to point at that same User.

```text
TWE User
has
Authentication Methods / External Identities
    - Local credentials
    - Google identity
    - Discord identity
```

Google-created users and Discord-created users are not separate account types. Google and Discord are providers linked to one TWE User.

## Implemented Model

Migration:

```text
backend/genesis/migrations/0007_external_identities_oauth.sql
```

New tables:

- `user_external_identities`
- `oauth_states`

`user_external_identities` is provider-neutral and stores the immutable provider subject for `google` and `discord`.

`discord_identities` remains as Discord integration metadata used by Trog authorization. Discord OAuth login/linking writes the same immutable Discord user ID into `user_external_identities(provider='discord')` and syncs `discord_identities` for existing Trog authorization.

Local credentials remain on `users.password_hash`. OAuth-created users may have no local password.

## Identity Rules

- TWE User is canonical.
- Provider `provider_subject` is the immutable identity key.
- Google email is not the identity key.
- Discord email is not the identity key.
- Discord user ID is the immutable Discord identity.
- Matching provider email never silently merges accounts.
- Duplicate accounts are not automatically merged in this slice.
- A provider identity linked to another TWE User is a conflict.
- A User cannot unlink their final usable authentication method.

## OAuth State and Security

OAuth begins by creating a one-time `oauth_states` row.

State is bound to:

- provider;
- purpose: `login` or `link`;
- current TWE User for link flows;
- safe post-authentication redirect path;
- PKCE verifier;
- Google nonce when used;
- expiration time.

The callback consumes state atomically. Reuse, invalid state, expired state, provider mismatch, and session-user mismatch fail safely.

Redirect paths must be same-origin relative paths. Open redirects are rejected to safe defaults.

OAuth access tokens, refresh tokens, provider authorization codes, and client secrets are not stored in source control or browser JavaScript.

## Google Login Flow

1. User clicks **Continue with Google**.
2. TWE creates OAuth state, PKCE, and nonce.
3. TWE redirects to Google.
4. Google redirects back with `code` and `state`.
5. TWE consumes and validates state.
6. TWE exchanges the code server-side.
7. TWE resolves the immutable Google subject.
8. If linked, TWE signs in the linked User.
9. If unlinked, TWE creates a new TWE User and links the Google identity.

If Google returns an email that already belongs to a local account, TWE does not auto-link that account. The User must sign into the existing account and explicitly connect Google.

## Discord Login Flow

1. User clicks **Continue with Discord**.
2. TWE creates OAuth state and PKCE.
3. TWE redirects to Discord.
4. Discord redirects back with `code` and `state`.
5. TWE consumes and validates state.
6. TWE exchanges the code server-side.
7. TWE resolves the immutable Discord user ID.
8. If linked, TWE signs in the linked User.
9. If unlinked, TWE creates a new TWE User, links the Discord identity, and syncs `discord_identities`.
10. TWE stores a one-hour snapshot of servers where Discord reports owner, Administrator, or Manage Guild authority. Provider access tokens are discarded after the exchange.

Discord login does not grant Community Membership, provider approval, Trog installation access, Instance Access Grants, Server Operation capabilities, or ownership.

## Account Linking Flow

Signed-in Users can open:

```text
/account/
```

The page shows:

- Local password
- Google
- Discord

Connecting Google or Discord starts a link-purpose OAuth flow. The callback must still belong to the same signed-in User that started linking.

If the provider identity is already linked to the same User, linking is idempotent. If it is linked to another User, TWE returns a conflict and does not move or merge the identity.

## Trog Onboarding Behavior

The Discord/Trog request page checks connected accounts. If Discord is not linked, it presents **Connect Discord** before the request form.

After Discord linking, the user returns to:

```text
/discord/request-access/
```

The linked Discord identity is then available to existing Trog authorization workflows through `discord_identities`.
The request page uses the short-lived managed-server snapshot as a dropdown. **Refresh Discord servers** repeats the idempotent account-link flow to update that list without disconnecting the identity.

## Mattertrala Flow

1. Chad sends Mattertrala a Cohorts invitation link.
2. Mattertrala opens it.
3. Mattertrala chooses **Continue with Google**.
4. TWE creates one canonical TWE User and links Google.
5. The pending invite path is preserved.
6. Mattertrala accepts and becomes a basic Cohorts member.
7. Mattertrala opens the Cohorts -> Genesis -> LizzLive Trog request.
8. TWE detects Discord is not connected.
9. Mattertrala clicks **Connect Discord**.
10. Discord OAuth links the verified Discord user ID to the existing Google-created TWE User.
11. Mattertrala returns to the Trog request.
12. TWE uses the linked Discord identity for guild-authority verification.
13. No duplicate TWE account is created.

## Endpoints

```text
GET    /api/v1/auth/google/start
GET    /api/v1/auth/google/callback
GET    /api/v1/auth/discord/start
GET    /api/v1/auth/discord/callback
GET    /api/v1/account/identities
POST   /api/v1/account/identities/google/connect
POST   /api/v1/account/identities/discord/connect
DELETE /api/v1/account/identities/{provider}
```

The legacy prototype `POST /api/v1/discord/identity/link` endpoint has been removed. Discord identity links can only be created by the provider OAuth callback; the browser cannot submit an arbitrary Discord user ID.

## Environment Variables

```text
TWE_GOOGLE_CLIENT_ID
TWE_GOOGLE_CLIENT_SECRET
TWE_GOOGLE_REDIRECT_URI
TROG_DISCORD_CLIENT_ID
TROG_DISCORD_CLIENT_SECRET
TROG_DISCORD_REDIRECT_URI
```

Client secrets must remain server-side.

Google ID tokens are verified with `google-auth` against Google's published signing keys. Verification includes the signature, issuer, audience, expiration, and the OAuth nonce. Provider controls remain disabled in Account Settings until the corresponding client ID, client secret, and account callback URI are configured.

## Manual Provider Setup

Google Developer Console:

1. Create or select an OAuth client for the TWE web app.
2. Add the exact Google redirect URI used by `TWE_GOOGLE_REDIRECT_URI`.
3. Enable OpenID Connect scopes: `openid email profile`.
4. Store client ID and secret only in server environment configuration.

Discord Developer Portal:

1. Select the Trog/TWE application.
2. Add the exact redirect URI used by `TROG_DISCORD_REDIRECT_URI`.
3. Add the separate exact guild-install redirect URI used by `TROG_DISCORD_INSTALL_REDIRECT_URI`.
4. Confirm OAuth scopes needed for account linking (`identify email guilds`) and guild installation (`identify guilds bot applications.commands`).
5. Store client ID, client secret, and bot token only in server environment configuration.

## Testing

Automated tests use mocked provider responses and do not contact Google or Discord.

Run:

```text
backend/genesis/.venv/bin/python backend/genesis/scripts/migrate.py
backend/genesis/.venv/bin/python -m pytest backend/genesis/tests/test_multi_provider_auth_integration.py
backend/genesis/.venv/bin/python -m pytest backend/genesis/tests
```

## Rollback Implications

Migration `0007` is forward-only. Rolling back manually requires dropping `oauth_states` and `user_external_identities` after confirming no active OAuth/linking workflows depend on them. Existing local users, sessions, communities, invitations, and Discord integration tables are preserved by the forward migration.

## Not Implemented

- automatic account merge;
- verified account-recovery merge workflow;
- storing provider refresh tokens;
- live OAuth verification against Google or Discord.
