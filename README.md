# SystemOptiflow

SystemOptiflow is a traffic monitoring and signal-control project with two runtime modes:

- `app.py` starts the legacy desktop operator UI built with Tkinter.
- `web_server.py` starts the FastAPI web runtime used for Docker and VPS deployment.

The desktop UI is the local default. The web runtime is the deployment target for MJPEG streaming, WebSocket dashboard updates, and headless hosting.

## Runtime Modes

### Desktop mode

Use this for the original operator interface shown in the Tkinter dashboard:

```powershell
python app.py
```

Or with the virtual environment interpreter:

```powershell
.\.venv\Scripts\python.exe app.py
```

### Web mode

Use this for browser access, Docker, and DigitalOcean deployment:

```powershell
python web_server.py
```

The web UI is available at `http://127.0.0.1:8000/login`.

### Docker / VPS

```powershell
docker compose up --build
```

This starts:

- `mediamtx` for RTSP relay
- `optiflow-app` for FastAPI, camera runtime, MJPEG streams, and WebSocket updates
- `nginx` as the reverse proxy

## Requirements

- Python `3.11` recommended
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

Important variables:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SESSION_SECRET`
- `HOST`
- `PORT`
- `CAMERA_SOURCE_NORTH`, `CAMERA_SOURCE_SOUTH`, `CAMERA_SOURCE_EAST`, `CAMERA_SOURCE_WEST`

## Main Paths

- `desktop_app.py`: desktop application flow and dashboard startup
- `webapp/main.py`: FastAPI routes, templates, sessions, and runtime startup
- `webapp/runtime.py`: camera, detection, and traffic runtime coordination
- `webapp/templates/`: web login and dashboard templates
- `views/`: Tkinter desktop UI components
- `unified_schema.sql`: Supabase schema, including verification codes used by web auth

## Verification

The non-GUI smoke test covers the web runtime import path:

```powershell
python test_system.py
```
