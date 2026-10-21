import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import AppManager
from controllers.auth_controller import AuthController
from models.database import DatabaseAuthenticationError, TrafficDB


class SignupWiringTests(unittest.TestCase):
    def test_signup_passes_all_fields_to_auth_and_verification(self):
        manager = AppManager.__new__(AppManager)
        manager.auth = Mock()
        manager.auth.register_user.return_value = True
        manager.show_email_verification_page = Mock()

        manager.handle_signup(
            "First",
            "Last",
            "operator1",
            "operator@example.com",
            "password123",
        )

        manager.auth.register_user.assert_called_once_with(
            "First",
            "Last",
            "operator1",
            "operator@example.com",
            "password123",
            role="operator",
        )
        manager.show_email_verification_page.assert_called_once_with(
            "operator@example.com",
            "operator1",
        )

    def test_disconnected_database_is_not_reported_as_bad_credentials(self):
        database = TrafficDB.__new__(TrafficDB)
        database.supabase = None
        database.logger = Mock()

        with self.assertRaises(DatabaseAuthenticationError):
            database.authenticate_user("operator1", "password-hash")

    def test_login_shows_database_error_when_authentication_is_unavailable(self):
        manager = AuthController.__new__(AuthController)
        manager.db = Mock()
        manager.db.authenticate_user.side_effect = DatabaseAuthenticationError()
        manager.current_user = None

        with patch("controllers.auth_controller.MessageBox.showerror") as show_error:
            self.assertFalse(manager.login("operator1", "password123"))

        show_error.assert_called_once()
        self.assertEqual(show_error.call_args.args[0], "Login unavailable")


if __name__ == "__main__":
    unittest.main()
