#!/usr/bin/env bash
# =============================================================================
# SystemOptiflow — DigitalOcean VPS first-time setup script
#
# Run this ONCE on a fresh Ubuntu 22.04 droplet from the project root:
#   git clone https://github.com/dager33x/SystemOptiflow.git
#   cd SystemOptiflow
#   cp .env.example .env          # then edit .env with your real values
#   chmod +x scripts/vps_setup.sh
#   sudo bash scripts/vps_setup.sh
#
# What it does:
#   1. Installs Docker + Docker Compose plugin
#   2. Configures UFW firewall
#   3. Creates a temporary self-signed cert so nginx can start
#   4. Starts all containers (docker compose up)
#   5. Obtains a real Let's Encrypt cert via DuckDNS DNS challenge
#   6. Reloads nginx with the real cert
#   7. Schedules auto-renewal via cron
# =============================================================================
set -euo pipefail

# ── Require root ──────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: run as root (sudo bash scripts/vps_setup.sh)" >&2
  exit 1
fi

# ── Load .env ─────────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
  echo "ERROR: .env not found. Copy .env.example → .env and fill in your values." >&2
  exit 1
fi
set -o allexport
source .env
set +o allexport

: "${DOMAIN:?'.env must set DOMAIN (e.g. optiflow.duckdns.org)'}"
: "${DUCKDNS_TOKEN:?'.env must set DUCKDNS_TOKEN'}"
: "${CERTBOT_EMAIL:?'.env must set CERTBOT_EMAIL'}"

CERT_DIR="./certbot/conf/live/optiflow"

echo "==> [1/7] Installing Docker"
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  # Allow current user to run docker without sudo (takes effect on next login)
  usermod -aG docker "${SUDO_USER:-$USER}" || true
else
  echo "     Docker already installed — skipping"
fi

echo "==> [2/7] Configuring UFW firewall"
ufw allow 22/tcp   comment "SSH"
ufw allow 80/tcp   comment "HTTP (ACME + redirect)"
ufw allow 443/tcp  comment "HTTPS dashboard"
ufw allow 8554/tcp comment "RTSP ingest (phone cameras)"
ufw allow 8554/udp comment "RTSP ingest UDP"
ufw --force enable

echo "==> [3/7] Creating bootstrap self-signed cert (so nginx can start)"
if [[ ! -f "$CERT_DIR/fullchain.pem" ]]; then
  mkdir -p "$CERT_DIR"
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout "$CERT_DIR/privkey.pem" \
    -out    "$CERT_DIR/fullchain.pem" \
    -subj   "/CN=localhost" 2>/dev/null
  # nginx needs chain.pem too
  cp "$CERT_DIR/fullchain.pem" "$CERT_DIR/chain.pem"
  echo "     Dummy cert written to $CERT_DIR"
else
  echo "     Cert already exists — skipping dummy cert creation"
fi

# Ensure certbot output dirs exist
mkdir -p ./certbot/conf ./certbot/www

echo "==> [4/7] Building and starting containers"
docker compose up -d --build

echo "     Waiting 15 s for containers to stabilise..."
sleep 15

echo "==> [5/7] Obtaining Let's Encrypt cert via DuckDNS DNS challenge"
docker compose --profile certbot run --rm certbot
echo "     Certificate obtained for $DOMAIN"

echo "==> [6/7] Reloading nginx with real cert"
docker compose exec nginx nginx -s reload

echo "==> [7/7] Scheduling auto-renewal (runs daily at 03:30)"
CRON_CMD="30 3 * * * cd $(pwd) && docker compose --profile certbot run --rm certbot renew --quiet && docker compose exec nginx nginx -s reload >> /var/log/certbot-renew.log 2>&1"
(crontab -l 2>/dev/null | grep -v "certbot"; echo "$CRON_CMD") | crontab -

echo ""
echo "============================================================"
echo "  Setup complete!"
echo "  Dashboard: https://${DOMAIN}"
echo "  Health:    https://${DOMAIN}/health"
echo ""
echo "  Phone RTSP push URL (one per lane):"
echo "    rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/north"
echo "    rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/south"
echo "    rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/east"
echo "    rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/west"
echo ""
echo "  Then update .env on the VPS:"
echo "    CAMERA_SOURCE_NORTH=rtsp://mediamtx:8554/north"
echo "    CAMERA_SOURCE_SOUTH=rtsp://mediamtx:8554/south"
echo "    ... and docker compose up -d to apply"
echo "============================================================"
