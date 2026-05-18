#!/bin/bash
# Startup script for Multi-Agent Orchestrator

set -e

echo "🚀 Starting Multi-Agent Orchestrator..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Copying from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your OPENAI_API_KEY"
    exit 1
fi

# Check if Redis is running
if ! command -v redis-cli &> /dev/null; then
    echo "⚠️  Redis CLI not found. Please install Redis or use Docker Compose."
else
    if redis-cli ping &> /dev/null; then
        echo "✅ Redis is running"
    else
        echo "⚠️  Redis is not running. Starting with Docker Compose..."
        docker-compose up -d redis
        sleep 2
    fi
fi

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

echo "📦 Installing dependencies..."
source venv/bin/activate
pip install -q -r requirements.txt

echo "✅ Setup complete!"
echo ""
echo "Starting the orchestrator API..."
echo "API will be available at: http://localhost:8000"
echo "API docs at: http://localhost:8000/docs"
echo ""

# Run the server
python -m uvicorn src.gateway.api:app --reload --host 0.0.0.0 --port 8000
