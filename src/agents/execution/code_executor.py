"""Code Executor agent for running code in a sandbox."""
from typing import Dict, Any, Optional
import asyncio
import subprocess
import tempfile
import os
from pathlib import Path

from src.utils.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class CodeExecutor:
    """Agent responsible for executing code safely in a sandbox."""
    
    def __init__(self):
        """Initialize the code executor."""
        self.timeout = settings.code_execution_timeout
        self.enabled = settings.enable_code_execution
    
    async def execute(
        self,
        task: str,
        dependencies: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute code according to the task.
        
        Args:
            task: Description of code to execute
            dependencies: Data from previous steps
            context: Additional context
            
        Returns:
            Execution result with output and status
        """
        if not self.enabled:
            logger.warning("code_execution_disabled")
            return {
                "status": "disabled",
                "message": "Code execution is disabled in configuration"
            }
        
        logger.info("code_execution_task", task=task)
        
        # For demo purposes, execute simple Python code
        # In production, use E2B, Modal, or Docker for sandboxing
        
        # Extract or generate code (simplified)
        code = self._extract_code_from_task(task, dependencies)
        
        if not code:
            return {
                "status": "error",
                "message": "No code to execute"
            }
        
        # Execute in sandbox
        result = await self._execute_python_sandbox(code)
        
        logger.info(
            "code_executed",
            status=result.get("status"),
            output_length=len(result.get("output", ""))
        )
        
        return result
    
    def _extract_code_from_task(
        self,
        task: str,
        dependencies: Dict[str, Any]
    ) -> Optional[str]:
        """Extract executable code from task description.
        
        In production, this would parse markdown code blocks or
        use an LLM to generate code.
        
        Args:
            task: Task description
            dependencies: Previous results
            
        Returns:
            Code string or None
        """
        # Simple extraction - look for code blocks
        if "```python" in task.lower():
            # Extract code block
            parts = task.split("```python")
            if len(parts) > 1:
                code_part = parts[1].split("```")[0]
                return code_part.strip()
        
        # Default: create a simple print statement
        return f'print("Executing task: {task}")'
    
    async def _execute_python_sandbox(self, code: str) -> Dict[str, Any]:
        """Execute Python code in a sandbox.
        
        This is a simplified implementation. In production, use:
        - E2B Code Interpreter
        - Modal Labs sandbox
        - Docker containers with resource limits
        - Firecracker microVMs
        
        Args:
            code: Python code to execute
            
        Returns:
            Execution result
        """
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False
            ) as f:
                f.write(code)
                temp_path = f.name
            
            try:
                # Execute with timeout and resource limits
                # WARNING: This is NOT secure for production!
                # Use proper sandboxing in real applications
                process = await asyncio.create_subprocess_exec(
                    'python3',
                    temp_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    # Set resource limits (Linux only)
                    preexec_fn=self._set_resource_limits if os.name == 'posix' else None
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
                
                return_code = process.returncode
                
                result = {
                    "status": "success" if return_code == 0 else "error",
                    "output": stdout.decode('utf-8', errors='replace'),
                    "error": stderr.decode('utf-8', errors='replace'),
                    "return_code": return_code
                }
                
                logger.info(
                    "sandbox_execution_complete",
                    return_code=return_code,
                    output_length=len(result["output"])
                )
                
                return result
            
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except:
                    pass
        
        except asyncio.TimeoutError:
            logger.warning("code_execution_timeout", timeout=self.timeout)
            return {
                "status": "timeout",
                "error": f"Execution exceeded timeout of {self.timeout}s"
            }
        
        except Exception as e:
            logger.error("code_execution_error", error=str(e), exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _set_resource_limits(self):
        """Set resource limits for subprocess (Linux only)."""
        try:
            import resource
            
            # Limit CPU time to 30 seconds
            resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
            
            # Limit memory to 512MB
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        except:
            pass
