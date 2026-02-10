#!/bin/bash
# JAIBird Deploy Script
# Run this on the Pi to pull latest code and restart services.
# Usage: ./deploy.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  JAIBird Deploy"
echo "=========================================="

# Pull latest code
echo "Pulling latest code..."
git pull

# Rebuild and restart containers
echo "Rebuilding containers..."
docker compose build

echo "Restarting services..."
docker compose up -d

echo ""
echo "=========================================="
echo "  Deploy complete!"
echo "=========================================="
docker compose ps
echo ""
echo "View logs: docker compose logs -f"
echo "=========================================="
