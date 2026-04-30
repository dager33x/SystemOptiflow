# SystemOptiflow Setup and Installation Guide

This project supports two startup modes:

- Desktop UI: `python desktop_app.py`
- Web server: `python web_server.py`

Use the desktop UI for the original operator dashboard. Use the web server for browser access, Docker, and VPS deployment.

## 1. Prerequisites

- Python `3.11` recommended (local dev only; Docker handles this automatically)
- Git
- Optional: Supabase project for cloud-backed auth and events
- Optional: local camera or RTSP source

## 2. Create a Virtual Environment

If `.venv` was created with the wrong Python version, delete it first and recreate it with Python 3.11.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy Unrestricted -Scope Process
```

## 3. Install Dependencies

```powershell
pip install -r requirements.base.txt -r requirements.ml.txt -r requirements.dev.txt
```

## 4. Configure Environment Variables

Create `.env` from the template:

```powershell
Copy-Item .env.example .env
```

Minimum useful values for local development:

```ini
SESSION_SECRET=change-me-before-production
HOST=0.0.0.0
PORT=8000
DEMO_USERNAME=admin
DEMO_PASSWORD=admin123
```

If you want database-backed auth and event pages, apply `unified_schema.sql` in Supabase and set:

```ini
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-public-key
```

## 5. Run the Desktop UI

This opens the original Tkinter operator interface.

```powershell
python desktop_app.py
```

Or:

```powershell
.\.venv\Scripts\python.exe desktop_app.py
```

## 6. Run the Web UI

This starts the FastAPI runtime used by Docker and VPS deployment.

```powershell
python web_server.py
```

Then open:

```text
http://127.0.0.1:8000/login
```

## 7. Run with Docker Compose (local)

```powershell
docker compose up --build
```

This runs the web stack only:

- `mediamtx` — RTSP relay for phone cameras
- `optiflow-app` — FastAPI runtime, camera processing, MJPEG streams, WebSocket updates
- `nginx` — reverse proxy

## 8. Smoke Test

```powershell
python test_system.py
```

## 9. VPS Deployment (DigitalOcean)

Tested on a fresh Ubuntu 22.04 droplet.

### 9.1 VPS Prerequisites

- Ubuntu 22.04 VPS with root/sudo access
- A [DuckDNS](https://www.duckdns.org/) account with a registered domain and your token
- An email address for Let's Encrypt certificate notifications

### 9.2 Required `.env` Variables

Beyond the general variables, VPS deployment requires:

| Variable | Description |
| --- | --- |
| `DOMAIN` | Your DuckDNS subdomain (e.g. `optiflow.duckdns.org`) |
| `DUCKDNS_TOKEN` | Token from the DuckDNS dashboard |
| `CERTBOT_EMAIL` | Email for Let's Encrypt expiry notices |
| `RTSP_PUBLISH_PASSWORD` | Password phone cameras use to push RTSP streams |
| `SESSION_SECRET` | Random 32-char string — do not leave as the placeholder |

### 9.3 First-Time Setup Steps

```bash
# On the VPS:
git clone https://github.com/dager33x/SystemOptiflow.git
cd SystemOptiflow
git checkout deploy/vps-setup

cp .env.example .env
nano .env   # fill in the 5 required VPS variables above

chmod +x scripts/vps_setup.sh
sudo bash scripts/vps_setup.sh
```

The script runs in ~2 minutes and handles all seven steps automatically:

1. Installs Docker + Docker Compose (skips if already present)
2. Configures UFW firewall (opens ports 22, 80, 443, 8554)
3. Creates a temporary self-signed cert so nginx can start
4. Builds and starts all containers
5. Obtains a real Let's Encrypt cert via DuckDNS DNS challenge
6. Reloads nginx with the real cert
7. Schedules daily auto-renewal at 03:30 UTC via cron

### 9.4 Connecting Phone Cameras

After setup, configure each phone camera app to push to:

```text
rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/north
rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/south
rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/east
rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/west
```

Then activate the streams in `.env` on the VPS:

```ini
CAMERA_SOURCE_NORTH=rtsp://mediamtx:8554/north
CAMERA_SOURCE_SOUTH=rtsp://mediamtx:8554/south
CAMERA_SOURCE_EAST=rtsp://mediamtx:8554/east
CAMERA_SOURCE_WEST=rtsp://mediamtx:8554/west
```

Apply by restarting the app container:

```bash
docker compose restart optiflow-app
```

### 9.5 Post-Deployment Verification

```bash
docker compose ps                          # all 3 services should be Up
docker compose logs nginx --tail 20        # check for nginx errors
curl -k https://localhost/health           # FastAPI should return {"status":"ok"}
sudo crontab -l | grep certbot             # renewal job should be scheduled
```

## 10. Troubleshooting

### General

- If the wrong UI opens, check which command you used:
  - `python desktop_app.py` opens the desktop UI
  - `python web_server.py` opens the web UI
- If Supabase fails, verify `SUPABASE_URL` and `SUPABASE_KEY`.
- If cameras do not appear in web mode, check the lane source variables in `.env`.
- If you are deploying to Docker, use `web_server.py`; the desktop UI is not meant for headless containers.

### Local Development

| Problem | Fix |
| --- | --- |
| Python venv wrong version | Delete `.venv`, recreate with `py -3.11 -m venv .venv` |
| PyTorch install fails (no CUDA wheel) | `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| PowerShell blocks venv activation | `Set-ExecutionPolicy Unrestricted -Scope Process` |

### VPS / Docker

| Error / Symptom | Cause | Fix |
| --- | --- | --- |
| `ERROR: .env not found` | Script ran before `.env` was created | `cp .env.example .env` then fill in values |
| `ERROR: run as root` | Script ran without sudo | `sudo bash scripts/vps_setup.sh` |
| Certbot times out waiting for DNS | Wrong `DUCKDNS_TOKEN` or domain not registered | Verify at duckdns.org, fix `.env`, re-run script |
| Dashboard returns 502 Bad Gateway | App container still building or crashed | `docker compose logs optiflow-app --tail 50` |
| Phone cameras can't connect on port 8554 | Firewall blocked the RTSP port | `sudo ufw status` — ensure 8554/tcp and 8554/udp are allowed |
| Cameras still show "Simulated" after connecting phones | `.env` camera sources not updated or container not restarted | Update `CAMERA_SOURCE_*` in `.env`, then `docker compose restart optiflow-app` |
| Warning about default `SESSION_SECRET` | `.env` still has the placeholder value | Replace with a random 32-char string |
| `docker compose: command not found` | Old Docker install without Compose v2 | Re-run `sudo bash scripts/vps_setup.sh` from step 1; it installs Docker via `get.docker.com` |
| Docker commands fail after first install | Group membership not applied to current session | Log out and back in, or run `newgrp docker` |
| Certbot renewal not running | Cron job missing | `sudo crontab -l` — if missing, re-run setup script or add manually |
