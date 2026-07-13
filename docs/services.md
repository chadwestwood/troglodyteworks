# Troglodyte Works Services

Services are capabilities that Members may enable within their Communities.

A Service does not necessarily imply hosting or a paid subscription.

Services should provide value independently while working together as a complete platform.

---

# Community Services

Help communities organize and communicate.

Examples:

- Community Management
- Member Roles
- Community Invitations
- Announcements
- Events
- Polls
- Scheduling
- Notifications

---

# Server Services

Help Members manage game servers regardless of where they are hosted.

Examples:

- Server Monitoring
- Server Settings
- Restart Scheduling
- Mod Management
- Backup Management
- Log Viewing
- Performance Monitoring

Supported providers may include:

- Troglodyte Works Hosting
- Self-hosted Servers
- Nitrado
- Future Providers

---

# Hosting Services

Troglodyte Works may host servers directly.

Examples:

- ARK Survival Ascended
- ARK Survival Evolved
- Minecraft
- Palworld

Additional games should be added without changing the overall architecture.

---

# Automation Services

Automate repetitive work.

Examples:

- Scheduled Restarts
- Automatic Backups
- Event Scheduling
- Discord Notifications
- Poll-triggered Actions
- Workflow Automation

---

# Integration Services

Connect Communities with external platforms.

Examples:

- Discord
- Steam
- Google
- Microsoft
- Future Integrations

The platform should feel connected rather than isolated.

## Community Invitations

Community Invitations let authorized Community leaders bring people into a TWE Community without manual database work.

Supported V1 paths:

- direct invitation to an existing TWE user;
- shareable invitation link for someone who may need to create an account first;
- optional leader approval after redemption.

Invitation acceptance creates only Community Membership. It does not grant instance access, Discord installation approval, Server Operations, restart, save, mods, or ownership. Rate limiting is not yet implemented and remains an operational follow-up.

## Discord Integration

The Discord Integration provides a database-backed Trog bot foundation.

Trog may answer direct mentions for:

- server status
- player count
- player names

The bot must use deterministic intent matching.

The bot must not require AI to answer these first questions.

Guild installation, immutable Discord identity, identity linking, instance access grants, capability allowlists, and channel policy are persisted in PostgreSQL. Public reads remain available without identity linking only after a provider-approved active grant exists for the exact instance. Administrative capabilities require server-side TWE membership and capability authorization. Restart authorization is implemented, but execution remains disabled and no destructive action is called.

The Mattertrala-to-LizzLive onboarding path lets a linked Discord administrator request access to a Cohorts-owned Genesis instance, prove Discord guild authority, wait for Cohorts provider approval, confirm installation, and activate read-only Trog responses in selected channels. LizzLive consumes approved capabilities; it does not own Genesis.

See:

```text
docs/discord-integration.md
```

---

# Guidance Services

Help Members accomplish goals confidently.

Examples:

- Contextual Guidance
- Configuration Explanations
- Troubleshooting
- Recommendations
- Journey Assistance

Guidance should always remain optional.

---

# AI Services

Use MCP-powered tools to safely assist Members.

Examples:

- Diagnose Problems
- Recommend Solutions
- Execute Approved Actions
- Explain Configuration
- Coordinate Automations

AI should reason.

Tools should act.

---

# Design Principle

Every Service should answer one question:

"Does this help a Community accomplish something meaningful?"

If not, it probably doesn't belong in Troglodyte Works.
