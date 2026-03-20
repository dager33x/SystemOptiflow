import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
from .styles import Colors

class LoginPage(ctk.CTkFrame):
    """Modern Login page using CustomTkinter"""
    
    def __init__(self, parent, on_login_callback=None, on_signup_callback=None, 
                 on_forgot_password_callback=None):
        super().__init__(parent, fg_color=Colors.BACKGROUND)
        self.on_login_callback = on_login_callback
        self.on_signup_callback = on_signup_callback
        self.on_forgot_password_callback = on_forgot_password_callback
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create modern login page widgets"""
        # Master container for 50/50 split
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER, relwidth=0.9, relheight=0.9)
        
        # Exact half-half scaling
        main_frame.grid_columnconfigure(0, weight=1, uniform="half")
        main_frame.grid_columnconfigure(1, weight=1, uniform="half")
        main_frame.grid_rowconfigure(0, weight=1)

        # ── Left panel (Branding) ──
        left_panel = ctk.CTkFrame(main_frame, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew")
        
        # Vertically/Horizontally centered logo
        logo_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        logo_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        ctk.CTkLabel(logo_frame, text="🛡️", font=("Segoe UI Emoji", 90), text_color=Colors.PRIMARY).pack(pady=(0, 15))
        ctk.CTkLabel(logo_frame, text="OPTIFLOW", font=("Segoe UI", 42, "bold"), text_color="white").pack(pady=(0, 5))
        ctk.CTkLabel(logo_frame, text="Advanced Traffic Management", font=("Segoe UI", 15), text_color=Colors.TEXT_MUTED).pack()
        
        # ── Right panel (Form) ──
        right_panel = ctk.CTkFrame(main_frame, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew")
        
        # Form Card
        self.form_container = ctk.CTkFrame(right_panel, fg_color=Colors.CARD_BG, corner_radius=15, border_width=1, border_color="#2c3a52", width=400)
        self.form_container.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        # Internal padding frame
        inner_form = ctk.CTkFrame(self.form_container, fg_color="transparent")
        inner_form.pack(padx=40, pady=40, fill=tk.BOTH, expand=True)
        
        # Welcome text
        ctk.CTkLabel(inner_form, text="Welcome Back", font=("Segoe UI", 24, "bold"), text_color="white").pack(anchor=tk.W, pady=(0, 5))
        ctk.CTkLabel(inner_form, text="Sign in to your account", font=("Segoe UI", 13), text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(0, 30))
        
        # Username field
        self.username_entry = ctk.CTkEntry(inner_form, placeholder_text="Username", width=320,
                                           height=45, corner_radius=8, border_width=1, 
                                           border_color="#2c3a52", fg_color="#0f1522", font=("Segoe UI", 13))
        self.username_entry.pack(fill=tk.X, pady=(0, 20))
        
        # Password wrapper for eye icon
        pass_wrap = ctk.CTkFrame(inner_form, fg_color="#0f1522", corner_radius=8, border_width=1, border_color="#2c3a52", height=45)
        pass_wrap.pack(fill=tk.X, pady=(0, 30))
        pass_wrap.pack_propagate(False)
        
        self.password_entry = ctk.CTkEntry(pass_wrap, placeholder_text="Password", show="*",
                                           height=43, border_width=0, 
                                           fg_color="transparent", font=("Segoe UI", 13))
        self.password_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(2, 0))
        
        self.show_pwd = False
        self.eye_btn = ctk.CTkButton(pass_wrap, text="👁️", width=30, height=30, fg_color="transparent", 
                                     hover_color="#161f33", text_color=Colors.TEXT_MUTED, font=("Segoe UI Emoji", 14), 
                                     command=self.toggle_password)
        self.eye_btn.pack(side=tk.RIGHT, padx=5)

        # Login button
        self.login_button = ctk.CTkButton(inner_form, text="Sign In", command=self.handle_login,
                                          height=45, corner_radius=8, font=("Segoe UI", 14, "bold"),
                                          fg_color=Colors.PRIMARY, hover_color="#2563EB")
        self.login_button.pack(fill=tk.X, pady=(0, 25))
        
        # Footer
        footer_frame = ctk.CTkFrame(inner_form, fg_color="transparent")
        footer_frame.pack(fill=tk.X)
        
        forgot_btn = ctk.CTkButton(footer_frame, text="Forgot Password?", font=("Segoe UI", 12), text_color=Colors.TEXT_MUTED,
                                   fg_color="transparent", hover_color=Colors.BACKGROUND, width=120, anchor="w",
                                   command=self.handle_forgot_password)
        forgot_btn.pack(side=tk.LEFT)
        
        signup_btn = ctk.CTkButton(footer_frame, text="Create Account", font=("Segoe UI", 12, "bold"), text_color=Colors.PRIMARY,
                                   fg_color="transparent", hover_color=Colors.BACKGROUND, width=120, anchor="e",
                                   command=self.handle_signup)
        signup_btn.pack(side=tk.RIGHT)

    def toggle_password(self):
        self.show_pwd = not self.show_pwd
        if self.show_pwd:
            self.password_entry.configure(show="")
        else:
            self.password_entry.configure(show="*")

    def handle_login(self):
        """Handle login button click"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        
        if not username:
            messagebox.showwarning("Input Error", "Please enter username")
            return
        
        if not password:
            messagebox.showwarning("Input Error", "Please enter password")
            return
        
        if self.on_login_callback:
            self.on_login_callback(username, password)
    
    def handle_signup(self):
        if self.on_signup_callback:
            self.on_signup_callback()
    
    def handle_forgot_password(self):
        if self.on_forgot_password_callback:
            self.on_forgot_password_callback()
