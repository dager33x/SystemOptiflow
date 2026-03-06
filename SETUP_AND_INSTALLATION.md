# SystemOptiflow Setup and Installation Guide

This guide provides step-by-step instructions for setting up the SystemOptiflow environment, installing dependencies, and running the application.

## 1. Prerequisites

Before you begin, ensure you have the following installed on your system:

*   **Python 3.9 or higher**: [Download Python](https://www.python.org/downloads/)
*   **Git**: [Download Git](https://git-scm.com/downloads)
*   **Supabase Account**: You will need a project URL and API Key from [Supabase](https://supabase.com).

## 2. Project Structure

Ensure your project folder contains the following necessary directories and files:

```text
SystemOptiflow/
├── controllers/          # Application logic and controllers
├── detection/            # Object detection (YOLO) and traffic logic
├── models/               # Database models and DQN models
├── utils/                # Utility scripts
├── views/                # UI components (pages, styles, widgets)
├── .env                  # Environment variables (To be created)
├── app.py                # Main entry point
├── requirements.txt      # Main Python dependencies
├── requirements_dqn.txt  # AI/ML dependencies
├── unified_schema.sql    # Database schema for Supabase
└── best.pt               # YOLO custom trained model weights
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

Install the required Python packages from both requirements files.

```powershell
pip install -r requirements.txt
pip install -r requirements_dqn.txt
```

### Step 4: Configure Environment Variables

Create a file named `.env` in the root directory (same folder as `app.py`).

**Command to create template (Windows):**
```powershell
New-Item -Path .env -ItemType File
```

Open the `.env` file and add your Supabase credentials. You need to replace the placeholders with your actual keys from the Supabase dashboard.

**Content of `.env`:**
```ini
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-anon-public-key
```

### Step 5: Database Setup

You need to set up the database tables in Supabase.

1.  Log in to your [Supabase Dashboard](https://supabase.com/dashboard).
2.  Go to the **SQL Editor**.
3.  Open the `unified_schema.sql` file in this project, copy its contents, and paste them into the SQL Editor.
4.  Click **Run** to create the necessary tables (`users`, `vehicles`, `violations`, `reports`, etc.).

## 4. Running the Application

Once everything is set up, you can start the application.

```powershell
python app.py
```

## 5. Troubleshooting

*   **Matplotlib Error**: If you see errors related to `matplotlib` or missing DLLs, try reinstalling it:
    ```powershell
    pip uninstall matplotlib
    pip install matplotlib
    ```
*   **Supabase Connection Error**: Double-check your `SUPABASE_URL` and `SUPABASE_KEY` in the `.env` file. Ensure there are no extra spaces or quotes around the values.
*   **Camera Issues**: If the simulated camera feed does not appear, check the logs in the terminal for any OpenCV errors. The system defaults to simulation mode if no physical camera is found, but it requires the `best.pt` file.

## 6. Developer Notes

*   **Adding New Pages**: Create new page classes in `views/pages/` and register them in `controllers/main_controller.py`.
*   **Modifying Traffic Logic**: check `detection/traffic_controller.py` for the traffic light timing logic.
