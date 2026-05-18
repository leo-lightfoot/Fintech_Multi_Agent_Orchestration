# Multi-Agent Orchestration System

A production-ready multi-agent orchestration platform with planning, execution, and validation phases. Built with LangGraph, FastAPI, and Redis.

## Architecture

```
[User Input]
      ↓
[User Proxy / Gateway]  ← Handles session, auth, input sanitization
      ↓
[Coordinator / Orchestrator]  ← Central FSM brain (LangGraph state machine)
      │
      ├─► Defines goals, acceptance criteria, & spawns dynamic teams
      │
      ▼
[Planning Phase]                  [Execution Phase]                  [Validation Phase]
(Blue agents)                     (Green agents)                     (Orange agents – Rivals!)
  ↓                                 ↓                                  ↓
Pre-Planner → Plan Refiner        Executors → Data Writers           Critics (multiple levels)
  │   Generate DAG / steps          │   Write & submit code/tasks      │   Review outputs
  │                                 │   → Remote Code Executor          │   → Veto / Reject → Retry loop
  └─────────────────────────────────┼────────────────────────────────────┘
                                    │
                                    ▼
                          [Domain Experts / SMEs]  ← Provide specialized knowledge on-demand
                                    │
                                    ▼
                          [Summarizers]  ← Clean & condense results
                                    │
                                    ▼
                          [Responders]  ← Format final output
                                    │
                                    ▼
[User Proxy / Gateway]  → Clean, audited response to user
      ↑
[Session Recovery / Memory]  ← Persists state across interruptions
```

## Features

- 🧠 **LangGraph FSM**: Sophisticated state machine for agent coordination
- 🔒 **Security First**: Input sanitization, auth, and sandboxed code execution
- 🔄 **Retry Logic**: Multi-level critics with veto power and automatic retries
- 💾 **State Persistence**: Redis-backed session recovery for production reliability
- 📊 **DAG Planning**: Parallel task execution where dependencies allow
- 🎯 **Cost Control**: Budget limits and iteration caps prevent runaway costs
- 📝 **Context Management**: Automatic summarization prevents context pollution

## Quick Start

### Prerequisites

- Python 3.11+
- Redis server
- OpenAI API key (or compatible LLM provider)

### Installation

```bash
# Clone the repository
cd multi-agent-orchestrator

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your API keys and configuration

# Start Redis (if not already running)
redis-server

# Run the server
python -m uvicorn src.gateway.api:app --reload
```

### Usage

```bash
# Submit a task
curl -X POST http://localhost:8000/api/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Build a REST API for user management with authentication",
    "session_id": "user-123"
  }'

# Check task status
curl http://localhost:8000/api/task/{task_id}

# Get session history
curl http://localhost:8000/api/session/{session_id}
```

## Project Structure

```
multi-agent-orchestrator/
├── src/
│   ├── gateway/           # User Proxy & API
│   │   ├── api.py
│   │   ├── auth.py
│   │   └── sanitizer.py
│   ├── orchestrator/      # Coordinator & FSM
│   │   ├── coordinator.py
│   │   ├── state.py
│   │   └── graph.py
│   ├── agents/
│   │   ├── planning/      # Blue agents
│   │   │   ├── pre_planner.py
│   │   │   └── plan_refiner.py
│   │   ├── execution/     # Green agents
│   │   │   ├── executor.py
│   │   │   ├── data_writer.py
│   │   │   └── code_executor.py
│   │   ├── validation/    # Orange agents (Rivals)
│   │   │   └── critics.py
│   │   ├── experts/       # Domain SMEs
│   │   │   └── domain_expert.py
│   │   ├── summarizers/
│   │   │   └── summarizer.py
│   │   └── responders/
│   │       └── responder.py
│   ├── memory/            # Session & State
│   │   ├── redis_store.py
│   │   └── recovery.py
│   └── utils/
│       ├── config.py
│       └── logging.py
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

## Configuration

See `.env.example` for all configuration options:

- `OPENAI_API_KEY`: Your LLM provider API key
- `REDIS_URL`: Redis connection string
- `MAX_ITERATIONS`: Maximum retry loops (default: 3)
- `BUDGET_LIMIT`: Maximum cost per task
- `CODE_EXECUTION_TIMEOUT`: Sandbox timeout in seconds

## Development

```bash
# Run tests
pytest

# Format code
black src/
ruff check src/ --fix

# Type checking
mypy src/
```

## Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for:
- Docker containerization
- Kubernetes deployment
- Scaling strategies
- Monitoring setup

## License

MIT
