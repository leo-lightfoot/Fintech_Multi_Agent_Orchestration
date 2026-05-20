"""Unit tests for the fintech multi-agent orchestrator."""
import pytest

from src.orchestrator.state import create_initial_state, Phase, TaskStatus
from src.gateway.sanitizer import InputSanitizer


class TestInputSanitizer:
    """Tests for input sanitization."""

    def test_sanitize_text_strips_xss(self):
        text = "<script>alert('xss')</script>Hello"
        sanitized = InputSanitizer.sanitize_text(text, allow_html=False)
        assert "<script>" not in sanitized
        assert "Hello" in sanitized

    def test_natural_language_with_sql_words_is_allowed(self):
        """Ops users say things like 'select the top funds' -- must not be blocked."""
        task = "Select the top 10 funds by AUM and create a report"
        is_safe, threats = InputSanitizer.check_for_injections(task)
        assert is_safe
        assert threats == []

    def test_shell_injection_is_blocked(self):
        """Shell metacharacters in a task description should be flagged."""
        malicious = "show me funds; rm -rf /"
        is_safe, threats = InputSanitizer.check_for_injections(malicious)
        assert not is_safe
        assert "potential_command_injection" in threats

    def test_validate_sql_param_blocks_injection(self):
        """SQL keywords in a raw query parameter must be blocked."""
        malicious_param = "' OR 1=1; DROP TABLE funds --"
        is_safe, threats = InputSanitizer.validate_sql_param(malicious_param)
        assert not is_safe
        assert "potential_sql_injection" in threats

    def test_sanitize_dict(self):
        data = {"name": "<b>Test</b>", "value": 123}
        sanitized = InputSanitizer.sanitize_dict(data)
        assert "<b>" not in sanitized["name"]
        assert sanitized["value"] == 123


class TestOrchestratorState:
    """Tests for orchestrator state."""

    def test_create_initial_state(self):
        state = create_initial_state(
            task_id="test-123",
            session_id="session-456",
            user_id="user-789",
            task="Test task",
        )
        assert state["task_id"] == "test-123"
        assert state["phase"] == Phase.INIT
        assert state["status"] == TaskStatus.SUBMITTED
        assert state["progress"] == 0.0
        assert state["agents_selected"] == []
        assert state["agent_results"] == {}

    def test_cost_tracking_within_budget(self):
        from src.orchestrator.state import CostTracking
        tracker = CostTracking(budget_limit_usd=10.0, total_cost_usd=5.0)
        assert tracker.within_budget() is True

    def test_cost_tracking_over_budget(self):
        from src.orchestrator.state import CostTracking
        tracker = CostTracking(budget_limit_usd=10.0, total_cost_usd=10.5)
        assert tracker.within_budget() is False


@pytest.mark.asyncio
class TestSqlTool:
    """Tests for the SQL query tool and placeholder database."""

    async def test_valid_select_returns_data(self):
        """A valid SELECT should return rows from the seeded database."""
        from src.tools.sql import execute_query
        import json

        result = await execute_query("SELECT fund_id, fund_name FROM funds ORDER BY fund_id")
        rows = json.loads(result)

        assert isinstance(rows, list)
        assert len(rows) == 3
        assert rows[0]["fund_id"] == "F001"
        assert rows[0]["fund_name"] == "Alpha Growth Fund"

    async def test_non_select_is_blocked(self):
        """INSERT/UPDATE/DELETE/DROP must be rejected."""
        from src.tools.sql import execute_query
        import json

        result = await execute_query("DROP TABLE funds")
        data = json.loads(result)
        assert "error" in data

    async def test_sql_injection_in_query_is_blocked(self):
        """A query containing injection patterns must be blocked."""
        from src.tools.sql import execute_query
        import json

        result = await execute_query("SELECT * FROM funds; DROP TABLE funds --")
        data = json.loads(result)
        assert "error" in data

    async def test_breached_limits_query(self):
        """Querying for breached limits should return only breached rows."""
        from src.tools.sql import execute_query
        import json

        result = await execute_query(
            "SELECT rule_id, fund_id, rule_name FROM limit_rules WHERE breached = 1"
        )
        rows = json.loads(result)
        assert isinstance(rows, list)
        assert len(rows) == 2  # R002 and R004 are breached in seed data
        rule_ids = {r["rule_id"] for r in rows}
        assert "R002" in rule_ids
        assert "R004" in rule_ids


