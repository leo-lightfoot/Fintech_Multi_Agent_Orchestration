"""Responder agent for formatting final outputs."""
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from src.utils.logging import get_logger

logger = get_logger(__name__)


class Responder:
    """Responder agent that formats final outputs for users."""
    
    SYSTEM_PROMPT = """You are a Response Formatting expert responsible for creating clear, user-friendly outputs.

Your job is to:
1. Format technical information for user consumption
2. Structure responses clearly and logically
3. Highlight key outcomes and next steps
4. Make complex information accessible
5. Provide actionable insights

When formatting responses:
- Start with a clear summary of what was accomplished
- Use proper formatting (headings, lists, code blocks)
- Explain technical concepts when necessary
- Include relevant details without overwhelming
- End with next steps or recommendations if applicable
- Be professional but approachable
"""
    
    def __init__(self, llm: ChatOpenAI):
        """Initialize the responder.
        
        Args:
            llm: Language model instance
        """
        self.llm = llm
    
    async def format_response(
        self,
        task: str,
        summary: str,
        results: Dict[str, Any]
    ) -> str:
        """Format final response for the user.
        
        Args:
            task: Original task
            summary: Summarized results
            results: Full execution results
            
        Returns:
            Formatted response ready for user
        """
        logger.info("formatting_response", task_length=len(task))
        
        # Prepare additional context
        success_count = sum(
            1 for r in results.values()
            if isinstance(r, dict) and r.get('status') == 'success'
        )
        total_steps = len(results)
        
        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=f"""Create a final response for the user based on the following:

ORIGINAL REQUEST:
{task}

EXECUTION SUMMARY:
{summary}

STATISTICS:
- Total steps executed: {total_steps}
- Successful steps: {success_count}
- Success rate: {(success_count/total_steps*100) if total_steps > 0 else 0:.1f}%

Format this into a clear, well-structured response that:
1. Confirms what was done
2. Presents key results
3. Highlights any important notes or issues
4. Suggests next steps if appropriate

Use markdown formatting for clarity.""")
        ]
        
        response = await self.llm.ainvoke(messages)
        formatted = response.content
        
        logger.info("response_formatted", response_length=len(formatted))
        
        return formatted
