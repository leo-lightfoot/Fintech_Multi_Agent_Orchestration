"""Plan Refiner agent for optimizing execution plans."""
from typing import Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
import networkx as nx

from src.orchestrator.state import ExecutionPlan, PlanStep
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PlanRefiner:
    """Plan Refiner agent that optimizes and validates execution plans."""
    
    SYSTEM_PROMPT = """You are a plan refinement agent responsible for optimizing execution plans.

Your job is to:
1. Review the initial plan
2. Identify opportunities for parallelization
3. Optimize dependencies to maximize parallel execution
4. Ensure critical path is minimized
5. Add error handling considerations
6. Validate the plan is executable

When refining:
- Look for steps that can run in parallel (no data dependencies)
- Ensure proper error handling checkpoints
- Validate resource requirements
- Check for missing steps
- Ensure the plan is achievable within budget/time constraints

Provide specific recommendations for:
- Which steps can be parallelized
- Any missing steps or considerations
- Potential risks or bottlenecks
"""
    
    def __init__(self, llm: ChatOpenAI):
        """Initialize the plan refiner.
        
        Args:
            llm: Language model instance
        """
        self.llm = llm
    
    async def refine_plan(
        self,
        plan: ExecutionPlan,
        task: str
    ) -> ExecutionPlan:
        """Refine and optimize an execution plan.
        
        Args:
            plan: Initial execution plan
            task: Original task description
            
        Returns:
            Refined execution plan
        """
        logger.info("refining_plan", num_steps=len(plan.steps))
        
        # Build context about the plan
        plan_summary = self._summarize_plan(plan)
        
        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=f"""Original task: {task}

Current plan:
{plan_summary}

Refine this plan by:
1. Identifying steps that can run in parallel
2. Optimizing dependencies
3. Adding any missing steps
4. Flagging potential issues

Provide your analysis and recommendations.""")
        ]
        
        # Get refinement suggestions
        response = await self.llm.ainvoke(messages)
        refinement_text = response.content
        
        logger.info("refinement_generated", length=len(refinement_text))
        
        # Apply refinements
        refined_plan = self._apply_refinements(plan, refinement_text)
        
        # Optimize for parallelization
        refined_plan = self._optimize_parallelization(refined_plan)
        
        # Mark as refined
        refined_plan.refined = True
        
        logger.info(
            "plan_refined",
            num_steps=len(refined_plan.steps),
            parallel_groups=self._count_parallel_groups(refined_plan)
        )
        
        return refined_plan
    
    def _summarize_plan(self, plan: ExecutionPlan) -> str:
        """Create a text summary of the plan.
        
        Args:
            plan: Execution plan
            
        Returns:
            Text summary
        """
        lines = []
        
        for i, step in enumerate(plan.steps, 1):
            deps = step.dependencies if step.dependencies else ["None"]
            lines.append(
                f"{i}. {step.step_id}: {step.description}\n"
                f"   Agent: {step.agent_type}\n"
                f"   Dependencies: {', '.join(deps)}"
            )
        
        return "\n".join(lines)
    
    def _apply_refinements(
        self,
        plan: ExecutionPlan,
        refinement_text: str
    ) -> ExecutionPlan:
        """Apply refinement suggestions to the plan.
        
        In a more sophisticated implementation, this would parse
        the LLM's structured suggestions. For now, we'll focus on
        optimizing what we have.
        
        Args:
            plan: Original plan
            refinement_text: Refinement suggestions from LLM
            
        Returns:
            Refined plan
        """
        # For now, return the plan as-is
        # In production, parse and apply specific suggestions
        return plan
    
    def _optimize_parallelization(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Optimize the plan for maximum parallelization.
        
        Args:
            plan: Execution plan
            
        Returns:
            Optimized plan
        """
        # Build dependency graph
        G = nx.DiGraph()
        
        for step in plan.steps:
            G.add_node(step.step_id)
            for dep in step.dependencies:
                G.add_edge(dep, step.step_id)
        
        # Find independent steps (no common ancestors)
        # This is where we could optimize dependencies
        
        # For now, keep the structure but validate it
        if not nx.is_directed_acyclic_graph(G):
            logger.warning("dag_not_acyclic_after_refinement")
        
        return plan
    
    def _count_parallel_groups(self, plan: ExecutionPlan) -> int:
        """Count how many steps can potentially run in parallel.
        
        Args:
            plan: Execution plan
            
        Returns:
            Number of potential parallel execution groups
        """
        # Build graph
        G = nx.DiGraph()
        
        for step in plan.steps:
            G.add_node(step.step_id)
            for dep in step.dependencies:
                G.add_edge(dep, step.step_id)
        
        # Count nodes at each level
        try:
            levels = list(nx.topological_generations(G))
            max_parallel = max(len(level) for level in levels) if levels else 1
            return max_parallel
        except:
            return 1
