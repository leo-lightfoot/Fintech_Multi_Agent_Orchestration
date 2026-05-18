# Fintech Multi-Agent Orchestrator — Rebuild Checklist

Transforming the existing multi-agent system into a simplified, production-grade orchestrator
for a fintech/asset management solutions (ops) team.

Architecture: Supervisor → Specialist Agents → Validator → Responder
Stack: LangGraph + FastAPI + Redis + Provider-agnostic LLM

---

## Phase 1 — Skeleton (get something running end-to-end)

### 1.1 State & Orchestrator

- [ ] Simplify `OrchestratorState` TypedDict — remove DAG/planning fields, add `intent`, `agents_selected`, `audit_entries`
- [ ] Rewrite `src/orchestrator/graph.py` — 6-node LangGraph graph: `receive → supervise → execute → validate → respond → done`
- [ ] Add conditional retry edge from `validate` back to `execute` (max 1 retry, not 3)
- [ ] Delete `src/orchestrator/` planning-related files (pre_planner, plan_refiner, dag logic)

### 1.2 LLM Factory (provider abstraction)

- [ ] Create `src/utils/llm.py` — `get_llm(provider, model, **kwargs)` factory returning a LangChain `BaseChatModel`
- [ ] Support `anthropic`, `openai`, `azure_openai` as provider options driven by env vars
- [ ] Add `PROVIDER`, `MODEL`, `API_KEY` to `.env.example`
- [ ] Ensure all agents import from `llm.py` — no hardcoded `ChatOpenAI` anywhere

### 1.3 Supervisor Agent

- [ ] Create `src/agents/supervisor.py`
- [ ] Use structured output (Pydantic model) — output `SupervisorDecision(agents: list[str], tools: list[str], reasoning: str)`
- [ ] Write system prompt covering the 4 use cases: portfolio Q&A, report generation, data queries, risk/compliance
- [ ] Map intent → agent sequence (e.g. "risk report" → `[data, risk, report]`)
- [ ] Add fallback for unrecognised intent — return clear error, do not hallucinate a plan

### 1.4 DataAgent + SQL Tool

