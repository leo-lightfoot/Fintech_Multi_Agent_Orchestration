"""Domain Expert agent for specialized knowledge."""
from typing import Dict, Any, Optional, List
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from src.utils.logging import get_logger

logger = get_logger(__name__)


class DomainExpert:
    """Domain expert agent that provides specialized knowledge on-demand."""
    
    # Domain expertise mappings
    DOMAINS = {
        "software": {
            "keywords": ["code", "api", "database", "architecture", "software"],
            "prompt": """You are a Software Architecture expert with deep knowledge of:
- Design patterns and best practices
- API design and microservices
- Database design and optimization
- Security and scalability
- Modern frameworks and tools"""
        },
        "data": {
            "keywords": ["data", "analytics", "ml", "ai", "machine learning", "statistics"],
            "prompt": """You are a Data Science and Analytics expert with deep knowledge of:
- Data pipelines and ETL
- Machine learning models and algorithms
- Statistical analysis
- Data visualization
- Big data technologies"""
        },
        "devops": {
            "keywords": ["deploy", "docker", "kubernetes", "ci/cd", "infrastructure"],
            "prompt": """You are a DevOps and Infrastructure expert with deep knowledge of:
- Container orchestration (Docker, Kubernetes)
- CI/CD pipelines
- Cloud platforms (AWS, GCP, Azure)
- Infrastructure as Code
- Monitoring and observability"""
        },
        "security": {
            "keywords": ["security", "auth", "encryption", "vulnerability"],
            "prompt": """You are a Security expert with deep knowledge of:
- Application security best practices
- Authentication and authorization
- Encryption and cryptography
- Common vulnerabilities (OWASP)
- Security testing and auditing"""
        }
    }
    
    def __init__(self, llm: ChatOpenAI):
        """Initialize the domain expert.
        
        Args:
            llm: Language model instance
        """
        self.llm = llm
    
    async def provide_insights(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Provide domain-specific insights for a task.
        
        Args:
            task: Task description
            context: Additional context
            
        Returns:
            List of insights and recommendations
        """
        logger.info("providing_expert_insights", task_length=len(task))
        
        # Determine relevant domain(s)
        domains = self._identify_domains(task)
        
        if not domains:
            domains = ["software"]  # Default domain
        
        logger.info("domains_identified", domains=domains)
        
        insights = []
        
        # Get insights from each relevant domain
        for domain in domains:
            domain_config = self.DOMAINS.get(domain)
            if domain_config:
                domain_insights = await self._get_domain_insights(
                    domain_config,
                    task,
                    context
                )
                insights.extend(domain_insights)
        
        logger.info("insights_provided", num_insights=len(insights))
        
        return insights
    
    def _identify_domains(self, task: str) -> List[str]:
        """Identify relevant domains based on task content.
        
        Args:
            task: Task description
            
        Returns:
            List of relevant domain identifiers
        """
        task_lower = task.lower()
        relevant_domains = []
        
        for domain_id, domain_config in self.DOMAINS.items():
            keywords = domain_config.get("keywords", [])
            if any(keyword in task_lower for keyword in keywords):
                relevant_domains.append(domain_id)
        
        return relevant_domains
    
    async def _get_domain_insights(
        self,
        domain_config: Dict[str, Any],
        task: str,
        context: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Get insights from a specific domain expert.
        
        Args:
            domain_config: Domain configuration
            task: Task description
            context: Additional context
            
        Returns:
            List of insights
        """
        context_str = ""
        if context:
            context_str = f"\n\nContext: {context}"
        
        messages = [
            SystemMessage(content=domain_config["prompt"]),
            HumanMessage(content=f"""Task: {task}{context_str}

Provide expert insights and recommendations for this task. Focus on:
1. Best practices specific to this domain
2. Potential pitfalls to avoid
3. Recommended approaches or technologies
4. Critical considerations

Provide 3-5 key insights as a bulleted list.""")
        ]
        
        response = await self.llm.ainvoke(messages)
        insights_text = response.content
        
        # Parse into list
        insights = []
        for line in insights_text.split('\n'):
            line = line.strip()
            if line and (line.startswith('-') or line.startswith('*') or line.startswith('•')):
                insights.append(line[1:].strip())
        
        return insights
