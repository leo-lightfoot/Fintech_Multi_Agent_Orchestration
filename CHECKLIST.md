# Fintech Multi-Agent Orchestrator -- Rebuild Checklist

Transforming the existing multi-agent system into a simplified, production-grade orchestrator
for a fintech/asset management solutions (ops) team.

Architecture: Supervisor -> Specialist Agents -> Validator -> Responder
Stack: LangGraph + FastAPI + Redis + Provider-agnostic LLM

> **Rule**: Always write new files BEFORE deleting old ones. All deletions are in Phase 3.

---

## Phase 1 -- Skeleton [COMPLETE]

### 1.1 State & Orchestrator

- [x] Simplify `src/orchestrator/state.py`
- [x] Rewrite `src/orchestrator/graph.py` -- 6-node supervisor graph
- [x] Add retry node (read-only edge function + dedicated _retry_node)
- [x] Update `src/orchestrator/coordinator.py`

### 1.2 Config

- [x] Update `src/utils/config.py`
- [x] Update `.env.example`
- [x] Update `docker-compose.yml`

### 1.3 LLM Factory

- [x] Create `src/utils/llm.py` -- `get_llm()` factory (anthropic / openai / azure_openai)

### 1.4 Fix InputSanitizer

- [x] `check_for_injections()` -- natural language, no SQL keywords blocked
- [x] `validate_sql_query()` -- query structure (UNION, semicolons, DDL)
- [x] `validate_sql_param()` -- raw parameter values

### 1.5 Supervisor Agent

- [x] `src/agents/supervisor.py` -- structured output, 8 intent categories, sanitize fallback

### 1.6 DataAgent + SQL Tool

- [x] `src/agents/data.py` -- tool-calling loop (up to 5 iterations)
- [x] `src/tools/sql.py` -- SQLite placeholder DB, seeded with 5 fintech tables
- [x] `src/tools/registry.py` -- central tool registry
- [x] 4 tests passing (valid query, non-SELECT blocked, injection blocked, breached limits)

### 1.7 Audit Trail

- [x] `src/audit/trail.py` -- `AuditEntry` model + `AuditTrail` class
- [x] Redis: `save_audit_entry()` / `get_audit_log()` (append-only, 90-day TTL)
- [x] `GET /api/audit/{session_id}` endpoint
- [x] Graph writes one entry per agent after every execution (success / stub / error)

### 1.8 Rate Limiting

- [x] `src/gateway/middleware.py` -- slowapi limiter (20/min task, 100/min reads, 10/min auth)
- [x] All routes decorated with `@limiter.limit()`
- [x] CORS restricted to localhost
- [x] `API_DOCS.md` rewritten with real rate limit table

### 1.9 Redis Deserialization

- [x] `_deserialize_state()` reconstructs `CostTracking` and `ValidationResult` as Pydantic models
- [x] `save_audit_entry()` / `get_audit_log()` added
- [x] 4 round-trip tests: CostTracking, ValidationResult, None, primitive fields

---

## Phase 2 -- Specialist Agents & Tools

### 2.1 PortfolioAgent

- [ ] Create `src/agents/portfolio.py`
- [ ] System prompt: portfolio analysis, P&L attribution, position-level breakdown
- [ ] Tools: `sql_tool` (positions, trades, NAV tables)
- [ ] Use structured output: `PortfolioResult(summary, positions, attribution, warnings)`
- [ ] Handle empty portfolio gracefully -- return clear message, not a hallucination

### 2.2 RiskAgent

- [ ] Create `src/agents/risk.py`
- [ ] System prompt: exposure analysis, limit breach detection, compliance flag generation
- [ ] Tools: `sql_tool` (limits, exposures, benchmark tables)
- [ ] Use structured output: `RiskResult(flags: list[RiskFlag], breaches: list[LimitBreach], summary)`
- [ ] Define `RiskFlag` and `LimitBreach` Pydantic models
- [ ] Never suppress a breach -- validator must confirm all flags are surfaced

### 2.3 ReportAgent

- [ ] Create `src/agents/reports.py`
- [ ] System prompt: turn structured data into clear, professional prose for ops users
- [ ] Input: structured output from other agents (not raw data)
- [ ] Templating: support `performance`, `risk`, `mandate_summary` report types
- [ ] Output plain text + optional markdown table -- no raw JSON to end user

### 2.4 Validator -- Single Pass

- [ ] Create `src/agents/validator.py` (single file replaces entire critics system)
- [ ] Use structured output: `ValidationResult(approved: bool, issues: list[str], severity: "ok|warn|reject")`
- [ ] Checks: completeness (all requested sections present), no hallucinated figures, no PII in output
- [ ] On `reject` -> trigger one retry with issues fed back as context

### 2.5 Document Tool (RAG)

- [ ] Create `src/tools/documents.py` -- `document_tool`: semantic search over PDF/doc store
- [ ] Decide and record vector store choice: ChromaDB (local, zero-infra) or pgvector (if Postgres already in stack)
- [ ] Create `scripts/` directory and `scripts/ingest_docs.py` -- reads PDFs, chunks, embeds, stores
- [ ] Add `DOCS_PATH`, `VECTOR_STORE_URL` to config (already covered in 1.2)
- [ ] Write 1 test: search returns relevant chunk for a known query

### 2.6 Excel Tool

- [ ] Create `src/tools/excel.py` -- `excel_tool`: reads `.xlsx`/`.csv`, returns typed DataFrame summary
- [ ] Detect and handle common ops file formats (multi-header, merged cells, date columns)
- [ ] Sanitize file path -- prevent directory traversal; use `pathlib` with an allowed base path
- [ ] Cap file size at 50MB, row count at 100k
- [ ] Write 1 test: reads a sample file, returns correct schema

