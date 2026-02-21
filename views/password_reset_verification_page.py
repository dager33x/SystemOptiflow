# views/password_reset_verification_page.py
import tkinter as tk
from tkinter import messagebox
from .styles import Colors, Fonts, WidgetStyles


class PasswordResetVerificationPage(tk.Frame):
    """Password reset verification page"""
    
    def __init__(self, parent, email, username, on_verify_callback=None, on_back_callback=None):
        super().__init__(parent, bg=Colors.BACKGROUND)
        self.email = email
        self.username = username
        self.on_verify_callback = on_verify_callback
        self.on_back_callback = on_back_callback
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create verification page widgets"""
        # Main container
        main_container = tk.Frame(self, bg=Colors.BACKGROUND)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Left panel (Branding) - matching login page with security theme
        left_panel = tk.Frame(main_container, bg=Colors.CARD_BG, width=350)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        left_panel.pack_propagate(False)
        
        # Logo area
        logo_frame = tk.Frame(left_panel, bg=Colors.CARD_BG)
        logo_frame.pack(pady=60, expand=True, fill=tk.X)
        
        # Security icon with emphasis
        icon_container = tk.Frame(logo_frame, bg=Colors.CARD_BG)
        icon_container.pack(pady=(0, 10), fill=tk.X)
        
        # Large lock icon for security emphasis
        lock_icon = tk.Label(
            icon_container,
            text="🔐",
            font=("Segoe UI Emoji", 80),
            bg=Colors.CARD_BG,
            fg=Colors.DANGER,  # Red for security/warning emphasis
            justify=tk.CENTER
        )
        lock_icon.pack(anchor=tk.CENTER)
        
        # OptiFlow text
        title_label = tk.Label(
            logo_frame,
            text="OPTIFLOW",
            font=("Segoe UI", 28, "bold"),
            bg=Colors.CARD_BG,
            fg=Colors.TEXT,
            justify=tk.CENTER
        )
        title_label.pack(pady=(0, 2), anchor=tk.CENTER, fill=tk.X)
        
        # Subtitle with emphasis
        subtitle_label = tk.Label(
            logo_frame,
            text="Password Reset",
            font=("Segoe UI", 11),
            bg=Colors.CARD_BG,
            fg=Colors.TEXT_LIGHT,
            justify=tk.CENTER
        )
        subtitle_label.pack(anchor=tk.CENTER, fill=tk.X)
        
        # Security status indicators
        status_frame = tk.Frame(logo_frame, bg=Colors.CARD_BG)
        status_frame.pack(pady=45)
        
        # Security steps
        security_steps = [
            ("✓", Colors.SUCCESS, "Code Sent"),
            ("●", Colors.WARNING, "Verify Code"),
            ("○", Colors.TEXT_LIGHT, "New Password")
        ]
        
        for icon, color, label in security_steps:
            status_item = tk.Frame(status_frame, bg=Colors.CARD_BG)
            status_item.pack(pady=5)
            
            tk.Label(
                status_item,
                text=icon,
                font=("Arial", 14),
                bg=Colors.CARD_BG,
                fg=color
            ).pack(anchor=tk.CENTER)
            
            tk.Label(
                status_item,
                text=label,
                font=("Segoe UI", 9),
                bg=Colors.CARD_BG,
                fg=Colors.TEXT_LIGHT
            ).pack(anchor=tk.CENTER, pady=(2, 0))
        
        # Right panel (Form) - matching login page
        right_panel = tk.Frame(main_container, bg=Colors.BACKGROUND)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Form container (Card)
        form_container = tk.Frame(right_panel, bg=Colors.CARD_BG, padx=40, pady=40)
        form_container.pack(expand=True)
        
        # Title with security emphasis
        title = tk.Label(
            form_container,
            text="Reset Your Password",
            font=("Segoe UI", 24, "bold"),
            bg=Colors.CARD_BG,
            fg=Colors.TEXT
        )
        title.pack(pady=(0, 5), anchor=tk.W)
        
        # Subtitle
        subtitle = tk.Label(
            form_container,
            text=f"Enter the security code sent to {self.email}",
            font=("Segoe UI", 10),
            bg=Colors.CARD_BG,
            fg=Colors.TEXT_LIGHT
        )
        subtitle.pack(pady=(0, 30), anchor=tk.W)
        
        # Security notice
        notice_frame = tk.Frame(form_container, bg="#fff3cd", padx=15, pady=10)
        notice_frame.pack(fill=tk.X, pady=(0, 20))
        
        notice_icon = tk.Label(
            notice_frame,
            text="⚠️",
            font=("Segoe UI Emoji", 12),
            bg="#fff3cd",
            fg="#856404"
        )
        notice_icon.pack(side=tk.LEFT, padx=(0, 10))
        
        notice_text = tk.Label(
            notice_frame,
            text="For your security, this code expires in 15 minutes",
            font=("Segoe UI", 9),
            bg="#fff3cd",
            fg="#856404",
            justify=tk.LEFT
        )
        notice_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Verification code field
        tk.Label(
            form_container,
            text="Security Code",
            font=("Segoe UI", 10, "bold"),
            bg=Colors.CARD_BG,
            fg=Colors.TEXT
        ).pack(anchor=tk.W, pady=(0, 8))
        
        code_wrap = tk.Frame(form_container, bg=Colors.BACKGROUND, pady=1, padx=1)
        code_wrap.pack(fill=tk.X, pady=(0, 25))
        
        self.code_entry = tk.Entry(
            code_wrap,
            font=("Segoe UI", 14),
            bg=Colors.BACKGROUND,
            fg=Colors.TEXT,
            relief=tk.FLAT,
            bd=0,
            justify=tk.CENTER,
            insertbackground=Colors.PRIMARY
        )
        self.code_entry.insert(0, "Enter 6-digit code")
        self.code_entry.pack(fill=tk.X, ipady=12, padx=10)
        self.code_entry.config(fg=Colors.TEXT_LIGHT)
        
        # Focus events
        def on_code_focus_in(event):
            if self.code_entry.get() == "Enter 6-digit code":
                self.code_entry.delete(0, tk.END)
                self.code_entry.config(fg=Colors.TEXT)
        
        def on_code_focus_out(event):
            if self.code_entry.get() == "":
                self.code_entry.insert(0, "Enter 6-digit code")
                self.code_entry.config(fg=Colors.TEXT_LIGHT)
        
        self.code_entry.bind("<FocusIn>", on_code_focus_in)
        self.code_entry.bind("<FocusOut>", on_code_focus_out)
        
        # Verify button - using primary blue color
        verify_button = WidgetStyles.create_modern_button(
            form_container,
            text="Reset Password",
            command=self.verify_code,
            style='primary'
        )
        verify_button.pack(fill=tk.X, pady=(0, 20), ipady=2)
        
        # Footer
        footer_frame = tk.Frame(form_container, bg=Colors.CARD_BG)
        footer_frame.pack(fill=tk.X)
        
        back_button = tk.Button(
            footer_frame,
            text="← Back to Login",
            font=("Segoe UI", 9),
            bg=Colors.CARD_BG,
            fg=Colors.TEXT_LIGHT,
            activebackground=Colors.CARD_BG,
            activeforeground=Colors.PRIMARY,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=self.on_back_callback if self.on_back_callback else self.pack_forget
        )
        back_button.pack(side=tk.LEFT)
        
        # Help text
        help_text = tk.Label(
            footer_frame,
            text="Didn't receive code?",
            font=("Segoe UI", 9),
            bg=Colors.CARD_BG,
            fg=Colors.TEXT_LIGHT
        )
        help_text.pack(side=tk.RIGHT)
    
    def verify_code(self):
        """Verify reset code"""
        code = self.code_entry.get().strip()
        
        if not code or code == "Enter 6-digit code":
            messagebox.showwarning("Input Error", "Please enter the verification code")
            return
        
        if len(code) != 6 or not code.isdigit():
            messagebox.showwarning("Invalid Code", "Verification code must be 6 digits")
            return
        
        if self.on_verify_callback:
            self.on_verify_callback(self.email, code)
