#!/bin/bash
# Production Deployment Script for TTEK SMS
# Run this on your Hostinger KVM server

set -e

DOMAIN="ttek-sms.com"
EMAIL="admin@ttek-sms.com"  # Change this to your email

echo "=========================================="
echo "TTEK SMS Production Deployment"
echo "=========================================="

# Check if .env.prod exists
if [ ! -f .env.prod ]; then
    echo "❌ Error: .env.prod file not found!"
    echo "   Copy .env.prod.example to .env.prod and configure it first."
    exit 1
fi

# Function to check if SSL certs exist
ssl_certs_exist() {
    docker compose -f docker-compose.prod.yml run --rm nginx test -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem 2>/dev/null
}

case "${1:-deploy}" in
    initial)
        echo ""
        echo "🚀 INITIAL DEPLOYMENT (First time setup)"
        echo "=========================================="

        # Step 1: Use initial nginx config (HTTP only)
        echo "📝 Step 1: Setting up HTTP-only nginx config..."
        cp nginx/conf.d/default.conf nginx/conf.d/default.conf.ssl.backup
        cp nginx/conf.d/default.conf.initial nginx/conf.d/default.conf

        # Step 2: Start services
        echo "🐳 Step 2: Starting services..."
        docker compose -f docker-compose.prod.yml up -d --build

        echo "⏳ Waiting for services to be ready..."
        sleep 10

        # Step 3: Obtain SSL certificates
        echo "🔐 Step 3: Obtaining SSL certificates..."
        echo "   Domain: $DOMAIN"
        echo "   Email: $EMAIL"

        docker compose -f docker-compose.prod.yml run --rm certbot certonly \
            --webroot \
            -w /var/www/certbot \
            -d $DOMAIN \
            -d www.$DOMAIN \
            --email $EMAIL \
            --agree-tos \
            --no-eff-email

        # Note: Wildcard certificates require DNS challenge, not webroot
        echo ""
        echo "⚠️  NOTE: For wildcard certificate (*.${DOMAIN}), you need DNS challenge."
        echo "   Run manually if needed:"
        echo "   docker compose -f docker-compose.prod.yml run --rm certbot certonly --manual --preferred-challenges dns -d *.${DOMAIN}"

        # Step 4: Restore SSL nginx config
        echo "📝 Step 4: Enabling HTTPS nginx config..."
        cp nginx/conf.d/default.conf.ssl.backup nginx/conf.d/default.conf
        rm nginx/conf.d/default.conf.ssl.backup

        # Step 5: Restart nginx
        echo "🔄 Step 5: Restarting nginx with SSL..."
        docker compose -f docker-compose.prod.yml restart nginx

        echo ""
        echo "✅ Initial deployment complete!"
        echo ""
        echo "📋 Next steps:"
        echo "   1. Update .env.prod: Set SECURE_SSL_REDIRECT=True"
        echo "   2. Restart web: docker compose -f docker-compose.prod.yml restart web"
        echo "   3. Create superuser if needed: docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser"
        echo ""
        ;;

    deploy)
        echo ""
        echo "🚀 STANDARD DEPLOYMENT (Update existing)"
        echo "=========================================="

        # Pull latest code (if using git)
        if [ -d .git ]; then
            echo "📥 Pulling latest code..."
            git pull
        fi

        # Build and deploy
        echo "🐳 Building and deploying..."
        docker compose -f docker-compose.prod.yml up -d --build

        echo ""
        echo "✅ Deployment complete!"
        ;;

    restart)
        echo "🔄 Restarting all services..."
        docker compose -f docker-compose.prod.yml restart
        echo "✅ Services restarted!"
        ;;

    logs)
        echo "📜 Showing logs (Ctrl+C to exit)..."
        docker compose -f docker-compose.prod.yml logs -f ${2:-}
        ;;

    status)
        echo "📊 Service Status:"
        docker compose -f docker-compose.prod.yml ps
        ;;

    backup)
        echo "💾 Creating database backup..."
        BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).sql"
        docker compose -f docker-compose.prod.yml exec -T db pg_dump -U $POSTGRES_USER $POSTGRES_DB > "backups/$BACKUP_FILE"
        echo "✅ Backup created: backups/$BACKUP_FILE"
        ;;

    *)
        echo "Usage: $0 {initial|deploy|restart|logs|status|backup}"
        echo ""
        echo "Commands:"
        echo "  initial  - First-time deployment with SSL setup"
        echo "  deploy   - Standard deployment (rebuild and restart)"
        echo "  restart  - Restart all services"
        echo "  logs     - View logs (optionally specify service: logs web)"
        echo "  status   - Show service status"
        echo "  backup   - Create database backup"
        exit 1
        ;;
esac
