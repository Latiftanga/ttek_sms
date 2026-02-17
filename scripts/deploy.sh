#!/bin/bash
# =============================================================================
# TTEK SMS - Production Deployment Script
# =============================================================================
# Safe deployment for multi-tenant schools (behind Cloudflare).
#
# Usage:   ./scripts/deploy.sh
# Rollback:
#   cp nginx/conf.d/default.conf.bak nginx/conf.d/default.conf
#   docker compose -f docker-compose.prod.yml up -d
# =============================================================================

set -e

COMPOSE="docker compose -f docker-compose.prod.yml"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

# ---- Pre-flight checks ----
log "=== Step 1/7: Pre-flight checks ==="

[ -f "docker-compose.prod.yml" ] || fail "Run from project root (where docker-compose.prod.yml is)"
[ -f ".env.prod" ] || fail ".env.prod not found. Copy .env.prod.example and configure it."

$COMPOSE ps --format "table {{.Name}}\t{{.Status}}" || fail "Cannot reach Docker"
echo ""

# ---- Backup ----
log "=== Step 2/7: Backup database and nginx config ==="

mkdir -p backups
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Source DB credentials from .env.prod
PGUSER=$(grep -E '^POSTGRES_USER=' .env.prod | cut -d= -f2)
PGDB=$(grep -E '^POSTGRES_DB=' .env.prod | cut -d= -f2)

if [ -n "$PGUSER" ] && [ -n "$PGDB" ]; then
    log "Backing up database..."
    $COMPOSE exec -T db pg_dump -U "$PGUSER" "$PGDB" | gzip > "backups/pre_deploy_${TIMESTAMP}.sql.gz" \
        && log "Database backed up: backups/pre_deploy_${TIMESTAMP}.sql.gz" \
        || warn "Database backup failed — continuing (backup service runs daily)"
else
    warn "Could not read DB credentials from .env.prod — skipping DB backup"
fi

# Backup current active nginx config (the SSL one on the server)
cp nginx/conf.d/default.conf nginx/conf.d/default.conf.bak
log "Nginx config backed up to default.conf.bak"

# ---- Pull latest code ----
log "=== Step 3/7: Pull latest code ==="

git pull origin main
log "Code pulled"

# ---- Restore SSL nginx config ----
log "=== Step 4/7: Preserve SSL nginx config ==="

# CRITICAL: git pull overwrites default.conf with the HTTP-only version from git.
# The SSL version is maintained in default.conf.ssl — copy it as the active config.
cp nginx/conf.d/default.conf.ssl nginx/conf.d/default.conf
log "SSL config applied from default.conf.ssl"

# ---- Build new image ----
log "=== Step 5/7: Build new image ==="

# Build once — web tags ttek_sms:latest, celery/celery-beat reuse it
$COMPOSE build web
log "Image built: ttek_sms:latest"

# ---- Rolling restart ----
log "=== Step 6/7: Rolling restart (services stay up during transition) ==="

# 1. Web first — entrypoint runs migrations + collectstatic automatically
log "Restarting web (runs migrations + collectstatic via entrypoint)..."
$COMPOSE up -d web

# 2. Wait for web healthcheck
log "Waiting for web to be healthy..."
TIMEOUT=90
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$($COMPOSE ps web --format "{{.Status}}" 2>/dev/null)
    if echo "$STATUS" | grep -q "(healthy)"; then
        log "Web is healthy!"
        break
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    echo "  ... waiting ($ELAPSED/${TIMEOUT}s) — $STATUS"
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    warn "Web not healthy after ${TIMEOUT}s. Checking logs..."
    $COMPOSE logs web --tail=20
    fail "Deploy halted. Fix the issue, or rollback with: cp nginx/conf.d/default.conf.bak nginx/conf.d/default.conf && $COMPOSE up -d"
fi

# 3. Celery and beat — depend on web healthy
log "Restarting celery and celery-beat..."
$COMPOSE up -d celery celery-beat

# 4. Nginx last — depends on web healthy
log "Restarting nginx..."
$COMPOSE up -d nginx

# 5. Stop old certbot if it was running (now disabled via profiles)
$COMPOSE rm -sf certbot 2>/dev/null || true

# ---- Verify ----
log "=== Step 7/7: Verify all services ==="

sleep 5
echo ""
$COMPOSE ps --format "table {{.Name}}\t{{.Status}}"
echo ""

# Check each tenant responds via Cloudflare
DOMAINS=("ttek-sms.com" "uniqamass.ttek-sms.com" "willigif.ttek-sms.com")
ALL_OK=true

for domain in "${DOMAINS[@]}"; do
    HTTP_CODE=$(curl -so /dev/null -w "%{http_code}" --max-time 10 "https://$domain" 2>/dev/null)
    if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 400 ]; then
        log "$domain — OK ($HTTP_CODE)"
    else
        warn "$domain — HTTP $HTTP_CODE"
        ALL_OK=false
    fi
done

echo ""
if [ "$ALL_OK" = true ]; then
    log "=== Deployment successful! All schools responding. ==="
else
    warn "=== Some sites may have issues. Check: ==="
    echo "  $COMPOSE logs web --tail=30"
    echo "  $COMPOSE logs nginx --tail=30"
fi

# Clean up unused Docker images
docker image prune -f 2>/dev/null || true

echo ""
echo "Useful commands:"
echo "  View logs:     $COMPOSE logs -f"
echo "  View web logs: $COMPOSE logs -f web"
echo "  Restart:       $COMPOSE restart"
echo "  Rollback:      cp nginx/conf.d/default.conf.bak nginx/conf.d/default.conf && $COMPOSE up -d"
