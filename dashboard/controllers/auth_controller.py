# controllers/auth_controller.py
from dashboard.models.user import User
from dashboard.models.database import TrafficDB
from dashboard.utils.email_service import EmailService


class AuthController:
    """Handle authentication logic"""
    
    def __init__(self, db: TrafficDB, notifier=None):
        if notifier is None:
            from dashboard.services.tasks import Messages
            notifier = Messages()
        self.messages = notifier
        self.db = db
        self.current_user = None
        self.email_service = EmailService()
        self.pending_verification = {}  # Store pending registrations
    
    def register_user(self, first_name: str, last_name: str, username: str, email: str, password: str, 
                     role: str = "operator") -> bool:
        """Register a new user and send verification email"""
        if role != 'operator':
            self.messages.showerror('Registration', 'Public registration is for operator accounts only.')
            return False
        if len(password) < 6:
            self.messages.showerror('Registration', 'Password must contain at least 6 characters.')
            return False
        # Validate inputs
        if not first_name or not last_name or not username or not email or not password:
            self.messages.showerror("Error", "All fields are required")
            return False
        if not self._approval_ready():
            return False
        
        # Check if username is available
        if not self.db.check_username_available(username):
            self.messages.showerror("Error", "Username already exists")
            return False
        
        # Check if email is available
        if not self.db.check_email_available(email):
            self.messages.showerror("Error", "Email already exists")
            return False
        
        # Store pending registration
        password_hash = User.hash_password(password)
        self.pending_verification[email] = {
            'first_name': first_name,
            'last_name': last_name,
            'username': username,
            'email': email,
            'password_hash': password_hash,
            'role': role
        }
        
        # Send verification email
        success, code, email_sent = self.email_service.send_verification_email(email, username)
        if success:
            if not email_sent:
                # Fallback message for failed/unconfigured email
                msg = (
                    f"⚠️ Email delivery failed or not configured.\n\n"
                    f"Here is your verification code for testing:\n"
                    f"👉 {code}\n\n"
                    f"Please enter this code on the next screen."
                )
            else:
                # standard message
                msg = (
                    f"✅ Registration Successful!\n\n"
                    f"A verification code has been sent to:\n{email}\n\n"
                    f"⏱️ The code expires in 10 minutes.\n"
                    f"📧 Please check your email and enter the code on the next screen."
                )
            
            self.messages.showinfo("Verification", msg)
            return True
        else:
            del self.pending_verification[email]
            self.messages.showerror("Email delivery failed", self.email_service.last_error or
                                    "Unable to send the verification email. Please try again.")
            return False
    
    def verify_email(self, email: str, code: str) -> bool:
        """Verify email code and complete registration"""
        if email not in self.pending_verification:
            self.messages.showerror("Error", "No pending registration for this email")
            return False
        
        # Verify code
        is_valid, message = self.email_service.verify_code(email, code)
        
        if not is_valid:
            self.messages.showerror("Verification Error", message)
            return False
        
        # Create user
        pending = self.pending_verification[email]
        user_id, error_msg = self.db.create_user(
            pending['first_name'],
            pending['last_name'],
            pending['username'],
            pending['email'],
            pending['password_hash'],
            'operator', is_active=False, approval_status='pending'
        )
        
        if user_id:
            del self.pending_verification[email]
            self.messages.showsuccess('Pending approval',
                'Email verified. Your account is pending administrator approval. '
                'You can sign in after an administrator accepts your request.')
            return True
        else:
            self.messages.showerror("Error", f"Failed to create account: {error_msg}")
            return False
    
    def login(self, username: str, password: str) -> bool:
        """Authenticate user"""
        self.current_user = None
        # Validate inputs
        if not username or not password:
            self.messages.showerror("Error", "Please enter username and password")
            return False
        if not self._approval_ready():
            return False

        if not self.db.is_connected():
            self.messages.showerror(
                "Database unavailable",
                "The database client could not be initialized. Your account has not been checked.\n\n"
                "Check SUPABASE_URL and SUPABASE_KEY in the application's .env file "
                "or environment, then restart the application. If they are already "
                "configured, check the startup log for the initialization error."
            )
            return False
        
        # Hash password
        password_hash = User.hash_password(password)
        
        # Authenticate user
        user = self.db.check_user_credentials(username, password_hash)
        
        if user:
            status = User.get_approval_status(user)
            if status == 'pending':
                self.messages.showinfo('Pending approval',
                    'Your email is verified, but your account is still awaiting administrator approval.')
                return False
            if status == 'rejected':
                reason = user.get('rejection_reason') or 'Contact your administrator for details.'
                self.messages.showerror('Registration rejected', 'Your registration was rejected. ' + reason)
                return False
            if not User.can_sign_in(user):
                self.messages.showerror('Access unavailable', 'This account is not active or approved. Contact your administrator.')
                return False
            self.current_user = user
            return True
        else:
            self.messages.showerror("Error", "Invalid username or password")
            return False
    
    def reset_password(self, username: str, email: str) -> bool:
        """Send password reset email"""
        # Get user
        user = self.db.get_user_by_username(username)
        
        if not user:
            self.messages.showerror("Error", "User not found")
            return False
        
        # Verify email matches
        if user['email'].lower() != email.lower():
            self.messages.showerror("Error", "Email does not match username")
            return False
        
        # Store pending password reset
        self.pending_verification[f"reset_{user['email']}"] = {
            'username': username,
            'email': user['email'],
            'user_id': user['user_id']
        }
        
        # Send password reset email
        success, code, email_sent = self.email_service.send_password_reset_email(user['email'], username)
        if success:
            if not email_sent:
                # Fallback message
                msg = (
                    f"⚠️ Email delivery failed or not configured.\n\n"
                    f"Here is your reset code for testing:\n"
                    f"👉 {code}\n\n"
                    f"Please enter this code on the next screen."
                )
            else:
                # Show message without displaying the code
                msg = (
                    f"✅ Password Reset Initiated!\n\n"
                    f"A reset code has been sent to:\n{user['email']}\n\n"
                    f"⏱️ The code expires in 15 minutes.\n"
                    f"📧 Please check your email and enter the code on the next screen."
                )
                
            self.messages.showinfo("Reset Code", msg)
            return True
        else:
            del self.pending_verification[f"reset_{user['email']}"]
            self.messages.showerror("Email delivery failed", self.email_service.last_error or
                                    "Unable to send the password reset email. Please try again.")
            return False
    
    def verify_reset_code(self, email: str, code: str, new_password: str) -> bool:
        """Verify password reset code and update password"""
        key = f"reset_{email}"
        
        if key not in self.pending_verification:
            self.messages.showerror("Error", "No password reset request for this email")
            return False
        
        # Verify code
        is_valid, message = self.email_service.verify_reset_code(email, code)
        
        if not is_valid:
            self.messages.showerror("Verification Error", message)
            return False
        
        # Update password
        pending = self.pending_verification[key]
        password_hash = User.hash_password(new_password)
        
        success = self.db.update_user(pending['user_id'], password_hash=password_hash)
        
        if success:
            del self.pending_verification[key]
            self.messages.showsuccess("Success", "Password reset successfully! Please login with your new password.")
            return True
        else:
            self.messages.showerror("Error", "Failed to reset password")
            return False
    
    def logout(self):
        """Logout current user"""
        self.current_user = None
    
    def get_current_user(self):
        """Get current logged in user"""
        return self.current_user
    
    # Admin User Management

    def _approval_ready(self):
        if self.db.approval_schema_ready():
            return True
        self.messages.showerror('Registration unavailable',
            'The administrator needs to enable account approval in the database. '
            'If setup is complete, check the database connection and try again.')
        return False

    def _require_admin(self):
        user = self.current_user
        current = self.db.get_user_by_id(user['user_id']) if user and user.get('user_id') else None
        if not current or current.get('role') != 'admin' or not User.can_sign_in(current):
            self.messages.showerror('Administrator required', 'Only an active, approved administrator can manage users.')
            return False
        return True

    def review_user(self, user_id, decision, reason=''):
        if not self._require_admin():
            return False
        if user_id == self.current_user['user_id'] or decision not in ('approved', 'rejected'):
            self.messages.showerror('Invalid review', 'Select another pending account to approve or reject.')
            return False
        if decision == 'rejected' and not reason.strip():
            self.messages.showerror('Reason required', 'Enter a reason for rejecting this registration.')
            return False
        success = self.db.review_user(user_id, self.current_user['user_id'], decision, reason)
        if not success:
            self.messages.showerror('Review not saved',
                'The account may already have been reviewed. Refresh the list. '
                'If it is still pending, check database access and apply the account-approval migration.')
        return success
    
    def add_user(self, username: str, email: str, password: str, 
                role: str = "operator") -> bool:
        """Add new user (admin only)"""
        if not self._require_admin():
            return False
        # Validate inputs
        if not username or not email or not password:
            self.messages.showerror("Error", "All fields are required")
            return False
        
        # Check if username is available
        if not self.db.check_username_available(username):
            self.messages.showerror("Error", "Username already exists")
            return False
        
        # Check if email is available
        if not self.db.check_email_available(email):
            self.messages.showerror("Error", "Email already exists")
            return False
        
        # Hash password
        password_hash = User.hash_password(password)
        
        # Create user
        # Pass empty strings for first/last name for now as Admin UI doesn't support them yet
        if role not in ('operator', 'admin') or len(password) < 6:
            self.messages.showerror('Invalid account', 'Choose a valid role and a password of at least 6 characters.')
            return False
        user_id, error_msg = self.db.create_user("", "", username, email, password_hash, role,
                                              is_active=True, approval_status='approved')
        
        if not user_id and error_msg:
             self.messages.showerror("Error", f"Failed to add user: {error_msg}")
        
        return user_id is not None
    
    def get_all_users(self) -> list:
        """Get all users (admin only)"""
        if not self._require_admin():
            return []
        return self.db.get_all_users()
    
    def edit_user(self, user_id: str, email: str, role: str) -> bool:
        """Edit user information (admin only)"""
        if not self._require_admin() or role not in ('operator', 'admin'):
            return False
        if user_id == self.current_user['user_id'] and role != 'admin':
            return False
        return self.db.update_user(user_id, email=email, role=role)
    
    def delete_user(self, user_id: str) -> bool:
        """Delete user (admin only)"""
        if not self._require_admin() or user_id == self.current_user['user_id']:
            return False
        return self.db.delete_user(user_id)
