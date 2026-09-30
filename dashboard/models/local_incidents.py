"""Atomic local incident persistence with stable IDs and workflow history."""
import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4
from dashboard.models.incident_workflow import normalize_incident, workflow_change

_LOCK = RLock()


class LocalIncidents:
    def __init__(self, path):
        self.path = Path(path)

    def _write(self, rows):
        temporary = self.path.with_suffix('.json.tmp')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(rows, indent=2), encoding='utf-8')
        os.replace(temporary, self.path)

    def _read(self):
        if not self.path.exists():
            return []
        try:
            rows = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError('Invalid incident file')
        except (ValueError, OSError) as error:
            raise ValueError('Local incident file cannot be read. It has not been overwritten.') from error
        changed = False
        for row in rows:
            if not row.get('accident_id'):
                row['accident_id'] = 'local-' + str(uuid4())
                changed = True
        if changed:
            self._write(rows)
        return rows

    def read(self):
        with _LOCK:
            return [dict(normalize_incident(row), _storage='local') for row in self._read()]

    def append(self, row):
        with _LOCK:
            rows = self._read()
            rows.insert(0, normalize_incident(dict(row, accident_id='local-' + str(uuid4()))))
            self._write(rows)

    def update(self, incident_id, expected_version, actor, action, value, note):
        with _LOCK:
            rows = self._read()
            for row in rows:
                if row['accident_id'] == incident_id:
                    if row.get('workflow_version', 0) != expected_version:
                        raise ValueError('This incident changed. Refresh and review the latest state.')
                    row.update(workflow_change(row, actor, action, value, note))
                    self._write(rows)
                    return dict(row, _storage='local')
            raise ValueError('Local incident no longer exists. Refresh the list.')
