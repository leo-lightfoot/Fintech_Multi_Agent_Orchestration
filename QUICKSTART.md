# Quick Start Guide

## Prerequisites

- Python 3.11+
- Redis server (or Docker)
- OpenAI API key

## Installation

### Option 1: Quick Start (Recommended)

```bash
cd multi-agent-orchestrator

# Make startup script executable
chmod +x start.sh

# Copy environment template
cp .env.example .env

# Edit .env and add your OPENAI_API_KEY
nano .env  # or your preferred editor

# Run the startup script
./start.sh
```

### Option 2: Docker Compose

```bash
cd multi-agent-orchestrator

# Set your API key
export OPENAI_API_KEY=sk-your-key-here
export API_SECRET_KEY=your-secret-key

# Start everything
docker-compose up -d

# View logs
docker-compose logs -f
```

### Option 3: Manual Setup

```bash
# Install Redis
brew install redis  # macOS
# or
sudo apt-get install redis  # Ubuntu

# Start Redis
redis-server

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your API key

# Run the server
python -m uvicorn src.gateway.api:app --reload
```

## Testing

Once running, visit:
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

### Submit a Test Task

```bash
curl -X POST http://localhost:8000/api/task \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Create a simple Python function to calculate fibonacci numbers",
    "context": {"language": "python"}
  }'
```

This will return a `task_id`. Check status with:

```bash
curl http://localhost:8000/api/task/<task_id>
```

## Architecture Overview

The system processes tasks through multiple phases:

1. **Planning Phase** (Blue agents)
   - Pre-Planner creates execution plan
   - Plan Refiner optimizes for parallelization

2. **Execution Phase** (Green agents)
   - Executor runs tasks in parallel where possible
   - Code Executor runs code in sandbox
   - Data Writer persists results

3. **Validation Phase** (Orange agents - Critics)
   - Quality Critic checks correctness
   - Security Critic reviews security
   - Architecture Critic evaluates design
   - Any rejection triggers retry loop

4. **Finalization**
   - Domain Experts provide insights
   - Summarizer condenses results
   - Responder formats final output

## Configuration

Edit `.env` to customize:

- `MAX_ITERATIONS=3` - Maximum retry attempts
- `BUDGET_LIMIT_USD=10.0` - Cost limit per task
- `CODE_EXECUTION_TIMEOUT=60` - Sandbox timeout
- `MAX_CONCURRENT_SESSIONS=100` - Session limit

## Development

Run tests:
```bash
pytest tests/ -v
```

Format code:
```bash
black src/
ruff check src/ --fix
```

## Next Steps

- See [API_DOCS.md](API_DOCS.md) for API reference
- See [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment
- Check examples in the README

## Troubleshooting

**Redis connection failed:**
```bash
# Check Redis is running
redis-cli ping

# Or use Docker
docker run -d -p 6379:6379 redis:7-alpine
```

**Import errors:**
```bash
# Ensure you're in virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

**Port already in use:**
```bash
# Use different port
uvicorn src.gateway.api:app --port 8001
```
