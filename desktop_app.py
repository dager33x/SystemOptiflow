# desktop_app.py
import tkinter as tk
from models.database import TrafficDB
from views.main_window import MainWindow
from views.login_page import LoginPage
from views.signup_page import SignupPage
from views.forgot_password_page import ForgotPasswordPage
from views.email_verification_page import EmailVerificationPage
from views.password_reset_verification_page import PasswordResetVerificationPage
from views.styles import Colors
from controllers.main_controller import MainController
from controllers.auth_controller import AuthController
from controllers.violation_controller import ViolationController
from controllers.accident_controller import AccidentController
from controllers.emergency_controller import EmergencyController
from desktop_remote import (
    APIClientError,
    DesktopClientProfile,
    RemoteAPIClient,
    RemoteAccidentController,
    RemoteAuthController,
    RemoteMainController,
    RemoteViolationController,
)


class AppManager:
    """Manage application flow and authentication"""

    def __init__(self, root):
        self.root = root
        self.root.withdraw()
        self.local_db = TrafficDB()
        self.local_auth = AuthController(self.local_db)
        self.db = self.local_db
        self.auth = self.local_auth
        self.client_profile = DesktopClientProfile()
        self.remote_client = None
        self.remote_auth = None
        self.remote_main_controller = None
        self.mode = "local"
        self.current_server_url = self._login_prefill_server_url()
        self.setup_window()
        self.show_login_page()
        self.root.deiconify()

    def _saved_server_url(self) -> str:
        return self.client_profile.last_server_url()

    def _login_prefill_server_url(self) -> str:
        saved_url = self._saved_server_url()
        should_prefill = self.client_profile.get("prefer_remote", bool(saved_url))
        return saved_url if saved_url and should_prefill else ""

    def _persist_remote_server_url(self, server_url: str) -> None:
        normalized = (server_url or "").strip()
        if normalized:
            self.client_profile.set_last_server_url(normalized)
            self.current_server_url = normalized

    def setup_window(self):
        self.root.title("OptiFlow - Traffic Management System")
        window_width = 851
        window_height = 545
        self.root.geometry(f"{window_width}x{window_height}")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_position = (screen_width - window_width) // 2
        y_position = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        self.root.configure(bg=Colors.BACKGROUND)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.root.quit)

    def set_auth_window_size(self):
        window_width = 851
        window_height = 545
        self.root.geometry(f"{window_width}x{window_height}")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_position = (screen_width - window_width) // 2
        y_position = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        self.root.resizable(False, False)

    def set_dashboard_window_size(self):
        window_width = 1600
        window_height = 900
        self.root.geometry(f"{window_width}x{window_height}")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_position = (screen_width - window_width) // 2
        y_position = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        self.root.resizable(True, True)

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def show_login_page(self, server_url=None):
        self.set_auth_window_size()
        self.clear_window()
        if server_url is None:
            self.current_server_url = self._login_prefill_server_url()
        else:
            self.current_server_url = (server_url or "").strip()
        login_page = LoginPage(
            self.root,
            on_login_callback=self.handle_login,
            on_signup_callback=self.show_signup_page,
            on_forgot_password_callback=self.show_forgot_password_page,
            initial_server_url=self.current_server_url,
        )
        login_page.pack(fill=tk.BOTH, expand=True)

    def show_signup_page(self, server_url=None):
        if server_url is not None:
            self.current_server_url = (server_url or "").strip()
        self.set_auth_window_size()
        self.clear_window()
        signup_page = SignupPage(
            self.root,
            on_signup_callback=self.handle_signup,
            on_back_callback=self.show_login_page,
        )
        signup_page.pack(fill=tk.BOTH, expand=True)

    def show_forgot_password_page(self, server_url=None):
        if server_url is not None:
            self.current_server_url = (server_url or "").strip()
        self.set_auth_window_size()
        self.clear_window()
        forgot_page = ForgotPasswordPage(
            self.root,
            on_reset_callback=self.handle_password_reset,
            on_back_callback=self.show_login_page,
        )
        forgot_page.pack(fill=tk.BOTH, expand=True)

    def _prepare_auth(self, server_url: str = ""):
        requested = (server_url or "").strip()
        if requested:
            self.mode = "remote"
            self.current_server_url = requested
            if not self.remote_client or self.remote_client.base_url != RemoteAPIClient(requested).base_url:
                self.remote_client = RemoteAPIClient(requested)
                self.remote_auth = RemoteAuthController(self.remote_client)
            self.auth = self.remote_auth
            self.db = None
        else:
            self.mode = "local"
            self.current_server_url = ""
            self.remote_client = None
            self.remote_auth = None
            self.auth = self.local_auth
            self.db = self.local_db

    def handle_login(self, username, password, server_url=""):
        try:
            self._prepare_auth(server_url)
        except APIClientError as exc:
            from tkinter import messagebox

            messagebox.showerror("Connection Error", str(exc))
            return
        if self.auth.login(username, password):
            if self.mode == "remote" and self.remote_client:
                self._persist_remote_server_url(self.remote_client.base_url)
            user = self.auth.get_current_user()
            self.show_main_dashboard(user)

    def handle_signup(self, first_name, last_name, username, email, password):
        try:
            self._prepare_auth(self.current_server_url)
        except APIClientError as exc:
            from tkinter import messagebox

            messagebox.showerror("Connection Error", str(exc))
            return
        if self.auth.register_user(first_name, last_name, username, email, password, role="operator"):
            self.show_email_verification_page(email, username)

    def show_email_verification_page(self, email, username):
        self.set_auth_window_size()
        self.clear_window()
        verification_page = EmailVerificationPage(
            self.root,
            email=email,
            username=username,
            on_verify_callback=self.handle_email_verification,
            on_back_callback=self.show_login_page,
        )
        verification_page.pack(fill=tk.BOTH, expand=True)

    def handle_email_verification(self, email, code):
        if self.auth.verify_email(email, code):
            self.show_login_page()

    def handle_password_reset(self, username, email):
        try:
            self._prepare_auth(self.current_server_url)
        except APIClientError as exc:
            from tkinter import messagebox

            messagebox.showerror("Connection Error", str(exc))
            return
        if self.auth.reset_password(username, email):
            self.show_password_reset_verification_page(email, username)

    def show_password_reset_verification_page(self, email, username):
        self.set_auth_window_size()
        self.clear_window()
        verification_page = PasswordResetVerificationPage(
            self.root,
            email=email,
            username=username,
            on_verify_callback=self.handle_reset_verification,
            on_back_callback=self.show_login_page,
        )
        verification_page.pack(fill=tk.BOTH, expand=True)

    def handle_reset_verification(self, email, code):
        import tkinter.simpledialog as simpledialog
        from tkinter import messagebox

        new_password = simpledialog.askstring(
            "Set New Password",
            "Enter your new password (minimum 6 characters):",
            show="*",
        )
        if not new_password:
            messagebox.showinfo("Cancelled", "Password reset cancelled")
            return
        if len(new_password) < 6:
            messagebox.showwarning("Invalid Password", "Password must be at least 6 characters")
            return
        if self.auth.verify_reset_code(email, code, new_password):
            messagebox.showinfo("Success", "Password has been reset successfully")
            self.show_login_page()

    def show_main_dashboard(self, current_user):
        self.set_dashboard_window_size()
        self.clear_window()
        container = tk.Frame(self.root, bg=Colors.BACKGROUND)
        container.pack(fill=tk.BOTH, expand=True)
        if self.mode == "remote":
            controllers = {
                "violation": RemoteViolationController(self.remote_client),
                "accident": RemoteAccidentController(self.remote_client),
                "emergency": None,
            }
            main_controller = RemoteMainController(
                root=container,
                view=None,
                client=self.remote_client,
                current_user=current_user,
                auth_controller=self.auth,
                on_logout_callback=self.handle_logout,
                violation_controller=controllers["violation"],
                accident_controller=controllers["accident"],
                connection_profile=self.client_profile,
            )
            self.remote_main_controller = main_controller
        else:
            controllers = {
                "violation": ViolationController(self.db),
                "accident": AccidentController(self.db),
                "emergency": EmergencyController(self.db),
            }
            main_controller = MainController(
                root=container,
                view=None,
                db=self.db,
                current_user=current_user,
                auth_controller=self.auth,
                on_logout_callback=self.handle_logout,
                violation_controller=controllers["violation"],
                accident_controller=controllers["accident"],
                connection_profile=self.client_profile,
            )
        controllers["main"] = main_controller
        view = MainWindow(container, controllers, current_user=current_user)
        main_controller.view = view
        main_controller.initialize_pages()
        main_controller.update_sidebar_navigation()
        main_controller.start_camera_feed()
        try:
            main_controller.handle_navigation("dashboard")
        except Exception as exc:
            print(f"Error loading dashboard: {exc}")

    def handle_logout(self):
        self.auth.logout()
        self.show_login_page()


def main():
    try:
        root = tk.Tk()
        AppManager(root)
        root.mainloop()
    except Exception as exc:
        print(f"Fatal error: {exc}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
