# Fintech Multi-Agent Orchestrator — Rebuild Checklist

Transforming the existing multi-agent system into a simplified, production-grade orchestrator
for a fintech/asset management solutions (ops) team.

Architecture: Supervisor → Specialist Agents → Validator → Responder
Stack: LangGraph + FastAPI + Redis + Provider-agnostic LLM

> **Rule**: Always write new files BEFORE deleting old ones. All deletions are in Phase 3.

---

## Phase 1 — Skeleton (get something running end-to-end)

### 1.1 State & Orchestrator

- [ ] Simplify `src/orchestrator/state.py` — remove `ExecutionPlan`, `PlanStep`, `AgentType` models; add `intent: str`, `agents_selected: list[str]`, `agent_results: dict` to `OrchestratorState`; simplify `ValidationResult` (remove `critic_level` field — only one validator now); update `Phase` and `TaskStatus` enums to match 6-node graph
- [ ] Rewrite `src/orchestrator/graph.py` — 6-node LangGraph graph: `receive → supervise → execute → validate → respond → done`; replace all 8 current agent imports with the new supervisor + specialist agents
- [ ] Add conditional retry edge from `validate` back to `execute` (max 1 retry); update default in `settings` from 3 → 1
- [ ] Update `src/orchestrator/coordinator.py` — remove references to `execution_plan`, `expert_insights`, `step_results`; use new `agent_results` field

### 1.2 Config — Update Before Anything Else

> Do this first. Several other items depend on it. Skipping will cause startup failures.

- [ ] Update `src/utils/config.py` — make `openai_api_key` Optional (currently required — will break startup if only Claude/Azure key is set); add `llm_provider: str = "openai"`, `llm_api_key: str`; add `db_host`, `db_port: int`, `db_name`, `db_user`, `db_password` fields; add `docs_path: str`, `vector_store_url: str`; remove `enable_code_execution`, `docker_enabled`, `code_execution_timeout` (no longer needed)
- [ ] Update `.env.example` — replace `OPENAI_API_KEY` with `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`; add `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`; add `DOCS_PATH`, `VECTOR_STORE_URL`; remove `CODE_EXECUTION_TIMEOUT`, `ENABLE_CODE_EXECUTION`, `DOCKER_ENABLED`; keep `OPENAI_API_KEY` as a commented alias for backwards compat
- [ ] Update `docker-compose.yml` — change `OPENAI_API_KEY` env var to `LLM_PROVIDER` + `LLM_API_KEY`; add DB service if running locally; add vector store service (ChromaDB or pgvector) when chosen

### 1.3 LLM Factory (provider abstraction)

- [ ] Create `src/utils/llm.py` — `get_llm(provider, model, **kwargs)` factory returning a LangChain `BaseChatModel`
- [ ] Support `anthropic`, `openai`, `azure_openai` as provider values driven by `LLM_PROVIDER` env var
- [ ] Update all existing agents that accept `llm: ChatOpenAI` — change type hint to `BaseChatModel`; remove `from langchain_openai import ChatOpenAI` imports; affected files: `graph.py`, `critics.py`, `pre_planner.py`, `plan_refiner.py`, `executor.py`, `summarizer.py`, `responder.py`, `domain_expert.py`

### 1.4 Fix InputSanitizer (breaking for fintech use)

> The current sanitizer blocks SQL keywords like SELECT, CREATE, ALTER, EXECUTE.
> An ops user asking "select the top 10 funds by AUM" will get a 400 error. Fix before any other work.

- [ ] Update `src/gateway/sanitizer.py` — remove SQL keyword check from the main task/natural-language input path; SQL injection checks should only apply to raw query strings passed to `sql_tool`, not to user task descriptions
- [ ] Keep command injection and XSS checks on all input paths — those are still valid
- [ ] Add a separate `validate_sql_param(text: str)` method for use inside `sql_tool` only

### 1.5 Supervisor Agent

- [ ] Create `src/agents/supervisor.py`
- [ ] Use structured output (Pydantic model) — output `SupervisorDecision(agents: list[str], tools: list[str], reasoning: str)`
- [ ] Write system prompt covering the 4 use cases: portfolio Q&A, report generation, data queries, risk/compliance
- [ ] Map intent → agent sequence (e.g. "risk report" → `[data, risk, report]`)
- [ ] Add fallback for unrecognised intent — return clear error, do not hallucinate a plan

### 1.6 DataAgent + SQL Tool

- [ ] Create `src/agents/data.py` — DataAgent that orchestrates tool calls
- [ ] Create `src/tools/` directory and `src/tools/registry.py` — central tool registration; agents declare which tools they use
- [ ] Create `src/tools/sql.py` — `sql_tool`: parameterized queries only (no raw string interpolation), returns typed results; use `validate_sql_param()` from sanitizer on all inputs
- [ ] Write 2 tests: valid query returns structured data, SQL injection attempt is blocked

### 1.7 Audit Trail

