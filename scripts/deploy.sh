#!/usr/bin/env bash
# AI Crawler v2 — One-click VPS deployment
#
# Usage:
#   bash scripts/deploy.sh              # Deploy with Docker Compose
#   bash scripts/deploy.sh --no-ssl     # Skip SSL setup
#   bash scripts/deploy.sh --port 9090  # Custom port
#
# Prerequisites:
#   - Docker + Docker Compose installed
#   - Domain pointed to this server (for SSL)
#   - .env file with DEEPSEEK_API_KEY

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Defaults
PORT="${CRAWLER_PORT:-8080}"
SETUP_SSL=true
DOMAIN=""

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-ssl) SETUP_SSL=false; shift ;;
        --port) PORT="$2"; shift 2 ;;
        --domain) DOMAIN="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "============================================"
echo "  CrawlWeaver — Deployment"
echo "============================================"
echo ""

# Step 1: Check prerequisites
echo "[1/5] Checking prerequisites..."
for cmd in docker docker-compose; do
    if ! command -v "$cmd" &>/dev/null && ! docker compose version &>/dev/null; then
        echo "❌ Missing: $cmd"
        echo "   Install Docker: https://docs.docker.com/engine/install/"
        exit 1
    fi
done
echo "  ✅ Docker available"

# Step 2: Check .env
echo "[2/5] Checking configuration..."
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    echo "  ⚠️  No .env file found. Creating from template..."
    cat > "$PROJECT_DIR/.env" << 'EOF'
# CrawlWeaver — Environment Configuration
DEEPSEEK_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
CRAWLER_PORT=8080
CRAWLER_BASE_URL=https://example.com
EOF
    echo "  📝 Created .env — please edit with your API key"
    echo "     vim $PROJECT_DIR/.env"
    exit 1
fi
echo "  ✅ .env exists"

# Step 3: Build and deploy
echo "[3/5] Building Docker image..."
cd "$PROJECT_DIR"
CRAWLER_PORT="$PORT" docker compose build --quiet

echo "[4/5] Starting services..."
CRAWLER_PORT="$PORT" docker compose up -d

# Wait for health
echo "  ⏳ Waiting for health check..."
for i in $(seq 1 30); do
    if curl -sf "http://localhost:$PORT/api/health" >/dev/null 2>&1; then
        echo "  ✅ Service is healthy"
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo "  ❌ Health check failed after 30s"
        echo "     Check logs: docker compose logs"
        exit 1
    fi
    sleep 1
done

# Step 4: Nginx reverse proxy (optional)
echo "[5/5] Configuring nginx..."
if [[ -n "$DOMAIN" ]] && command -v nginx &>/dev/null; then
    NGINX_CONF="/etc/nginx/sites-available/ai-crawler"
    cat > "$NGINX_CONF" << NGINX
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINX
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx
    echo "  ✅ Nginx configured for $DOMAIN"

    if $SETUP_SSL && command -v certbot &>/dev/null; then
        echo "  🔒 Setting up SSL..."
        certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@"$DOMAIN" || true
    fi
else
    echo "  ⏭️  Skipping nginx (no domain specified or nginx not installed)"
fi

echo ""
echo "============================================"
echo "  ✅ Deployment complete!"
echo ""
echo "  Dashboard: http://localhost:$PORT"
echo "  API:       http://localhost:$PORT/api/health"
echo ""
echo "  Useful commands:"
echo "    docker compose logs -f        # View logs"
echo "    docker compose restart        # Restart"
echo "    docker compose down           # Stop"
echo "============================================"
