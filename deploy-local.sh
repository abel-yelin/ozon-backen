#!/bin/bash
# Quick deployment script for local testing

echo "🚀 Building and starting Python Capability Service..."

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker-compose -f docker-compose.prod.yml down

# Build new image
echo "🔨 Building Docker image..."
docker-compose -f docker-compose.prod.yml build

# Start containers
echo "▶️  Starting containers..."
docker-compose -f docker-compose.prod.yml up -d

# Wait for service to be ready
echo "⏳ Waiting for service to start..."
sleep 5

# Check health
echo "🏥 Checking service health..."
curl -f http://localhost:8000/api/v1/health || echo "❌ Health check failed"

echo ""
echo "✅ Deployment complete!"
echo "📍 API: http://localhost:8000"
echo "📚 Docs: http://localhost:8000/docs"
echo "🏥 Health: http://localhost:8000/api/v1/health"
echo ""
echo "To view logs: docker-compose -f docker-compose.prod.yml logs -f"
echo "To stop: docker-compose -f docker-compose.prod.yml down"
