#!/bin/bash
# UK House Prices — one-shot VPS setup script
# Run as root on a fresh Ubuntu 24.04 server:
#   curl -sSL <raw-url>/deploy/setup.sh | bash
# Or: scp deploy/setup.sh root@server: && ssh root@server bash setup.sh
#
# Prerequisites: Git repo URL set below (or pass as $1)

set -euo pipefail

REPO_URL="${1:-https://github.com/YOUR_USERNAME/uk-house-prices.git}"
APP_DIR="/opt/uk-house-prices"
APP_USER="ukhp"

echo "==> Installing system dependencies..."
apt-get update
apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    nodejs npm \
    build-essential libxml2-dev libxslt1-dev \
    libopenblas-dev gfortran \
    caddy \
    git

echo "==> Creating application user..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -m -d "$APP_DIR" -s /bin/bash "$APP_USER"
fi

echo "==> Cloning repository..."
if [ -d "$APP_DIR/.git" ]; then
    echo "    Repo already exists, pulling latest..."
    cd "$APP_DIR"
    sudo -u "$APP_USER" git pull
else
    git clone "$REPO_URL" "$APP_DIR"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

cd "$APP_DIR"

echo "==> Setting up Python virtual environment..."
sudo -u "$APP_USER" python3.11 -m venv venv
sudo -u "$APP_USER" venv/bin/pip install --upgrade pip
sudo -u "$APP_USER" venv/bin/pip install -r requirements.txt

echo "==> Building frontend..."
cd frontend
sudo -u "$APP_USER" npm install
sudo -u "$APP_USER" npm run build
cd "$APP_DIR"

echo "==> Creating data directory..."
sudo -u "$APP_USER" mkdir -p data/postcodes

echo "==> Setting up environment file..."
if [ ! -f .env ]; then
    cp .env.production .env
    chown "$APP_USER:$APP_USER" .env
    echo "    Created .env from template — edit it with your values:"
    echo "    sudo -u $APP_USER nano $APP_DIR/.env"
fi

echo "==> Installing systemd services..."
cp deploy/uk-house-prices.service /etc/systemd/system/
cp deploy/uk-house-prices-scrape.service /etc/systemd/system/
cp deploy/uk-house-prices-scrape.timer /etc/systemd/system/

echo "==> Setting up Caddy..."
cp deploy/Caddyfile /etc/caddy/Caddyfile

echo "==> Enabling and starting services..."
systemctl daemon-reload
systemctl enable --now uk-house-prices
systemctl enable --now uk-house-prices-scrape.timer
systemctl restart caddy

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "  App:    http://$(hostname -I | awk '{print $1}')"
echo "  Status: systemctl status uk-house-prices"
echo "  Logs:   journalctl -u uk-house-prices -f"
echo "  Timer:  systemctl list-timers uk-house-prices-scrape*"
echo ""
echo "  Next steps:"
echo "  1. Edit $APP_DIR/.env with your API keys and domain"
echo "  2. If using a domain, edit /etc/caddy/Caddyfile and restart Caddy"
echo "  3. Copy your data/ directory from local machine if needed:"
echo "     scp -r data/ $APP_USER@server:$APP_DIR/data/"
echo ""
