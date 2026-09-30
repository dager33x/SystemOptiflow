"""Offline account approval/access-control regression checks."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.controllers.auth_controller import AuthController
from dashboard.models.database import TrafficDB
from dashboard.models.user import User
from dashboard.services.tasks import Messages


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.db.is_connected.return_value = True
        self.db.approval_schema_ready.return_value = True
        self.messages = Messages()
        self.email = Mock()
        self.email.send_verification_email.return_value = (True, '123456', True)
        self.email.verify_code.return_value = (True, 'Verified')
        with patch('dashboard.controllers.auth_controller.EmailService', return_value=self.email):
            self.auth = AuthController(self.db, self.messages)
        self.admin = {'user_id': 'admin-id', 'role': 'admin', 'is_active': True, 'approval_status': 'approved'}

    def login(self, status, active=True):
        self.db.check_user_credentials.return_value = dict(user_id='new-user', role='operator',
            approval_status=status, is_active=active, rejection_reason='Unable to verify personnel affiliation.')
        return self.auth.login('personnel', 'password')

    def test_pending_login_blocked_even_if_active(self):
        self.assertFalse(self.login('pending'))
        self.assertIsNone(self.auth.current_user)
        self.assertIn('awaiting administrator', self.messages.items[-1][2])

    def test_rejected_login_shows_reason(self):
        self.assertFalse(self.login('rejected', False))
        self.assertIn('Unable to verify personnel', self.messages.items[-1][2])

    def test_approved_active_login_allowed(self):
        self.assertTrue(self.login('approved'))
        self.assertEqual(self.auth.current_user['user_id'], 'new-user')

    def test_inactive_and_unknown_status_denied(self):
        self.assertFalse(self.login('approved', False))
        self.assertFalse(self.login(None))
        self.assertFalse(self.login('anything'))

    def test_failed_login_clears_previous_session(self):
        self.auth.current_user = self.admin
        self.db.check_user_credentials.return_value = None
        self.assertFalse(self.auth.login('personnel', 'wrong'))
        self.assertIsNone(self.auth.current_user)
        self.assertEqual(self.messages.items[-1][2], 'Invalid username or password')

    def test_existing_accounts_keep_access(self):
        self.db.check_user_credentials.return_value = {'user_id': 'legacy', 'role': 'admin'}
        self.assertTrue(self.auth.login('legacy', 'password'))

    def test_verified_signup_is_inactive_pending_operator(self):
        self.db.create_user.return_value = ('new-id', None)
        self.assertTrue(self.auth.register_user('First', 'Last', 'personnel', 'p@example.test', 'password'))
        self.assertTrue(self.auth.verify_email('p@example.test', '123456'))
        self.assertEqual(self.db.create_user.call_args.args[-1], 'operator')
        self.assertEqual(self.db.create_user.call_args.kwargs, {'is_active': False, 'approval_status': 'pending'})
        self.assertIsNone(self.auth.current_user)
        self.assertIn('pending administrator approval', self.messages.items[-1][2])

    def test_public_signup_cannot_request_admin(self):
        self.assertFalse(self.auth.register_user('First', 'Last', 'personnel', 'p@example.test', 'password', 'admin'))
        self.email.send_verification_email.assert_not_called()

    def test_missing_schema_blocks_registration_before_email(self):
        self.db.approval_schema_ready.return_value = False
        self.assertFalse(self.auth.register_user('First', 'Last', 'personnel', 'p@example.test', 'password'))
        self.email.send_verification_email.assert_not_called()
        self.db.create_user.assert_not_called()

    def test_bad_verification_code_cannot_create_account(self):
        self.auth.pending_verification['p@example.test'] = {}
        self.email.verify_code.return_value = (False, 'Invalid code')
        self.assertFalse(self.auth.verify_email('p@example.test', 'wrong'))
        self.db.create_user.assert_not_called()

    def test_admin_can_review_pending_account(self):
        self.auth.current_user = self.admin
        self.db.get_user_by_id.return_value = self.admin
        self.db.review_user.return_value = True
        self.assertTrue(self.auth.review_user('pending-user', 'approved'))
        self.db.review_user.assert_called_once_with('pending-user', 'admin-id', 'approved', '')

    def test_reject_requires_reason_and_self_review_blocked(self):
        self.auth.current_user = self.admin
        self.db.get_user_by_id.return_value = self.admin
        self.assertFalse(self.auth.review_user('pending-user', 'rejected', ' '))
        self.assertFalse(self.auth.review_user('admin-id', 'approved'))
        self.db.review_user.assert_not_called()

    def test_operator_and_demoted_admin_cannot_manage_users(self):
        self.auth.current_user = self.admin
        self.db.get_user_by_id.return_value = dict(self.admin, role='operator')
        self.assertFalse(self.auth.review_user('pending-user', 'approved'))
        self.assertFalse(self.auth.add_user('new', 'new@example.test', 'password'))
        self.assertFalse(self.auth.edit_user('new', 'e@example.test', 'admin'))
        self.assertFalse(self.auth.delete_user('new'))
        self.assertEqual(self.auth.get_all_users(), [])
        self.db.review_user.assert_not_called()
        self.db.update_user.assert_not_called()

    def test_admin_created_account_is_explicitly_approved(self):
        self.auth.current_user = self.admin
        self.db.get_user_by_id.return_value = self.admin
        self.db.create_user.return_value = ('new', None)
        self.assertTrue(self.auth.add_user('new', 'new@example.test', 'password'))
        self.assertEqual(self.db.create_user.call_args.kwargs, {'is_active': True, 'approval_status': 'approved'})

    def test_password_reset_does_not_approve_account(self):
        self.auth.pending_verification['reset:p'] = {}  # unrelated entry ignored
        self.auth.pending_verification['reset_p@example.test'] = {'user_id': 'pending-user'}
        self.email.verify_reset_code.return_value = (True, 'Verified')
        self.db.update_user.return_value = True
        self.assertTrue(self.auth.verify_reset_code('p@example.test', '123456', 'new-password'))
        self.assertEqual(set(self.db.update_user.call_args.kwargs), {'password_hash'})


class DatabaseApprovalTests(unittest.TestCase):
    def setUp(self):
        self.db = TrafficDB.__new__(TrafficDB)
        self.db.logger = Mock()
        self.db.supabase = Mock()
        self.db.is_connected = Mock(return_value=True)
        self.query = self.db.supabase.table.return_value
        for name in ('select', 'eq', 'update', 'insert', 'limit'):
            getattr(self.query, name).return_value = self.query

    def test_new_user_payload_defaults_pending_and_inactive(self):
        self.query.execute.side_effect = [SimpleNamespace(data=[]), SimpleNamespace(data=[{'user_id': 'new'}])]
        self.assertEqual(self.db.create_user('First', 'Last', 'u', 'e', 'hash'), ('new', None))
        data = self.query.insert.call_args.args[0]
        self.assertEqual(data['approval_status'], 'pending')
        self.assertFalse(data['is_active'])

    def test_missing_column_never_falls_back_to_unrestricted_signup(self):
        self.query.execute.side_effect = [SimpleNamespace(data=[]), RuntimeError('approval_status column missing')]
        user_id, error = self.db.create_user('F', 'L', 'u', 'e', 'hash')
        self.assertIsNone(user_id)
        self.assertIn('migration', error)
        self.assertEqual(self.query.insert.call_count, 1)

    def test_review_is_conditional_and_records_reviewer(self):
        self.db.get_user_by_id = Mock(return_value={'role': 'admin', 'is_active': True, 'approval_status': 'approved'})
        self.query.execute.return_value = SimpleNamespace(data=[{'user_id': 'pending-user'}])
        self.assertTrue(self.db.review_user('pending-user', 'admin', 'rejected', 'Wrong office'))
        self.query.eq.assert_any_call('approval_status', 'pending')
        data = self.query.update.call_args.args[0]
        self.assertFalse(data['is_active'])
        self.assertEqual(data['reviewed_by'], 'admin')
        self.assertEqual(data['rejection_reason'], 'Wrong office')
        self.assertIn('reviewed_at', data)
        self.query.execute.return_value = SimpleNamespace(data=[])
        self.assertFalse(self.db.review_user('pending-user', 'admin', 'approved'))

    def test_direct_authentication_also_enforces_approval(self):
        self.db.check_user_credentials = Mock(return_value={'approval_status': 'pending', 'is_active': True})
        self.assertIsNone(self.db.authenticate_user('u', 'hash'))
        self.db.check_user_credentials.return_value['approval_status'] = 'approved'
        self.assertIsNotNone(self.db.authenticate_user('u', 'hash'))


if __name__ == '__main__':
    unittest.main()