class TestRedisStoreSerialisation:
    """Tests for state serialisation/deserialisation without a live Redis connection."""

    def _make_store(self):
        """Return a RedisStore instance with the Redis client patched out."""
        from unittest.mock import MagicMock
        from src.memory.redis_store import RedisStore
        store = object.__new__(RedisStore)   # bypass __init__ (avoids Redis connection)
        store.redis = MagicMock()
        return store

    def test_round_trip_preserves_cost_tracking(self):
        """CostTracking must come back as a CostTracking model, not a plain dict."""
        from src.orchestrator.state import CostTracking, ValidationResult
        from src.memory.redis_store import RedisStore

        store = self._make_store()
        state = create_initial_state(
            task_id="t1", session_id="s1", user_id="u1", task="test"
        )
        state["cost_tracking"] = CostTracking(
            budget_limit_usd=10.0,
            total_cost_usd=2.5,
            llm_calls=3,
            tokens_used=1500,
        )

        serialised = store._serialize_state(state)
        restored = store._deserialize_state(serialised)

        ct = restored["cost_tracking"]
        assert isinstance(ct, CostTracking), f"expected CostTracking, got {type(ct)}"
        assert ct.total_cost_usd == 2.5
        assert ct.llm_calls == 3
        assert ct.within_budget() is True

    def test_round_trip_preserves_validation_result(self):
        """ValidationResult must come back as a ValidationResult model, not a dict."""
        from src.orchestrator.state import ValidationResult
        from src.memory.redis_store import RedisStore

        store = self._make_store()
        state = create_initial_state(
            task_id="t2", session_id="s2", user_id="u2", task="test"
        )
        state["validation_result"] = ValidationResult(
            approved=False,
            severity="reject",
            issues=["missing risk section", "no NAV data"],
            feedback="incomplete output",
        )

        serialised = store._serialize_state(state)
        restored = store._deserialize_state(serialised)

        vr = restored["validation_result"]
        assert isinstance(vr, ValidationResult), f"expected ValidationResult, got {type(vr)}"
        assert vr.approved is False
        assert vr.severity == "reject"
        assert len(vr.issues) == 2

    def test_round_trip_none_validation_result(self):
        """None validation_result must deserialise back to None, not crash."""
        from src.memory.redis_store import RedisStore

        store = self._make_store()
        state = create_initial_state(
            task_id="t3", session_id="s3", user_id="u3", task="test"
        )
        assert state["validation_result"] is None

        serialised = store._serialize_state(state)
        restored = store._deserialize_state(serialised)

        assert restored["validation_result"] is None

    def test_round_trip_preserves_primitive_fields(self):
        """task, user_id, progress, errors must all survive the round trip."""
        from src.memory.redis_store import RedisStore

        store = self._make_store()
        state = create_initial_state(
            task_id="t4", session_id="s4", user_id="alice", task="show me the funds"
        )
        state["progress"] = 0.65
        state["errors"] = ["agent timed out"]
        state["agents_selected"] = ["data", "risk"]

        serialised = store._serialize_state(state)
        restored = store._deserialize_state(serialised)

        assert restored["user_id"] == "alice"
        assert restored["task"] == "show me the funds"
        assert restored["progress"] == 0.65
        assert restored["errors"] == ["agent timed out"]
        assert restored["agents_selected"] == ["data", "risk"]


# ---------------------------------------------------------------------------
# Supervisor routing -- pure logic tests (no LLM needed)
# ---------------------------------------------------------------------------