- [ ] Create `src/audit/trail.py` — `AuditTrail` class with `log(entry: AuditEntry)` method
- [ ] Define `AuditEntry` Pydantic model: `timestamp, user_id, session_id, task_id, action, data_accessed, agent, role, cost_usd, result_summary`
- [ ] Store entries in Redis as append-only sorted set (score = timestamp)
- [ ] Add `GET /api/audit/{session_id}` endpoint — returns audit log for a session
- [ ] Ensure every agent call writes an audit entry (wrap in orchestrator, not in each agent)

### 1.8 Gateway — Rate Limiting (actually implement it)

- [ ] Add `slowapi` to `requirements.txt`
- [ ] Create `src/gateway/middleware.py` — rate limit: 100 req/min per user, 10 concurrent tasks per session
- [ ] Wire middleware into `src/gateway/api.py`
- [ ] Restrict CORS in `api.py` — change `allow_origins=["*"]` to the internal domain(s) of your ops tooling
- [ ] Remove documented-but-missing rate limit comments from `API_DOCS.md` and replace with real docs

### 1.9 Redis Store — Fix Deserialization

> File is `src/memory/redis_store.py` — not `store.py`

- [ ] Fix `src/memory/redis_store.py` `_deserialize_state()` — reconstruct Pydantic models properly, not plain dicts; the current implementation just returns `json.loads(state_json)` which loses all type safety
- [ ] Add `save_audit_entry()` and `get_audit_log()` methods to `RedisStore`
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

- [ ] Create `src/agents/validator.py` (single file replaces entire critics system)
- [ ] Use structured output: `ValidationResult(approved: bool, issues: list[str], severity: "ok|warn|reject")`
- [ ] Checks: completeness (all requested sections present), no hallucinated figures, no PII in output
- [ ] On `reject` → trigger one retry with issues fed back as context

### 2.5 Document Tool (RAG)

- [ ] Create `src/tools/documents.py` — `document_tool`: semantic search over PDF/doc store
- [ ] Decide and record vector store choice: ChromaDB (local, zero-infra) or pgvector (if Postgres already in stack)
- [ ] Create `scripts/` directory and `scripts/ingest_docs.py` — reads PDFs, chunks, embeds, stores
- [ ] Add `DOCS_PATH`, `VECTOR_STORE_URL` to config (already covered in 1.2)
- [ ] Write 1 test: search returns relevant chunk for a known query

### 2.6 Excel Tool

- [ ] Create `src/tools/excel.py` — `excel_tool`: reads `.xlsx`/`.csv`, returns typed DataFrame summary
- [ ] Detect and handle common ops file formats (multi-header, merged cells, date columns)
- [ ] Sanitize file path — prevent directory traversal; use `pathlib` with an allowed base path
- [ ] Cap file size at 50MB, row count at 100k
- [ ] Write 1 test: reads a sample file, returns correct schema

### 2.7 RBAC

- [ ] Define roles: `ops_read`, `ops_write`, `risk_read`, `admin`
- [ ] Add `role` field to `TokenData` in `src/gateway/auth.py` (reuse existing JWT skeleton — just add the field)
- [ ] Add role check decorator `@require_role(...)` for FastAPI routes
- [ ] DataAgent: restrict which DB tables each role can query
- [ ] AuditTrail: `role` is already in `AuditEntry` model (covered in 1.7) — confirm it's being populated

---

## Phase 3 — Hardening

### 3.1 Structured Output Everywhere

- [ ] Audit every agent — confirm all LLM calls use `.with_structured_output()` or a Pydantic output parser
- [ ] Confirm zero line-by-line text parsing in the codebase (the old `APPROVED:` / `ISSUES:` header scanning in `critics.py` is gone after deletion)
- [ ] Add fallback: if structured parse fails, log and return a safe error — never silently corrupt state

### 3.2 Real Cost Tracking

- [ ] Hook into LangChain callback `on_llm_end` to capture actual `prompt_tokens` + `completion_tokens` from response metadata
- [ ] Add pricing table in `src/utils/llm.py` per model (update when models change)
- [ ] Replace hardcoded `$0.01 / 1000 tokens` estimates (currently in `src/agents/execution/executor.py:154-156`)
- [ ] Surface `cost_usd` per task in API response and audit log

### 3.3 Graceful Shutdown

- [ ] Add `lifespan` context manager to FastAPI app in `src/gateway/api.py`
- [ ] On SIGTERM: stop accepting new tasks, wait for in-flight tasks to complete (timeout: 30s)
- [ ] On timeout: checkpoint in-flight task state to Redis with `status: interrupted`
- [ ] Add `GET /api/task/{task_id}/resume` endpoint stub for interrupted tasks

### 3.4 Test Coverage

