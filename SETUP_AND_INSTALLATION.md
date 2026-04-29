# SystemOptiflow Setup and Installation Guide

This project supports two startup modes:

- Desktop UI: `python app.py`
- Web server: `python web_server.py`

Use the desktop UI for the original operator dashboard. Use the web server for browser access, Docker, and VPS deployment.

## 1. Prerequisites

- Python `3.11` recommended
- Git
- Optional: Supabase project
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

Minimum useful values:

```ini
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-public-key
SESSION_SECRET=change-me-before-production
HOST=0.0.0.0
PORT=8000
DEMO_USERNAME=admin
DEMO_PASSWORD=admin123
```

If you want database-backed auth and event pages, apply `unified_schema.sql` in Supabase before testing registration or password reset flows.

## 5. Run the Desktop UI

This opens the original Tkinter operator interface.

```powershell
python app.py
```

Or:

```powershell
.\.venv\Scripts\python.exe app.py
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

## 7. Run with Docker Compose

```powershell
docker compose up --build
```

This runs the web stack only:

- `mediamtx`
- `optiflow-app`
- `nginx`

## 8. Smoke Test

```powershell
python test_system.py
```

## 9. Troubleshooting

- If the wrong UI opens, check which command you used:
  - `python app.py` opens the desktop UI
  - `python web_server.py` opens the web UI
- If Supabase fails, verify `SUPABASE_URL` and `SUPABASE_KEY`.
- If cameras do not appear in web mode, check the lane source variables in `.env`.
- If you are deploying to Docker, use `web_server.py`; the desktop UI is not meant for headless containers.
