# Deployment Guide

## Docker Compose (recommended for local + staging)

```bash
# Set required env vars
export LLM_API_KEY=your-key-here
export API_SECRET_KEY=change-this-in-production

# Start all services (Redis + orchestrator)
docker-compose up -d

# View logs
docker-compose logs -f orchestrator

# Stop
docker-compose down
```

The `docker-compose.yml` at the repo root defines both services.
Persistent Redis data is stored in the `redis-data` Docker volume.

## Environment variables

Copy `.env.example` to `.env` and fill in:

```
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_MODEL=claude-sonnet-4-6
API_SECRET_KEY=<strong-random-string>
REDIS_URL=redis://redis:6379/0
```

All other settings have safe defaults. See `.env.example` for the full list.

## Manual / VM deployment

```bash
# Install system deps
sudo apt-get install redis-server python3.11 python3.11-venv

# App setup
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Ingest documents once
python scripts/ingest_docs.py

# Run with gunicorn + uvicorn workers
pip install gunicorn
gunicorn src.gateway.api:app \
  --workers 2 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120
```

## Data persistence

| What | Where | Notes |
|---|---|---|
| Task state | Redis (`task:{id}`) | 24-hour TTL |
| Session history | Redis (`session:{id}:history`) | 7-day TTL |
| Audit log | Redis (`audit:{session_id}`) | 90-day TTL |
| Vector store | `data/chroma/` | Local ChromaDB, persist this directory |
| Sample data | `data/` | Excel + text docs committed to repo |

## Scaling notes

- The API is stateless -- run multiple replicas behind a load balancer
- All shared state lives in Redis -- point every replica at the same instance
- ChromaDB in this setup is local (single-node) -- for multi-replica deployments, use a hosted vector DB or shared volume
- LLM calls are the bottleneck -- budget accordingly

## Health check

```bash
curl http://localhost:8000/health
# {"status":"healthy","version":"1.0.0","redis_connected":true,...}
```

## Graceful shutdown

The API handles SIGTERM gracefully:
1. Stops accepting new requests
2. Waits up to 30 seconds for in-flight tasks to complete
3. Cancels any remaining tasks and closes Redis connection

Send SIGTERM (or `docker-compose stop`) -- do not use SIGKILL unless the process is hung.