- [ ] Supervisor routing: 1 test per use case (portfolio, risk, report, data query)
- [ ] DataAgent + sql_tool: valid query, empty result, injection blocked
- [ ] RiskAgent: breach detected, no breach, missing data handled
- [ ] Validator: approves clean output, rejects incomplete output, retry path works
- [ ] Audit trail: entries written, retrieved correctly, append-only (no deletes)
- [ ] Redis round-trip: state serialization/deserialization for all Pydantic models
- [ ] End-to-end: submit task → poll status → get result (happy path per use case)

### 3.5 Cleanup — Delete Old Code

> Only do this after all new files in Phase 1 & 2 are written and tested.

- [ ] Delete `src/agents/execution/code_executor.py` — the subprocess security hole
- [ ] Delete `src/agents/execution/data_writer.py` — replaced by `sql_tool` and `excel_tool`
- [ ] Delete `src/agents/execution/executor.py` — replaced by specialist agents
- [ ] Delete `src/agents/planning/` directory (contains `pre_planner.py` and `plan_refiner.py`)
- [ ] Delete `src/agents/experts/domain_expert.py`
- [ ] Delete `src/agents/summarizers/` directory
- [ ] Delete `src/agents/validation/critics.py` — replaced by `src/agents/validator.py`
- [ ] Delete `src/memory/recovery.py` — checkpoint/recovery logic tied to old DAG state; not needed in new design
- [ ] Remove `e2b-code-interpreter` from `requirements.txt` (listed but was never imported)
- [ ] Remove `networkx` from `requirements.txt` (only used by `pre_planner.py` and `executor.py`, both deleted)
- [ ] Remove `docker` from `requirements.txt` (only needed for code execution sandbox, now deleted)
- [ ] Replace `langchain-openai` with `langchain-anthropic` in `requirements.txt` (Claude is now the default provider)
- [ ] Add `chromadb` to `requirements.txt` (vector store for document_tool)
- [ ] Add `sqlalchemy` + `aiosqlite` to `requirements.txt` (SQLite placeholder for sql_tool)
- [ ] Add `openpyxl` to `requirements.txt` (Excel file reading)
- [ ] Add `slowapi` to `requirements.txt` (rate limiting — if not already added in 1.8)
- [ ] Add `pypdf` or `pdfplumber` to `requirements.txt` (PDF ingestion for document_tool)
- [ ] Update `README.md`, `API_DOCS.md`, `QUICKSTART.md`, `DEPLOYMENT.md`, `STATUS.md` to reflect new design (note: there is no `ARCHITECTURE.md` — it does not exist in this repo)

---

## Decisions — Locked

> This is a **learning project**. All databases and external services are **placeholders/mocks**.
> No production data. No real credentials required beyond an LLM API key.

| Decision | Choice | Notes |
|---|---|---|
| **LLM provider** | Anthropic Claude | Default model: `claude-sonnet-4-6`. Use `langchain-anthropic`. Remove `langchain-openai` dependency. |
| **Vector store** | ChromaDB | Runs in-process, no extra service. Add `chromadb` to `requirements.txt`. |
| **Report format** | Markdown | Plain `.md` string returned in API response. No PDF/HTML deps needed. |
| **Auth** | Keep existing JWT | Extend `TokenData` in `auth.py` with a `role` field. No SSO needed. |
| **DB schema** | Placeholder/mock | `sql_tool` will use SQLite in-memory with seeded fake data (positions, trades, NAV, limits tables). No real DWH. |
| **CORS** | Localhost only | `allow_origins=["http://localhost:3000", "http://localhost:8080"]` — learning project, no prod domain. |

### What "placeholder" means for each tool

- **`sql_tool`** — connects to an in-memory SQLite DB seeded with fake fintech data (10 funds, 50 positions, 100 trades)
- **`document_tool`** — ingests 2–3 sample PDF stubs stored in `data/docs/`
- **`excel_tool`** — reads a sample `data/sample_portfolio.xlsx` file committed to the repo
- **LLM API key** — real key needed (Claude). Everything else is local/mocked.

---

## Corrections vs Original Checklist

The following errors were found and fixed in this version:

| # | Original (wrong) | Corrected |
|---|---|---|
| 1 | "Delete `src/orchestrator/` planning files" | Planning files are in `src/agents/planning/` — deletion moved to Phase 3 |
| 2 | Fix `src/memory/store.py` | Actual file is `src/memory/redis_store.py` |
| 3 | "Delete `quality_critic.py`, `security_critic.py`, `architecture_critic.py`" | All critics are in one file: `src/agents/validation/critics.py` |
| 4 | "Update `ARCHITECTURE.md`" | This file does not exist in the repo |
| 5 | *(missing)* | `config.py` must be updated first — `openai_api_key` is required and will break startup with Claude/Azure |
| 6 | *(missing)* | `InputSanitizer` blocks SQL keywords in natural language — breaks all ops queries |
| 7 | *(missing)* | `data_writer.py`, `executor.py`, `recovery.py` missing from deletion list |
| 8 | *(missing)* | `docker-compose.yml` needs env var updates for provider-agnostic LLM |

---

_Total tasks: ~75 | Estimated effort: 4–5 weeks for one developer_
