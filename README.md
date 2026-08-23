#Payment Orchestration Platform

A backend service that routes payments across two independent payment gateways, guaranteeing correctness — no duplicate charges, no lost payments — even when a gateway fails, times out, or a webhook is delivered twice or not at all.

Built to demonstrate the kind of failure-handling and correctness thinking real payment infrastructure requires, rather than just "call an API and show a result."



## What This Solves

Payment gateways fail, time out, and occasionally deliver the same "success" webhook twice. A naive integration either double-charges customers, silently drops failed payments, or has no way to recover when a webhook never arrives. This project builds the reliability layer that a real payments system needs around those failure modes:

- The same request sent twice **never** results in two charges.
- A failing gateway is retried with backoff, then automatically failed over to a second gateway.
- A payment that fails repeatedly is flagged for manual review instead of retrying forever or disappearing silently.
- A lost webhook doesn't mean a lost payment — a scheduled reconciliation job catches and self-heals the discrepancy.

## Architecture


                     ┌─────────────┐
   client  ────────► │   FastAPI   │ ── writes ──►  ┌────────────┐
                     │   (web)     │                │ PostgreSQL │
                     └──────┬──────┘ ── reads  ────►│            │
                            │                        └────────────┘
                      enqueues job                          ▲
                            │                                │
                            ▼                                │
                     ┌─────────────┐                         │
                     │    Redis    │                         │
                     │ (queue +    │                         │
                     │  idempotency)│                        │
                     └──────┬──────┘                         │
                            │                                │
              ┌─────────────┴─────────────┐                  │
              ▼                           ▼                  │
       ┌─────────────┐            ┌──────────────┐          │
       │  RQ Worker   │            │ RQ Scheduler │           │
       │ (retries,    │───────────►│ (reconciles  │───────────┘
       │  failover,   │  writes    │  every 60s)  │
       │  webhooks)   │            └──────────────┘
       └──────────────┘


`web`, `worker`, and `scheduler` are three independent processes built from the same codebase — they can be scaled or restarted independently of each other, the same way real payment infrastructure separates request-handling capacity from background-processing capacity.

## Core Features

| Feature | What it does |
|---|---|
| **Idempotency keys** | An atomic, unique-constraint-based check-then-insert guarantees the same request never creates two payments — no explicit locking required. |
| **Exponential backoff retries** | Failed gateway calls are retried with increasing delay (`base * 2^attempt` + jitter) instead of hammering an already-struggling gateway. |
| **Automatic failover** | If Gateway A exhausts its retry budget, the payment automatically routes to Gateway B — decided through a shared interface, not gateway-specific branching. |
| **Dead-letter queue** | A payment that fails 3 full rounds through both gateways stops retrying and is flagged `dead_letter` for manual review, instead of retrying forever. |
| **Webhook handling** | Inbound gateway callbacks are deduplicated (gateways deliver at-least-once) and verified via HMAC-SHA256 signature before being trusted. |
| **Scheduled reconciliation** | A background job runs every 60 seconds, compares each payment's recorded state against its gateway history, and self-heals any mismatch — the safety net for when a webhook never arrives. |
| **Full audit trail** | Every status transition is permanently logged (append-only, never overwritten) alongside a note explaining *why* it changed. |
| **Admin dashboard** | A live-updating view of every payment, its full gateway/audit history, and a manual "replay" action for failed or dead-lettered payments. |

## Tech Stack

- **API:** FastAPI (async, Pydantic validation, auto-generated OpenAPI docs)
- **Database:** PostgreSQL, via SQLAlchemy + Alembic migrations
- **Queue / Cache:** Redis, used both for idempotency checks and as the RQ message broker
- **Background processing:** RQ (Redis Queue) + rq-scheduler for periodic jobs
- **Admin UI:** Server-rendered HTML (Jinja2) with a small amount of vanilla JS for live polling — no separate frontend build
- **Infra:** Docker + Docker Compose (four services: `web`, `worker`, `scheduler`, plus `db` and `redis`)

## Database Schema

| Table | Purpose |
|---|---|
| `payments` | The current state of each payment — status, amount, which gateway was used, retry count |
| `gateway_attempts` | Every individual attempt made against a gateway, with its outcome (a payment can have many) |
| `audit_log` | Append-only history of every status transition a payment goes through, with a human-readable note |
| `idempotency_keys` | Tracks which request keys have already been claimed, enforcing the no-duplicate-charge guarantee |
| `processed_webhooks` | Tracks which inbound webhook event IDs have already been handled, since gateways deliver at-least-once |

## Getting Started (Local)

**Requirements:** Docker Desktop, Git.


git clone https://github.com/<your-username>/Payment-Orchestra.git
cd Payment-Orchestra
cp .env.example .env   # fill in your own local values
docker-compose up --build


Run the first migration once your containers are up:


docker-compose exec web alembic upgrade head


Then visit:
- `http://localhost:8000/` — health check
- `http://localhost:8000/docs` — interactive API docs (Swagger)
- `http://localhost:8000/admin` — live admin dashboard

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/payments` | Create a payment. Requires an `idempotency_key`; safe to retry with the same key. |
| `POST` | `/webhooks/gateway-callback` | Receives gateway status callbacks. Requires a valid `x-signature` header. |
| `GET` | `/admin` | The admin dashboard. |
| `GET` | `/admin/api/payments` | JSON list of all payments with summary stats (used by the dashboard's live refresh). |
| `GET` | `/admin/api/payments/{id}` | Full gateway-attempt and audit-log history for one payment. |
| `POST` | `/admin/payments/{id}/replay` | Resets a `failed`/`dead_letter` payment's retry budget and requeues it. |

## Verifying the Guarantees


# Same idempotency key fired twice → exactly one payment created
curl -X POST localhost:8000/payments -H "Content-Type: application/json" \
  -d '{"idempotency_key":"abc123","amount":500,"currency":"INR"}'
curl -X POST localhost:8000/payments -H "Content-Type: application/json" \
  -d '{"idempotency_key":"abc123","amount":500,"currency":"INR"}'
# → both responses identical, same "id"


Check `gateway_attempts` for a given payment to see its full retry/failover history, and `audit_log` for its complete state-transition history.

## Project Structure


Payment-Orchestra/
├── app/
│   ├── main.py            # FastAPI app, /payments and /webhooks routes
│   ├── admin.py            # Admin dashboard routes
│   ├── models.py           # SQLAlchemy models (the 5 tables above)
│   ├── database.py         # DB engine/session setup
│   ├── tasks.py             # Background job: retries, failover, dead-lettering
│   ├── retry.py             # Exponential backoff logic
│   ├── reconciliation.py   # Scheduled self-healing job
│   ├── security.py          # HMAC webhook signature verification
│   ├── queue_config.py     # Redis/RQ connection setup
│   ├── gateways/            # Gateway interface + two mock implementations
│   └── templates/           # Admin dashboard HTML
├── migrations/               # Alembic migration history
├── scripts/                  # One-off developer utilities (not deployed)
├── docker-compose.yml
├── Dockerfile
└── requirements.txt

##Deliberately out of scope
- Kafka/RabbitMQ, replaced by Redis + RQ (same concept, far less operational overhead for this scale)
- Prometheus/Grafana/OpenTelemetry, replaced by structured logs
- Fraud detection — unrelated to the reliability story this project demonstrates
- Circuit breaker, rate limiting — valid stretch goals, not required to prove the core failure-handling story
