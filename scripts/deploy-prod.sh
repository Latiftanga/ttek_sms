#!/bin/bash
# Production Deployment Script for TTEK SMS (Multi-tenant SaaS)
# Hostinger KVM Ubuntu Server

set -e

# Configuration - UPDATE THESE
DOMAIN="ttek-sms.com"
EMAIL="admin@ttek-sms.com"
COMPOSE_FILE="docker-compose.prod.yml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_prereqs() {
    if [ ! -f .env.prod ]; then
        log_error ".env.prod not found! Copy .env.prod.example and configure it."
        exit 1
    fi
    if ! command -v docker &> /dev/null; then
        log_error "Docker not installed!"
        exit 1
    fi
}

# Clean everything
clean_all() {
    log_warn "This will DELETE all containers, volumes, and data!"
    read -p "Type 'yes' to confirm: " confirm
    [ "$confirm" != "yes" ] && echo "Aborted." && exit 0

    log_info "Stopping containers..."
    docker compose -f $COMPOSE_FILE down -v --remove-orphans 2>/dev/null || true

    log_info "Removing volumes..."
    docker volume ls -q | grep ttek_sms | xargs -r docker volume rm 2>/dev/null || true

    log_info "Pruning Docker..."
    docker system prune -af

    log_success "Clean complete!"
}

# Switch nginx configs
use_http() {
    log_info "Switching to HTTP-only config..."
    cp nginx/conf.d/default.conf.initial nginx/conf.d/default.conf
}

use_https() {
    log_info "Switching to HTTPS config..."
    cp nginx/conf.d/default.conf.ssl nginx/conf.d/default.conf
}

# Initial deployment
deploy_initial() {
    echo ""
    log_info "============================================"
    log_info "  TTEK SMS - Initial Deployment"
    log_info "  Domain: $DOMAIN"
    log_info "============================================"
    echo ""

    check_prereqs

    # Step 1: HTTP config first
    use_http

    # Step 2: Build and start
    log_info "Building containers (this takes a few minutes)..."
    docker compose -f $COMPOSE_FILE build --no-cache

    log_info "Starting services..."
    docker compose -f $COMPOSE_FILE up -d

    log_info "Waiting for services to start (45s)..."
    sleep 45

    # Step 3: Check web service
    if ! docker compose -f $COMPOSE_FILE ps | grep -q "web.*Up"; then
        log_error "Web service failed! Logs:"
        docker compose -f $COMPOSE_FILE logs --tail=30 web
        exit 1
    fi
    log_success "Web service running"

    # Step 4: Check nginx
    if ! docker compose -f $COMPOSE_FILE ps | grep -q "nginx.*Up"; then
        log_error "Nginx failed! Logs:"
        docker compose -f $COMPOSE_FILE logs --tail=30 nginx
        exit 1
    fi
    log_success "Nginx running"

    echo ""
    log_success "============================================"
    log_success "  HTTP Deployment Complete!"
    log_success "============================================"
    echo ""
    echo "Site available at: http://$DOMAIN"
    echo ""
    echo "NEXT: Set up SSL certificates"
    echo ""
    echo "For WILDCARD certificate (*.${DOMAIN}) - required for subdomains:"
    echo "  You need DNS challenge. Run:"
    echo ""
    echo "  docker compose -f $COMPOSE_FILE run --rm certbot certonly \\"
    echo "    --manual --preferred-challenges dns \\"
    echo "    -d $DOMAIN -d www.$DOMAIN -d '*.$DOMAIN' \\"
    echo "    --email $EMAIL --agree-tos"
    echo ""
    echo "  (You'll need to add TXT records to your DNS)"
    echo ""
    echo "For BASIC certificate (no wildcard) - main domain only:"
    echo ""
    echo "  docker compose -f $COMPOSE_FILE run --rm certbot certonly \\"
    echo "    --webroot -w /var/www/certbot \\"
    echo "    -d $DOMAIN -d www.$DOMAIN \\"
    echo "    --email $EMAIL --agree-tos"
    echo ""
    echo "After getting certificates, run: $0 enable-ssl"
}

