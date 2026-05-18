"""Multi-level Critic agents for validation with veto power."""
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from src.orchestrator.state import ValidationResult, ExecutionPlan
from src.utils.logging import get_logger

logger = get_logger(__name__)


class CriticAgent:
    """Multi-level critic agent with veto power and detailed feedback."""
    
    # Different critic levels with different focus areas
    CRITIC_LEVELS = {
        1: {
            "name": "Quality Critic",
            "focus": "Output quality, completeness, and correctness",
            "prompt": """You are a Quality Critic reviewing task outputs.

Focus on:
- Is the output complete and correct?
- Does it fully address the task requirements?
- Are there any obvious errors or omissions?
- Is the quality acceptable?

Be thorough but fair. Only reject if there are significant issues."""
        },
        2: {
            "name": "Security Critic",
            "focus": "Security vulnerabilities and best practices",
            "prompt": """You are a Security Critic reviewing task outputs.

Focus on:
- Are there any security vulnerabilities?
- Are credentials or sensitive data properly handled?
- Are best security practices followed?
- Are there injection risks or other security issues?

Reject if you find ANY security concerns."""
        },
        3: {
            "name": "Architecture Critic",
            "focus": "Design patterns, scalability, and maintainability",
            "prompt": """You are an Architecture Critic reviewing task outputs.

Focus on:
- Is the architecture sound and scalable?
- Are appropriate design patterns used?
- Is the code/solution maintainable?
- Are there better architectural approaches?

Provide constructive feedback even if approving."""
        }
    }
    
    def __init__(self, llm: ChatOpenAI):
        """Initialize the critic agent.
        
        Args:
            llm: Language model instance
        """
        self.llm = llm
    
    async def validate(
        self,
        task: str,
        results: Dict[str, Any],
        plan: ExecutionPlan
    ) -> ValidationResult:
        """Run multi-level validation on execution results.
        
        Args:
            task: Original task
            results: Execution results
            plan: Execution plan
            
        Returns:
            Validation result with approval and feedback
        """
        logger.info("starting_validation", num_critics=len(self.CRITIC_LEVELS))
        
        all_feedback = []
        all_issues = []
        all_suggestions = []
        
        # Run all critic levels
        for level, critic_config in self.CRITIC_LEVELS.items():
            logger.info(
                "running_critic",
                level=level,
                critic_name=critic_config["name"]
            )
            
            critic_result = await self._run_critic_level(
                level=level,
                critic_config=critic_config,
                task=task,
                results=results,
                plan=plan
            )
            
            all_feedback.append(f"[{critic_config['name']}] {critic_result['feedback']}")
            all_issues.extend(critic_result.get('issues', []))
            all_suggestions.extend(critic_result.get('suggestions', []))
            
            # If any critic rejects, fail validation
            if not critic_result['approved']:
                logger.warning(
                    "critic_rejected",
                    level=level,
                    critic_name=critic_config["name"]
                )
                
                return ValidationResult(
                    approved=False,
                    critic_level=level,
                    feedback="\n".join(all_feedback),
                    issues=all_issues,
                    suggestions=all_suggestions
                )
        
        # All critics approved
        logger.info("validation_passed", num_critics=len(self.CRITIC_LEVELS))
        
        return ValidationResult(
            approved=True,
            critic_level=len(self.CRITIC_LEVELS),
            feedback="\n".join(all_feedback),
            issues=all_issues,
            suggestions=all_suggestions
        )
    
    async def _run_critic_level(
        self,
        level: int,
        critic_config: Dict[str, str],
        task: str,
        results: Dict[str, Any],
        plan: ExecutionPlan
    ) -> Dict[str, Any]:
        """Run a single critic level.
        
        Args:
            level: Critic level number
            critic_config: Configuration for this critic
            task: Original task
            results: Execution results
            plan: Execution plan
            
        Returns:
            Critic evaluation result
        """
        # Build review context
        results_summary = self._summarize_results(results)
        plan_summary = self._summarize_plan(plan)
        
        messages = [
            SystemMessage(content=critic_config["prompt"]),
            HumanMessage(content=f"""Review the following task execution:

TASK: {task}

PLAN:
{plan_summary}

RESULTS:
{results_summary}

Provide your evaluation in the following format:
APPROVED: Yes/No
ISSUES: (list any issues, one per line, or "None")
SUGGESTIONS: (list any suggestions for improvement, one per line, or "None")
FEEDBACK: (detailed feedback)

Focus on: {critic_config['focus']}
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        evaluation_text = response.content
        
        # Parse the response
        parsed = self._parse_critic_response(evaluation_text)
        
        logger.info(
            "critic_level_complete",
            level=level,
            approved=parsed['approved']
        )
        
        return parsed
    
    def _summarize_results(self, results: Dict[str, Any]) -> str:
        """Summarize execution results for review.
        
        Args:
            results: Execution results
            
        Returns:
            Text summary
        """
        lines = []
        
        for step_id, result in results.items():
            status = result.get('status', 'unknown')
            
            if isinstance(result, dict):
                result_preview = str(result.get('result', result))[:200]
            else:
                result_preview = str(result)[:200]
            
            lines.append(f"- {step_id}: {status}")
            lines.append(f"  Result: {result_preview}")
        
        return "\n".join(lines) if lines else "No results"
    
    def _summarize_plan(self, plan: ExecutionPlan) -> str:
        """Summarize execution plan.
        
        Args:
            plan: Execution plan
            
        Returns:
            Text summary
        """
        lines = []
        
        for step in plan.steps:
            lines.append(f"- {step.step_id}: {step.description}")
        
        return "\n".join(lines) if lines else "No plan"
    
    def _parse_critic_response(self, response_text: str) -> Dict[str, Any]:
        """Parse critic response into structured format.
        
        Args:
            response_text: Raw critic response
            
        Returns:
            Parsed evaluation
        """
        lines = response_text.split('\n')
        
        approved = False
        issues = []
        suggestions = []
        feedback = ""
        
        current_section = None
        
        for line in lines:
            line = line.strip()
            
            if line.upper().startswith('APPROVED:'):
                approved_text = line.split(':', 1)[1].strip().lower()
                approved = approved_text in ['yes', 'true', 'approved']
            
            elif line.upper().startswith('ISSUES:'):
                current_section = 'issues'
                issue_text = line.split(':', 1)[1].strip()
                if issue_text.lower() not in ['none', '']:
                    issues.append(issue_text)
            
            elif line.upper().startswith('SUGGESTIONS:'):
                current_section = 'suggestions'
                suggestion_text = line.split(':', 1)[1].strip()
                if suggestion_text.lower() not in ['none', '']:
                    suggestions.append(suggestion_text)
            
            elif line.upper().startswith('FEEDBACK:'):
                current_section = 'feedback'
                feedback = line.split(':', 1)[1].strip()
            
            elif line and current_section == 'issues':
                if line.startswith('-') or line.startswith('*'):
                    line = line[1:].strip()
                if line.lower() not in ['none', '']:
                    issues.append(line)
            
            elif line and current_section == 'suggestions':
                if line.startswith('-') or line.startswith('*'):
                    line = line[1:].strip()
                if line.lower() not in ['none', '']:
                    suggestions.append(line)
            
            elif line and current_section == 'feedback':
                feedback += " " + line
        
        return {
            'approved': approved,
            'issues': issues,
            'suggestions': suggestions,
            'feedback': feedback.strip() if feedback else "No detailed feedback provided"
        }
