# TTEK SMS - Deployment Guide

Complete step-by-step guides to deploy your multi-tenant Django application.

## Deployment Options

| Platform | Pros | Cons | Cost |
|----------|------|------|------|
| **Fly.io** | Easy, cheap, wildcard SSL included | Ephemeral filesystem | ~$10-15/month |
| **Render.com** | Very easy, managed services | Wildcard needs Team plan ($19) | ~$25/month |
| **Hetzner** | Full control, cheapest, persistent storage | Manual server management | ~$6/month |

---

# Option A: Fly.io Deployment (Recommended - Best Value)

## Table of Contents
1. [Prerequisites](#a1-prerequisites-fly)
2. [Install Fly CLI](#a2-install-fly-cli)
3. [Deploy Application](#a3-deploy-application)
4. [Configure Database & Redis](#a4-configure-database--redis)
5. [Set Environment Variables](#a5-set-environment-variables)
6. [Configure Custom Domain](#a6-configure-custom-domain-fly)
7. [Setup Media Storage](#a7-setup-media-storage-fly)
8. [Maintenance](#a8-maintenance-fly)

---

## A.1 Prerequisites (Fly)

1. A [Fly.io](https://fly.io) account (sign up with GitHub)
2. This repository cloned locally
3. A domain name (for multi-tenancy with subdomains)

---

## A.2 Install Fly CLI

```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh

# Windows (PowerShell)
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"

# Login
fly auth login
```

---

## A.3 Deploy Application

```bash
cd ttek_sms

# First deployment - creates app and resources
fly launch --no-deploy

# Create PostgreSQL database
fly postgres create --name ttek-sms-db --region lhr --initial-cluster-size 1 --vm-size shared-cpu-1x --volume-size 1

# Attach database to app
fly postgres attach ttek-sms-db

# Create Redis (using Upstash - Fly's managed Redis)
fly redis create --name ttek-sms-redis --region lhr --no-eviction

# Deploy the app
fly deploy
```

---

## A.4 Configure Database & Redis

The `fly postgres attach` command automatically sets `DATABASE_URL`. For Redis:

```bash
# Get Redis URL
fly redis status ttek-sms-redis

# Set Redis URL as secret
fly secrets set REDIS_URL="redis://default:password@your-redis-host.upstash.io:6379"
```

---

## A.5 Set Environment Variables

```bash
# Required secrets
fly secrets set SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
fly secrets set FIELD_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

# Domain configuration
fly secrets set ALLOWED_HOSTS="ttek-sms.fly.dev,yourdomain.com,*.yourdomain.com"
fly secrets set CSRF_TRUSTED_ORIGINS="https://ttek-sms.fly.dev,https://yourdomain.com,https://*.yourdomain.com"

# Optional: Email
fly secrets set EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
fly secrets set EMAIL_HOST="smtp.gmail.com"
fly secrets set EMAIL_HOST_USER="your-email@gmail.com"
fly secrets set EMAIL_HOST_PASSWORD="your-app-password"

# Optional: SMS (Arkesel)
fly secrets set SMS_BACKEND="arkesel"
fly secrets set ARKESEL_API_KEY="your-api-key"
fly secrets set ARKESEL_SENDER_ID="YourSchool"
```

---

## A.6 Configure Custom Domain (Fly)

### Add Your Domain
```bash
# Add apex domain
fly certs create yourdomain.com

# Add wildcard for subdomains (FREE on Fly.io!)
fly certs create "*.yourdomain.com"
```

### Configure DNS
Add these records at your DNS provider:

| Type | Name | Value |
|------|------|-------|
| A | @ | `fly.io` IP (shown in dashboard) |
| AAAA | @ | `fly.io` IPv6 (shown in dashboard) |
| CNAME | * | `ttek-sms.fly.dev` |

```bash
# Verify certificates
fly certs show yourdomain.com
fly certs show "*.yourdomain.com"
```

---

## A.7 Setup Media Storage (Fly)

Fly.io has ephemeral filesystem. Use Tigris (Fly's S3-compatible storage) or external S3:

### Option 1: Tigris (Fly's Built-in Storage)
```bash
# Create Tigris bucket
fly storage create

# This auto-sets AWS_* environment variables
```

### Option 2: Cloudflare R2 / AWS S3
```bash
fly secrets set AWS_ACCESS_KEY_ID="your-key"
fly secrets set AWS_SECRET_ACCESS_KEY="your-secret"
fly secrets set AWS_STORAGE_BUCKET_NAME="your-bucket"
fly secrets set AWS_S3_ENDPOINT_URL="https://your-account.r2.cloudflarestorage.com"
```

---

## A.8 Maintenance (Fly)

### SSH into Container
```bash
fly ssh console
```

### Run Management Commands
```bash
fly ssh console -C "python manage.py createsuperuser"
fly ssh console -C "python manage.py migrate_schemas"
```

### View Logs
```bash
fly logs
fly logs -a ttek-sms  # specific app
```

### Scale Up/Down
```bash
# Scale memory
fly scale memory 1024

# Scale instances
fly scale count 2

# View current scale
fly scale show
```

### Database Backup
```bash
fly postgres connect -a ttek-sms-db
# Then run: pg_dump -U postgres ttek_sms > backup.sql
```

### Deploy Updates
```bash
git pull
fly deploy
```

---

## Fly.io Cost Estimate

| Resource | Specs | Monthly Cost |
|----------|-------|--------------|
| Web App | shared-cpu-1x, 512MB | ~$3-5 |
| Worker | shared-cpu-1x, 256MB | ~$2-3 |
| PostgreSQL | 1GB, shared | ~$0 (free tier) |
| Redis (Upstash) | 256MB | ~$0 (free tier) |
| **Total** | | **~$5-10/month** |

*Prices are pay-as-you-go based on usage*

---
---

# Option B: Render.com Deployment

*Note: Wildcard subdomains require Render Team plan ($19/month). Consider Fly.io for cheaper wildcard support.*

## Table of Contents
1. [Prerequisites](#b1-prerequisites)
2. [Deploy with Render Blueprint](#b2-deploy-with-render-blueprint)
3. [Configure Environment Variables](#a3-configure-environment-variables)
4. [Configure Custom Domain](#a4-configure-custom-domain)
5. [Setup Media Storage (S3/R2)](#a5-setup-media-storage)
6. [Create First School](#a6-create-first-school)
7. [Maintenance](#a7-maintenance)

---

## A.1 Prerequisites

1. A [Render.com](https://render.com) account (sign up with GitHub)
2. This repository pushed to GitHub
3. A domain name (optional but recommended for multi-tenancy)

---

## A.2 Deploy with Render Blueprint

### Quick Deploy (One-Click)
1. Push this repository to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com)
3. Click **New** → **Blueprint**
4. Connect your GitHub repository
5. Render will detect `render.yaml` and create all services

### What Gets Created
- **ttek-sms-web**: Main Django application
- **ttek-sms-worker**: Celery worker for background tasks
- **ttek-sms-beat**: Celery beat for scheduled tasks
- **ttek-sms-db**: PostgreSQL 16 database
- **ttek-sms-redis**: Redis for Celery message queue

---

## A.3 Configure Environment Variables

After deployment, go to each service's **Environment** tab and set:

### Required Variables (set manually)

```bash
# Your domain(s) - comma separated
ALLOWED_HOSTS=ttek-sms-web.onrender.com,yourdomain.com,*.yourdomain.com

# CSRF origins - must include https://
CSRF_TRUSTED_ORIGINS=https://ttek-sms-web.onrender.com,https://yourdomain.com,https://*.yourdomain.com
```

### Optional Variables

```bash
# Email (for sending notifications)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# SMS (Arkesel)
SMS_BACKEND=arkesel
ARKESEL_API_KEY=your-api-key
ARKESEL_SENDER_ID=YourSchool

# Payments (Paystack)
PLATFORM_PAYSTACK_SECRET_KEY=sk_live_xxxxx
PLATFORM_PAYSTACK_PUBLIC_KEY=pk_live_xxxxx
```

---

## A.4 Configure Custom Domain

### For Single Domain (e.g., `app.yourdomain.com`)
1. Go to your web service → **Settings** → **Custom Domains**
2. Add `app.yourdomain.com`
3. Configure DNS: `CNAME app → ttek-sms-web.onrender.com`

### For Wildcard Subdomains (Multi-tenant)
Render supports wildcard domains on **paid plans**:

1. Upgrade to Render Team plan
2. Add `*.yourdomain.com` as custom domain
3. Configure DNS:
   ```
   A     @    → (Render IP)
   CNAME *    → ttek-sms-web.onrender.com
   ```
4. Update environment variables:
   ```
   ALLOWED_HOSTS=yourdomain.com,*.yourdomain.com
   CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://*.yourdomain.com
   ```

---

## A.5 Setup Media Storage

**Important:** Render has an ephemeral filesystem. Media files (student photos, documents) will be lost on redeploy. Use external storage:

### Option 1: Cloudflare R2 (Recommended - Cheaper)

1. Create R2 bucket at [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Create R2 API token with read/write permissions
3. Add to environment variables:
   ```
   AWS_ACCESS_KEY_ID=your-r2-access-key
   AWS_SECRET_ACCESS_KEY=your-r2-secret-key
   AWS_STORAGE_BUCKET_NAME=your-bucket-name
   AWS_S3_ENDPOINT_URL=https://your-account-id.r2.cloudflarestorage.com
   AWS_S3_CUSTOM_DOMAIN=your-bucket.your-domain.com
   ```

### Option 2: AWS S3

1. Create S3 bucket in AWS Console
2. Create IAM user with S3 permissions
3. Add to environment variables:
   ```
   AWS_ACCESS_KEY_ID=your-access-key
   AWS_SECRET_ACCESS_KEY=your-secret-key
   AWS_STORAGE_BUCKET_NAME=your-bucket-name
   AWS_S3_REGION_NAME=us-east-1
   ```

---

## A.6 Create First School

1. Access Django admin: `https://your-app.onrender.com/admin/`
2. Create superuser (run in Render Shell):
   ```bash
   python manage.py createsuperuser
   ```
3. Create a School in admin with domain `school1.yourdomain.com`
4. Visit `https://school1.yourdomain.com` to access the school

---

## A.7 Maintenance

### View Logs
- Go to service → **Logs** tab

### Run Management Commands
1. Go to web service → **Shell** tab
2. Run commands:
   ```bash
   python manage.py migrate_schemas
   python manage.py createsuperuser
   ```

### Database Backup
1. Go to database service → **Backups**
2. Click **Create Backup** or enable automatic backups

### Redeploy
- Push to GitHub (auto-deploys if connected)
- Or click **Manual Deploy** in Render dashboard

### Scale Up
- Go to service → **Settings** → change plan

---

## Render Cost Estimate

| Service | Plan | Monthly Cost |
|---------|------|--------------|
| Web Service | Starter | $7 |
| Worker | Starter | $7 |
| Beat | Starter | $7 |
| PostgreSQL | Starter | $7 |
| Redis | Starter | $0 (free) |
| **Total** | | **~$28/month** |

*Upgrade to Standard plans for production workloads (~$50/month)*

---
---

# Option C: Hetzner Deployment (Full Control - Cheapest)

Complete step-by-step guide to deploy on Hetzner Cloud (or any VPS).

## Table of Contents
1. [Create Hetzner Account & Server](#c1-create-hetzner-account--server)
2. [Initial Server Setup](#2-initial-server-setup)
3. [Install Docker](#3-install-docker)
4. [Configure Domain & DNS](#4-configure-domain--dns)
5. [Deploy Application](#5-deploy-application)
6. [Setup SSL Certificates](#6-setup-ssl-certificates)
7. [Final Configuration](#7-final-configuration)
8. [Maintenance Commands](#8-maintenance-commands)

---

## 1. Create Hetzner Account & Server

### 1.1 Sign Up
1. Go to [Hetzner Cloud](https://www.hetzner.com/cloud)
2. Click "Sign Up" and create an account
3. Verify your email and add payment method

### 1.2 Create a Project
1. In Hetzner Cloud Console, click "New Project"
2. Name it: `ttek-sms`

### 1.3 Create SSH Key (On Your Local Machine)
```bash
# Generate SSH key if you don't have one
ssh-keygen -t ed25519 -C "your-email@example.com"

# Display your public key (copy this)
cat ~/.ssh/id_ed25519.pub
```

### 1.4 Add SSH Key to Hetzner
1. Go to Project → Security → SSH Keys
2. Click "Add SSH Key"
3. Paste your public key
4. Name it: `my-laptop`

### 1.5 Create Server
1. Click "Add Server"
2. **Location:** Nuremberg or Falkenstein (cheapest)
3. **Image:** Ubuntu 24.04
4. **Type:** CX22 (2 vCPU, 4GB RAM) - €4.51/month
5. **SSH Key:** Select your key
6. **Name:** `ttek-sms-prod`
7. Click "Create & Buy Now"

### 1.6 Note Your Server IP
After creation, note the IP address (e.g., `123.45.67.89`)

---

## 2. Initial Server Setup

### 2.1 Connect to Server
```bash
ssh root@YOUR_SERVER_IP
```

### 2.2 Update System
```bash
apt update && apt upgrade -y
```

### 2.3 Create Deploy User
```bash
# Create user
adduser deploy
# Add to sudo group
usermod -aG sudo deploy
# Copy SSH keys
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

### 2.4 Configure Firewall
```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status
```

### 2.5 Disable Root Login (Security)
```bash
nano /etc/ssh/sshd_config
```
Change these lines:
```
PermitRootLogin no
PasswordAuthentication no
```
Then restart SSH:
```bash
systemctl restart sshd
```

### 2.6 Reconnect as Deploy User
```bash
# Exit and reconnect
exit
ssh deploy@YOUR_SERVER_IP
```

---

## 3. Install Docker

### 3.1 Install Docker Engine
```bash
# Install prerequisites
sudo apt install -y ca-certificates curl gnupg

# Add Docker's GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add deploy user to docker group
sudo usermod -aG docker deploy

# Apply group changes (or logout/login)
newgrp docker

# Verify installation
docker --version
docker compose version
```

---

## 4. Configure Domain & DNS

### 4.1 Buy/Configure Domain
If you don't have a domain, buy one from:
- [Namecheap](https://namecheap.com) (~$10/year for .com)
- [Cloudflare Registrar](https://www.cloudflare.com/products/registrar/) (at cost)
- [GoDaddy](https://godaddy.com)

### 4.2 Configure DNS Records
In your domain registrar's DNS settings, add these records:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | @ | YOUR_SERVER_IP | 300 |
| A | * | YOUR_SERVER_IP | 300 |
| A | www | YOUR_SERVER_IP | 300 |

**Example for `tteksms.com`:**
```
A    @    →  123.45.67.89      (main domain)
A    *    →  123.45.67.89      (wildcard - all subdomains)
A    www  →  123.45.67.89      (www subdomain)
```

### 4.3 Verify DNS Propagation
Wait 5-30 minutes, then verify:
```bash
# On your local machine
dig tteksms.com +short
dig washs.tteksms.com +short
dig anyschool.tteksms.com +short
```
All should return your server IP.

---

## 5. Deploy Application

### 5.1 Clone Repository
```bash
# On server as deploy user
cd ~
git clone https://github.com/Latiftanga/ttek_sms.git
cd ttek_sms
```

### 5.2 Create Production Environment File
```bash
cp .env.prod.example .env.prod
nano .env.prod
```

Fill in your production values:
```bash
# Core Settings
DEBUG=0
SECRET_KEY=your-super-secret-key-generate-a-new-one
ALLOWED_HOSTS=tteksms.com,*.tteksms.com,www.tteksms.com

# Database
DATABASE_URL=postgres://ttek_user:SuperSecurePassword123@db:5432/ttek_sms_db
POSTGRES_DB=ttek_sms_db
POSTGRES_USER=ttek_user
POSTGRES_PASSWORD=SuperSecurePassword123

# Redis
REDIS_URL=redis://redis:6379/0

# Email (use your SMTP provider)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=TTEK SMS <noreply@tteksms.com>

# SMS (Arkesel)
SMS_BACKEND=arkesel
ARKESEL_API_KEY=your-api-key
ARKESEL_SENDER_ID=TTEKSMS

# Security
FIELD_ENCRYPTION_KEY=generate-new-key
```

### 5.3 Generate Secret Key
```bash
# Generate Django secret key
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 5.4 Generate Encryption Key
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 5.5 Update Nginx Configuration
```bash
nano nginx/conf.d/default.conf
```

Update `server_name` to your domain:
```nginx
server {
    listen 80;
    server_name tteksms.com *.tteksms.com;
    # ... rest of config
}
```

### 5.6 Build and Start Application
```bash
# Build images
docker compose -f docker-compose.prod.yml build

# Start services
docker compose -f docker-compose.prod.yml up -d

# Check logs
docker compose -f docker-compose.prod.yml logs -f web
```

### 5.7 Verify Application is Running
```bash
# Check all services
docker compose -f docker-compose.prod.yml ps

# Test locally
curl -I http://localhost
```

---

## 6. Setup SSL Certificates

### 6.1 Install Certbot
```bash
sudo apt install -y certbot
```

### 6.2 Stop Nginx Temporarily
```bash
docker compose -f docker-compose.prod.yml stop nginx
```

### 6.3 Get Wildcard SSL Certificate
For wildcard certificates, you need DNS validation:

```bash
sudo certbot certonly \
  --manual \
  --preferred-challenges dns \
  -d tteksms.com \
  -d "*.tteksms.com" \
  --email your-email@example.com \
  --agree-tos
```

**During this process:**
1. Certbot will ask you to create TXT DNS records
2. Go to your DNS provider and add the TXT records
3. Wait 2-5 minutes for propagation
4. Press Enter to continue

### 6.4 Copy Certificates
```bash
sudo cp /etc/letsencrypt/live/tteksms.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/tteksms.com/privkey.pem nginx/ssl/
sudo chown deploy:deploy nginx/ssl/*.pem
```

### 6.5 Update Nginx for HTTPS
```bash
nano nginx/conf.d/default.conf
```

Replace the entire file with:
```nginx
upstream django {
    server web:8000;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name tteksms.com *.tteksms.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name tteksms.com *.tteksms.com;

    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;

    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Static files
    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Media files
    location /media/ {
        alias /app/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # Django application
    location / {
        proxy_pass http://django;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_redirect off;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        limit_req zone=one burst=20 nodelay;
    }
}
```

### 6.6 Restart Nginx
```bash
docker compose -f docker-compose.prod.yml up -d nginx
```

### 6.7 Setup Auto-Renewal
```bash
# Create renewal script
sudo nano /etc/cron.d/certbot-renew
```

Add:
```
0 3 * * * root certbot renew --quiet --deploy-hook "cp /etc/letsencrypt/live/tteksms.com/*.pem /home/deploy/ttek_sms/nginx/ssl/ && docker compose -f /home/deploy/ttek_sms/docker-compose.prod.yml restart nginx"
```

---

## 7. Final Configuration

### 7.1 Create Platform Admin
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

### 7.2 Populate Ghana Regions (Optional)
If you have the populate_locations command:
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py populate_locations
```

### 7.3 Test Your Deployment
1. Visit `https://tteksms.com` - Should show landing page
2. Visit `https://tteksms.com/admin/` - Should show Django admin
3. Create a school in admin with domain `washs.tteksms.com`
4. Visit `https://washs.tteksms.com` - Should show school login

### 7.4 Custom Domain Support
When a school wants their own domain (e.g., `amass.edu.gh`):

1. **School adds CNAME record:**
   ```
   CNAME  @  →  tteksms.com
   ```
   Or A record pointing to your server IP

2. **You add their domain in Django admin:**
   - Go to Schools → Domains
   - Add `amass.edu.gh` for that school

3. **Get SSL for custom domain:**
   ```bash
   sudo certbot certonly --webroot -w /home/deploy/ttek_sms/nginx/certbot/www -d amass.edu.gh
   ```

---

## 8. Maintenance Commands

### View Logs
```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f celery
docker compose -f docker-compose.prod.yml logs -f nginx
```

### Restart Services
```bash
# Restart all
docker compose -f docker-compose.prod.yml restart

# Restart specific service
docker compose -f docker-compose.prod.yml restart web
```

### Update Application
```bash
cd ~/ttek_sms

# Pull latest code
git pull origin main

# Rebuild and restart
docker compose -f docker-compose.prod.yml build web celery celery-beat
docker compose -f docker-compose.prod.yml up -d
```

### Database Backup
```bash
# Create backup
docker compose -f docker-compose.prod.yml exec db pg_dump -U ttek_user ttek_sms_db > backup_$(date +%Y%m%d).sql

# Restore backup
cat backup_20250101.sql | docker compose -f docker-compose.prod.yml exec -T db psql -U ttek_user ttek_sms_db
```

### Django Management Commands
```bash
# Run migrations
docker compose -f docker-compose.prod.yml exec web python manage.py migrate_schemas

# Collect static files
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput

# Django shell
docker compose -f docker-compose.prod.yml exec web python manage.py shell
```

### Monitor Resources
```bash
# Docker stats
docker stats

# Disk usage
df -h

# Memory usage
free -m
```

---

## Troubleshooting

### Application Not Loading
```bash
# Check if containers are running
docker compose -f docker-compose.prod.yml ps

# Check web logs
docker compose -f docker-compose.prod.yml logs web

# Check nginx logs
docker compose -f docker-compose.prod.yml logs nginx
```

### Database Connection Issues
```bash
# Check database logs
docker compose -f docker-compose.prod.yml logs db

# Test connection
docker compose -f docker-compose.prod.yml exec web python manage.py dbshell
```

### SSL Certificate Issues
```bash
# Check certificate status
sudo certbot certificates

# Force renewal
sudo certbot renew --force-renewal
```

### Permission Issues
```bash
# Fix media/static permissions
sudo chown -R deploy:deploy ~/ttek_sms/media
sudo chown -R deploy:deploy ~/ttek_sms/staticfiles
```

---

## Cost Summary

| Item | Monthly Cost |
|------|--------------|
| Hetzner CX22 | €4.51 (~$5) |
| Domain (.com) | ~$1 (yearly $12) |
| **Total** | **~$6/month** |

---

## Security Checklist

- [x] SSH key authentication only
- [x] Root login disabled
- [x] Firewall configured (UFW)
- [x] HTTPS enabled with auto-renewal
- [x] DEBUG=0 in production
- [x] Strong database password
- [x] Secret key not in version control
- [ ] Regular backups configured
- [ ] Monitoring setup (optional: UptimeRobot)

---

## Support

For issues with this deployment:
- Check logs first: `docker compose -f docker-compose.prod.yml logs -f`
- GitHub Issues: https://github.com/Latiftanga/ttek_sms/issues

**Your app is now live at `https://tteksms.com`!**
