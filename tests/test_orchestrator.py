"""Unit tests for the fintech multi-agent orchestrator."""
import pytest
import asyncio

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
        """Ops users say things like 'select the top funds' — must not be blocked."""
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
