"""Durable violation logs independent of the working directory and network."""
import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

_LOCK = RLock()


class LocalViolations:
    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        if not self.path.exists():
            return []
        rows = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Invalid local violation file; it has not been overwritten.')
        return rows

    def _write(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(rows, indent=2), encoding='utf-8')
        os.replace(temporary, self.path)

    def read(self):
        with _LOCK:
            return self._read()

    def append(self, row):
        with _LOCK:
            rows = self._read()
            saved = dict(row, violation_id='local-' + str(uuid4()))
            rows.insert(0, saved)
            self._write(rows)
            return saved

    def mark_uploaded(self, local_id, remote_id):
        with _LOCK:
            rows = self._read()
            for row in rows:
                if row.get('violation_id') == local_id:
                    row['_remote_id'] = remote_id
                    break
            self._write(rows)