- [ ] Create `src/agents/data.py` — DataAgent that orchestrates tool calls
- [ ] Create `src/tools/registry.py` — central tool registration, agents declare which tools they use
- [ ] Create `src/tools/sql.py` — `sql_tool`: parameterized queries only (no raw string interpolation), returns typed results
- [ ] Add connection config: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` to `.env.example`
- [ ] Validate SQL output before returning — check for empty results, schema errors
- [ ] Write 2 tests: valid query returns structured data, SQL injection attempt is blocked

### 1.5 Audit Trail

- [ ] Create `src/audit/trail.py` — `AuditTrail` class with `log(entry: AuditEntry)` method
- [ ] Define `AuditEntry` Pydantic model: `timestamp, user_id, session_id, task_id, action, data_accessed, agent, cost_usd, result_summary`
- [ ] Store entries in Redis as append-only sorted set (score = timestamp)
- [ ] Add `GET /api/audit/{session_id}` endpoint — returns audit log for a session
- [ ] Ensure every agent call writes an audit entry (wrap in orchestrator, not in each agent)

### 1.6 Gateway — Rate Limiting (actually implement it)

- [ ] Add `slowapi` or `fastapi-limiter` to `requirements.txt`
- [ ] Create `src/gateway/middleware.py` — rate limit: 100 req/min per user, 10 concurrent tasks per session
- [ ] Wire middleware into `src/gateway/api.py`
- [ ] Remove documented-but-missing rate limit comments from `API_DOCS.md` and replace with real docs

### 1.7 Redis Store — Fix Deserialization

- [ ] Fix `src/memory/store.py` `_deserialize_state()` — reconstruct Pydantic models properly, not plain dicts
- [ ] Add `save_audit_entry()` and `get_audit_log()` methods
- [ ] Remove checkpoint/recovery code for the old DAG state (no longer needed)
- [ ] Write 1 test: serialize → deserialize round-trip preserves all model types

---

## Phase 2 — Specialist Agents & Tools

### 2.1 PortfolioAgent

- [ ] Create `src/agents/portfolio.py`
- [ ] System prompt: portfolio analysis, P&L attribution, position-level breakdown
- [ ] Tools: `sql_tool` (positions, trades, NAV tables)
- [ ] Use structured output: `PortfolioResult(summary, positions, attribution, warnings)`
- [ ] Handle empty portfolio gracefully — return clear message, not a hallucination

### 2.2 RiskAgent

- [ ] Create `src/agents/risk.py`
- [ ] System prompt: exposure analysis, limit breach detection, compliance flag generation
- [ ] Tools: `sql_tool` (limits, exposures, benchmark tables)
- [ ] Use structured output: `RiskResult(flags: list[RiskFlag], breaches: list[LimitBreach], summary)`
- [ ] Define `RiskFlag` and `LimitBreach` Pydantic models
- [ ] Never suppress a breach — validator must confirm all flags are surfaced

### 2.3 ReportAgent

- [ ] Create `src/agents/reports.py`
- [ ] System prompt: turn structured data into clear, professional prose for ops users
- [ ] Input: structured output from other agents (not raw data)
- [ ] Templating: support `performance`, `risk`, `mandate_summary` report types
- [ ] Output plain text + optional markdown table — no raw JSON to end user

### 2.4 Validator — Single Pass

- [ ] Rewrite `src/agents/validation/` as single `src/agents/validator.py`
- [ ] Use structured output: `ValidationResult(approved: bool, issues: list[str], severity: "ok|warn|reject")`
- [ ] Checks: completeness (all requested sections present), no hallucinated figures, no PII in output
- [ ] On `reject` → trigger one retry with issues fed back as context
- [ ] Delete old 3-critic system (`quality_critic.py`, `security_critic.py`, `architecture_critic.py`)

### 2.5 Document Tool (RAG)

- [ ] Create `src/tools/documents.py` — `document_tool`: semantic search over PDF/doc store
- [ ] Choose vector store: ChromaDB (local, simple) or pgvector (if Postgres already in stack)
- [ ] Add document ingestion script: `scripts/ingest_docs.py` — reads PDFs, chunks, embeds, stores
- [ ] Add `DOCS_PATH`, `VECTOR_STORE_URL` to `.env.example`
- [ ] Write 1 test: search returns relevant chunk for a known query

### 2.6 Excel Tool

- [ ] Create `src/tools/excel.py` — `excel_tool`: reads `.xlsx`/`.csv`, returns typed DataFrame summary
- [ ] Detect and handle common ops file formats (multi-header, merged cells, date columns)
- [ ] Sanitize file path — prevent directory traversal
- [ ] Cap file size at 50MB, row count at 100k
- [ ] Write 1 test: reads a sample file, returns correct schema

### 2.7 RBAC

- [ ] Define roles: `ops_read`, `ops_write`, `risk_read`, `admin`
- [ ] Add `role` field to JWT payload (reuse existing auth skeleton)
- [ ] Add role check decorator `@require_role(...)` for FastAPI routes
- [ ] DataAgent: restrict which DB tables each role can query
- [ ] AuditTrail: log role alongside user_id on every entry

---

## Phase 3 — Hardening

### 3.1 Structured Output Everywhere

- [ ] Audit every agent — confirm all LLM calls use Pydantic output parser or `.with_structured_output()`
- [ ] Delete all line-by-line text parsing (the brittle `APPROVED:` / `ISSUES:` header scanning)
- [ ] Add fallback: if structured parse fails, log and return a safe error — never silently corrupt state

### 3.2 Real Cost Tracking

- [ ] Hook into LangChain callback `on_llm_end` to capture actual `prompt_tokens` + `completion_tokens`
- [ ] Add pricing table in `src/utils/llm.py` per model (update when models change)
- [ ] Replace hardcoded `$0.01 / 1000 tokens` estimates in old executor
- [ ] Surface `cost_usd` per task in API response and audit log

### 3.3 Graceful Shutdown

- [ ] Add `lifespan` context manager to FastAPI app
- [ ] On SIGTERM: stop accepting new tasks, wait for in-flight tasks to complete (timeout: 30s)
- [ ] On timeout: checkpoint in-flight task state to Redis with `status: interrupted`
- [ ] Add `GET /api/task/{task_id}/resume` endpoint stub for interrupted tasks

### 3.4 Test Coverage

- [ ] Supervisor routing: write 1 test per use case (portfolio, risk, report, data query)
- [ ] DataAgent + sql_tool: valid query, empty result, injection blocked
- [ ] RiskAgent: breach detected, no breach, missing data handled
- [ ] Validator: approves clean output, rejects incomplete output, retry path works
- [ ] Audit trail: entries written, retrieved correctly, append-only (no deletes)
- [ ] Redis round-trip: state serialization/deserialization for all Pydantic models
- [ ] End-to-end: submit task → poll status → get result (happy path per use case)

### 3.5 Cleanup

- [ ] Delete `src/agents/execution/code_executor.py` (the subprocess security hole)
- [ ] Delete `src/agents/planning/` directory entirely
- [ ] Delete `src/agents/experts/domain_expert.py`
- [ ] Delete `src/agents/summarizers/` (folded into Responder)
- [ ] Remove `e2b-code-interpreter` from `requirements.txt` (listed but never used)
- [ ] Remove `networkx` from `requirements.txt` (DAG execution removed)
- [ ] Update `README.md`, `API_DOCS.md`, `ARCHITECTURE.md` to reflect new design
- [ ] Update `docker-compose.yml` — add vector store service if using ChromaDB/pgvector

---

## Decisions to Make Before Starting

- [ ] **Vector store**: ChromaDB (zero-infra, local) vs pgvector (if Postgres already exists)
- [ ] **Report output format**: markdown tables, JSON, or PDF generation (reportlab/weasyprint)?
- [ ] **Auth**: keep existing JWT skeleton or replace with your org's SSO/OAuth?
- [ ] **DB schema**: confirm table names for positions, trades, NAV, limits — needed before writing sql_tool
- [ ] **LLM default**: which provider + model to default in `.env.example`?

---

_Total tasks: ~65 | Estimated effort: 4–5 weeks for one developer_
