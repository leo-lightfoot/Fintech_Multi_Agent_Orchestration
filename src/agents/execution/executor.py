"""Executor agent for running planned tasks."""
from typing import Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
import asyncio
import networkx as nx

from src.orchestrator.state import ExecutionPlan, PlanStep, AgentType, CostTracking
from src.agents.execution.data_writer import DataWriter
from src.agents.execution.code_executor import CodeExecutor
from src.utils.logging import get_logger

logger = get_logger(__name__)


class Executor:
    """Main executor agent that coordinates step execution."""
    
    SYSTEM_PROMPT = """You are an execution agent responsible for carrying out planned tasks.

Your job is to:
1. Execute tasks according to the plan
2. Handle data from previous steps
3. Produce clear, actionable outputs
4. Report progress and results

Be thorough and precise in your execution."""
    
    def __init__(self, llm: ChatOpenAI):
        """Initialize the executor.
        
        Args:
            llm: Language model instance
        """
        self.llm = llm
        self.data_writer = DataWriter(llm)
        self.code_executor = CodeExecutor()
    
    async def execute_plan(
        self,
        plan: ExecutionPlan,
        context: Optional[Dict[str, Any]],
        cost_tracking: CostTracking
    ) -> Dict[str, Any]:
        """Execute all steps in the plan.
        
        Args:
            plan: Execution plan with DAG
            context: Additional context
            cost_tracking: Cost tracking object
            
        Returns:
            Dictionary mapping step_id to results
        """
        logger.info("executing_plan", num_steps=len(plan.steps))
        
        results = {}
        
        # Build execution order using topological sort
        execution_order = self._get_execution_order(plan)
        
        logger.info("execution_order_determined", order=execution_order)
        
        # Execute steps in order, parallelizing where possible
        for level in execution_order:
            # Execute all steps at this level in parallel
            if len(level) > 1:
                logger.info("parallel_execution", num_steps=len(level))
            
            level_tasks = []
            for step_id in level:
                step = self._get_step_by_id(plan, step_id)
                if step:
                    level_tasks.append(
                        self._execute_step(step, results, context, cost_tracking)
                    )
            
            # Wait for all steps at this level to complete
            level_results = await asyncio.gather(*level_tasks, return_exceptions=True)
            
            # Store results
            for i, step_id in enumerate(level):
                if isinstance(level_results[i], Exception):
                    logger.error(
                        "step_execution_failed",
                        step_id=step_id,
                        error=str(level_results[i])
                    )
                    results[step_id] = {
                        "error": str(level_results[i]),
                        "status": "failed"
                    }
                else:
                    results[step_id] = level_results[i]
        
        logger.info("plan_execution_complete", num_results=len(results))
        
        return results
    
    async def _execute_step(
        self,
        step: PlanStep,
        previous_results: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        cost_tracking: CostTracking
    ) -> Any:
        """Execute a single step.
        
        Args:
            step: Step to execute
            previous_results: Results from previous steps
            context: Additional context
            cost_tracking: Cost tracking
            
        Returns:
            Step result
        """
        logger.info(
            "executing_step",
            step_id=step.step_id,
            agent_type=step.agent_type,
            description=step.description
        )
        
        # Gather dependencies
        dep_data = {}
        for dep_id in step.dependencies:
            if dep_id in previous_results:
                dep_data[dep_id] = previous_results[dep_id]
        
        # Route to appropriate executor
        try:
            if step.agent_type == AgentType.CODE_EXECUTOR:
                result = await self.code_executor.execute(
                    step.description,
                    dep_data,
                    context
                )
            elif step.agent_type == AgentType.DATA_WRITER:
                result = await self.data_writer.write(
                    step.description,
                    dep_data,
                    context
                )
            else:
                # Default execution with LLM
                result = await self._execute_with_llm(
                    step.description,
                    dep_data,
                    context
                )
            
            # Update cost tracking (simplified)
            cost_tracking.llm_calls += 1
            cost_tracking.tokens_used += 1000  # Estimate
            cost_tracking.total_cost_usd += 0.01  # Estimate
            
            logger.info(
                "step_completed",
                step_id=step.step_id,
                result_type=type(result).__name__
            )
            
            return {
                "status": "success",
                "result": result,
                "step_id": step.step_id
            }
        
        except Exception as e:
            logger.error(
                "step_execution_error",
                step_id=step.step_id,
                error=str(e),
                exc_info=True
            )
            raise
    
    async def _execute_with_llm(
        self,
        task: str,
        dependencies: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Execute a task using the LLM.
        
        Args:
            task: Task description
            dependencies: Data from dependencies
            context: Additional context
            
        Returns:
            Execution result
        """
        # Build prompt with dependencies
        dep_text = ""
        if dependencies:
            dep_text = "\n\nData from previous steps:\n"
            for dep_id, dep_data in dependencies.items():
                dep_text += f"- {dep_id}: {dep_data}\n"
        
        context_text = ""
        if context:
            context_text = f"\n\nAdditional context:\n{context}"
        
        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=f"""Task: {task}{dep_text}{context_text}

Execute this task and provide the result.""")
        ]
        
        response = await self.llm.ainvoke(messages)
        return response.content
    
    def _get_execution_order(self, plan: ExecutionPlan) -> list[list[str]]:
        """Get execution order using topological sort.
        
        Returns steps grouped by level, where each level can be
        executed in parallel.
        
        Args:
            plan: Execution plan
            
        Returns:
            List of lists, where each inner list contains step_ids
            that can be executed in parallel
        """
        # Build graph
        G = nx.DiGraph()
        
        for step in plan.steps:
            G.add_node(step.step_id)
            for dep in step.dependencies:
                G.add_edge(dep, step.step_id)
        
        # Get topological generations
        try:
            generations = list(nx.topological_generations(G))
            return generations
        except nx.NetworkXError as e:
            logger.error("topological_sort_failed", error=str(e))
            # Fallback to sequential
            return [[step.step_id] for step in plan.steps]
    
    def _get_step_by_id(self, plan: ExecutionPlan, step_id: str) -> Optional[PlanStep]:
        """Get a step by its ID.
        
        Args:
            plan: Execution plan
            step_id: Step identifier
            
        Returns:
            PlanStep or None
        """
        for step in plan.steps:
            if step.step_id == step_id:
                return step
        return None
