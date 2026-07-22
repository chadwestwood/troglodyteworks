# ADR-0001: Railway Is the Production Runtime

**Status:** Accepted  
**Date:** 2026-07-21

## Decision

GitHub is the deployment source. Railway runs the TWE web service, Trog worker, and PostgreSQL database. Cloudflare routes `troglodyteworks.com` to Railway. The former DC001/in-house server and household router are removed from the production path.

## Consequences

- Production changes flow through repository commits and Railway deployments.
- The web and Discord worker are separate services with different health behavior.
- Local development remains useful but has no production authority.
- Apache, NGINX, HestiaCP, remote VS Code, and `10.0.0.103` are not current production dependencies.

