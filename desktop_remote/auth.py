from tkinter import messagebox

from models.user import User

from .api_client import APIClientError, RemoteAPIClient


class RemoteAuthController:
    def __init__(self, client: RemoteAPIClient):
        self.client = client
        self.current_user = None

    def register_user(
        self,
        first_name: str,
        last_name: str,
        username: str,
        email: str,
        password: str,
        role: str = "operator",
    ) -> bool:
        try:
            payload = self.client.register_user(first_name, last_name, username, email, password, role)
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return False
        if payload.get("dev_code"):
            message = (
                f"Email delivery is unavailable.\n\n"
                f"Use this verification code:\n{payload['dev_code']}"
            )
        else:
            message = f"Verification code sent to:\n{email}"
        messagebox.showinfo("Verification", message)
        return True

    def verify_email(self, email: str, code: str) -> bool:
        try:
            self.client.verify_email(email, code)
        except APIClientError as exc:
            messagebox.showerror("Verification Error", str(exc))
            return False
        messagebox.showinfo("Success", "Account created successfully. Please log in.")
        return True

    def login(self, username: str, password: str) -> bool:
        try:
            self.current_user = self.client.login(username, password)
            return True
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return False

    def reset_password(self, username: str, email: str) -> bool:
        try:
            payload = self.client.request_password_reset(username, email)
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return False
        if payload.get("dev_code"):
            message = (
                f"Email delivery is unavailable.\n\n"
                f"Use this reset code:\n{payload['dev_code']}"
            )
        else:
            message = f"Password reset code sent to:\n{email}"
        messagebox.showinfo("Reset Code", message)
        return True

    def verify_reset_code(self, email: str, code: str, new_password: str) -> bool:
        try:
            self.client.reset_password(email, code, new_password)
        except APIClientError as exc:
            messagebox.showerror("Verification Error", str(exc))
            return False
        messagebox.showinfo("Success", "Password reset successfully.")
        return True

    def logout(self):
        try:
            self.client.logout()
        except APIClientError:
            pass
        self.current_user = None

    def get_current_user(self):
        return self.current_user

    def add_user(self, username: str, email: str, password: str, role: str = "operator") -> bool:
        if not username or not email or not password:
            messagebox.showerror("Error", "All fields are required")
            return False
        try:
            self.client.create_user(username, email, password, role)
            messagebox.showinfo("Success", f"User '{username}' created successfully.")
            return True
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return False

    def get_all_users(self) -> list:
        try:
            return self.client.list_users()
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return []

    def edit_user(self, user_id: str, email: str, role: str) -> bool:
        try:
            self.client.update_user(user_id, email=email, role=role)
            messagebox.showinfo("Success", "User updated successfully.")
            return True
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return False

    def delete_user(self, user_id: str) -> bool:
        try:
            self.client.delete_user(user_id)
            messagebox.showinfo("Success", "User deleted successfully.")
            return True
        except APIClientError as exc:
            messagebox.showerror("Error", str(exc))
            return False
