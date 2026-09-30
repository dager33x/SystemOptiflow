"""Exercise admin approval controls offscreen using fake users and decisions."""
import os
from pathlib import Path
import sys
from unittest.mock import Mock, patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFontDatabase
from dashboard.views.pages import UsersPage
from dashboard.views.main_window import STYLE
from dashboard.services.tasks import Messages


class ImmediateRunner:
    def submit(self, function, callback):
        callback(function(), None)


app = QApplication([])
for font in ('segoeui.ttf', 'segoeuib.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
admin = {'user_id': 'admin', 'username': 'Administrator', 'role': 'admin', 'approval_status': 'approved'}
users = [dict(admin, email='admin@example.test', first_name='System', last_name='Admin'),
         {'user_id': 'pending1', 'username': 'j.santos', 'email': 'santos@example.test', 'first_name': 'Jamie', 'last_name': 'Santos',
          'role': 'operator', 'approval_status': 'pending', 'created_at': '2026-09-30'},
         {'user_id': 'pending2', 'username': 'm.reyes', 'email': 'reyes@example.test', 'first_name': 'Morgan', 'last_name': 'Reyes',
          'role': 'operator', 'approval_status': 'pending', 'created_at': '2026-09-30'}]
auth = Mock()
auth.messages = Messages()
auth.get_all_users.side_effect = lambda: [dict(user) for user in users]
def review(user_id, decision, reason):
    row = next(user for user in users if user['user_id'] == user_id)
    row.update(approval_status=decision, rejection_reason=reason)
    return True
auth.review_user.side_effect = review
page = UsersPage(auth, admin, ImmediateRunner())
page.setStyleSheet(STYLE)
page.resize(1280, 650)
page.show()
page.reload()
assert page.pending_count.text() == 'Pending approvals: 2'
assert not page.approve_button.isEnabled()
page.table.selectRow(0)
assert page.approve_button.isEnabled() and page.reject_button.isEnabled()
app.processEvents()
page.grab().save(str(root / 'screenshots' / 'user-approval-preview.png'))
with patch('dashboard.views.pages.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
    page.approve_button.click()
assert users[1]['approval_status'] == 'approved'
assert page.pending_count.text() == 'Pending approvals: 1'
page.approval_filter.setCurrentIndex(1)
assert len(page.visible_rows) == 1 and not page.approve_button.isEnabled()
page.table.selectRow(0)
with patch('dashboard.views.pages.form', return_value={'reason': 'Personnel affiliation could not be verified.'}):
    page.reject_button.click()
assert users[2]['approval_status'] == 'rejected'
assert page.pending_count.text() == 'Pending approvals: 0'
assert not page.visible_rows
page.approval_filter.setCurrentIndex(3)
assert len(page.visible_rows) == 1
page.table.selectRow(0)
assert not page.approve_button.isEnabled() and not page.reject_button.isEnabled()
page.close()
print('Pending list, count, selection guards, approve/reject actions, refresh and filters passed.')
