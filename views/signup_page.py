# views/signup_page.py
import tkinter as tk
from tkinter import messagebox
import re
from .styles import Colors, WidgetStyles


class SignupPage(tk.Frame):
    """Signup/Create Account page"""
    
    def __init__(self, parent, on_signup_callback=None, on_back_callback=None):
        super().__init__(parent, bg="#f8fafc")
        self.on_signup_callback = on_signup_callback
        self.on_back_callback = on_back_callback
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create signup page widgets"""
        # Main container
        main_container = tk.Frame(self, bg=Colors.BACKGROUND)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Center container
        center_frame = tk.Frame(main_container, bg=Colors.BACKGROUND)
        center_frame.pack(expand=True, fill=tk.BOTH)
        
        # Form card - centered
        form_card = tk.Frame(center_frame, bg=Colors.CARD_BG, padx=40, pady=30)
        form_card.pack(expand=True)
        
        # Title
        title_label = tk.Label(
            form_card,
            text="Create Account",
            font=("Segoe UI", 24, "bold"),
            bg=Colors.CARD_BG,
            fg=Colors.TEXT
        )
        title_label.pack(pady=(0, 15))
        
        # Subtitle with "Sign in" link
        subtitle_frame = tk.Frame(form_card, bg=Colors.CARD_BG)
        subtitle_frame.pack(pady=(0, 30))
        
        tk.Label(
            subtitle_frame,
            text="Have an account already? ",
            font=("Segoe UI", 10),
            bg=Colors.CARD_BG,
            fg=Colors.TEXT_LIGHT
        ).pack(side=tk.LEFT)
        
        signin_link = tk.Label(
            subtitle_frame,
            text="Sign in",
            font=("Segoe UI", 10, "bold"),
            bg=Colors.CARD_BG,
            fg=Colors.PRIMARY,
            cursor="hand2"
        )
        signin_link.pack(side=tk.LEFT)
        signin_link.bind("<Button-1>", lambda e: self.on_back_callback())
        
        # --- Form Fields ---
        
        # Name Row (First Name | Last Name)
        name_row = tk.Frame(form_card, bg=Colors.CARD_BG)
        name_row.pack(fill=tk.X, pady=(0, 20))
        
        # First Name
        fn_wrap = self.create_styled_entry(name_row, "First Name")
        fn_wrap.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.first_name_entry = fn_wrap.entry
        self.first_name_placeholder = "First Name"
        
        # Last Name
        ln_wrap = self.create_styled_entry(name_row, "Last Name")
        ln_wrap.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        self.last_name_entry = ln_wrap.entry
        self.last_name_placeholder = "Last Name"
        
        # Username
        user_wrap = self.create_styled_entry(form_card, "Username")
        user_wrap.pack(fill=tk.X, pady=(0, 20))
        self.username_entry = user_wrap.entry
        self.username_placeholder = "Username"
        
        # Email
        email_wrap = self.create_styled_entry(form_card, "Email")
        email_wrap.pack(fill=tk.X, pady=(0, 20))
        self.email_entry = email_wrap.entry
        self.email_placeholder = "Email"
        
        # Password
        pass_wrap = self.create_styled_entry(form_card, "Password", is_password=True)
        pass_wrap.pack(fill=tk.X, pady=(0, 20))
        self.password_entry = pass_wrap.entry
        self.password_placeholder = "Password"
        
        # Confirm Password
        confirm_wrap = self.create_styled_entry(form_card, "Repeat Password", is_password=True)
        confirm_wrap.pack(fill=tk.X, pady=(0, 30))
        self.confirm_password_entry = confirm_wrap.entry
        self.confirm_password_placeholder = "Repeat Password"
        
        # Signup button
        signup_button = WidgetStyles.create_modern_button(
            form_card,
            text="Sign up",
            command=self.handle_signup,
            style='primary'
        )
        signup_button.pack(fill=tk.X, ipady=2)



    def create_styled_entry(self, parent, placeholder, is_password=False):
        """Create a styled entry with placeholder text and optional eye icon"""
        # Outer container (Border/Background)
        container = tk.Frame(parent, bg=Colors.BACKGROUND, padx=1, pady=1)
        
        # Inner frame (Content)
        inner_frame = tk.Frame(container, bg=Colors.BACKGROUND)
        inner_frame.pack(fill=tk.BOTH, expand=True)
        
        # Entry widget
        entry = tk.Entry(
            inner_frame,
            font=("Segoe UI", 11),
            bg=Colors.BACKGROUND,
            fg=Colors.TEXT_LIGHT, # Placeholder color
            relief=tk.FLAT,
            bd=0,
            insertbackground=Colors.PRIMARY
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(10, 5))
        
        # Set placeholder
        entry.insert(0, placeholder)
        
        # State tracking
        entry.placeholder_text = placeholder
        entry.password_visible = False
        
        def on_focus_in(event):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.config(fg=Colors.TEXT)
                if is_password and not entry.password_visible:
                    entry.config(show="*")

        def on_focus_out(event):
            if not entry.get():
                if is_password:
                    entry.config(show="")
                entry.insert(0, placeholder)
                entry.config(fg=Colors.TEXT_LIGHT)
        
        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        
        # Eye Icon for Password
        if is_password:
            def toggle_visibility():
                # Don't toggle if placeholder is showing
                if entry.get() == placeholder:
                    return

                entry.password_visible = not entry.password_visible
                if entry.password_visible:
                    entry.config(show="")
                else:
                    entry.config(show="*")
            
            eye_btn = tk.Button(
                inner_frame,
                text="👁️",
                font=("Segoe UI", 12),
                bg=Colors.BACKGROUND,
                fg=Colors.TEXT_LIGHT,
                relief=tk.FLAT,
                bd=0,
                cursor="hand2",
                activebackground=Colors.BACKGROUND,
                activeforeground=Colors.PRIMARY,
                command=toggle_visibility
            )
            eye_btn.pack(side=tk.RIGHT, padx=5)
            
            # Update eye button color on hover for better UX
            def on_enter(e): eye_btn.config(fg=Colors.PRIMARY)
            def on_leave(e): eye_btn.config(fg=Colors.TEXT_LIGHT)
            eye_btn.bind("<Enter>", on_enter)
            eye_btn.bind("<Leave>", on_leave)

        container.entry = entry
        return container



    
    def handle_signup(self):
        """Handle signup button click"""
        first_name = self.first_name_entry.get().strip()
        last_name = self.last_name_entry.get().strip()
        username = self.username_entry.get().strip()
        email = self.email_entry.get().strip()
        password = self.password_entry.get()
        confirm_password = self.confirm_password_entry.get()
        
        # Filter placeholders
        if first_name == getattr(self, 'first_name_placeholder', ''):
            first_name = ""
        if last_name == getattr(self, 'last_name_placeholder', ''):
            last_name = ""
        if username == getattr(self, 'username_placeholder', ''):
            username = ""
        if email == getattr(self, 'email_placeholder', ''):
            email = ""
        
        # Passwords might be "Password" or "Repeat Password" if type is text, but for show="*" entries 
        # the .get() usually returns the actual text. 
        # However, my placeholder logic toggles show="*" depending on focus.
        # If the user hasn't typed anything, it shows "Password" (text mode). 
        # So .get() will return "Password".
        if password == getattr(self, 'password_placeholder', ''):
            password = ""
        if confirm_password == getattr(self, 'confirm_password_placeholder', ''):
            confirm_password = ""
        
        # Validation
        if not first_name:
            messagebox.showwarning("Input Error", "Please enter first name")
            return
            
        if not last_name:
            messagebox.showwarning("Input Error", "Please enter last name")
            return

        if not username:
            messagebox.showwarning("Input Error", "Please enter username")
            return
        
        if len(username) < 3:
            messagebox.showwarning("Input Error", "Username must be at least 3 characters")
            return
        
        if not email:
            messagebox.showwarning("Input Error", "Please enter email")
            return
        
        # Email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            messagebox.showwarning("Input Error", "Please enter a valid email")
            return
        
        if not password:
            messagebox.showwarning("Input Error", "Please enter password")
            return
        
        if len(password) < 6:
            messagebox.showwarning("Input Error", "Password must be at least 6 characters")
            return
        
        if password != confirm_password:
            messagebox.showwarning("Input Error", "Passwords do not match")
            return
        
        if self.on_signup_callback:
            self.on_signup_callback(first_name, last_name, username, email, password)
