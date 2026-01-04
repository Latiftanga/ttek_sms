#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== TTEK SMS Deployment Script ===${NC}"

# Check if .env.prod exists
if [ ! -f .env.prod ]; then
    echo -e "${RED}Error: .env.prod file not found!${NC}"
    echo "Copy .env.prod.example to .env.prod and configure it first."
    exit 1
fi

# Pull latest code
echo -e "${YELLOW}Pulling latest code...${NC}"
git pull origin main

# Build and restart containers
echo -e "${YELLOW}Building and starting containers...${NC}"
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# Wait for database to be ready
echo -e "${YELLOW}Waiting for database...${NC}"
sleep 10

# Run migrations
echo -e "${YELLOW}Running migrations...${NC}"
docker compose -f docker-compose.prod.yml exec -T web python manage.py migrate_schemas --shared
docker compose -f docker-compose.prod.yml exec -T web python manage.py migrate_schemas --tenant

# Collect static files (in case of changes)
echo -e "${YELLOW}Collecting static files...${NC}"
docker compose -f docker-compose.prod.yml exec -T web python manage.py collectstatic --noinput

# Clean up old images
echo -e "${YELLOW}Cleaning up old Docker images...${NC}"
docker image prune -f

echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo "Useful commands:"
echo "  View logs:     docker compose -f docker-compose.prod.yml logs -f"
echo "  View web logs: docker compose -f docker-compose.prod.yml logs -f web"
echo "  Restart:       docker compose -f docker-compose.prod.yml restart"
echo "  Stop:          docker compose -f docker-compose.prod.yml down"
