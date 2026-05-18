"""Data Writer agent for persisting data."""
from typing import Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
import json
from pathlib import Path

from src.utils.logging import get_logger

logger = get_logger(__name__)


class DataWriter:
    """Agent responsible for writing and persisting data."""
    
    SYSTEM_PROMPT = """You are a data writing agent responsible for persisting information.

Your job is to:
1. Structure data appropriately for storage
2. Choose appropriate format (JSON, text, etc.)
3. Ensure data integrity
4. Provide confirmation of what was written

When writing data:
- Use clear, consistent formatting
- Include relevant metadata
- Ensure data is valid and complete
"""
    
    def __init__(self, llm: ChatOpenAI):
        """Initialize the data writer.
        
        Args:
            llm: Language model instance
        """
        self.llm = llm
        self.data_dir = Path("/tmp/multi_agent_data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    async def write(
        self,
        task: str,
        dependencies: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Write data according to the task.
        
        Args:
            task: Description of what to write
            dependencies: Data from previous steps
            context: Additional context
            
        Returns:
            Write confirmation with path and metadata
        """
        logger.info("data_write_task", task=task)
        
        # Use LLM to determine what to write
        dep_text = ""
        if dependencies:
            dep_text = "\n\nData to write:\n" + json.dumps(dependencies, indent=2)
        
        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=f"""Task: {task}{dep_text}

Determine what data should be written and in what format. 
Respond with a JSON object containing:
- filename: suggested filename
- content: the data to write
- format: file format (json, txt, etc.)
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        response_text = response.content
        
        # For now, write dependencies as JSON
        # In production, parse LLM response more carefully
        filename = f"data_{hash(task)}.json"
        filepath = self.data_dir / filename
        
        data_to_write = {
            "task": task,
            "dependencies": dependencies,
            "context": context
        }
        
        # Write the file
        with open(filepath, 'w') as f:
            json.dump(data_to_write, f, indent=2, default=str)
        
        logger.info("data_written", filepath=str(filepath), size=filepath.stat().st_size)
        
        return {
            "status": "written",
            "filepath": str(filepath),
            "filename": filename,
            "format": "json",
            "size_bytes": filepath.stat().st_size
        }
