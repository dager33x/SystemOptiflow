# views/forgot_password_page.py
import tkinter as tk
from tkinter import messagebox
from .styles import Colors, WidgetStyles


class ForgotPasswordPage(tk.Frame):
    """Forgot password page"""
    
    def __init__(self, parent, on_reset_callback=None, on_back_callback=None):
        super().__init__(parent, bg="#f8fafc")
        self.on_reset_callback = on_reset_callback
        self.on_back_callback = on_back_callback
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create forgot password page widgets"""
        # Main container
        main_container = tk.Frame(self, bg=Colors.BACKGROUND)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Header with back button
        header_frame = tk.Frame(main_container, bg=Colors.BACKGROUND, height=60)
        header_frame.pack(fill=tk.X, pady=(10, 0))
        header_frame.pack_propagate(False)
        
        back_button = tk.Button(
            header_frame,
            text="← Back",
            font=("Segoe UI", 10, "bold"),
            bg=Colors.BACKGROUND,
            fg=Colors.TEXT,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            activebackground=Colors.BACKGROUND,
            activeforeground=Colors.PRIMARY,
            command=self.on_back_callback
        )
        back_button.pack(side=tk.LEFT, padx=20, pady=12)
        
        # Form container - centered card
        form_container = tk.Frame(main_container, bg=Colors.CARD_BG, padx=40, pady=40)
        form_container.pack(expand=True)
        
        # Title
        title_label = tk.Label(
            form_container,
            text="Reset Your Password",
            font=("Segoe UI", 24, "bold"),
            bg=Colors.CARD_BG,
            fg=Colors.TEXT
        )
        title_label.pack(pady=(0, 5))
        
        subtitle_label = tk.Label(
            form_container,
            text="Enter your details to receive reset code",
            font=("Segoe UI", 10),
            bg=Colors.CARD_BG,
            fg=Colors.TEXT_LIGHT
        )
        subtitle_label.pack(pady=(0, 25))
        
        # Username field
        user_wrap = self.create_styled_entry(form_container, "Username")
        user_wrap.pack(fill=tk.X, pady=(0, 20))
        self.username_entry = user_wrap.entry
        self.username_placeholder = "Username"
        
        # Email field
        email_wrap = self.create_styled_entry(form_container, "Email Address")
        email_wrap.pack(fill=tk.X, pady=(0, 25))
        self.email_entry = email_wrap.entry
        self.email_placeholder = "Email Address"
        
        # Send code button
        reset_button = WidgetStyles.create_modern_button(
            form_container,
            text="SEND RESET CODE",
            command=self.handle_reset,
            style='primary'
        )
        reset_button.pack(fill=tk.X, ipady=2)
        
    def create_styled_entry(self, parent, placeholder, is_password=False):
        """Create a styled entry with placeholder text"""
        container = tk.Frame(parent, bg=Colors.BACKGROUND, padx=1, pady=1)
        
        inner_frame = tk.Frame(container, bg=Colors.BACKGROUND)
        inner_frame.pack(fill=tk.BOTH, expand=True)
        
        entry = tk.Entry(
            inner_frame,
            font=("Segoe UI", 11),
            bg=Colors.BACKGROUND,
            fg=Colors.TEXT_LIGHT,
            relief=tk.FLAT,
            bd=0,
            insertbackground=Colors.PRIMARY
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=10)
        
        entry.insert(0, placeholder)
        
        def on_focus_in(event):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.config(fg=Colors.TEXT)
                if is_password:
                    entry.config(show="*")

        def on_focus_out(event):
            if not entry.get():
                if is_password:
                    entry.config(show="")
                entry.insert(0, placeholder)
                entry.config(fg=Colors.TEXT_LIGHT)
        
        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        
        container.entry = entry
        return container
    
    def handle_reset(self):
        """Handle password reset request"""
        username = self.username_entry.get().strip()
        email = self.email_entry.get().strip()
        
        # Filter placeholders
        if username == getattr(self, 'username_placeholder', ''):
            username = ""
        if email == getattr(self, 'email_placeholder', ''):
            email = ""
        
        if not username:
            messagebox.showwarning("Input Error", "Please enter username")
            return
        
        if not email:
            messagebox.showwarning("Input Error", "Please enter email address")
            return
        
        if '@' not in email:
            messagebox.showwarning("Input Error", "Please enter a valid email address")
            return
        
        if self.on_reset_callback:
            self.on_reset_callback(username, email)
