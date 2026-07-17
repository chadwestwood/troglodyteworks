# Troglodyte Works

Troglodyte Works is a web-based game server hosting platform that enables customers to manage dedicated game servers through an intuitive web interface without requiring Linux or SSH knowledge.

This project serves two purposes:

1. Develop a production-ready hosting platform for managing dedicated game servers.
2. Demonstrate modern software engineering and Quality Assurance practices using Agile methodologies.

---

## Current Status

🚧 Active Development

Current Phase:
- Product Planning
- Jira Backlog Development
- Git Integration

---

## Planned Features

- User Authentication
- Customer Dashboard
- Server Management
- Server Configuration
- Mod Management
- Discord Integration
- Backups & Restore
- Monitoring & Logs

---

## Technology Stack

Backend
- Python
- Flask
- PostgreSQL
- Linux

Frontend
- HTML
- CSS
- JavaScript

Development
- Git
- GitHub
- Jira

Future
- Playwright
- Postman

---

## Repository Layout

backend/        Backend services

site/           Frontend website

docs/           Technical documentation

Blueprint/      System architecture

Decisions/      Architecture decisions

Ideas/          Future enhancements

Meetings/       Sprint and planning notes

Research/       Technical research

---

## TWE Backend Development Setup

Genesis is an ARK game instance name in Cohorts in the Wild.

Genesis is not the platform/backend package name.

The first approved vertical slice uses PostgreSQL persistence and a Flask API under `/api/v1`.

### Environment

Copy the placeholder environment file and fill in local values outside source control:

```bash
cp backend/trog/.env.example backend/trog/.env
```

Required values:

- `TWE_DATABASE_URL`
- `TWE_INITIAL_USER_EMAIL`
- `TWE_INITIAL_USER_PASSWORD`
- `TWE_INITIAL_USER_DISPLAY_NAME`

Optional health-check values:

- `TWE_ASA_EXPECTED_PROCESS`
- `TWE_ASA_HEALTH_HOST`
- `TWE_ASA_HEALTH_PORT`

Do not commit real database passwords, user passwords, session secrets, or RCON credentials.

### Install Dependencies

```bash
backend/trog/.venv/bin/python -m pip install -r backend/trog/requirements.txt
```

### Migrations

```bash
TWE_DATABASE_URL='postgresql://twe_app:password@localhost:5432/twe' \
backend/trog/.venv/bin/python backend/trog/scripts/migrate.py
```

Migrations are version-controlled SQL files in `backend/trog/migrations/`.

### Seed Initial Data

```bash
TWE_DATABASE_URL='postgresql://twe_app:password@localhost:5432/twe' \
TWE_INITIAL_USER_EMAIL='chad@example.com' \
TWE_INITIAL_USER_PASSWORD='replace-with-real-password' \
TWE_INITIAL_USER_DISPLAY_NAME='Chad' \
backend/trog/.venv/bin/python backend/trog/scripts/seed_initial.py
```

The seed is designed to be safe to run more than once.

### Run the Application

```bash
TWE_DATABASE_URL='postgresql://twe_app:password@localhost:5432/twe' \
backend/trog/.venv/bin/python backend/trog/app.py
```

The application binds to `127.0.0.1:8787` by default.

For local review, Flask serves the static files in `site/` and the API routes from the same origin.

Production Apache/NGINX should serve `site/` as the public web root and proxy these API prefixes to the Flask application:

- `/api/v1`
- `/api/genesis` (legacy compatibility endpoint for the Cohorts Genesis instance pages)

Session cookies are HTTP-only and same-origin. If the browser is on the live domain, the live domain must serve the static site and proxy the API paths on that same domain for authentication to work.

### Run Tests

```bash
backend/trog/.venv/bin/python -m unittest discover backend/trog/tests
```

### Live Server Safety

The `local_asa` Management Adapter boundary is present. `instance.status` can create a Server Operation and run deterministic health checks. `instance.players.list`, `instance.save`, and `instance.restart` are intentionally unavailable in this pass.

Live restart execution remains disabled pending explicit human review and approval.

---

## Project Goals

This repository is being developed as both a functional hosting platform and a professional software engineering portfolio demonstrating Agile planning, QA processes, version control, and modern development practices.
