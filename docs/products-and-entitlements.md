# Products and Entitlements

Status: current product contract

Troglodyte Works offers five Trog plans. Plans determine which product capabilities a customer may use; they do not grant authority over a Community, Game Server, or Game Server Instance.

| Plan | Price | Primary capability |
| --- | ---: | --- |
| Free | $0 | Natural-language, read-only status, player, and configuration answers. |
| Control | $5 per managed server/month | Exact routine operations such as start, stop, restart, and update. |
| Assist | $8 per managed server/month | Context-aware requests, follow-up questions, and guided operations. |
| Admin | $10 per managed server/month | Configuration, mod, and delegated operator management. |
| Pro | $15 per managed server/month | Recommendations, plans, polls, events, and monitored follow-through. |

## Authority rule

A subscription unlocks product capabilities but never bypasses authorization. An operation is permitted only when both conditions are true:

1. the applicable subscription includes the requested capability; and
2. the Instance owner has granted that user, Discord identity, role, or installation permission to use it for that Instance.

An owner may expose the same Instance through more than one Discord server or channel. Each installation and channel mapping starts with read-only access. Higher permissions are delegated to specific people or roles and remain bounded by the Instance owner's maximum grant.

## Product pages

- `/products/` is the comparison and plan-selection page.
- `/products/free/`, `/products/control/`, `/products/assist/`, `/products/admin/`, and `/products/pro/` explain individual plans.
- Product calls to action use the existing sign-in and onboarding flows. Billing and self-service subscription activation are not represented as available until those systems are implemented.

## Naming

The plan names Free, Control, Assist, Admin, and Pro are customer-facing product names. Authorization roles and capability grants remain separate internal concepts and must not be inferred from a plan name.
