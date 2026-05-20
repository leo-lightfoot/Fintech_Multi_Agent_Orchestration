# Fintech Multi-Agent Orchestrator

A supervisor-pattern multi-agent system built for a fintech solutions / ops team.
Agents collaborate to answer portfolio questions, query data, flag risk breaches,
and generate reports.

Stack: LangGraph + FastAPI + Redis + Anthropic Claude

---

## How it works

```
POST /api/task
    |
    v
Supervisor          classifies intent, selects agents
    |
    v
Specialist agents   run in sequence
  data              fetches from SQL, Excel, or document store
  portfolio         P&L, attribution, position analysis
  risk              limit breaches, exposure flags
  report            formats results into markdown
    |
    v
Validator           single-pass quality check, one retry allowed
    |
    v
Responder           final markdown response
    |
    v
GET /api/task/{id}  poll for result
```

---

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # set LLM_API_KEY
python scripts/ingest_docs.py # load sample documents
redis-server
python -m uvicorn src.gateway.api:app --reload
```

See [QUICKSTART.md](QUICKSTART.md) for Docker setup and troubleshooting.
See [API_DOCS.md](API_DOCS.md) for the full endpoint reference.
See [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment.

---

## License

MIT