class TestSupervisorRouting:
    """Tests for the supervisor sanitize / routing logic -- no LLM calls."""

    def _make_decision(self, intent: str, agents: list[str]):
        from src.agents.supervisor import SupervisorDecision
        return SupervisorDecision(intent=intent, agents=agents, reasoning="test")

    def _sanitize(self, decision):
        from src.agents.supervisor import Supervisor
        from unittest.mock import MagicMock
        sup = object.__new__(Supervisor)
        sup.llm = MagicMock()
        return sup._sanitize(decision)

    def test_unknown_intent_falls_back_to_data(self):
        d = self._make_decision("completely_unknown_intent", ["data"])
        result = self._sanitize(d)
        assert result.intent == "unknown"
        assert result.agents == ["data"]

    def test_valid_intent_kept_unchanged(self):
        d = self._make_decision("risk_report", ["data", "risk", "report"])
        result = self._sanitize(d)
        assert result.intent == "risk_report"
        assert result.agents == ["data", "risk", "report"]

    def test_invalid_agent_name_replaced_with_canonical(self):
        d = self._make_decision("data_query", ["data", "nonexistent_agent"])
        result = self._sanitize(d)
        # canonical pipeline for data_query is ["data"]
        assert all(a in {"data", "portfolio", "risk", "report"} for a in result.agents)

    def test_data_always_first(self):
        d = self._make_decision("portfolio_query", ["portfolio", "data"])
        result = self._sanitize(d)
        assert result.agents[0] == "data"

    def test_full_analysis_pipeline(self):
        d = self._make_decision("full_analysis", ["data", "portfolio", "risk", "report"])
        result = self._sanitize(d)
        assert result.intent == "full_analysis"
        assert result.agents == ["data", "portfolio", "risk", "report"]


# ---------------------------------------------------------------------------
# RiskAgent -- pure logic tests
# ---------------------------------------------------------------------------

class TestRiskAgentHelpers:
    """Tests for RiskAgent helper functions."""

    def test_extract_data_from_previous_results(self):
        from src.agents.utils import extract_data_text
        previous = {"data": {"status": "success", "result": "Fund F001: breached=1 on R002"}}
        text = extract_data_text(previous)
        assert "F001" in text
        assert "breached" in text

    def test_extract_data_missing_returns_placeholder(self):
        from src.agents.utils import extract_data_text
        assert extract_data_text(None) == "No data available."
        assert extract_data_text({}) == "No data available."

    def test_risk_result_model_validates(self):
        from src.agents.risk import RiskResult, RiskFlag, LimitBreach
        result = RiskResult(
            overall_status="breach",
            breaches=[LimitBreach(
                rule_id="R002", fund_id="F001", rule_name="Cash Min",
                limit_value=2.0, current_value=1.5, overshoot_pct=-25.0
            )],
            flags=[RiskFlag(
                rule_id="R002", fund_id="F001", rule_name="Cash Min",
                rule_type="MIN_CASH_PCT", limit_value=2.0, current_value=1.5,
                breached=True, severity="warning"
            )],
            summary="One breach found.",
        )
        assert result.overall_status == "breach"
        assert len(result.breaches) == 1
        assert result.breaches[0].rule_id == "R002"


# ---------------------------------------------------------------------------
# Validator -- pure logic tests
# ---------------------------------------------------------------------------

class TestValidatorHelpers:
    """Tests for Validator helper functions."""

    def test_summarise_success_result(self):
        from src.agents.validator import _summarise_results
        results = {"data": {"status": "success", "result": "Found 3 funds"}}
        summary = _summarise_results(results)
        assert "[data]" in summary
        assert "Found 3 funds" in summary

    def test_summarise_stub_result(self):
        from src.agents.validator import _summarise_results
        results = {"risk": {"status": "stub", "result": "[risk not yet implemented]"}}
        summary = _summarise_results(results)
        assert "not yet implemented" in summary

    def test_summarise_error_result(self):
        from src.agents.validator import _summarise_results
        results = {"portfolio": {"status": "error", "error": "connection refused"}}
        summary = _summarise_results(results)
        assert "ERROR" in summary
        assert "connection refused" in summary

    def test_summarise_pydantic_model_result(self):
        from src.agents.validator import _summarise_results
        from src.agents.risk import RiskResult
        risk_result = RiskResult(overall_status="ok", summary="All clear.")
        results = {"risk": {"status": "success", "result": risk_result}}
        summary = _summarise_results(results)
        # Pydantic model should be serialised to JSON, not raw repr
        assert "overall_status" in summary
        assert "RiskResult" not in summary


