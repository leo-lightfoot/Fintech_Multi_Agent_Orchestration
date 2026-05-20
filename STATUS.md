# Project Status

## What is built

A fintech multi-agent orchestrator for a solutions / ops team.

Stack: LangGraph + FastAPI + Redis + Anthropic Claude + SQLite placeholder DB

## Architecture

```
POST /api/task
    |
    v
Supervisor (intent classification + agent routing)
    |
    v
Specialist agents run in sequence:
  data       -- sql_query / excel_query / document_search tools
  portfolio  -- structured P&L and position analysis
  risk       -- limit breach detection and compliance flags
  report     -- markdown report composition
    |
    v
Validator (single pass -- approve / retry / fail)
    |
    v
Responder (final markdown formatting)
    |
    v
GET /api/task/{id}
```

## Source files

```
src/
  agents/
    supervisor.py      intent routing (8 categories, structured output)
    data.py            tool-calling agent (sql, excel, documents)
    portfolio.py       portfolio analysis (structured output)
    risk.py            risk and compliance (structured output)
    reports.py         markdown report composer
    validator.py       output validation (structured output)
    responder.py       final response formatter
  audit/
    trail.py           append-only compliance log (Redis, 90-day TTL)
  gateway/
    api.py             FastAPI with lifespan, rate limiting, RBAC
    auth.py            JWT + role-based access (4 roles)
    middleware.py      slowapi rate limiter
    sanitizer.py       3-tier input sanitization
  memory/
    redis_store.py     task state + session history + audit log
  orchestrator/
    graph.py           LangGraph 6-node supervisor graph
    state.py           OrchestratorState TypedDict
    coordinator.py     task submission and lifecycle
  tools/
    sql.py             SELECT-only SQL tool + SQLite placeholder DB
    excel.py           xlsx/csv reader (path-safe, size-capped)
    documents.py       ChromaDB semantic search
    registry.py        lazy tool registry
  utils/
    config.py          pydantic-settings (provider-agnostic)
    llm.py             get_llm() factory (anthropic/openai/azure)
    cost.py            CostCallback + pricing table
    logging.py         structlog JSON logging
```

## Placeholder data

All data is fake and local -- no real credentials or databases required.

- SQLite in-memory: 3 funds, 9 positions, 5 trades, 7 NAV records, 5 limit rules (2 breached)
- ChromaDB: fund mandate + risk policy documents (6 chunks)
- Excel: data/sample_portfolio.xlsx with 3 sheets

## Tests

37 tests covering:
- Input sanitization (natural language vs SQL param vs query)
- State serialization round-trip
- SQL tool (valid query, injection blocked, breach detection)
- Redis deserialization (Pydantic model reconstruction)
- Supervisor routing logic
- RiskAgent helpers and model validation
- Validator output summarization
- Audit trail model
- Excel tool (read, sheet filter, path traversal blocked)
- Cost tracking (pricing table, unknown model fallback)

Run: pytest tests/ -v

## Phase completion

- Phase 1 (skeleton): complete
- Phase 2 (specialist agents + tools): complete
- Phase 3 (hardening): complete

## What is NOT production-ready

- SQLite placeholder -- swap get_db() in src/tools/sql.py for a real connection
- ChromaDB is local single-node -- use a hosted vector DB for multi-replica
- Auth is optional (no login enforcement) -- add SSO before exposing externally
- CORS is localhost-only -- update allow_origins in api.py for your domain
- No Prometheus metrics (config stub exists but no client wired)
