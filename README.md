# InfraPulse AI

A production-quality, multi-tenant SaaS platform for monitoring Proxmox servers, bare-metal Ubuntu servers, VMs, containers, logs, and infrastructure health — with AI-powered incident analysis.

## Features

- **Multi-tenant** — full org isolation, role-based access (owner/admin/operator/viewer)
- **Linux Agent** — lightweight Python agent collects CPU, memory, disk, network, and system logs
- **Proxmox Integration** — connects to Proxmox VE API to inventory nodes, VMs, and LXC containers
- **Real-time Metrics** — time-series metrics stored in PostgreSQL with Chart.js visualizations
- **Log Explorer** — full-text search on ingested logs with level/source filtering
- **Alert Engine** — configurable threshold-based rules evaluated by Celery workers
- **Incident Management** — create, track, and link alerts to incidents
- **AI Operations** — Groq / OpenAI / Ollama-powered analysis of alerts, servers, and incidents
- **Notifications** — Slack, email (SMTP), generic webhook, and PagerDuty channels
- **Dark Enterprise UI** — fully responsive single-page app (vanilla HTML/CSS/JS + Chart.js)

## Quick Start

### Prerequisites

- Docker and Docker Compose v2

### 1. Clone and configure

```bash
git clone <repo-url> infraPulseAI
cd infraPulseAI
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY and POSTGRES_PASSWORD
nano .env
```

### 2. Start the stack

```bash
docker compose up --build
```

This starts:
- **PostgreSQL** — primary database
- **Redis** — Celery broker + cache
- **Backend** — FastAPI on port 8000 (internal)
- **Celery Worker** — background task processing
- **Celery Beat** — scheduled polling (Proxmox, alert evaluation, heartbeat checks)
- **Nginx** — reverse proxy on port 80 (and 443 with TLS configured)

### 3. Open the UI

```
http://localhost/
```

Demo credentials (if `SEED_DEMO_DATA=true` in `.env`):
- **Email:** `owner@acme-corp.example.com`
- **Password:** `Demo123!`

## Installing the Monitoring Agent

On any Linux server you want to monitor:

```bash
# Generate a registration token from the web UI:
# Servers → + Add Server → Generate Token

curl -sSL http://YOUR_INFRAPULSE_URL/agent/install.sh | \
  bash -s -- \
  --server-url http://YOUR_INFRAPULSE_URL \
  --token YOUR_REGISTRATION_TOKEN \
  --environment production
```

The agent installs as a systemd service and starts automatically.

**Manual installation:**

```bash
pip install psutil
python3 agent/infrapulse_agent.py \
  --server-url http://YOUR_URL \
  --token YOUR_TOKEN \
  --environment production
```

**Check system metrics only (no API call):**

```bash
python3 agent/infrapulse_agent.py --check
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | JWT signing key (required, min 32 chars) |
| `DATABASE_URL` | postgresql+asyncpg://... | Async PostgreSQL DSN |
| `SYNC_DATABASE_URL` | postgresql+psycopg2://... | Sync DSN for Alembic |
| `REDIS_URL` | redis://redis:6379/0 | Redis connection string |
| `SEED_DEMO_DATA` | false | Seed demo org and data on startup |
| `GROQ_API_KEY` | — | Default Groq API key (optional) |
| `OPENAI_API_KEY` | — | Default OpenAI API key (optional) |
| `SMTP_HOST` | — | SMTP server for email notifications |
| `SMTP_USER` | — | SMTP username |
| `SMTP_PASS` | — | SMTP password |
| `SMTP_FROM` | noreply@infrapulse.ai | From address for emails |
| `ENCRYPTION_KEY` | — | Fernet key for secrets at rest (auto-derived if not set) |
| `CORS_ORIGINS` | http://localhost | Comma-separated allowed origins |

## API

All endpoints are under `/api/v1/`. Authentication uses JWT Bearer tokens.

```
POST /api/v1/auth/register       Register new user + org
POST /api/v1/auth/login          Login
POST /api/v1/auth/refresh        Refresh access token
POST /api/v1/auth/logout         Logout

GET  /api/v1/organizations/{id}  Get org details
GET  /api/v1/organizations/{id}/servers      List servers
GET  /api/v1/organizations/{id}/metrics/...  Metrics queries
GET  /api/v1/organizations/{id}/logs         Log search
GET  /api/v1/organizations/{id}/alerts       Alert list
GET  /api/v1/organizations/{id}/incidents    Incident list
GET  /api/v1/organizations/{id}/proxmox/...  Proxmox management
POST /api/v1/organizations/{id}/ai/...       AI analysis

# Agent endpoints (X-Agent-Token header)
POST /api/v1/agent/register
POST /api/v1/agent/heartbeat
POST /api/v1/agent/metrics
POST /api/v1/agent/logs
```

Full interactive docs: `http://localhost/api/docs`

## Development

### Backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Running tests

```bash
cd backend
pip install pytest pytest-asyncio httpx aiosqlite
pytest ../tests/ -v
```

### Frontend

The frontend is pure HTML/CSS/JS — no build step required. Serve via Nginx (already configured) or any static file server.

## Project Structure

```
infraPulseAI/
├── docker-compose.yml
├── .env.example
├── nginx/
│   ├── nginx.conf
│   └── Dockerfile
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/versions/001_initial_schema.py
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── models/          # SQLAlchemy ORM models
│       ├── schemas/         # Pydantic request/response schemas
│       ├── api/v1/          # FastAPI route handlers
│       ├── services/        # Business logic (AI, Proxmox, notifications)
│       ├── workers/         # Celery tasks
│       └── scripts/         # seed_data.py
├── frontend/
│   ├── index.html           # Auth redirect
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── infrastructure.html
│   ├── servers.html
│   ├── server-detail.html
│   ├── proxmox.html
│   ├── logs.html
│   ├── alerts.html
│   ├── incidents.html
│   ├── ai-ops.html
│   ├── notifications.html
│   ├── team.html
│   ├── settings.html
│   └── assets/
│       ├── css/main.css
│       └── js/
│           ├── api-client.js
│           └── components.js
├── agent/
│   ├── infrapulse_agent.py  # Linux monitoring agent
│   ├── install.sh           # One-command installer
│   └── infrapulse-agent.service
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_servers.py
    ├── test_alerts.py
    ├── test_proxmox.py
    └── test_organizations.py
```

## AI Providers

Configure via **AI Operations → ⚙️ AI Config** in the UI, or via `POST /api/v1/organizations/{id}/ai/config`.

| Provider | Speed | Cost | Notes |
|---|---|---|---|
| **Groq** | Very fast | Free tier available | Recommended for most use cases |
| **OpenAI** | Fast | Pay per token | GPT-4o-mini is cost-effective |
| **Ollama** | Local | Free | Requires self-hosted Ollama instance |

## License

MIT
