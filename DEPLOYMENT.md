# Multi-Agent Orchestrator Deployment Guide

## Production Deployment

### Docker Deployment

1. **Build the Docker image:**

```bash
cd multi-agent-orchestrator
docker build -t multi-agent-orchestrator:latest .
```

2. **Run with Docker Compose:**

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes
  
  orchestrator:
    image: multi-agent-orchestrator:latest
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - API_SECRET_KEY=${API_SECRET_KEY}
    depends_on:
      - redis
    restart: unless-stopped

volumes:
  redis-data:
```

```bash
docker-compose up -d
```

### Kubernetes Deployment

1. **Create Kubernetes manifests:**

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: multi-agent-orchestrator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orchestrator
  template:
    metadata:
      labels:
        app: orchestrator
    spec:
      containers:
      - name: orchestrator
        image: multi-agent-orchestrator:latest
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_URL
          value: "redis://redis-service:6379/0"
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: orchestrator-secrets
              key: openai-api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
---
apiVersion: v1
kind: Service
metadata:
  name: orchestrator-service
spec:
  selector:
    app: orchestrator
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

2. **Deploy to Kubernetes:**

```bash
kubectl apply -f k8s/
```

### Environment Variables

Required:
- `OPENAI_API_KEY`: Your OpenAI API key
- `API_SECRET_KEY`: Secret key for JWT tokens
- `REDIS_URL`: Redis connection string

Optional:
- `MAX_ITERATIONS`: Maximum retry attempts (default: 3)
- `BUDGET_LIMIT_USD`: Maximum cost per task (default: 10.0)
- `CODE_EXECUTION_TIMEOUT`: Timeout for code execution (default: 60s)

### Scaling Considerations

1. **Horizontal Scaling:**
   - The API server can be scaled horizontally
   - Use a load balancer to distribute traffic
   - Redis handles state synchronization

2. **Redis Scaling:**
   - Use Redis Cluster for high availability
   - Consider Redis Sentinel for automatic failover
   - Enable Redis persistence (AOF + RDB)

3. **Rate Limiting:**
   - Implement rate limiting at the API gateway
   - Use Redis for distributed rate limiting

### Monitoring

1. **Prometheus Metrics:**
   - Set `PROMETHEUS_ENABLED=true`
   - Metrics available at `:9090/metrics`

2. **Logging:**
   - Structured JSON logs for easy parsing
   - Ship logs to ELK, Datadog, or CloudWatch

3. **Health Checks:**
   - Liveness: `GET /health`
   - Readiness: Check Redis connectivity

### Security

1. **API Security:**
   - Use HTTPS in production
   - Implement rate limiting
   - Enable CORS restrictions
   - Use strong JWT secrets

2. **Code Execution:**
   - Run code in isolated containers
   - Use E2B or Modal for production sandboxing
   - Never execute untrusted code directly

3. **Secrets Management:**
   - Use Kubernetes Secrets or AWS Secrets Manager
   - Never commit secrets to version control
   - Rotate API keys regularly

### Performance Tuning

1. **Redis:**
   - Tune maxmemory and eviction policies
   - Use connection pooling
   - Enable persistence for production

2. **API:**
   - Configure uvicorn workers based on CPU cores
   - Use gunicorn for production
   - Enable HTTP/2 if supported

3. **LLM Calls:**
   - Implement caching for repeated queries
   - Use streaming for long responses
   - Monitor token usage and costs

## Cloud-Specific Deployments

### AWS ECS

```bash
# Create task definition
aws ecs register-task-definition --cli-input-json file://ecs-task-def.json

# Create service
aws ecs create-service --cluster my-cluster --service-name orchestrator --task-definition orchestrator:1 --desired-count 3
```

### Google Cloud Run

```bash
# Build and push
gcloud builds submit --tag gcr.io/PROJECT_ID/orchestrator

# Deploy
gcloud run deploy orchestrator --image gcr.io/PROJECT_ID/orchestrator --platform managed
```

### Azure Container Instances

```bash
az container create --resource-group myResourceGroup --name orchestrator --image orchestrator:latest --cpu 2 --memory 4
```

## Backup and Recovery

1. **Redis Backups:**
   - Enable AOF persistence
   - Regular RDB snapshots
   - Backup to S3 or cloud storage

2. **State Recovery:**
   - Use the RecoveryManager to resume interrupted tasks
   - Checkpoints saved automatically at each phase

3. **Disaster Recovery:**
   - Multi-region Redis replication
   - Regular database backups
   - Documented recovery procedures
