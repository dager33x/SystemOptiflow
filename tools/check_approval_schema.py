"""Read-only approval schema check; never print user records or credentials."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard.models.database import TrafficDB

db = TrafficDB()
if not db.is_connected():
    print('Database connection unavailable. Apply migrations/20260930_user_approval.sql in Supabase SQL Editor.')
    raise SystemExit(1)
try:
    db.supabase.table('users').select('approval_status,is_active,reviewed_by,reviewed_at,rejection_reason').limit(1).execute()
except Exception as error:
    code = getattr(error, 'code', '')
    print(f'Approval schema is not ready (database code: {code or type(error).__name__}).')
    print('Apply migrations/20260930_user_approval.sql in Supabase SQL Editor, then rerun this check.')
    raise SystemExit(1)
print('All approval fields are available. No user records were changed.')
