"""Qt report, incident, settings and administration pages."""
import csv
import html
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QTextEdit, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QMessageBox, QFileDialog, QAbstractItemView)
from dashboard.views.widgets import LANE_NAMES
from dashboard.models.user import User


def button(text, callback, layout):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    layout.addWidget(widget)
    return widget


def form(parent, title, fields):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(460)
    layout = QFormLayout(dialog)
    inputs = {}
    for key, label, value in fields:
        if isinstance(value, list):
            control = QComboBox()
            control.addItems(value)
        elif key == 'description':
            control = QTextEdit(str(value))
        else:
            control = QLineEdit(str(value))
            if 'password' in key:
                control.setEchoMode(QLineEdit.EchoMode.Password)
        inputs[key] = control
        layout.addRow(label, control)
    actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    actions.accepted.connect(dialog.accept)
    actions.rejected.connect(dialog.reject)
    layout.addRow(actions)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return {key: value.currentText() if isinstance(value, QComboBox) else
            value.toPlainText().strip() if isinstance(value, QTextEdit) else
            value.text() if 'password' in key else value.text().strip() for key, value in inputs.items()}


class TablePage(QWidget):
    def __init__(self, title, columns, runner):
        super().__init__()
        self.runner, self.columns, self.rows = runner, columns, []
        self.busy = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel(title)
        heading.setObjectName('title')
        self.layout.addWidget(heading)
        self.actions = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search records…')
        self.search.textChanged.connect(self.filter_rows)
        self.actions.addWidget(self.search, 1)
        button('Refresh', self.reload, self.actions)
        button('Export CSV', self.export_csv, self.actions)
        self.layout.addLayout(self.actions)
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels([label for _, label in columns])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.layout.addWidget(self.table, 1)
        self.status = QLabel('Ready')
        self.status.setWordWrap(True)
        self.layout.addWidget(self.status)

    def run(self, function, callback):
        if self.busy:
            return
        self.busy = True
        if hasattr(self, 'update_actions'):
            self.update_actions()
        self.status.setText('Working…')
        def complete(result, error):
            from shiboken6 import isValid
            if not isValid(self):
                return
            self.busy = False
            try:
                if error:
                    self.status.setText('Operation failed: ' + error)
                else:
                    callback(result)
            finally:
                if isValid(self) and hasattr(self, 'update_actions'):
                    self.update_actions()
        self.runner.submit(function, complete)

    def display(self, rows):
        self.rows = rows or []
        self.filter_rows()
        self.status.setText(f'{len(self.rows)} records')

    def filter_rows(self):
        query = self.search.text().lower()
        self.visible_rows = [row for row in self.rows if self.include_row(row) and
                            query in ' '.join(str(row.get(k, '')) for k, _ in self.columns).lower()]
        self.table.setRowCount(len(self.visible_rows))
        for i, row in enumerate(self.visible_rows):
            for j, (key, _) in enumerate(self.columns):
                self.table.setItem(i, j, QTableWidgetItem(str(row.get(key, ''))))

    def include_row(self, row):
        return True

    def selected(self):
        index = self.table.currentRow()
        if index < 0:
            QMessageBox.information(self, 'Select a record', 'Select a row first.')
            return None
        return self.visible_rows[index]

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export CSV', 'optiflow-report.csv', 'CSV (*.csv)')
        if path:
            try:
                with open(path, 'w', newline='', encoding='utf-8-sig') as stream:
                    writer = csv.writer(stream)
                    writer.writerow([label for _, label in self.columns])
                    for row in self.visible_rows:
                        values = [str(row.get(key, '')) for key, _ in self.columns]
                        writer.writerow(["'"+v if v.startswith(('=', '+', '-', '@')) else v for v in values])
                self.status.setText('Exported ' + path)
            except OSError as error:
                QMessageBox.warning(self, 'Export failed', str(error))


