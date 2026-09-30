"""Personnel review/response UI flow using fake incident data only."""
import os
from pathlib import Path
import sys
from unittest.mock import Mock, patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from dashboard.views.main_window import STYLE
from dashboard.views.incidents import IncidentPage
from dashboard.models.incident_workflow import normalize_incident, workflow_change


class Runner:
    def submit(self, function, callback):
        callback(function(), None)


app = QApplication([])
for font in ('segoeui.ttf', 'segoeuib.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
actor = {'user_id': 'operator', 'username': 'Officer Reyes', 'role': 'operator', 'approval_status': 'approved', 'is_active': True}
records = [normalize_incident({'accident_id': 'one', 'lane': 0, 'timestamp': '2026-09-30 09:10:00',
                              'description': 'Possible collision - review required.'}),
           normalize_incident({'accident_id': 'two', 'lane': 2, 'timestamp': '2026-09-30 09:15:00',
                              'description': 'Possible collision - review required.'})]
controller = Mock()
controller.accidents.get_incidents.side_effect = lambda: [dict(row) for row in records]
def update(incident_id, version, action, value, note):
    row = next(row for row in records if row['accident_id'] == incident_id)
    if row['workflow_version'] != version:
        raise ValueError('Another person updated this incident. Refresh.')
    row.update(workflow_change(row, actor, action, value, note))
    return row
controller.accidents.update_workflow.side_effect = update
page = IncidentPage(Mock(), controller, actor, Runner())
page.setStyleSheet(STYLE)
page.resize(1400, 650)
page.show()
page.reload()
assert page.summary.text() == '2 unreviewed  /  2 open'
assert not page.review_button.isEnabled()
page.table.selectRow(0)
assert page.review_button.isEnabled() and page.advance_button.isEnabled()
page.table.clearSelection()
assert not page.review_button.isEnabled() and not page.advance_button.isEnabled()
assert 'Select an incident' in page.action_hint.text()
page.table.selectRow(0)
# A failed asynchronous request must restore actions for the selected row.
class DeferredRunner:
    def submit(self, function, callback):
        self.callback = callback
deferred = DeferredRunner()
page.runner = deferred
page.run(lambda: None, lambda result: None)
assert not page.review_button.isEnabled()
deferred.callback(None, 'Temporary connection failure')
assert page.review_button.isEnabled() and page.advance_button.isEnabled()
page.runner = Runner()
with patch('dashboard.views.incidents.form', return_value={'decision': 'Confirmed', 'description': 'Camera and field report confirm a collision.'}):
    page.review_button.click()
assert records[0]['review_status'] == 'confirmed'
for expected in ('acknowledged', 'responding', 'resolved'):
    page.table.selectRow(0)
    with patch('dashboard.views.incidents.form', return_value={'description': f'Personnel action: {expected}.'}):
        page.advance_button.click()
    assert records[0]['response_status'] == expected
assert len(records[0]['workflow_history']) == 4
page.table.selectRow(1)
with patch('dashboard.views.incidents.form', return_value={'decision': 'False detection', 'description': 'Vehicles passed safely; overlapping boxes only.'}):
    page.review_button.click()
assert records[1]['response_status'] == 'resolved'
page.response_filter.setCurrentIndex(1)
assert not page.visible_rows
page.response_filter.setCurrentIndex(0)
page.table.selectRow(0)
assert not page.advance_button.isEnabled()
document = page.record_document(page.visible_rows[0])
assert 'Officer Reyes' in document and 'Activity history' in document and 'Personnel action: resolved.' in document
malicious = dict(page.visible_rows[0], review_note='<script>bad()</script>')
assert '<script>' not in page.record_document(malicious)
# Reopen a mistakenly dismissed alert for investigation.
page.table.selectRow(1)
with patch('dashboard.views.incidents.form', return_value={'decision': 'Needs investigation', 'description': 'Additional footage needs review.'}):
    page.review_button.click()
assert records[1]['response_status'] == 'pending'
page.table.selectRow(1)
app.processEvents()
page.grab().save(str(root / 'screenshots' / 'incident-workflow-preview.png'))
# Database migration absence must be visible and disable unsupported writes.
page.display([dict(records[0], _workflow_ready=False)])
page.table.selectRow(0)
assert page.setup_notice.isVisible()
assert not page.review_button.isEnabled()
assert not page.advance_button.isEnabled()
assert 'database setup' in page.action_hint.text()
# Refresh after applying the migration enables the selected record again.
page.reload()
page.table.selectRow(1)
assert not page.setup_notice.isVisible()
assert page.review_button.isEnabled() and page.advance_button.isEnabled()
page.close()
print('Confirm/dismiss, full response progression, reopen, filters, history, escaping and migration notice passed.')