### 2.7 RBAC

- [ ] Define roles: `ops_read`, `ops_write`, `risk_read`, `admin`
- [ ] Add `role` field to `TokenData` in `src/gateway/auth.py` (reuse existing JWT skeleton -- just add the field)
- [ ] Add role check decorator `@require_role(...)` for FastAPI routes
- [ ] DataAgent: restrict which DB tables each role can query
- [ ] AuditTrail: `role` is already in `AuditEntry` model (covered in 1.7) -- confirm it's being populated

---

## Phase 3 -- Hardening

### 3.1 Structured Output Everywhere

- [ ] Audit every agent -- confirm all LLM calls use `.with_structured_output()` or a Pydantic output parser
- [ ] Confirm zero line-by-line text parsing in the codebase (the old `APPROVED:` / `ISSUES:` header scanning in `critics.py` is gone after deletion)
- [ ] Add fallback: if structured parse fails, log and return a safe error -- never silently corrupt state

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
- [ ] End-to-end: submit task -> poll status -> get result (happy path per use case)

### 3.5 Cleanup -- Delete Old Code

> Only do this after all new files in Phase 1 & 2 are written and tested.

- [ ] Delete `src/agents/execution/code_executor.py` -- the subprocess security hole
- [ ] Delete `src/agents/execution/data_writer.py` -- replaced by `sql_tool` and `excel_tool`
- [ ] Delete `src/agents/execution/executor.py` -- replaced by specialist agents
- [ ] Delete `src/agents/planning/` directory (contains `pre_planner.py` and `plan_refiner.py`)
- [ ] Delete `src/agents/experts/domain_expert.py`
- [ ] Delete `src/agents/summarizers/` directory
- [ ] Delete `src/agents/validation/critics.py` -- replaced by `src/agents/validator.py`
- [ ] Delete `src/memory/recovery.py` -- checkpoint/recovery logic tied to old DAG state; not needed in new design
- [ ] Remove `e2b-code-interpreter` from `requirements.txt` (listed but was never imported)
- [ ] Remove `networkx` from `requirements.txt` (only used by `pre_planner.py` and `executor.py`, both deleted)
- [ ] Remove `docker` from `requirements.txt` (only needed for code execution sandbox, now deleted)
- [ ] Replace `langchain-openai` with `langchain-anthropic` in `requirements.txt` (Claude is now the default provider)
- [ ] Add `chromadb` to `requirements.txt` (vector store for document_tool)
- [ ] Add `sqlalchemy` + `aiosqlite` to `requirements.txt` (SQLite placeholder for sql_tool)
- [ ] Add `openpyxl` to `requirements.txt` (Excel file reading)
- [ ] Add `slowapi` to `requirements.txt` (rate limiting -- if not already added in 1.8)
- [ ] Add `pypdf` or `pdfplumber` to `requirements.txt` (PDF ingestion for document_tool)
- [ ] Update `README.md`, `API_DOCS.md`, `QUICKSTART.md`, `DEPLOYMENT.md`, `STATUS.md` to reflect new design (note: there is no `ARCHITECTURE.md` -- it does not exist in this repo)

---

## Decisions -- Locked

> This is a **learning project**. All databases and external services are **placeholders/mocks**.
> No production data. No real credentials required beyond an LLM API key.

| Decision | Choice | Notes |
|---|---|---|
| **LLM provider** | Anthropic Claude | Default model: `claude-sonnet-4-6`. Use `langchain-anthropic`. Remove `langchain-openai` dependency. |
| **Vector store** | ChromaDB | Runs in-process, no extra service. Add `chromadb` to `requirements.txt`. |
| **Report format** | Markdown | Plain `.md` string returned in API response. No PDF/HTML deps needed. |
| **Auth** | Keep existing JWT | Extend `TokenData` in `auth.py` with a `role` field. No SSO needed. |
| **DB schema** | Placeholder/mock | `sql_tool` will use SQLite in-memory with seeded fake data (positions, trades, NAV, limits tables). No real DWH. |
| **CORS** | Localhost only | `allow_origins=["http://localhost:3000", "http://localhost:8080"]` -- learning project, no prod domain. |

### What "placeholder" means for each tool

- **`sql_tool`** -- connects to an in-memory SQLite DB seeded with fake fintech data (10 funds, 50 positions, 100 trades)
- **`document_tool`** -- ingests 2-3 sample PDF stubs stored in `data/docs/`
- **`excel_tool`** -- reads a sample `data/sample_portfolio.xlsx` file committed to the repo
- **LLM API key** -- real key needed (Claude). Everything else is local/mocked.

---

## Corrections vs Original Checklist

The following errors were found and fixed in this version:

| # | Original (wrong) | Corrected |
|---|---|---|
| 1 | "Delete `src/orchestrator/` planning files" | Planning files are in `src/agents/planning/` -- deletion moved to Phase 3 |
| 2 | Fix `src/memory/store.py` | Actual file is `src/memory/redis_store.py` |
| 3 | "Delete `quality_critic.py`, `security_critic.py`, `architecture_critic.py`" | All critics are in one file: `src/agents/validation/critics.py` |
| 4 | "Update `ARCHITECTURE.md`" | This file does not exist in the repo |
| 5 | *(missing)* | `config.py` must be updated first -- `openai_api_key` is required and will break startup with Claude/Azure |
| 6 | *(missing)* | `InputSanitizer` blocks SQL keywords in natural language -- breaks all ops queries |
| 7 | *(missing)* | `data_writer.py`, `executor.py`, `recovery.py` missing from deletion list |
| 8 | *(missing)* | `docker-compose.yml` needs env var updates for provider-agnostic LLM |

---

_Total tasks: ~75 | Estimated effort: 4-5 weeks for one developer_
