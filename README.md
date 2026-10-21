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

Keep `best.pt`, `yolov8n.pt`, and `bestw.pt` beside `app.py`; detector weights are loaded locally. The accident pipeline selects only the `accident` class from the supplied multiclass `bestw.pt`. Retain the supplied `checkpoints/dqn/` weights for the adaptive controller. The obsolete `accident.pt` has been removed; it is not required or loaded as a fallback.

You can also double-click `../start_optiflow.bat`. The launcher checks the virtual environment first and falls back to the project-local portable Python at `../.runtime/python312` when available. This local runtime was added because the existing virtual environment pointed to a missing Python installation; it is excluded from Git.

```powershell
.\.venv-pyside6\Scripts\python.exe app.py
```

To explore the simulated dashboard without login or database writes:

```powershell
.\.venv-pyside6\Scripts\python.exe app.py --preview
```

## Upload videos for four cameras

On **Traffic Live Camera**, click **Upload videos for four cameras…**. Choose a local video for North, South, East, and West, then click **Load videos**. You can also use **Upload video…** below an individual camera to change only that panel. Blank rows keep their current source.

Each selected file is checked for readable video before any camera changes. Valid videos start automatically, play at their recorded speed with preview frames sampled as needed, and loop independently, including when the same file is used in multiple panels. Unsupported or damaged files show an error and keep the current feeds. MP4, AVI, MKV, MOV, M4V, WMV, WebM, and MPEG files can be selected; playback depends on the file's codec.

AI detection processes the footage when enabled in Settings. Settings also lets you restart a video, return to a USB/network camera or simulation, and adjust each stop line. Logged-in sessions remember the video paths, so keep the files in the same location. Files are read from your computer; they are not uploaded to a cloud service. Preview mode does not save source preferences.

## Scope and limitations

Vehicle and emergency detection use the two small local traffic models at 416-pixel input. Vehicle results are published before the larger specialist model runs; accident and pedestrian checks run less frequently and have their own result/evidence channel. Four high-frame-rate files use bounded decoder threads and at most about 30 preview frames per second. Each camera shows its measured AI update rate and result age; processing speed depends on CPU load.

Emergency priority requires at least three different fresh observations spanning two seconds. Cached boxes cannot confirm priority. The controller gives a yellow warning and an all-red interval before granting the emergency lane exclusive green, rechecks that the emergency is still present, and clears through yellow/all-red before resuming the paused countdown. These are application signals, not physical traffic-light controls.

Use **Stop line…** below a camera to set the road boundary and travel direction. Left/right-moving traffic needs a vertical line; down/up-moving traffic needs a horizontal line. An uncalibrated line can miss crossings. Red-light records use the signal stamped on the detection frame. The specialist model's `jaywalker` class now produces **Possible Jaywalking** review records only after repeated matching observations; a person detection alone is not a violation.

Normal vehicle boxes are drawn on the live feed. Image-feature tracking updates their positions between model predictions and compensates for model delay using recent video frames. Tracks expire when image features are lost, the source changes, video loops, or a vehicle is not reconfirmed within 3.5 seconds. Emergency priority still requires fresh classifier observations and retains its two-second capture-age limit. Only possible accidents use an evidence inset; normal vehicles never do. See the [four-camera live verification](REALTIME_VERIFICATION.md) for measured tracking and inference rates, regression checks, and remaining limitations.

Uncalibrated stop lines now watch both crossing directions. **Stop line…** also offers horizontal or vertical lines restricted to one direction. Crossings use tracked vehicle identities and the signal recorded on each live frame. A vehicle already beyond the line when first detected, mere box overlap, and a crossing on green do not create a red-light record.

Accident alerts use the supplied `bestw.pt` model with a starting confidence threshold of 0.60, at least three matching fresh predictions, and a minimum one-second observation span. A prediction must overlap a detected vehicle; this rejects unsupported caption/background boxes but can also miss accidents when vehicles are obscured. Orange boxes show possible accident regions; personnel must review the evidence. Repeated detections of a persistent region are suppressed independently, so a distinct region need not wait for a camera-wide cooldown. Vehicle-motion rules are disabled by default and remain an optional experimental alert source. These mechanisms do not confirm a crash or its severity. The supplied checkpoint has not been independently evaluated on a labeled test set. See [model provenance and video verification](ACCIDENT_MODEL.md).

The supplied `bestw.pt` still fails the collision check on `accident.mp4.mp4`. The vehicle-context check removes the caption false alert seen in the [earlier verification](BESTW_VIDEO_VERIFICATION.md), but the actual collision remains undetected across all 324 frames. See the [current event-pipeline verification](EVENT_PIPELINE_VERIFICATION.md). The previous checkpoint's results remain in the [2026-10-01 diagnosis](ACCIDENT_DIAGNOSIS.md).

Red-light checks use the application's signal state, not recognition of an external traffic light. In each camera's settings, place the stop line on the actual road boundary and choose the travel direction. Down/up uses a horizontal line; left/right uses a vertical line. The tracker needs observations on both sides during the same red phase and retains a track for up to four seconds between detections. A vehicle first seen beyond the line is not sufficient evidence of a violation. For repeatable testing, choose the original video file with the camera's Video control; a webcam pointed at a phone screen adds glare, blur, and display artifacts. Detection quality depends on camera placement, calibration, footage, and hardware; this repository does not establish field accuracy or physical traffic-signal integration.

New incident and violation records, including evidence images, are saved locally before a background upload is attempted. Uploaded records are deduplicated in the history; the local backup survives a database outage. Failed uploads and historical local records are retained on the computer; there is no automatic retry/sync of those records. Authentication uses the application's custom users table; database access policies need review before deployment. Keep `.env`, credentials, and private incident evidence out of the public repository.

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
