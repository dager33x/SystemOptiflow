"""Read-only check of incident workflow schema availability."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.models.database import TrafficDB

db = TrafficDB()
columns = ('review_status,response_status,reviewed_by,reviewed_by_name,reviewed_at,review_note,'
           'response_by,response_by_name,response_at,response_note,workflow_version,workflow_history')
try:
    db.supabase.table('accidents').select(columns).limit(1).execute()
except Exception as error:
    print(f'Incident workflow schema unavailable ({getattr(error, "code", type(error).__name__)}).')
    print('Run migrations/20260930_incident_workflow.sql in Supabase SQL Editor.')
    raise SystemExit(1)
print('All incident workflow fields are available. No records were changed.')
