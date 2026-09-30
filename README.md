# Optiflow

**A desktop traffic-monitoring and incident-management system for traffic personnel.**

Optiflow brings four camera feeds, vehicle detection, traffic-signal visualization, and incident records into one dashboard. It helps personnel monitor traffic, review possible collisions and red-light violations, and track incident responses. Administrators manage user access through an account-approval workflow.

Built with Python, PySide6, OpenCV, YOLO, PyTorch, and Supabase.

## Key features

- **Four-camera monitoring** — Use webcams, video files, network streams, or simulated traffic sources.
- **Vehicle detection and signal management** — Detect supported vehicle classes and run adaptive signal timing with emergency-vehicle priority in the application.
- **Red-light violation alerts** — Configure a visible stop line for each camera and flag tracked vehicles crossing it during the application's red phase.
- **Incident review** — Mark possible collisions as Confirmed, False detection, or Needs investigation, with a note and retained evidence.
- **Response tracking** — Move incidents through Pending → Acknowledged → Responding → Resolved, recording who acted, when, and why.
- **Notifications and records** — Receive visual alerts and sound chimes, search incident and violation history, and export records to CSV or PDF.
- **Account approval** — New users verify their email and wait for an administrator to approve or reject access.

## Getting started

Use Python 3.12 on Windows. Run these commands from the folder containing `app.py`:

```powershell
python -m venv .venv-pyside6
.\.venv-pyside6\Scripts\python.exe -m pip install -r requirements.txt
```

Create a local `.env` file beside `app.py`:

```ini
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-project-key
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your-sender@gmail.com
SENDER_PASSWORD=your-gmail-app-password
```

For a fresh database, review and run [unified_schema.sql](unified_schema.sql) in Supabase SQL Editor and provision an approved, active administrator. For an existing installation, apply the [user-approval migration](migrations/20260930_user_approval.sql) and [incident-workflow migration](migrations/20260930_incident_workflow.sql). Incident review and response actions require the workflow migration.

Keep `best.pt` and `yolov8n.pt` beside `app.py`; detector weights are loaded locally. Retain the supplied `checkpoints/dqn/` weights for the adaptive controller.

```powershell
.\.venv-pyside6\Scripts\python.exe app.py
```

To explore the simulated dashboard without login or database writes:

```powershell
.\.venv-pyside6\Scripts\python.exe app.py --preview
```

## Scope and limitations

Possible-collision alerts use vehicle-motion rules and require human review; they are not confirmed crash diagnoses. The current collision heuristic runs during green phases and can miss incidents. Red-light checks use the application's signal state, not recognition of an external traffic light. Detection quality depends on camera placement, calibration, footage, and hardware; this repository does not establish field accuracy or physical traffic-signal integration.

Locally saved incident records remain on the computer and do not automatically sync to Supabase. Authentication uses the application's custom users table; database access policies need review before deployment. Keep `.env`, credentials, and private incident evidence out of the public repository.

## Project structure

```text
dashboard/
├── controllers/   # Application actions and workflow coordination
├── models/        # Data, database access, detection, and traffic logic
├── views/         # PySide6 screens and widgets
├── services/      # Camera capture, inference, and background tasks
└── utils/         # Configuration and shared helpers
assets/            # Logo, interface assets, and alert sounds
migrations/        # Database updates
tests/             # Automated checks
app.py             # Application entry point
```
