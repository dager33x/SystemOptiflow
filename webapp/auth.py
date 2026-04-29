import os
from typing import Any, Dict

from models.user import User
from utils.email_service import EmailService


class AuthError(Exception):
    pass


class AuthService:
    """HTTP-safe authentication and verification service."""

    def __init__(self, db, persistence):
        self.db = db
        self.persistence = persistence
        self.email_service = EmailService()
        self.demo_username = os.getenv("DEMO_USERNAME", "admin")
        self.demo_password = os.getenv("DEMO_PASSWORD", "admin123")
        self.demo_role = os.getenv("DEMO_ROLE", "admin")

    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        if not username or not password:
            raise AuthError("Username and password are required.")
        password_hash = User.hash_password(password)
        if self.db and self.db.is_connected():
            user = self.db.authenticate_user(username, password_hash)
            if not user:
                raise AuthError("Invalid username or password.")
            return user

        if username == self.demo_username and password == self.demo_password:
            return {
                "user_id": "demo-user",
                "username": self.demo_username,
                "email": "demo@example.com",
                "role": self.demo_role,
            }
        raise AuthError("Database is unavailable and demo credentials did not match.")

    def register_user(
        self,
        first_name: str,
        last_name: str,
        username: str,
        email: str,
        password: str,
        role: str = "operator",
    ) -> Dict[str, Any]:
        if not self.db or not self.db.is_connected():
            raise AuthError("Registration requires a configured database connection.")
        if not all([first_name, last_name, username, email, password]):
            raise AuthError("All registration fields are required.")
        if not self.db.check_username_available(username):
            raise AuthError("Username already exists.")
        if not self.db.check_email_available(email):
            raise AuthError("Email already exists.")

        code = self.email_service.generate_verification_code()
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "email": email,
            "password_hash": User.hash_password(password),
            "role": role,
        }
        self.persistence.store_verification_code(email, username, code, "signup", payload, expires_minutes=10)
        _, _, email_sent = self.email_service.send_verification_email(email, username, code=code)
        return {
            "message": "Verification code generated.",
            "email_sent": email_sent,
            "dev_code": None if email_sent else code,
        }

    def verify_registration(self, email: str, code: str) -> Dict[str, Any]:
        record = self.persistence.get_verification_code(email, code, "signup")
        if not record:
            raise AuthError("Verification code is invalid or expired.")
        payload = record["payload"]
        user_id, error = self.db.create_user(
            payload["first_name"],
            payload["last_name"],
            payload["username"],
            payload["email"],
            payload["password_hash"],
            payload["role"],
        )
        if not user_id:
            raise AuthError(error or "Failed to create user.")
        self.persistence.consume_verification_code(record["verification_id"])
        return {"message": "Account verified successfully.", "user_id": user_id}

    def request_password_reset(self, username: str, email: str) -> Dict[str, Any]:
        if not self.db or not self.db.is_connected():
            raise AuthError("Password reset requires a configured database connection.")
        user = self.db.get_user_by_username(username)
        if not user or user.get("email", "").lower() != email.lower():
            raise AuthError("Username and email did not match.")
        code = self.email_service.generate_verification_code()
        payload = {"user_id": user["user_id"], "username": username}
        self.persistence.store_verification_code(email, username, code, "reset_password", payload, expires_minutes=15)
        _, _, email_sent = self.email_service.send_password_reset_email(email, username, code=code)
        return {
            "message": "Password reset code generated.",
            "email_sent": email_sent,
            "dev_code": None if email_sent else code,
        }

    def reset_password(self, email: str, code: str, new_password: str) -> Dict[str, Any]:
        if not self.db or not self.db.is_connected():
            raise AuthError("Password reset requires a configured database connection.")
        if len(new_password) < 6:
            raise AuthError("Password must be at least 6 characters.")
        record = self.persistence.get_verification_code(email, code, "reset_password")
        if not record:
            raise AuthError("Password reset code is invalid or expired.")
        payload = record["payload"]
        success = self.db.update_user(payload["user_id"], password_hash=User.hash_password(new_password))
        if not success:
            raise AuthError("Failed to update the password.")
        self.persistence.consume_verification_code(record["verification_id"])
        return {"message": "Password reset successful."}
