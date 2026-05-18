# Fintech Multi-Agent Orchestrator

A learning project -- a supervisor-pattern multi-agent system built for a fintech
solutions / ops team. Agents collaborate to answer portfolio questions, run data
queries, flag risk breaches, and generate reports.

Stack: LangGraph + FastAPI + Redis + Anthropic Claude + SQLite (placeholder DB)

---

## How it works

```
POST /api/task
    |
    v
Supervisor Agent     -- classifies intent, picks specialist agents
    |
    v
Specialist Agents    -- run in sequence, each receives previous output
  data               -- SQL queries against the placeholder DB
  portfolio          -- P&L, attribution, position analysis  (Phase 2)
  risk               -- limit breaches, exposure flags        (Phase 2)
  report             -- formats results into markdown         (Phase 2)
    |
    v
Validator            -- single-pass check, one retry allowed  (Phase 2)
    |
    v
Responder            -- formats final markdown response
    |
    v
GET /api/task/{id}   -- poll for result
```

---

## Project structure

```
src/
  agents/
    supervisor.py      intent classification and routing
    data.py            SQL tool-calling agent
    responder.py       final response formatter
    validator.py       (Phase 2)
    portfolio.py       (Phase 2)
    risk.py            (Phase 2)
    reports.py         (Phase 2)
  audit/
    trail.py           (Phase 2)
  gateway/
    api.py             FastAPI routes
    auth.py            JWT auth
    sanitizer.py       input sanitization
  memory/
    redis_store.py     task state + session history
  orchestrator/
    graph.py           LangGraph 6-node supervisor graph
    state.py           OrchestratorState TypedDict
    coordinator.py     task submission and tracking
  tools/
    sql.py             sql_query tool + SQLite placeholder DB
    registry.py        tool registry
  utils/
    config.py          settings (pydantic-settings)
    llm.py             provider-agnostic LLM factory
    logging.py         structlog setup
tests/
  test_orchestrator.py
```

---

## Quick start

Requirements: Python 3.11+, Redis

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and edit env file
cp .env.example .env
# Set LLM_API_KEY to your Anthropic key

# Start Redis
redis-server

# Run the API
python -m uvicorn src.gateway.api:app --reload
```

---

## API

```bash
# Submit a task
curl -X POST http://localhost:8000/api/task \
  -H "Content-Type: application/json" \
  -d '{"task": "What are the current NAV values for all funds?"}'

# Poll for result
curl http://localhost:8000/api/task/{task_id}

# Session history
curl http://localhost:8000/api/session/{session_id}

# Health check
curl http://localhost:8000/health
```

---

## Configuration

All settings are in `.env.example`. Key variables:

| Variable | Default | Description |
|---|---|---|
| LLM_PROVIDER | anthropic | anthropic, openai, or azure_openai |
| LLM_API_KEY | (required) | your API key |
| LLM_MODEL | claude-sonnet-4-6 | model name |
| REDIS_URL | redis://localhost:6379/0 | Redis connection |
| MAX_RETRY_ATTEMPTS | 1 | validation retry limit |
| BUDGET_LIMIT_USD | 10.0 | max cost per task |

---

## Placeholder database

The SQL tool runs against an in-memory SQLite database seeded with fake data:

- 3 funds (Alpha Growth, Beta Income, Gamma Balanced)
- 9 positions across those funds
- 5 trades
- 7 NAV history records
- 5 limit rules (2 currently breached)

Swap `get_db()` in `src/tools/sql.py` for a real connection when ready.

---

## Running tests

```bash
pytest tests/ -v
```

---

## License

MIT
