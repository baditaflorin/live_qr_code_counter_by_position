#!/bin/bash
# Production deployment script for AprilTag detector with tunable configuration
# Run this on the production server at /opt/live_qr_wemeshup_com/

set -e

echo "🚀 Deploying AprilTag detector with runtime-tunable configuration..."

# Navigate to production directory
cd /opt/live_qr_wemeshup_com || exit 1

# Pull latest code from GitHub
echo "📥 Pulling latest code from GitHub..."
git fetch origin claude/hopeful-vaughan-9ad5f6
git checkout claude/hopeful-vaughan-9ad5f6
git pull origin claude/hopeful-vaughan-9ad5f6

# Show what's being deployed
echo ""
echo "📋 Recent commits:"
git log --oneline -5

echo ""
echo "🏗️  Rebuilding Docker container..."
docker compose -f docker-compose.prod.yml build --no-cache

echo ""
echo "🛑 Stopping current container..."
docker compose -f docker-compose.prod.yml down

echo ""
echo "🚀 Starting updated container..."
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "⏳ Waiting for container to be ready..."
sleep 5

# Check container status
if docker compose -f docker-compose.prod.yml ps | grep -q "live-qr-wemeshup"; then
    echo "✅ Container is running!"
else
    echo "❌ Container failed to start!"
    docker compose -f docker-compose.prod.yml logs
    exit 1
fi

echo ""
echo "✨ Deployment complete!"
echo ""
echo "📊 Test the new detector configuration endpoints:"
echo ""
echo "1. Get current config:"
echo "   curl http://10.10.10.20:18050/api/admin/detector/config"
echo ""
echo "2. Change to accurate mode (slower but detects distant markers):"
echo "   curl -X POST http://10.10.10.20:18050/api/admin/detector/config \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"apriltag\": {\"quad_decimate\": 2.0, \"refine_edges\": true}}'"
echo ""
echo "3. Change to fast mode (faster but misses distant markers):"
echo "   curl -X POST http://10.10.10.20:18050/api/admin/detector/config \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"apriltag\": {\"quad_decimate\": 6.0, \"refine_edges\": false}}'"
echo ""
echo "4. Switch to ArUco detector:"
echo "   curl -X POST http://10.10.10.20:18050/api/admin/detector/config \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"detector_type\": \"aruco\"}'"
echo ""
echo "📖 See DETECTOR_CONFIG_GUIDE.md for full documentation"
