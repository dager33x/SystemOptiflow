import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
import re
from .styles import Colors

class SignupPage(ctk.CTkFrame):
    """Modern Signup/Create Account page using CustomTkinter"""
    
    def __init__(self, parent, on_signup_callback=None, on_back_callback=None):
        super().__init__(parent, fg_color=Colors.BACKGROUND)
        self.on_signup_callback = on_signup_callback
        self.on_back_callback = on_back_callback
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create signup page widgets"""
        # Form Card - centered
        form_card = ctk.CTkFrame(self, fg_color=Colors.CARD_BG, corner_radius=15, border_width=1, border_color="#2c3a52")
        form_card.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        # Internal padding
        inner = ctk.CTkFrame(form_card, fg_color="transparent")
        inner.pack(padx=50, pady=40, fill=tk.BOTH, expand=True)
        
        # Title
        ctk.CTkLabel(inner, text="Create Account", font=("Segoe UI", 26, "bold"), text_color="white").pack(pady=(0, 5))
        
        # Subtitle with "Sign in" link
        subtitle_frame = ctk.CTkFrame(inner, fg_color="transparent")
        subtitle_frame.pack(pady=(0, 30))
        
        ctk.CTkLabel(subtitle_frame, text="Have an account already? ", font=("Segoe UI", 12), text_color=Colors.TEXT_MUTED).pack(side=tk.LEFT)
        
        signin_link = ctk.CTkButton(subtitle_frame, text="Sign in", font=("Segoe UI", 12, "bold"), text_color=Colors.PRIMARY,
                                    fg_color="transparent", hover_color=Colors.BACKGROUND, width=60, height=20,
                                    command=self.on_back_callback)
        signin_link.pack(side=tk.LEFT)
        
        # --- Form Fields ---
        
        # Name Row (First Name | Last Name)
        name_row = ctk.CTkFrame(inner, fg_color="transparent")
        name_row.pack(fill=tk.X, pady=(0, 20))
        
        self.first_name_entry = ctk.CTkEntry(name_row, placeholder_text="First Name", height=40, corner_radius=8, 
                                             border_width=1, border_color="#2c3a52", fg_color="#0f1522", font=("Segoe UI", 12))
        self.first_name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.last_name_entry = ctk.CTkEntry(name_row, placeholder_text="Last Name", height=40, corner_radius=8, 
                                            border_width=1, border_color="#2c3a52", fg_color="#0f1522", font=("Segoe UI", 12))
        self.last_name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Username
        self.username_entry = ctk.CTkEntry(inner, placeholder_text="Username", height=40, corner_radius=8, 
                                           border_width=1, border_color="#2c3a52", fg_color="#0f1522", font=("Segoe UI", 12))
        self.username_entry.pack(fill=tk.X, pady=(0, 20))
        
        # Email
        self.email_entry = ctk.CTkEntry(inner, placeholder_text="Email", height=40, corner_radius=8, 
                                        border_width=1, border_color="#2c3a52", fg_color="#0f1522", font=("Segoe UI", 12))
        self.email_entry.pack(fill=tk.X, pady=(0, 20))
        
        # Password
        pass_wrap = ctk.CTkFrame(inner, fg_color="#0f1522", corner_radius=8, border_width=1, border_color="#2c3a52", height=40)
        pass_wrap.pack(fill=tk.X, pady=(0, 20))
        pass_wrap.pack_propagate(False)
        
        self.password_entry = ctk.CTkEntry(pass_wrap, placeholder_text="Password", show="*",
                                           height=38, border_width=0, 
                                           fg_color="transparent", font=("Segoe UI", 12))
        self.password_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.show_pwd = False
        self.eye_btn1 = ctk.CTkButton(pass_wrap, text="👁️", width=30, height=30, fg_color="transparent", 
                                      hover_color="#161f33", text_color=Colors.TEXT_MUTED, font=("Segoe UI Emoji", 14), 
                                      command=self.toggle_password)
        self.eye_btn1.pack(side=tk.RIGHT, padx=5)
        
        # Confirm Password
        confirm_wrap = ctk.CTkFrame(inner, fg_color="#0f1522", corner_radius=8, border_width=1, border_color="#2c3a52", height=40)
        confirm_wrap.pack(fill=tk.X, pady=(0, 30))
        confirm_wrap.pack_propagate(False)
        
        self.confirm_password_entry = ctk.CTkEntry(confirm_wrap, placeholder_text="Repeat Password", show="*",
                                                   height=38, border_width=0, 
                                                   fg_color="transparent", font=("Segoe UI", 12))
        self.confirm_password_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.show_confirm_pwd = False
        self.eye_btn2 = ctk.CTkButton(confirm_wrap, text="👁️", width=30, height=30, fg_color="transparent", 
                                      hover_color="#161f33", text_color=Colors.TEXT_MUTED, font=("Segoe UI Emoji", 14), 
                                      command=self.toggle_confirm_password)
        self.eye_btn2.pack(side=tk.RIGHT, padx=5)
        
        # Signup button
        signup_button = ctk.CTkButton(inner, text="Sign up", command=self.handle_signup,
                                      height=45, corner_radius=8, font=("Segoe UI", 14, "bold"),
                                      fg_color=Colors.PRIMARY, hover_color="#2563EB")
        signup_button.pack(fill=tk.X)

    def toggle_password(self):
        self.show_pwd = not self.show_pwd
        if self.show_pwd:
            self.password_entry.configure(show="")
        else:
            self.password_entry.configure(show="*")

    def toggle_confirm_password(self):
        self.show_confirm_pwd = not self.show_confirm_pwd
        if self.show_confirm_pwd:
            self.confirm_password_entry.configure(show="")
        else:
            self.confirm_password_entry.configure(show="*")

    
    def handle_signup(self):
        """Handle signup button click"""
        first_name = self.first_name_entry.get().strip()
        last_name = self.last_name_entry.get().strip()
        username = self.username_entry.get().strip()
        email = self.email_entry.get().strip()
        password = self.password_entry.get()
        confirm_password = self.confirm_password_entry.get()
        
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
