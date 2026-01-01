#!/bin/bash
# TTEK SMS Deployment Script
# Usage: ./scripts/deploy.sh

set -e

echo "=========================================="
echo "  TTEK SMS Deployment"
echo "=========================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "docker-compose.prod.yml" ]; then
    echo "Error: docker-compose.prod.yml not found. Run this from the project root."
    exit 1
fi

# Check if .env.prod exists
if [ ! -f ".env.prod" ]; then
    echo "Error: .env.prod not found. Copy .env.prod.example and configure it."
    exit 1
fi

echo -e "${YELLOW}Step 1: Pulling latest code...${NC}"
git pull origin main

echo -e "${YELLOW}Step 2: Building Docker images...${NC}"
docker compose -f docker-compose.prod.yml build

echo -e "${YELLOW}Step 3: Running database migrations...${NC}"
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate_schemas --shared
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate_schemas --tenant

echo -e "${YELLOW}Step 4: Collecting static files...${NC}"
docker compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput

echo -e "${YELLOW}Step 5: Restarting services...${NC}"
docker compose -f docker-compose.prod.yml up -d

echo -e "${YELLOW}Step 6: Cleaning up old images...${NC}"
docker image prune -f

echo ""
echo -e "${GREEN}=========================================="
echo "  Deployment Complete!"
echo "==========================================${NC}"
echo ""
echo "Check status: docker compose -f docker-compose.prod.yml ps"
echo "View logs:    docker compose -f docker-compose.prod.yml logs -f web"
