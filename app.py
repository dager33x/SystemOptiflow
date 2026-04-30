# app.py
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


class AppManager:
    """Manage application flow and authentication"""
    
    def __init__(self, root):
        self.root = root
        self.root.withdraw()  # Hide initially
        
        # Initialize database
        self.db = TrafficDB()
        
        # Initialize auth controller
        self.auth = AuthController(self.db)
        
        # Setup window
        self.setup_window()
        
        # Show login page
        self.show_login_page()
        
        # Show window
        self.root.deiconify()
    
    def setup_window(self):
        """Configure root window"""
        self.root.title("OptiFlow - Traffic Management System")
        
        # Set window size to 851x545 for auth pages
        window_width = 851
        window_height = 545
        self.root.geometry(f"{window_width}x{window_height}")
        
        # Center window on screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_position = (screen_width - window_width) // 2
        y_position = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        
        from views.styles import Colors
        self.root.configure(bg=Colors.BACKGROUND)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # Disable resize for auth pages
        self.root.resizable(False, False)
        
        # Configure close button
        def on_close():
            self.root.quit()
        
        self.root.protocol("WM_DELETE_WINDOW", on_close)
    
    def set_auth_window_size(self):
     
        window_width = 851
        window_height = 545
        self.root.geometry(f"{window_width}x{window_height}")
        
        # Center window on screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_position = (screen_width - window_width) // 2
        y_position = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        
        self.root.resizable(False, False)
    
    def set_dashboard_window_size(self):
        """Set window size for dashboard (full screen)"""
        window_width = 1600
        window_height = 900
        self.root.geometry(f"{window_width}x{window_height}")
        
        # Center window on screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_position = (screen_width - window_width) // 2
        y_position = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        
        self.root.resizable(True, True)
    
    def clear_window(self):
        """Clear all widgets from window"""
        for widget in self.root.winfo_children():
            widget.destroy()
    
    def show_login_page(self):
        """Show login page"""
        self.set_auth_window_size()
        self.clear_window()
        
        login_page = LoginPage(
            self.root,
            on_login_callback=self.handle_login,
            on_signup_callback=self.show_signup_page,
            on_forgot_password_callback=self.show_forgot_password_page
        )
        login_page.pack(fill=tk.BOTH, expand=True)
    
    def show_signup_page(self):
        """Show signup page"""
        self.set_auth_window_size()
        self.clear_window()
        
        signup_page = SignupPage(
            self.root,
            on_signup_callback=self.handle_signup,
            on_back_callback=self.show_login_page
        )
        signup_page.pack(fill=tk.BOTH, expand=True)
    
    def show_forgot_password_page(self):
        """Show forgot password page"""
        self.set_auth_window_size()
        self.clear_window()
        
        forgot_page = ForgotPasswordPage(
            self.root,
            on_reset_callback=self.handle_password_reset,
            on_back_callback=self.show_login_page
        )
        forgot_page.pack(fill=tk.BOTH, expand=True)
    
    def handle_login(self, username, password):
        """Handle login"""
        if self.auth.login(username, password):
            user = self.auth.get_current_user()
            
            # Route to unified main dashboard
            self.show_main_dashboard(user)
        # Error message is shown by auth controller
    
    def handle_signup(self, first_name, last_name, username, email, password):
        """Handle signup - send verification email"""
        if self.auth.register_user(first_name, last_name, username, email, password, role="operator"):
            # Show email verification page
            self.show_email_verification_page(email, username)
        # Error message is shown by auth controller
    
    def show_email_verification_page(self, email, username):
        """Show email verification page"""
        self.set_auth_window_size()
        self.clear_window()
        
        verification_page = EmailVerificationPage(
            self.root,
            email=email,
            username=username,
            on_verify_callback=self.handle_email_verification,
            on_back_callback=self.show_login_page
        )
        verification_page.pack(fill=tk.BOTH, expand=True)
    
    def handle_email_verification(self, email, code):
        """Handle email verification"""
        if self.auth.verify_email(email, code):
            self.show_login_page()
    
    def handle_password_reset(self, username, email):
        """Handle password reset request - send verification email"""
        if self.auth.reset_password(username, email):
            # Show password reset verification page
            self.show_password_reset_verification_page(email, username)
        # Error message is shown by auth controller
    
    def show_password_reset_verification_page(self, email, username):
        """Show password reset verification page"""
        self.set_auth_window_size()
        self.clear_window()
        
        verification_page = PasswordResetVerificationPage(
            self.root,
            email=email,
            username=username,
            on_verify_callback=self.handle_reset_verification,
            on_back_callback=self.show_login_page
        )
        verification_page.pack(fill=tk.BOTH, expand=True)
    
    def handle_reset_verification(self, email, code):
        """Handle password reset code verification"""
        # Get new password from user - show password entry dialog
        import tkinter.simpledialog as simpledialog
        new_password = simpledialog.askstring(
            "Set New Password",
            "Enter your new password (minimum 6 characters):",
            show="*"
        )
        
        if not new_password:
            from tkinter import messagebox
            messagebox.showinfo("Cancelled", "Password reset cancelled")
            return
        
        if len(new_password) < 6:
            from tkinter import messagebox
            messagebox.showwarning("Invalid Password", "Password must be at least 6 characters")
            return
        
        # Verify code and reset password
        if self.auth.verify_reset_code(email, code, new_password):
            from tkinter import messagebox
            messagebox.showinfo("Success", "Password has been reset successfully")
            self.show_login_page()
        # Error message is shown by auth controller
    
    def show_main_dashboard(self, current_user):
        """Show main dashboard with traffic monitoring and dynamic role features"""
        self.set_dashboard_window_size()
        self.clear_window()
        
        # Create main container
        container = tk.Frame(self.root, bg=Colors.BACKGROUND)
        container.pack(fill=tk.BOTH, expand=True)
        
        # Initialize sub-controllers
        controllers = {
            'violation': ViolationController(self.db),
            'accident': AccidentController(self.db),
            'emergency': EmergencyController(self.db)
        }
        
        # Initialize main controller with required dependencies
        main_controller = MainController(
            root=container,
            view=None,
            db=self.db,
            current_user=current_user,
            auth_controller=self.auth,
            on_logout_callback=self.handle_logout,
            violation_controller=controllers['violation'],
            accident_controller=controllers['accident']
        )
        controllers['main'] = main_controller
        
        # Initialize unified main window
        view = MainWindow(container, controllers, current_user=current_user)
        
        # Update main controller with view reference and start application loops
        main_controller.view = view
        main_controller.initialize_pages()
        main_controller.update_sidebar_navigation()
        main_controller.start_camera_feed()
        
        # Show initial page
        try:
            main_controller.handle_navigation('dashboard')
        except Exception as e:
            print(f"Error loading dashboard: {e}")
    
    def handle_logout(self):
        """Handle logout"""
        self.auth.logout()
        self.show_login_page()


def main():
    """Main application entry point"""
    
    try:
        # Initialize root window
        root = tk.Tk()
        
        # Initialize app manager (handles auth flow)
        app = AppManager(root)
        
        # Run application
        root.mainloop()
        
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