# Enable SSL after certificates obtained
enable_ssl() {
    log_info "Enabling SSL..."

    # Check if certificates exist
    if ! docker compose -f $COMPOSE_FILE run --rm certbot certificates 2>/dev/null | grep -q "$DOMAIN"; then
        log_error "No certificates found for $DOMAIN"
        log_error "Run certbot first. See: $0 help"
        exit 1
    fi

    use_https
    docker compose -f $COMPOSE_FILE restart nginx

    sleep 3

    if docker compose -f $COMPOSE_FILE ps | grep -q "nginx.*Up"; then
        log_success "SSL enabled!"
        echo ""
        echo "Site available at: https://$DOMAIN"
        echo ""
        echo "Update .env.prod: SECURE_SSL_REDIRECT=True"
        echo "Then restart: docker compose -f $COMPOSE_FILE restart web"
    else
        log_error "Nginx failed with SSL config. Reverting..."
        use_http
        docker compose -f $COMPOSE_FILE restart nginx
        exit 1
    fi
}

# Standard update deployment
deploy_update() {
    log_info "============================================"
    log_info "  Updating Deployment"
    log_info "============================================"

    check_prereqs

    [ -d .git ] && git pull origin main

    log_info "Rebuilding and restarting..."
    docker compose -f $COMPOSE_FILE up -d --build

    sleep 15

    if docker compose -f $COMPOSE_FILE ps | grep -q "web.*Up"; then
        log_success "Update complete!"
        docker compose -f $COMPOSE_FILE ps
    else
        log_error "Update failed! Logs:"
        docker compose -f $COMPOSE_FILE logs --tail=30 web
    fi
}

# Status
show_status() {
    echo ""
    log_info "Service Status:"
    docker compose -f $COMPOSE_FILE ps
    echo ""
    log_info "Web Logs (last 15):"
    docker compose -f $COMPOSE_FILE logs --tail=15 web
}

# Logs
show_logs() {
    docker compose -f $COMPOSE_FILE logs -f ${1:-}
}

# Backup
backup_db() {
    mkdir -p backups
    BACKUP="backups/db_$(date +%Y%m%d_%H%M%S).sql"
    log_info "Creating backup: $BACKUP"
    docker compose -f $COMPOSE_FILE exec -T db pg_dumpall -U postgres > $BACKUP
    log_success "Backup saved: $BACKUP"
}

# SSL renewal
renew_ssl() {
    log_info "Renewing SSL certificates..."
    docker compose -f $COMPOSE_FILE run --rm certbot renew
    docker compose -f $COMPOSE_FILE restart nginx
    log_success "Done!"
}

# Django shell
django_shell() {
    docker compose -f $COMPOSE_FILE exec web python manage.py shell
}

# Create superuser
create_superuser() {
    docker compose -f $COMPOSE_FILE exec web python manage.py createsuperuser
}

# Help
show_help() {
    echo "TTEK SMS - Production Deployment Script"
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Deployment:"
    echo "  initial       First-time deployment (HTTP only)"
    echo "  enable-ssl    Enable HTTPS after getting certificates"
    echo "  update        Pull code, rebuild, restart"
    echo "  clean         Remove everything (DESTRUCTIVE)"
    echo ""
    echo "Management:"
    echo "  status        Show service status"
    echo "  logs [svc]    View logs (e.g., logs web, logs nginx)"
    echo "  restart       Restart all services"
    echo "  backup        Backup database"
    echo "  renew-ssl     Renew SSL certificates"
    echo ""
    echo "Django:"
    echo "  shell         Django shell"
    echo "  superuser     Create superuser"
    echo ""
    echo "SSL Setup (after initial deployment):"
    echo ""
    echo "  For wildcard (*.${DOMAIN}) - needed for tenant subdomains:"
    echo "    docker compose -f $COMPOSE_FILE run --rm certbot certonly \\"
    echo "      --manual --preferred-challenges dns \\"
    echo "      -d $DOMAIN -d www.$DOMAIN -d '*.$DOMAIN' \\"
    echo "      --email $EMAIL --agree-tos"
    echo ""
    echo "  Then run: $0 enable-ssl"
}

# Main
case "${1:-help}" in
    initial)     deploy_initial ;;
    enable-ssl)  enable_ssl ;;
    update)      deploy_update ;;
    clean)       clean_all ;;
    status)      show_status ;;
    logs)        show_logs $2 ;;
    restart)     docker compose -f $COMPOSE_FILE restart ;;
    backup)      backup_db ;;
    renew-ssl)   renew_ssl ;;
    shell)       django_shell ;;
    superuser)   create_superuser ;;
    *)           show_help ;;
esac
