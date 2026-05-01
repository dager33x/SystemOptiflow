"""
Seed local JSON fallback data into Supabase.

Run once from the project root:
    python scripts/seed_to_supabase.py

Safe to re-run — upserts are idempotent on the primary key.
"""

import json
import os
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Maps local JSON file → (Supabase table, primary key column)
TABLE_CONFIG = [
    ("accidents.json",        "accidents",        "accident_id"),
    ("violations.json",       "violations",       "violation_id"),
    ("reports.json",          "reports",          "report_id"),
    ("emergency_events.json", "emergency_events", "event_id"),
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Supabase CHECK constraint only accepts: Minor | Moderate | Severe
_SEVERITY_MAP = {
    "low":      "Minor",
    "minor":    "Minor",
    "medium":   "Moderate",
    "moderate": "Moderate",
    "high":     "Severe",
    "severe":   "Severe",
    "critical": "Severe",
}

def _normalise_accident(record: dict) -> dict:
    """Coerce fields to match the Supabase accidents_severity_check constraint."""
    record = dict(record)
    raw = str(record.get("severity") or "Moderate").strip().lower()
    record["severity"] = _SEVERITY_MAP.get(raw, "Moderate")
    return record

total_upserted = 0
total_errors = 0

for filename, table, pk in TABLE_CONFIG:
    path = DATA_DIR / filename
    if not path.exists():
        print(f"  skip  {filename} (not found)")
        continue

    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  ERROR reading {filename}: {exc}")
        total_errors += 1
        continue

    if not isinstance(records, list) or not records:
        print(f"  skip  {filename} (empty)")
        continue

    # Per-table field normalisation
    if table == "accidents":
        records = [_normalise_accident(r) for r in records]

    print(f"\n[{table}] {len(records)} record(s) found in {filename}")

    # Batch upsert — Supabase upsert skips rows whose PK already exists
    try:
        response = (
            supabase.table(table)
            .upsert(records, on_conflict=pk)
            .execute()
        )
        upserted = len(response.data) if response.data else 0
        print(f"  OK  upserted {upserted} record(s) into {table}")
        total_upserted += upserted
    except Exception as exc:
        # Fall back to one-by-one if batch fails (e.g. type mismatch on one row)
        print(f"  batch upsert failed ({exc}), trying row-by-row...")
        ok = fail = 0
        for record in records:
            try:
                supabase.table(table).upsert(record, on_conflict=pk).execute()
                ok += 1
            except Exception as row_exc:
                print(f"    skip {record.get(pk, '?')}: {row_exc}")
                fail += 1
        print(f"  OK  {ok} upserted, {fail} failed")
        total_upserted += ok
        total_errors += fail

print(f"\n{'-' * 40}")
print(f"Done -- {total_upserted} record(s) seeded, {total_errors} error(s)")
