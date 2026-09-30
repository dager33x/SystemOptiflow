"""Incident triage, response actions, and a readable personnel audit trail."""
import html
from datetime import datetime, timezone
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QComboBox, QMessageBox
from dashboard.views.pages import RecordsPage, TablePage, button, form
from dashboard.views.widgets import LANE_NAMES
from dashboard.models.incident_workflow import REVIEWS, RESPONSES, normalize_incident


class IncidentPage(RecordsPage):
    def __init__(self, db, controller, user, runner):
        super().__init__('incidents', db, controller, user, runner)
        self.columns = [('detected_label', 'Detected (UTC)'), ('lane_name', 'Camera'), ('review_label', 'Review'),
                        ('response_label', 'Response'), ('response_by_name', 'Handled by'),
                        ('response_time_label', 'Last response (UTC)'), ('review_note', 'Review note')]
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels([label for _, label in self.columns])
        self.table.setStyleSheet('QTableWidget { alternate-background-color: #18263a; }')
        self.setup_notice = QLabel('Database workflow setup is required. Run migrations/20260930_incident_workflow.sql in Supabase SQL Editor, then Refresh.')
        self.setup_notice.setWordWrap(True)
        self.setup_notice.setStyleSheet('color: #ffbf69; padding: 8px;')
        self.setup_notice.hide()
        controls = QHBoxLayout()
        self.summary = QLabel()
        controls.addWidget(self.summary)
        self.review_filter = QComboBox()
        self.review_filter.addItem('All reviews', '')
        for key, label in REVIEWS.items():
            self.review_filter.addItem(label, key)
        self.response_filter = QComboBox()
        self.response_filter.addItem('All responses', '')
        self.response_filter.addItem('Open responses', 'open')
        for key, label in RESPONSES.items():
            self.response_filter.addItem(label, key)
        for combo in (self.review_filter, self.response_filter):
            controls.addWidget(combo)
            combo.currentIndexChanged.connect(self.filter_rows)
        controls.addStretch()
        self.review_button = button('Review incident', self.review_incident, controls)
        self.advance_button = button('Acknowledge', self.advance_response, controls)
        self.layout.insertLayout(2, controls)
        self.layout.insertWidget(3, self.setup_notice)
        self.action_hint = QLabel()
        self.action_hint.setWordWrap(True)
        self.layout.insertWidget(4, self.action_hint)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.table.currentCellChanged.connect(self.update_actions)
        self.update_actions()

    def reload(self):
        self.run(self.controller.accidents.get_incidents, self.display)

    @staticmethod
    def time_label(value):
        if not value:
            return ''
        try:
            instant = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if instant.tzinfo:
                instant = instant.astimezone(timezone.utc)
            return instant.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            return str(value)

    def display(self, rows):
        prepared = []
        for raw in rows or []:
            row = normalize_incident(raw)
            lane = row.get('lane')
            row['lane_name'] = LANE_NAMES[lane] if isinstance(lane, int) and 0 <= lane < 4 else str(lane)
            row['review_label'] = REVIEWS.get(row['review_status'], row['review_status'])
            row['response_label'] = RESPONSES.get(row['response_status'], row['response_status'])
            row['detected_label'] = self.time_label(row.get('timestamp'))
            row['response_time_label'] = self.time_label(row.get('response_at'))
            if row.get('_storage') == 'local':
                row['lane_name'] += ' (local)'
            prepared.append(row)
        pending = sum(row['review_status'] == 'unreviewed' for row in prepared)
        active = sum(row['response_status'] != 'resolved' for row in prepared)
        self.summary.setText(f'{pending} unreviewed  /  {active} open')
        self.setup_notice.setVisible(any(not row.get('_workflow_ready', True) for row in prepared))
        TablePage.display(self, prepared)
        self.status.setText(f'{len(prepared)} records loaded • All action times are UTC • Local records stay on this computer')

    def include_row(self, row):
        review = self.review_filter.currentData() if hasattr(self, 'review_filter') else ''
        response = self.response_filter.currentData() if hasattr(self, 'response_filter') else ''
        return (not review or row['review_status'] == review) and (
            not response or (response == 'open' and row['response_status'] != 'resolved')
            or row['response_status'] == response)

    def filter_rows(self):
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        super().filter_rows()
        for i, row in enumerate(self.visible_rows):
            color = {'unreviewed': '#ffbf69', 'confirmed': '#ff747c',
                     'false_detection': '#93a5bb', 'needs_investigation': '#8db9ff'}.get(row['review_status'], '#e8eef9')
            self.table.item(i, 2).setForeground(QColor(color))
            for column in range(self.table.columnCount()):
                self.table.item(i, column).setToolTip(self.table.item(i, column).text())
        self.update_actions()

    def update_actions(self, *args):
        if not hasattr(self, 'review_button'):
            return
        selected = self.table.selectionModel().selectedRows()
        i = selected[0].row() if selected else -1
        rows = getattr(self, 'visible_rows', [])
        row = rows[i] if 0 <= i < len(rows) else None
        allowed = bool(row and row.get('_workflow_ready', True) and self.user.get('role') in ('admin', 'operator') and not self.busy)
        self.review_button.setEnabled(allowed)
        response = row['response_status'] if row else 'pending'
        self.advance_button.setText({'pending': 'Acknowledge', 'acknowledged': 'Start responding',
                                     'responding': 'Resolve incident', 'resolved': 'Resolved'}.get(response, 'Advance response'))
        self.advance_button.setEnabled(allowed and response != 'resolved' and row['review_status'] != 'false_detection')
        if self.busy:
            reason = 'Working. Actions will be available when this operation finishes.'
        elif self.user.get('role') not in ('admin', 'operator'):
            reason = 'Only administrators and operators can review or handle incidents.'
        elif row is None:
            reason = 'Select an incident row to review it or acknowledge the response.'
        elif not row.get('_workflow_ready', True):
            reason = 'This incident needs database setup: run the incident-workflow SQL migration, then click Refresh.'
        elif response == 'resolved':
            reason = 'Response closed. Use Review incident to update the review or reopen for investigation.'
        else:
            reason = 'Review the detection or record the next response step. Each action requires a note.'
        self.action_hint.setText(reason)
        self.review_button.setToolTip(reason)
        self.advance_button.setToolTip(reason)

    def review_incident(self):
        if self.busy:
            return
        row = self.selected()
        if not row:
            return
        labels = [label for key, label in REVIEWS.items() if key not in ('unreviewed', row['review_status'])]
        data = form(self, 'Review incident — false detections close the response',
                    [('decision', 'Review decision', labels), ('description', 'Review note (required)', '')])
        if data:
            decision = next(key for key, label in REVIEWS.items() if label == data['decision'])
            self.save_action(row, 'review', decision, data['description'])

    def advance_response(self):
        if self.busy:
            return
        row = self.selected()
        if not row:
            return
        target = {'pending': 'acknowledged', 'acknowledged': 'responding', 'responding': 'resolved'}.get(row['response_status'])
        if not target:
            return
        if target == 'resolved' and row['review_status'] != 'confirmed':
            QMessageBox.information(self, 'Review required', 'Confirm the incident, or dismiss it as a false detection, before resolving it.')
            return
        data = form(self, f'Mark as {RESPONSES[target]}', [('description', 'Action taken / response note (required)', '')])
        if data:
            self.save_action(row, 'response', target, data['description'])

    def save_action(self, row, action, value, note):
        if not 1 <= len(note.strip()) <= 1000:
            QMessageBox.warning(self, 'Note required', 'Enter a note between 1 and 1,000 characters.')
            return
        def perform():
            try:
                updated = self.controller.accidents.update_workflow(row.get('accident_id'), row['workflow_version'], action, value, note)
                return updated, None
            except (ValueError, OSError) as error:
                return None, str(error)
        def complete(result):
            updated, error = result
            if error:
                self.status.setText(error)
            else:
                self.reload()
            self.update_actions()
        self.run(perform, complete)
        self.update_actions()

    def record_document(self, row):
        esc = lambda value: html.escape(str(value or '—'))
        fields = [('Camera', row.get('lane_name')), ('Detected', row.get('timestamp')),
                  ('Review', row.get('review_label')), ('Response', row.get('response_label')),
                  ('Detection description', row.get('description')), ('Reviewed by', row.get('reviewed_by_name')),
                  ('Reviewed at (UTC)', row.get('reviewed_at')), ('Review note', row.get('review_note')),
                  ('Last handled by', row.get('response_by_name')), ('Last response (UTC)', row.get('response_at')),
                  ('Response note', row.get('response_note')),
                  ('Storage', 'This computer only' if row.get('_storage') == 'local' else 'Database')]
        document = '<h1>Optiflow incident</h1>' + ''.join(f'<p><b>{label}:</b> {esc(value)}</p>' for label, value in fields)
        document += '<h2>Activity history (UTC)</h2>'
        for entry in row.get('workflow_history', []):
            document += (f'<p><b>{esc(entry.get("at"))} — {esc(entry.get("actor_name"))}</b><br>'
                f'Review: {esc(REVIEWS.get(entry.get("review_from")))} → {esc(REVIEWS.get(entry.get("review_to")))}<br>'
                f'Response: {esc(RESPONSES.get(entry.get("response_from")))} → {esc(RESPONSES.get(entry.get("response_to")))}<br>'
                f'{esc(entry.get("note"))}</p>')
        if not row.get('workflow_history'):
            document += '<p>No personnel actions have been recorded yet.</p>'
        return document
