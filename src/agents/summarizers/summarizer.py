"""Summarizer agent for condensing context and preventing pollution."""
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from src.orchestrator.state import ValidationResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


class Summarizer:
    """Summarizer agent that condenses results to prevent context pollution."""
    
    SYSTEM_PROMPT = """You are a Summarization expert responsible for condensing complex information.

Your job is to:
1. Extract key information from execution results
2. Remove redundant or verbose content
3. Preserve critical details and decisions
4. Create clear, concise summaries
5. Maintain technical accuracy

When summarizing:
- Focus on outcomes and key results
- Highlight any issues or important notes
- Keep technical details that matter
- Remove boilerplate and verbosity
- Use clear, structured formatting
"""
    
    def __init__(self, llm: ChatOpenAI):
        """Initialize the summarizer.
        
        Args:
            llm: Language model instance
        """
        self.llm = llm
    
    async def summarize(
        self,
        task: str,
        results: Dict[str, Any],
        validation_results: List[ValidationResult]
    ) -> str:
        """Summarize execution results.
        
        Args:
            task: Original task
            results: Execution results
            validation_results: Validation feedback
            
        Returns:
            Concise summary
        """
        logger.info("summarizing_results", num_results=len(results))
        
        # Build content to summarize
        results_text = self._format_results(results)
        validation_text = self._format_validation(validation_results)
        
        # Calculate total content size
        total_length = len(task) + len(results_text) + len(validation_text)
        logger.info("content_to_summarize", length=total_length)
        
        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=f"""Summarize the following task execution:

ORIGINAL TASK:
{task}

EXECUTION RESULTS:
{results_text}

VALIDATION:
{validation_text}

Create a concise summary that:
1. States what was accomplished
2. Highlights key results
3. Notes any important issues or feedback
4. Provides relevant technical details

Keep the summary under 500 words.""")
        ]
        
        response = await self.llm.ainvoke(messages)
        summary = response.content
        
        compression_ratio = len(summary) / total_length if total_length > 0 else 0
        
        logger.info(
            "summary_created",
            original_length=total_length,
            summary_length=len(summary),
            compression_ratio=f"{compression_ratio:.2%}"
        )
        
        return summary
    
    def _format_results(self, results: Dict[str, Any]) -> str:
        """Format execution results for summarization.
        
        Args:
            results: Execution results
            
        Returns:
            Formatted text
        """
        lines = []
        
        for step_id, result in results.items():
            lines.append(f"\n{step_id}:")
            
            if isinstance(result, dict):
                status = result.get('status', 'unknown')
                lines.append(f"  Status: {status}")
                
                if 'result' in result:
                    result_str = str(result['result'])
                    # Truncate long results
                    if len(result_str) > 500:
                        result_str = result_str[:500] + "... (truncated)"
                    lines.append(f"  Result: {result_str}")
                
                if 'error' in result and result['error']:
                    lines.append(f"  Error: {result['error']}")
            else:
                result_str = str(result)
                if len(result_str) > 500:
                    result_str = result_str[:500] + "... (truncated)"
                lines.append(f"  {result_str}")
        
        return "\n".join(lines) if lines else "No results"
    
    def _format_validation(self, validation_results: List[ValidationResult]) -> str:
        """Format validation results.
        
        Args:
            validation_results: Validation results
            
        Returns:
            Formatted text
        """
        if not validation_results:
            return "No validation performed"
        
        latest = validation_results[-1]
        
        lines = [
            f"Approved: {'Yes' if latest.approved else 'No'}",
            f"Critic Level: {latest.critic_level}",
            f"\nFeedback:\n{latest.feedback}"
        ]
        
        if latest.issues:
            lines.append(f"\nIssues Found:")
            for issue in latest.issues:
                lines.append(f"  - {issue}")
        
        if latest.suggestions:
            lines.append(f"\nSuggestions:")
            for suggestion in latest.suggestions:
                lines.append(f"  - {suggestion}")
        
        return "\n".join(lines)
