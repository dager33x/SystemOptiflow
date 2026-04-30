# SystemOptiflow

SystemOptiflow is a traffic monitoring and signal-control project with two runtime modes:

- `desktop_app.py` starts the desktop operator UI built with Tkinter.
- `web_server.py` starts the FastAPI web runtime used for Docker and VPS deployment.

The desktop UI is the local default. The web runtime is the deployment target for MJPEG streaming, WebSocket dashboard updates, and headless hosting.

## Runtime Modes

### Desktop mode

Use this for the original operator interface shown in the Tkinter dashboard:

```powershell
python desktop_app.py
```

Or with the virtual environment interpreter:

```powershell
.\.venv\Scripts\python.exe desktop_app.py
```

### Web mode

Use this for browser access, Docker, and DigitalOcean deployment:

```powershell
python web_server.py
```

The web UI is available at `http://127.0.0.1:8000/login`.

### Docker / VPS

#### Local Docker

```powershell
docker compose up --build
```

This starts:

- `mediamtx` for RTSP relay
- `optiflow-app` for FastAPI, camera runtime, MJPEG streams, and WebSocket updates
- `nginx` as the reverse proxy

#### VPS First-Time Deployment

Tested on a fresh Ubuntu 22.04 DigitalOcean droplet.

##### Prerequisites

- Ubuntu 22.04 VPS with root/sudo access
- A [DuckDNS](https://www.duckdns.org/) account with a registered domain (e.g. `optiflow.duckdns.org`) and your token
- An email address for Let's Encrypt certificate notifications
- The repo cloned on the VPS

##### Quick start

```bash
# 1. Clone and switch to the deployment branch
git clone https://github.com/dager33x/SystemOptiflow.git
cd SystemOptiflow
git checkout deploy/vps-setup

# 2. Create and fill in your .env
cp .env.example .env
nano .env   # set the 5 required variables listed below
```

Minimum required variables for VPS deployment:

```ini
DOMAIN=optiflow.duckdns.org        # your DuckDNS subdomain
DUCKDNS_TOKEN=your-duckdns-token   # from duckdns.org dashboard
CERTBOT_EMAIL=your@email.com       # for Let's Encrypt expiry notices
RTSP_PUBLISH_PASSWORD=changeme     # password phone cameras use to push streams
SESSION_SECRET=change-me-before-production  # random 32-char string
```

```bash
# 3. Run the one-time setup script
chmod +x scripts/vps_setup.sh
sudo bash scripts/vps_setup.sh

# 4. Visit your dashboard (takes ~2 minutes)
# https://<your-domain>/
```

##### What the script does

1. Installs Docker and Docker Compose (skips if already installed)
2. Configures UFW firewall (opens 22, 80, 443, 8554)
3. Creates a temporary self-signed cert so nginx can start
4. Builds and starts all containers (`mediamtx`, `optiflow-app`, `nginx`)
5. Obtains a real Let's Encrypt cert via DuckDNS DNS challenge
6. Reloads nginx with the real cert
7. Schedules daily auto-renewal at 03:30 UTC via cron

##### Connecting phone cameras

Each phone camera app should push an RTSP stream to:

```text
rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/north
rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/south
rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/east
rtsp://publisher:<RTSP_PUBLISH_PASSWORD>@<vps-ip>:8554/west
```

Then activate them in `.env` on the VPS and restart the app container:

```bash
# In .env:
CAMERA_SOURCE_NORTH=rtsp://mediamtx:8554/north
CAMERA_SOURCE_SOUTH=rtsp://mediamtx:8554/south
CAMERA_SOURCE_EAST=rtsp://mediamtx:8554/east
CAMERA_SOURCE_WEST=rtsp://mediamtx:8554/west

docker compose restart optiflow-app
```

## Requirements

- Python `3.11` recommended (local dev only; Docker handles this automatically)
- Supabase optional for cloud-backed users, reports, violations, and incidents
- YOLO and OpenCV dependencies from `requirements.ml.txt`

Install locally with:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.base.txt -r requirements.ml.txt -r requirements.dev.txt
```

## Environment

Create a local `.env` file from the template:

```powershell
Copy-Item .env.example .env
```

General variables:

| Variable | Purpose |
| --- | --- |
| `SUPABASE_URL` / `SUPABASE_KEY` | Cloud-backed auth and events (optional) |
| `SESSION_SECRET` | Web session encryption key |
| `HOST` / `PORT` | Bind address for local web mode |
| `DEMO_USERNAME` / `DEMO_PASSWORD` | Initial login credentials |
| `CAMERA_SOURCE_NORTH/SOUTH/EAST/WEST` | Camera inputs per lane |

VPS-only variables:

| Variable | Purpose |
| --- | --- |
| `DOMAIN` | Your DuckDNS subdomain (e.g. `optiflow.duckdns.org`) |
| `DUCKDNS_TOKEN` | DuckDNS API token for DNS challenge cert issuance |
| `CERTBOT_EMAIL` | Email for Let's Encrypt expiry notifications |
| `RTSP_PUBLISH_PASSWORD` | Auth password for phone cameras pushing RTSP |

## Main Paths

- `desktop_app.py`: desktop application flow and dashboard startup
- `webapp/main.py`: FastAPI routes, templates, sessions, and runtime startup
- `webapp/runtime.py`: camera, detection, and traffic runtime coordination
- `webapp/templates/`: web login and dashboard templates
- `views/`: Tkinter desktop UI components
- `unified_schema.sql`: Supabase schema, including verification codes used by web auth

## Common First-Time Errors

| Error / Symptom | Cause | Fix |
| --- | --- | --- |
| `ERROR: .env not found` | Script ran before `.env` was created | `cp .env.example .env` then fill in values |
| `ERROR: run as root` | Script ran without sudo | `sudo bash scripts/vps_setup.sh` |
| Certbot times out waiting for DNS | Wrong `DUCKDNS_TOKEN` or domain not registered | Verify at duckdns.org, fix `.env`, re-run script |
| Dashboard returns 502 Bad Gateway | App container still building or crashed | `docker compose logs optiflow-app --tail 50` |
| Phone cameras can't connect on port 8554 | Firewall blocked the RTSP port | `sudo ufw status` — ensure 8554/tcp and 8554/udp are allowed |
| Cameras still show "Simulated" after connecting phones | `.env` camera sources not updated or container not restarted | Update `CAMERA_SOURCE_*` in `.env`, then `docker compose restart optiflow-app` |
| Warning about default `SESSION_SECRET` | `.env` still has the placeholder value | Replace with a random 32-char string before exposing publicly |
| `docker compose: command not found` | Old Docker install without Compose v2 | Run `sudo bash scripts/vps_setup.sh` from step 1; it installs Docker via `get.docker.com` |
| Docker commands fail after first install | Group membership not applied to current session | Log out and back in, or run `newgrp docker` |
| Python venv wrong version (local dev) | `.venv` was created with Python ≠ 3.11 | Delete `.venv`, recreate: `py -3.11 -m venv .venv` |
| PyTorch install fails (local dev) | No matching wheel for your platform or CUDA version | Install CPU-only: `pip install torch --index-url https://download.pytorch.org/whl/cpu` |

## Post-Deployment Verification

```bash
docker compose ps                          # all 3 services should be Up
docker compose logs nginx --tail 20        # check for nginx errors
curl -k https://localhost/health           # FastAPI should return {"status":"ok"}
sudo crontab -l | grep certbot             # renewal job should be scheduled
```

## Verification

The non-GUI smoke test covers the web runtime import path:

```powershell
python test_system.py
```
