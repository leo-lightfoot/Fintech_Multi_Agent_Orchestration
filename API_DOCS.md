# API Documentation

Base URL: `http://localhost:8000`

---

## Authentication

Optional for this learning project. Include a Bearer token if you have one:

```
Authorization: Bearer <token>
```

Get a token (no password required in dev mode):

```bash
curl -X POST "http://localhost:8000/api/auth/token?user_id=alice"
```

Response:
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "session_id": "<uuid>"
}
```

---

## Rate Limits

| Endpoint group | Limit |
|---|---|
| POST /api/task | 20 requests/minute per IP |
| GET /api/task, /api/session, /api/audit | 100 requests/minute per IP |
| POST /api/auth/token | 10 requests/minute per IP |

Exceeding a limit returns HTTP 429.

---

## Endpoints

### Health check

**GET** `/health`

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "redis_connected": true,
  "timestamp": "2026-01-30T12:00:00Z"
}
```

---

### Submit a task

**POST** `/api/task`

```bash
curl -X POST http://localhost:8000/api/task \
  -H "Content-Type: application/json" \
  -d '{"task": "What are the current NAV values for all funds?"}'
```

Request body:

```json
{
  "task": "string (required)",
  "session_id": "string (optional -- omit to start a new session)",
  "context": {"key": "value"},
  "user_id": "string (optional)"
}
```

Response:

```json
{
  "task_id": "<uuid>",
  "session_id": "<uuid>",
  "status": "submitted",
  "message": "Task submitted successfully and is being processed"
}
```

---

### Poll task status

**GET** `/api/task/{task_id}`

```bash
curl http://localhost:8000/api/task/<task_id>
```

Response:

```json
{
  "task_id": "<uuid>",
  "status": "completed",
  "phase": "completed",
  "progress": 1.0,
  "intent": "data_query",
  "agents_selected": ["data"],
  "result": "## Results\n\n...",
  "error": null,
  "created_at": "2026-01-30T12:00:00Z",
  "updated_at": "2026-01-30T12:00:05Z"
}
```

Status values:

| Value | Meaning |
|---|---|
| submitted | Task received, queued |
| supervising | Supervisor classifying intent |
| executing | Specialist agents running |
| validating | Validator checking output |
| retrying | Validation failed, one retry in progress |
| completed | Done, result available |
| failed | Could not complete |

---

### Session history

**GET** `/api/session/{session_id}`

```bash
curl http://localhost:8000/api/session/<session_id>
```

```json
{
  "session_id": "<uuid>",
  "task_count": 3,
  "history": [
    {
      "task_id": "<uuid>",
      "task": "What is the NAV for fund F001?",
      "status": "completed",
      "intent": "data_query",
      "agents": ["data"],
      "result": "...",
      "completed_at": "2026-01-30T12:00:05Z"
    }
  ]
}
```

---

### Audit log

**GET** `/api/audit/{session_id}?limit=100`

Returns the append-only compliance log for a session -- every agent action.

```bash
curl http://localhost:8000/api/audit/<session_id>
```

```json
{
  "session_id": "<uuid>",
  "count": 2,
  "entries": [
    {
      "timestamp": "2026-01-30T12:00:03Z",
      "task_id": "<uuid>",
      "session_id": "<uuid>",
      "user_id": "alice",
      "role": "ops",
      "action": "agent_executed",
      "agent": "data",
      "data_accessed": [],
      "status": "success",
      "result_summary": "Found 3 funds with NAV...",
      "cost_usd": 0.0
    }
  ]
}
```

---

## Error responses

| Code | Meaning |
|---|---|
| 400 | Input failed security check |
| 404 | Task or session not found |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

---

## Python client example

```python
import httpx
import asyncio

async def run_task(task: str):
    async with httpx.AsyncClient() as client:
        # Submit
        r = await client.post(
            "http://localhost:8000/api/task",
            json={"task": task}
        )
        data = r.json()
        task_id = data["task_id"]
        session_id = data["session_id"]
        print(f"Submitted: {task_id}")

        # Poll until done
        while True:
            r = await client.get(f"http://localhost:8000/api/task/{task_id}")
            s = r.json()
            print(f"  {s['status']} ({s['progress']*100:.0f}%)")
            if s["status"] in ("completed", "failed"):
                print(s.get("result") or s.get("error"))
                break
            await asyncio.sleep(2)

        # Audit log
        r = await client.get(f"http://localhost:8000/api/audit/{session_id}")
        print(f"Audit entries: {r.json()['count']}")

asyncio.run(run_task("What funds have breached their limits today?"))
```
