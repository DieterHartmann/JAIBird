#!/bin/bash
# JAIBird First-Time Pi Setup
# Run this once after cloning the repo on your Pi.
# Usage: ./setup-pi.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  JAIBird - First Time Pi Setup"
echo "=========================================="

# Check Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo ""
    echo "Docker installed. You need to log out and back in"
    echo "for group permissions to take effect, then re-run this script."
    exit 0
fi

# Check docker compose is available
if ! docker compose version &> /dev/null; then
    echo "ERROR: docker compose not available."
    echo "Try: sudo apt install docker-compose-plugin"
    exit 1
fi

echo "Docker: OK"

# Check for .env file
if [ ! -f .env ]; then
    echo ""
    echo "ERROR: .env file not found!"
    echo ""
    echo "Copy your .env file to this directory first."
    echo "From your Windows machine, you can use scp:"
    echo ""
    echo "  scp .env dieter@debbi:$(pwd)/.env"
    echo ""
    echo "Or create one from the template:"
    echo "  cp env_template.txt .env"
    echo "  nano .env"
    echo ""
    exit 1
fi

echo ".env file: OK"

# Create data directories
mkdir -p data/sens_pdfs/temp logs
echo "Directories: OK"

# Build and start
echo ""
echo "Building Docker image (this may take a few minutes on first run)..."
docker compose build

echo ""
echo "Starting JAIBird services..."
docker compose up -d

echo ""
echo "=========================================="
echo "  Setup complete!"
echo "=========================================="
echo ""
docker compose ps
echo ""
echo "JAIBird web interface: http://$(hostname -I | awk '{print $1}'):5055"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f          # View live logs"
echo "  docker compose logs scheduler   # Scheduler logs only"
echo "  docker compose restart          # Restart services"
echo "  docker compose down             # Stop services"
echo "  ./deploy.sh                     # Pull updates & restart"
echo "=========================================="
