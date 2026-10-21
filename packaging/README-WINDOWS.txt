SYSTEMOPTIFLOW - WINDOWS 64-BIT

1. Extract the entire ZIP to a folder on your computer.
2. Keep SystemOptiflow.exe together with the _internal folder.
3. Double-click SystemOptiflow.exe. No Python installation or NVIDIA graphics
   card is required. This release includes CPU inference dependencies.

FIRST-TIME SETUP
For sign-in and shared records, copy .env.example to .env beside the EXE.
Ask your administrator for the existing Supabase project configuration.
For email verification and password resets, configure the SMTP settings on
the operator's computer. Never post that .env file or SMTP password online.
The release deliberately contains no database or email credentials.
Existing account approval and database migrations are still required.

To explore the dashboard without an account or database, double-click
Preview.cmd. This starts simulation mode and does not save real incidents.

LOCAL DATA
Logs, screenshots, and local records are stored in:
  %LOCALAPPDATA%\SystemOptiflow
Close the app before installing a new release. Extract the new ZIP into
a new folder and copy your private .env file beside the new EXE.
Your per-user local records remain in the location above.

TROUBLESHOOTING
Extract the ZIP before launching; do not run the EXE from inside the ZIP.
If Windows blocks an unsigned download, verify its source and SHA256 checksum
with your administrator. This build has no code-signing certificate.
For startup problems, check dashboard.log and console.log in the data folder.
Detection performance depends on your CPU, footage, and camera settings.

SOURCE
https://github.com/dager33x/SystemOptiflow/tree/new-update
