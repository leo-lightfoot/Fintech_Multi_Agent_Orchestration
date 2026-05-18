"""Pre-Planner agent for initial task decomposition."""
from typing import Optional, Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
import networkx as nx
import uuid

from src.orchestrator.state import ExecutionPlan, PlanStep, AgentType
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PrePlanner:
    """Pre-Planner agent that creates initial execution plans with DAG."""
    
    SYSTEM_PROMPT = """You are a pre-planning agent responsible for decomposing complex tasks into actionable steps.

Your job is to:
1. Analyze the user's task
2. Break it down into clear, sequential steps
3. Identify dependencies between steps
4. Assign appropriate agent types to each step
5. Create a DAG (Directed Acyclic Graph) representation

Available agent types:
- executor: General task execution
- data_writer: Writing/storing data
- code_executor: Running code in sandbox
- domain_expert: Specialized knowledge

Output your plan as a structured list of steps with:
- step_id (unique identifier)
- description (what needs to be done)
- agent_type (which agent should handle this)
- dependencies (list of step_ids that must complete first)

Example:
Task: "Build a REST API for user management"
Steps:
1. step_id: "design_schema", description: "Design database schema", agent_type: "domain_expert", dependencies: []
2. step_id: "create_models", description: "Create data models", agent_type: "code_executor", dependencies: ["design_schema"]
3. step_id: "implement_endpoints", description: "Implement CRUD endpoints", agent_type: "code_executor", dependencies: ["create_models"]
4. step_id: "write_tests", description: "Write unit tests", agent_type: "code_executor", dependencies: ["implement_endpoints"]
"""
    
    def __init__(self, llm: ChatOpenAI):
        """Initialize the pre-planner.
        
        Args:
            llm: Language model instance
        """
        self.llm = llm
    
    async def create_plan(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ExecutionPlan:
        """Create an initial execution plan.
        
        Args:
            task: Task description
            context: Additional context
            
        Returns:
            Execution plan with steps and DAG
        """
        logger.info("creating_plan", task_length=len(task))
        
        # Build the prompt
        context_str = ""
        if context:
            context_str = f"\n\nAdditional context:\n{context}"
        
        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=f"Task: {task}{context_str}\n\nCreate a detailed execution plan.")
        ]
        
        # Get LLM response
        response = await self.llm.ainvoke(messages)
        plan_text = response.content
        
        logger.info("plan_generated", plan_length=len(plan_text))
        
        # Parse the response into structured steps
        steps = self._parse_plan(plan_text)
        
        # Build DAG
        dag = self._build_dag(steps)
        
        # Validate DAG (no cycles)
        if not self._validate_dag(dag):
            logger.warning("dag_has_cycles_fixing")
            dag = self._fix_dag_cycles(dag)
        
        plan = ExecutionPlan(
            steps=steps,
            dag=dag,
            refined=False
        )
        
        logger.info(
            "plan_created",
            num_steps=len(steps),
            num_dependencies=sum(len(deps) for deps in dag.values())
        )
        
        return plan
    
    def _parse_plan(self, plan_text: str) -> list[PlanStep]:
        """Parse LLM response into structured steps.
        
        This is a simplified parser. In production, you might use
        structured output or JSON mode.
        
        Args:
            plan_text: Raw plan text from LLM
            
        Returns:
            List of plan steps
        """
        steps = []
        
        # Simple parsing logic - in production use structured output
        lines = plan_text.split('\n')
        
        current_step = None
        for line in lines:
            line = line.strip()
            
            if not line or line.startswith('#'):
                continue
            
            # Look for step indicators
            if any(line.lower().startswith(prefix) for prefix in ['step', '1.', '2.', '3.', '-', '*']):
                # Try to extract a step
                step_id = f"step_{str(uuid.uuid4())[:8]}"
                
                # Simple heuristic: first sentence is the description
                description = line.split(':', 1)[-1].strip() if ':' in line else line.strip()
                
                # Default agent type
                agent_type = AgentType.EXECUTOR
                if any(keyword in description.lower() for keyword in ['code', 'implement', 'write code']):
                    agent_type = AgentType.CODE_EXECUTOR
                elif any(keyword in description.lower() for keyword in ['design', 'architecture', 'expert']):
                    agent_type = AgentType.DOMAIN_EXPERT
                elif any(keyword in description.lower() for keyword in ['save', 'store', 'write', 'database']):
                    agent_type = AgentType.DATA_WRITER
                
                current_step = PlanStep(
                    step_id=step_id,
                    description=description,
                    agent_type=agent_type,
                    dependencies=[]
                )
                
                steps.append(current_step)
        
        # If no steps parsed, create a default single step
        if not steps:
            logger.warning("no_steps_parsed_creating_default")
            steps.append(PlanStep(
                step_id="step_default",
                description="Execute the complete task",
                agent_type=AgentType.EXECUTOR,
                dependencies=[]
            ))
        
        return steps
    
    def _build_dag(self, steps: list[PlanStep]) -> Dict[str, list[str]]:
        """Build a DAG from steps.
        
        Args:
            steps: List of plan steps
            
        Returns:
            Dictionary mapping step_id to list of dependency step_ids
        """
        dag = {}
        
        for i, step in enumerate(steps):
            # If dependencies not explicitly set, make sequential
            if not step.dependencies and i > 0:
                step.dependencies = [steps[i-1].step_id]
            
            dag[step.step_id] = step.dependencies
        
        return dag
    
    def _validate_dag(self, dag: Dict[str, list[str]]) -> bool:
        """Check if DAG has no cycles.
        
        Args:
            dag: DAG to validate
            
        Returns:
            True if valid (acyclic), False otherwise
        """
        try:
            G = nx.DiGraph()
            for node, deps in dag.items():
                G.add_node(node)
                for dep in deps:
                    G.add_edge(dep, node)
            
            # Check for cycles
            return nx.is_directed_acyclic_graph(G)
        
        except Exception as e:
            logger.error("dag_validation_error", error=str(e))
            return False
    
    def _fix_dag_cycles(self, dag: Dict[str, list[str]]) -> Dict[str, list[str]]:
        """Remove cycles from DAG.
        
        Args:
            dag: DAG with potential cycles
            
        Returns:
            Acyclic DAG
        """
        # Simple fix: make it sequential
        nodes = list(dag.keys())
        fixed_dag = {}
        
        for i, node in enumerate(nodes):
            if i == 0:
                fixed_dag[node] = []
            else:
                fixed_dag[node] = [nodes[i-1]]
        
        return fixed_dag
