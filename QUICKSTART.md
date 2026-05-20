# Quick Start

## Prerequisites

- Python 3.11+
- Redis server
- Anthropic API key (or OpenAI / Azure OpenAI)

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and edit the environment file
cp .env.example .env
# Set LLM_API_KEY to your Anthropic key (minimum required)

# 3. Ingest sample documents into the vector store (one-time)
python scripts/ingest_docs.py

# 4. Start Redis
redis-server

# 5. Run the API
python -m uvicorn src.gateway.api:app --reload
```

The API is now available at http://localhost:8000.
Interactive docs: http://localhost:8000/docs

## Docker

```bash
export LLM_API_KEY=your-key-here
docker-compose up -d
```

## Submitting a task

```bash
# Submit
curl -X POST http://localhost:8000/api/task \
  -H "Content-Type: application/json" \
  -d '{"task": "What funds have breached their limits today?"}'

# Poll for result (use the task_id from the response)
curl http://localhost:8000/api/task/<task_id>
```

## Example tasks to try

```bash
# Data query
{"task": "Show me the NAV for all funds as of today"}

# Portfolio analysis
{"task": "Analyse the positions for fund F001 and highlight concentration risk"}

# Risk report
{"task": "Generate a risk report for all funds showing any limit breaches"}

# Document search
{"task": "What is the cash minimum requirement for the Alpha Growth Fund?"}
```

## Configuration

Set these in `.env` (see `.env.example` for the full list):

| Variable | Required | Default | Description |
|---|---|---|---|
| LLM_API_KEY | Yes | -- | Anthropic / OpenAI / Azure key |
| LLM_PROVIDER | No | anthropic | anthropic, openai, azure_openai |
| LLM_MODEL | No | claude-sonnet-4-6 | Model name |
| REDIS_URL | No | redis://localhost:6379/0 | Redis connection |

## Running tests

```bash
pytest tests/ -v
```

## Troubleshooting

**Redis connection failed:**
```bash
redis-cli ping         # should return PONG
docker run -d -p 6379:6379 redis:7-alpine   # or use Docker
```

**Document search returns empty:**
```bash
python scripts/ingest_docs.py   # re-run ingestion
```

**Port already in use:**
```bash
uvicorn src.gateway.api:app --port 8001
```
