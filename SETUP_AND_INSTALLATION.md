# SystemOptiflow Setup and Installation Guide

This guide provides step-by-step instructions for setting up the SystemOptiflow environment, installing dependencies, and running the application.

## 1. Prerequisites

Before you begin, ensure you have the following installed on your system:

*   **Python 3.10+**: [Download Python](https://www.python.org/downloads/)
*   **Git**: [Download Git](https://git-scm.com/downloads)
*   **Supabase Account (Optional)**: Only required if you want cloud database-backed pages (violations/reports/users) via [Supabase](https://supabase.com).
*   **Camera (Optional)**: If no physical camera is available, the app can still run, but camera-related features may be limited.

## 2. Project Structure (Current)

Ensure your project folder contains the following key directories and files:

```text
SystemOptiflow/
├── app.py                    # Main entry point
├── controllers/              # Application logic and controllers
├── detection/                # Object detection (YOLO) and traffic logic
├── models/                   # Database models (Supabase) and data models
├── utils/                    # Utility scripts (paths, email service, helpers)
├── views/                    # UI components (pages, styles, widgets)
├── requirements.txt          # Main Python dependencies
├── requirements_dqn.txt      # AI/ML dependencies (optional training-related)
├── unified_schema.sql        # Supabase database schema (recommended)
├── DATABASE_SETUP.md         # Schema + policies reference (readable docs)
├── supabase_guide/           # Manual Supabase connection guide
├── build.bat                 # Windows build helper (optional)
├── best.pt                   # YOLO custom trained model weights (optional)
└── .env / .env.example       # Local environment variables (DO NOT COMMIT .env)
```

## 3. Installation Steps

### Step 1: Open a Terminal

Navigate to the project directory:

```powershell
cd path\to\SystemOptiflow
```

### Step 2: Create a Virtual Environment (Recommended)

It is best practice to use a virtual environment to isolate dependencies.

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*Note: If you see a permission error, run `Set-ExecutionPolicy Unrestricted -Scope Process` first.*

**Mac/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies

Install the required Python packages.

```powershell
pip install -r requirements.txt
```

**Optional (Training / DQN extras):**

```powershell
pip install -r requirements_dqn.txt
```

### Step 4: Configure Environment Variables (Recommended)

Use the provided `.env.example` template and copy it to `.env` in the project root (same folder as `app.py`).

**Windows (PowerShell):**

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace placeholders with your own values.

**Minimum (Supabase optional):**

```ini
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-public-key
```

**Optional (Email verification / password reset):**

These are used by `utils/email_service.py`.

```ini
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=your_gmail_app_password
```

> Important: `.env` is meant to be local-only. Do not commit secrets.

### Step 5: Database Setup (Optional: Supabase)

You need to set up the database tables in Supabase.

1.  Log in to your [Supabase Dashboard](https://supabase.com/dashboard).
2.  Go to the **SQL Editor**.
3.  Use **one** of the following:
    - `unified_schema.sql` (recommended), or
    - `DATABASE_SETUP.md` (reference copy), or
    - `supabase_guide/CONNECT_MANUAL.md` (manual steps)
4.  Click **Run** to create the necessary tables (`users`, `vehicles`, `violations`, `accidents`, `reports`, `emergency_events`, `system_logs`, etc.).

## 4. Running the Application

Once everything is set up, you can start the application.

```powershell
python app.py
```

If you created the virtual environment at `.venv`, you can run with the explicit interpreter:

```powershell
.\.venv\Scripts\python.exe app.py
```

## 5. Troubleshooting

*   **Matplotlib Error**: If you see errors related to `matplotlib` or missing DLLs, try reinstalling it:
    ```powershell
    pip uninstall matplotlib
    pip install matplotlib
    ```
*   **Supabase Connection Error**: Double-check your `SUPABASE_URL` and `SUPABASE_KEY` in the `.env` file. Ensure there are no extra spaces or quotes around the values.
*   **Supabase Not Configured**: This is allowed — the app can run in UI-only mode, but database-backed pages may be empty/limited.
*   **Camera Issues**: If the camera feed does not appear, check the terminal logs for OpenCV errors and verify camera permissions/availability. Some detection features may require model weights (`best.pt`) depending on your configuration.
*   **Email Not Sending**: If email is not configured, the app may fall back to printing a verification code in the terminal (dev mode behavior).

## 6. Developer Notes

*   **Adding New Pages**: Create new page classes in `views/pages/` and register them in `controllers/main_controller.py`.
*   **Modifying Traffic Logic**: check `detection/traffic_controller.py` for the traffic light timing logic.