# ---------------------------------------------------------------------------
# Audit trail -- unit tests without live Redis
# ---------------------------------------------------------------------------

class TestAuditTrail:
    """Tests for AuditEntry model and AuditTrail logging."""

    def test_audit_entry_defaults(self):
        from src.audit.trail import AuditEntry
        entry = AuditEntry(
            task_id="t1", session_id="s1", user_id="alice",
            action="agent_executed", agent="data",
        )
        assert entry.status == "success"
        assert entry.role == "ops"    # default; graph passes real role at runtime
        assert entry.cost_usd == 0.0
        assert entry.timestamp  # auto-set

    @pytest.mark.asyncio
    async def test_audit_trail_fire_and_forget_on_none_store(self):
        """AuditTrail with no store must not raise."""
        from src.audit.trail import AuditTrail, AuditEntry
        trail = AuditTrail(redis_store=None)
        entry = AuditEntry(task_id="t", session_id="s", user_id="u",
                           action="test", agent="data")
        await trail.log(entry)  # should complete silently


# ---------------------------------------------------------------------------
# Excel tool -- reads the committed sample file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestExcelTool:
    """Tests for the Excel tool using the committed sample file."""

    async def test_read_sample_xlsx(self):
        """Reading the sample portfolio file should return all three sheets."""
        from src.tools.excel import _read_file
        import json

        result = _read_file("sample_portfolio.xlsx")
        data = json.loads(result)

        assert "sheets" in data
        sheet_names = [s["name"] for s in data["sheets"]]
        assert "Positions" in sheet_names
        assert "NAV History" in sheet_names
        assert "Limits" in sheet_names

    async def test_read_specific_sheet(self):
        """Reading a single sheet returns only that sheet."""
        from src.tools.excel import _read_file
        import json

        result = _read_file("sample_portfolio.xlsx", sheet="Limits")
        data = json.loads(result)
        assert len(data["sheets"]) == 1
        assert data["sheets"][0]["name"] == "Limits"

    async def test_nonexistent_file_returns_error(self):
        from src.tools.excel import _read_file
        import json

        result = _read_file("does_not_exist.xlsx")
        data = json.loads(result)
        assert "error" in data

    async def test_path_traversal_blocked(self):
        from src.tools.excel import _read_file
        import json

        result = _read_file("../../etc/passwd")
        data = json.loads(result)
        assert "error" in data


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

class TestCostTracking:
    """Tests for the pricing table and cost calculation."""

    def test_known_model_price(self):
        from src.utils.cost import calculate_cost
        # claude-sonnet-4-6: $3/M input, $15/M output
        cost = calculate_cost("claude-sonnet-4-6", input_tokens=1000, output_tokens=200)
        expected = (1000 * 3.00 + 200 * 15.00) / 1_000_000
        assert abs(cost - expected) < 1e-9

    def test_unknown_model_uses_default(self):
        from src.utils.cost import calculate_cost, PRICING
        cost = calculate_cost("some-unknown-model", input_tokens=1000, output_tokens=500)
        default_pricing = PRICING["_default"]
        expected = (1000 * default_pricing["input"] + 500 * default_pricing["output"]) / 1_000_000
        assert abs(cost - expected) < 1e-9

    def test_zero_tokens_zero_cost(self):
        from src.utils.cost import calculate_cost
        assert calculate_cost("claude-sonnet-4-6", 0, 0) == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
