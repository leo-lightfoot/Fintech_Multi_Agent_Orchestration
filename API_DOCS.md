# API Documentation

## Multi-Agent Orchestration System API

Base URL: `http://localhost:8000`

### Authentication

Optional for demo purposes. In production, include Bearer token:

```
Authorization: Bearer <token>
```

Get a token:
```bash
curl -X POST http://localhost:8000/api/auth/token \
  -d "user_id=your_user_id"
```

---

## Endpoints

### Health Check

**GET** `/health`

Check API health status.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "redis_connected": true,
  "timestamp": "2026-01-30T12:00:00Z"
}
```

---

### Submit Task

**POST** `/api/task`

Submit a new task for processing.

**Request Body:**
```json
{
  "task": "Build a REST API for user management with authentication",
  "session_id": "optional-session-id",
  "context": {
    "framework": "FastAPI",
    "database": "PostgreSQL"
  },
  "user_id": "optional-user-id"
}
```

**Response:**
```json
{
  "task_id": "uuid-here",
  "session_id": "session-uuid",
  "status": "submitted",
  "message": "Task submitted successfully and is being processed"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Create a Python script to process CSV files",
    "context": {"format": "pandas"}
  }'
```

---

### Get Task Status

**GET** `/api/task/{task_id}`

Get the current status and progress of a task.

**Response:**
```json
{
  "task_id": "uuid-here",
  "status": "executing",
  "phase": "execution",
  "progress": 0.6,
  "result": null,
  "error": null,
  "created_at": "2026-01-30T12:00:00Z",
  "updated_at": "2026-01-30T12:05:00Z"
}
```

**Status Values:**
- `submitted`: Task received
- `planning`: Creating execution plan
- `executing`: Running tasks
- `validating`: Validation in progress
- `summarizing`: Generating summary
- `completed`: Task completed
- `failed`: Task failed
- `retrying`: Retrying after validation failure

**Example:**
```bash
curl http://localhost:8000/api/task/abc-123-def-456
```

---

### Get Session History

**GET** `/api/session/{session_id}`

Retrieve all tasks and history for a session.

**Response:**
```json
{
  "session_id": "session-uuid",
  "task_count": 3,
  "history": [
    {
      "task_id": "uuid-1",
      "task": "Task description",
      "status": "completed",
      "result": "...",
      "completed_at": "2026-01-30T12:00:00Z",
      "timestamp": "2026-01-30T12:00:00Z"
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:8000/api/session/my-session-id
```

---

## Error Responses

**400 Bad Request:**
```json
{
  "detail": "Input rejected due to security concerns: potential_sql_injection"
}
```

**404 Not Found:**
```json
{
  "detail": "Task not found"
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Internal server error"
}
```

---

## Rate Limits

- 100 requests per minute per IP
- 10 concurrent tasks per session

---

## WebSocket Support (Future)

Real-time task progress updates will be available at:
```
ws://localhost:8000/ws/task/{task_id}
```

---

## Examples

### Python Client

```python
import httpx
import asyncio

async def submit_task():
    async with httpx.AsyncClient() as client:
        # Submit task
        response = await client.post(
            "http://localhost:8000/api/task",
            json={
                "task": "Build a user authentication system",
                "context": {
                    "technology": "JWT",
                    "language": "Python"
                }
            }
        )
        
        data = response.json()
        task_id = data["task_id"]
        print(f"Task submitted: {task_id}")
        
        # Poll for completion
        while True:
            status_response = await client.get(
                f"http://localhost:8000/api/task/{task_id}"
            )
            status = status_response.json()
            
            print(f"Progress: {status['progress']*100:.0f}%")
            
            if status["status"] in ["completed", "failed"]:
                print(f"Final result: {status['result']}")
                break
            
            await asyncio.sleep(5)

asyncio.run(submit_task())
```

### JavaScript Client

```javascript
async function submitTask() {
  const response = await fetch('http://localhost:8000/api/task', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      task: 'Create a Node.js Express API',
      context: { database: 'MongoDB' }
    })
  });
  
  const data = await response.json();
  console.log('Task submitted:', data.task_id);
  
  // Poll for status
  const taskId = data.task_id;
  const interval = setInterval(async () => {
    const statusResponse = await fetch(
      `http://localhost:8000/api/task/${taskId}`
    );
    const status = await statusResponse.json();
    
    console.log(`Progress: ${status.progress * 100}%`);
    
    if (['completed', 'failed'].includes(status.status)) {
      console.log('Result:', status.result);
      clearInterval(interval);
    }
  }, 5000);
}
```
