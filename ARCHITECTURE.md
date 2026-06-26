# InfraPulse AI — Architecture

## System Overview

```
                           ┌─────────────────────────────────────────────────┐
                           │                   Nginx                          │
                           │  :80/:443  ─── reverse proxy + rate limiting    │
                           └────────┬──────────────────┬───────────────────┘
                                    │                  │
                         ┌──────────▼──────┐   ┌──────▼──────────────┐
                         │   FastAPI       │   │   Static Files      │
                         │   Backend :8000 │   │   (HTML/CSS/JS)     │
                         └──────┬──────────┘   └─────────────────────┘
                                │
              ┌─────────────────┼──────────────────┐
              │                 │                  │
     ┌────────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐
     │  PostgreSQL   │  │    Redis     │  │  Celery      │
     │  (primary DB) │  │  (broker +   │  │  Workers     │
     └───────────────┘  │   cache)     │  │  + Beat      │
                        └──────────────┘  └──────────────┘

Linux Servers ──(agent)──► POST /api/v1/agent/metrics
Proxmox VE   ──────────────────── Celery Beat polls every 60s
```

## Component Breakdown

### Nginx
- Reverse proxy to FastAPI backend
- Serves static frontend files
- Rate limiting per IP (API: 100 req/min, auth: 10 req/min)
- Security headers (CSP, HSTS, X-Frame-Options)
- WebSocket-ready (`Upgrade` headers forwarded)

### FastAPI Backend
- **Auth:** JWT access tokens (15 min) + refresh tokens (7 days), bcrypt password hashing
- **Multi-tenancy:** every request authenticated; all DB queries scoped by `organization_id`
- **Async:** SQLAlchemy 2.0 async engine with asyncpg driver
- **Background tasks:** Celery workers for heavy operations (AI analysis, notification dispatch)

### Database Schema

```
organizations ──┬── organization_memberships ── users
                │                               └── refresh_tokens
                │                                   password_reset_tokens
                ├── servers ─── server_agents
                │               agent_registration_tokens
                ├── proxmox_connections ─── proxmox_nodes
                │                           proxmox_vms
                ├── metrics (time-series)
                ├── log_entries (FTS via GIN index on message)
                │   saved_searches
                ├── alert_rules ─── alerts ─── incident_alerts
                │                              └── incidents
                ├── ai_analyses
                └── notification_channels ─── notification_policies
                    audit_logs
                    api_keys
                    invitations
```

### Celery Workers

**Queues:**
- `default` — general tasks
- `proxmox` — Proxmox polling and sync
- `alerts` — alert rule evaluation
- `notifications` — notification dispatch

**Beat Schedule:**
| Task | Interval |
|---|---|
| `poll_all_proxmox_connections` | 60s |
| `evaluate_all_alert_rules` | 30s |
| `check_agent_heartbeats` | 60s |
| `cleanup_old_metrics` | 1 hour |

### Linux Agent

```
infrapulse_agent.py
├── SystemInfo         hostname, IPs, OS, CPU info
├── MetricsCollector   psutil: CPU, memory, disk, network, load
├── LogCollector       tail log files, detect level, batch push
└── APIClient          HTTP client, X-Agent-Token auth
```

Agent uses `X-Agent-Token` header (SHA-256 hashed token stored in DB). No user JWT required after registration.

### AI Service

```
AIOrchestrator
├── analyze_alert(alert_id)     → fetch alert + recent metrics + logs → prompt → store analysis
├── analyze_server(server_id)   → fetch server stats + alerts + logs → prompt → store analysis
└── analyze_incident(id)        → fetch incident + linked alerts → prompt → store analysis

Providers:
├── GroqProvider    (llama-3.1-70b-versatile, fast)
├── OpenAIProvider  (gpt-4o-mini, balanced)
└── OllamaProvider  (self-hosted, private)
```

AI provider is **per-organization**. API keys encrypted at rest with Fernet symmetric encryption.

### Secrets Encryption

Sensitive values stored encrypted in DB:
- Proxmox `api_token_secret` and `password`
- Notification webhook URLs and integration keys
- AI provider API keys

Encryption uses `ENCRYPTION_KEY` env var (Fernet). If not set, derived from `SECRET_KEY` via PBKDF2.

## Data Flow

### Metric Ingestion (Agent → DB)

```
Agent collects metrics (psutil)
  └─► POST /api/v1/agent/metrics  {metrics: [...]}
       └─► Validate X-Agent-Token (SHA-256 lookup)
            └─► Bulk INSERT into metrics table
                 └─► Update server.last_seen_at, health_score
```

### Alert Evaluation (Celery Beat)

```
Celery Beat (every 30s)
  └─► evaluate_all_alert_rules()
       └─► For each enabled alert rule:
            └─► Query recent metrics (within duration_minutes window)
                 └─► Check threshold condition
                      ├─► Condition met → create/update Alert (firing)
                      │    └─► Dispatch notification via policy
                      └─► Condition cleared → resolve existing Alert
```

### AI Analysis Flow

```
User triggers analysis (UI or API)
  └─► POST /api/v1/organizations/{id}/ai/analyze-alert/{alert_id}
       └─► AIOrchestrator.analyze_alert()
            ├─► Fetch alert + related metrics + recent logs
            ├─► Build prompt (redact sensitive data)
            ├─► Call AI provider (Groq/OpenAI/Ollama)
            ├─► Parse response → summary + recommendations
            └─► Store AIAnalysis record
```

## Security Considerations

- All secrets encrypted at rest (Fernet)
- Bcrypt password hashing (work factor 12)
- JWT refresh tokens stored as hash in DB — invalidated on logout
- Organization-scoped queries enforced at route level (not just business logic)
- Agent tokens are one-way hashed (SHA-256) — raw token never stored
- Nginx rate limiting prevents brute force on auth endpoints
- CSP, HSTS, X-Frame-Options, X-Content-Type-Options headers set by Nginx
- `ProtectSystem=strict` in systemd agent service unit

## Scalability Notes

- PostgreSQL partitioning recommended for `metrics` table at >100M rows (partition by month on `timestamp`)
- Celery workers scale horizontally — run multiple replicas with `--concurrency` flag
- Redis Cluster supported via `REDIS_URL` for HA
- All backend state in PostgreSQL + Redis — backend containers are stateless
- For Kubernetes: use PostgreSQL Operator (Zalando/CNPG) + Redis Sentinel/Cluster