class RecordsPage(TablePage):
    def __init__(self, kind, db, controller, user, runner):
        self.kind, self.db, self.controller, self.user = kind, db, controller, user
        columns = {'issues': [('title', 'Title'), ('priority', 'Priority'), ('status', 'Status'), ('author_name', 'Author'), ('created_at', 'Created')],
                   'incidents': [('timestamp', 'Time'), ('lane', 'Lane'), ('severity', 'Severity'), ('description', 'Description')],
                   'violations': [('timestamp', 'Time'), ('lane', 'Lane'), ('violation_type', 'Violation'), ('vehicle_id', 'Vehicle')]}
        super().__init__({'issues': 'Issue Reports', 'incidents': 'Incident History', 'violations': 'Violation Logs'}[kind], columns[kind], runner)
        button('View details', self.details, self.actions)
        self.table.cellDoubleClicked.connect(lambda row, col: self.details())
        if kind == 'issues':
            button('New report', self.create_report, self.actions)
        elif kind != 'incidents' and user.get('role') == 'admin':
            button('Clear records', self.clear_records, self.actions)

    def reload(self):
        loader = {'issues': self.db.get_all_reports, 'incidents': self.controller.accidents.get_incidents,
                  'violations': self.controller.violations.get_logs}[self.kind]
        def loaded(rows):
            if self.kind == 'incidents':
                # The DB severity enum has no "unassessed" value. Do not present
                # its compatibility value as an AI assessment of crash severity.
                rows = [dict(row, severity='Needs review')
                        if str(row.get('description', '')).startswith('Possible collision - review required.')
                        else row for row in (rows or [])]
            self.display(rows)
            if not self.db.is_connected():
                self.status.setText('Database unavailable. Showing available local records.')
        self.run(loader, loaded)

    def create_report(self):
        data = form(self, 'Create issue report', [('title', 'Title', ''), ('description', 'Description', ''),
                    ('priority', 'Priority', ['Low', 'Medium', 'High', 'Critical'])])
        if data is None:
            return
        if not data['title'] or not data['description']:
            QMessageBox.warning(self, 'Required fields', 'Enter a title and description.')
            return
        self.run(lambda: self.db.create_report(**data, author_id=self.user.get('user_id'),
                 author_name=self.user.get('username', 'User')), self._saved)

    def _saved(self, success):
        if success:
            self.reload()
        else:
            self.status.setText('Save failed. Check the database connection and permissions.')

    def clear_records(self):
        if self.user.get('role') != 'admin':
            return
        if QMessageBox.question(self, 'Clear records', 'Permanently remove these records and their local screenshots?') != QMessageBox.StandardButton.Yes:
            return
        operation = self.controller.accidents.clear_incidents if self.kind == 'incidents' else self.controller.violations.clear_logs
        self.run(operation, self._saved)

    def details(self):
        row = self.selected()
        if row is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Record details')
        dialog.resize(760, 650)
        layout = QVBoxLayout(dialog)
        document = self.record_document(row)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(document)
        layout.addWidget(text, 1)
        source = row.get('image_url')
        if source:
            path = Path(source)
            if not path.is_file():
                path = Path(__file__).resolve().parents[2] / source
            if path.is_file():
                preview = QLabel()
                preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
                preview.setPixmap(QPixmap(str(path)).scaled(680, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                layout.addWidget(preview)
                document += f'<img src="{html.escape(path.as_uri())}" width="580">'
            else:
                layout.addWidget(QLabel('Screenshot is not available on this computer.'))
        actions = QHBoxLayout()
        def export_pdf():
            path, _ = QFileDialog.getSaveFileName(dialog, 'Save PDF', 'optiflow-record.pdf', 'PDF (*.pdf)')
            if path:
                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(path)
                report = QTextDocument()
                report.setHtml(document)
                report.print_(printer)
        button('Export PDF', export_pdf, actions)
        button('Close', dialog.accept, actions)
        layout.addLayout(actions)
        dialog.exec()

    def record_document(self, row):
        return '<h1>Optiflow — Record details</h1>' + ''.join(
            f'<p><b>{html.escape(str(key).replace("_", " ").title())}:</b> {html.escape(str(value))}</p>'
            for key, value in row.items() if key != 'image_url')


class TrafficChart(QWidget):
    def __init__(self):
        super().__init__()
        self.counts = [0]*4
        self.setMinimumHeight(240)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()/4
        maximum = max(10, max(self.counts))
        for i, count in enumerate(self.counts):
            height = (self.height()-70)*count/maximum
            x = int(i*width+width*.23)
            painter.fillRect(x, int(self.height()-40-height), int(width*.54), int(height), QColor('#3987ff'))
            painter.setPen(QColor('#b9cce4'))
            painter.drawText(x, self.height()-15, LANE_NAMES[i])
            painter.drawText(x, int(self.height()-48-height), str(count))


class TrafficPage(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        title = QLabel('Traffic Reports')
        title.setObjectName('title')
        layout.addWidget(title)
        layout.addWidget(QLabel('Live queue counts by approach'))
        self.summary = QLabel()
        self.summary.setStyleSheet('font-size: 20px; padding: 20px 0;')
        layout.addWidget(self.summary)
        self.chart = TrafficChart()
        layout.addWidget(self.chart, 1)
        self.phase = QLabel()
        layout.addWidget(self.phase)

    def update_live(self, lanes):
        counts = [lane.vehicles for lane in lanes]
        self.chart.counts = counts
        self.chart.update()
        busiest = LANE_NAMES[counts.index(max(counts))] if sum(counts) else 'None'
        recorder = self.controller.workers.recorder
        self.summary.setText(f'Vehicles: {sum(counts)}     Busiest: {busiest}     Session violations: {recorder.violation_count if recorder else 0}')
        self.phase.setText(self.controller.store.summary()[3])


class UsersPage(TablePage):
    def __init__(self, auth, user, runner):
        self.auth, self.user = auth, user
        super().__init__('Manage Users', [('full_name', 'Full name'), ('username', 'Username'),
            ('email', 'Email'), ('role', 'Role'), ('approval_status', 'Approval'),
            ('created_at', 'Registered'), ('rejection_reason', 'Rejection reason')], runner)
        self.table.setStyleSheet('QTableWidget { alternate-background-color: #18263a; }')
        review_row = QHBoxLayout()
        self.pending_count = QLabel('Pending approvals: 0')
        self.pending_count.setStyleSheet('color: #ffbf69; font-weight: 600;')
        review_row.addWidget(self.pending_count)
        self.approval_filter = QComboBox()
        for label, value in (('All accounts', ''), ('Pending', 'pending'), ('Approved', 'approved'), ('Rejected', 'rejected')):
            self.approval_filter.addItem(label, value)
        self.approval_filter.currentIndexChanged.connect(self.filter_rows)
        review_row.addWidget(self.approval_filter)
        review_row.addStretch()
        self.approve_button = button('Approve account', lambda: self.review_account('approved'), review_row)
        self.approve_button.setStyleSheet('color: #34d399; border: 1px solid #26735d;')
        self.reject_button = button('Reject account', lambda: self.review_account('rejected'), review_row)
        self.reject_button.setStyleSheet('color: #ff747c; border: 1px solid #763d49;')
        self.layout.insertLayout(2, review_row)
        self.table.itemSelectionChanged.connect(self._review_selection)
        button('Add user', self.add_user, self.actions)
        button('Edit user', self.edit_user, self.actions)
        button('Delete user', self.delete_user, self.actions)
        self._review_selection()

    def display(self, rows):
        rows = [dict(row, full_name=' '.join(filter(None, (row.get('first_name'), row.get('last_name')))),
                     approval_status=User.get_approval_status(row)) for row in (rows or [])]
        rows.sort(key=lambda row: row['approval_status'] != 'pending')
        self.pending_count.setText(f'Pending approvals: {sum(row["approval_status"] == "pending" for row in rows)}')
        super().display(rows)
        self._review_selection()

    def include_row(self, row):
        selected = self.approval_filter.currentData() if hasattr(self, 'approval_filter') else ''
        return not selected or row.get('approval_status') == selected

    def filter_rows(self):
        # Never retain a selection after a filter maps the row index to another user.
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        super().filter_rows()
        for index, row in enumerate(self.visible_rows):
            color = {'pending': '#ffbf69', 'approved': '#34d399', 'rejected': '#ff747c'}.get(row.get('approval_status'))
            if color:
                self.table.item(index, 4).setForeground(QColor(color))
        self._review_selection()

    def _review_selection(self):
        if not hasattr(self, 'approve_button'):
            return
        index = self.table.currentRow()
        rows = getattr(self, 'visible_rows', [])
        row = rows[index] if 0 <= index < len(rows) else {}
        allowed = (self.user.get('role') == 'admin' and row.get('approval_status') == 'pending'
                   and row.get('user_id') != self.user.get('user_id') and not self.busy)
        self.approve_button.setEnabled(allowed)
        self.reject_button.setEnabled(allowed)

    def review_account(self, decision):
        if self.busy or self.user.get('role') != 'admin':
            return
        row = self.selected()
        if not row or row.get('approval_status') != 'pending' or row.get('user_id') == self.user.get('user_id'):
            return
        reason = ''
        if decision == 'rejected':
            data = form(self, f'Reject {row["username"]}', [('reason', 'Reason (shown at sign-in)', '')])
            if data is None:
                return
            reason = data['reason'].strip()
            if not reason or len(reason) > 500:
                QMessageBox.warning(self, 'Rejection reason', 'Enter a reason between 1 and 500 characters.')
                return
        elif QMessageBox.question(self, 'Approve account',
                f'Allow {row["username"]} to sign in as {row.get("role", "operator")}?') != QMessageBox.StandardButton.Yes:
            return
        self.run(lambda: self.auth.review_user(row['user_id'], decision, reason), self.saved)
        self._review_selection()

    def reload(self):
        if self.user.get('role') == 'admin':
            self.run(self.auth.get_all_users, self.display)

    def saved(self, success):
        messages = self.auth.messages.items[:]
        self.auth.messages.items.clear()
        if success:
            self.reload()
        else:
            self.status.setText(messages[-1][2] if messages else 'Operation failed; check database access.')
        self._review_selection()

    def add_user(self):
        if self.user.get('role') != 'admin':
            return
        data = form(self, 'Add user', [('username', 'Username', ''), ('email', 'Email', ''),
                    ('password', 'Password', ''), ('role', 'Role', ['operator', 'admin'])])
        if data:
            if len(data['password']) < 6:
                QMessageBox.warning(self, 'Password', 'Use at least 6 characters.')
                return
            self.run(lambda: self.auth.add_user(**data), self.saved)

    def edit_user(self):
        if self.user.get('role') != 'admin':
            return
        row = self.selected()
        if not row:
            return
        role = row.get('role', 'operator')
        data = form(self, 'Edit user', [('email', 'Email', row.get('email', '')),
                    ('role', 'Role', [role] + [r for r in ('operator', 'admin') if r != role])])
        if data:
            if row['user_id'] == self.user['user_id'] and data['role'] != 'admin':
                QMessageBox.warning(self, 'Current account', 'Use another administrator account to change your own role.')
                return
            self.run(lambda: self.auth.edit_user(row['user_id'], **data), self.saved)

    def delete_user(self):
        if self.user.get('role') != 'admin':
            return
        row = self.selected()
        if not row:
            return
        if row['user_id'] == self.user['user_id']:
            QMessageBox.warning(self, 'Current account', 'You cannot delete the account currently signed in.')
            return
        if QMessageBox.question(self, 'Delete user', f'Delete {row["username"]}?') == QMessageBox.StandardButton.Yes:
            self.run(lambda: self.auth.delete_user(row['user_id']), self.saved)
