"""Unit tests for the multi-agent orchestrator."""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from src.orchestrator.state import create_initial_state, Phase, TaskStatus
from src.agents.planning.pre_planner import PrePlanner
from src.gateway.sanitizer import InputSanitizer


class TestInputSanitizer:
    """Tests for input sanitization."""
    
    def test_sanitize_text_basic(self):
        """Test basic text sanitization."""
        text = "<script>alert('xss')</script>Hello"
        sanitized = InputSanitizer.sanitize_text(text, allow_html=False)
        assert "<script>" not in sanitized
        assert "Hello" in sanitized
    
    def test_check_sql_injection(self):
        """Test SQL injection detection."""
        malicious = "SELECT * FROM users WHERE id = 1"
        is_safe, threats = InputSanitizer.check_for_injections(malicious)
        assert not is_safe
        assert "potential_sql_injection" in threats
    
    def test_sanitize_dict(self):
        """Test dictionary sanitization."""
        data = {
            "name": "<b>Test</b>",
            "value": 123
        }
        sanitized = InputSanitizer.sanitize_dict(data)
        assert "<b>" not in sanitized["name"]
        assert sanitized["value"] == 123


class TestOrchestratorState:
    """Tests for orchestrator state."""
    
    def test_create_initial_state(self):
        """Test initial state creation."""
        state = create_initial_state(
            task_id="test-123",
            session_id="session-456",
            user_id="user-789",
            task="Test task"
        )
        
        assert state["task_id"] == "test-123"
        assert state["session_id"] == "session-456"
        assert state["phase"] == Phase.INIT
        assert state["status"] == TaskStatus.SUBMITTED
        assert state["progress"] == 0.0


@pytest.mark.asyncio
class TestPrePlanner:
    """Tests for pre-planner agent."""
    
    async def test_create_plan(self):
        """Test plan creation."""
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=Mock(content="Step 1: Test step"))
        
        planner = PrePlanner(mock_llm)
        plan = await planner.create_plan("Build a simple API")
        
        assert plan is not None
        assert len(plan.steps) > 0
        assert plan.dag is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
