import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
from .styles import Colors

class EmailVerificationPage(ctk.CTkFrame):
    """Modern Email verification page using CustomTkinter"""
    
    def __init__(self, parent, email, username, on_verify_callback=None, on_back_callback=None):
        super().__init__(parent, fg_color=Colors.BACKGROUND)
        self.email = email
        self.username = username
        self.on_verify_callback = on_verify_callback
        self.on_back_callback = on_back_callback
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create modern verification page widgets"""
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
        
        ctk.CTkLabel(logo_frame, text="✉️", font=("Segoe UI Emoji", 90), text_color=Colors.PRIMARY).pack(pady=(0, 15))
        ctk.CTkLabel(logo_frame, text="OPTIFLOW", font=("Segoe UI", 42, "bold"), text_color="white").pack(pady=(0, 5))
        ctk.CTkLabel(logo_frame, text="Email Verification", font=("Segoe UI", 15), text_color=Colors.TEXT_MUTED).pack()
        
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
        ctk.CTkLabel(inner_form, text="Verify Your Email", font=("Segoe UI", 24, "bold"), text_color="white").pack(anchor=tk.W, pady=(0, 5))
        
        subtitle = f"Code sent to {self.email}"
        ctk.CTkLabel(inner_form, text=subtitle, font=("Segoe UI", 12), text_color=Colors.TEXT_MUTED, wraplength=300, justify="left").pack(anchor=tk.W, pady=(0, 20))
        
        # Notice
        notice_frame = ctk.CTkFrame(inner_form, fg_color="#182c40", corner_radius=5)
        notice_frame.pack(fill=tk.X, pady=(0, 20))
        ctk.CTkLabel(notice_frame, text="ℹ️ Please check your spam folder just in case", 
                     font=("Segoe UI", 12), text_color="#5ea1eb").pack(pady=10, padx=10)
        
        # Verify Code Field
        self.code_entry = ctk.CTkEntry(inner_form, placeholder_text="Enter 6-digit code", width=320, justify="center",
                                           height=45, corner_radius=8, border_width=1, 
                                           border_color="#2c3a52", fg_color="#0f1522", font=("Segoe UI", 16, "bold"))
        self.code_entry.pack(fill=tk.X, pady=(0, 30))
        
        # Verify button
        self.verify_button = ctk.CTkButton(inner_form, text="Verify Account", command=self.verify_email,
                                          height=45, corner_radius=8, font=("Segoe UI", 14, "bold"),
                                          fg_color=Colors.PRIMARY, hover_color="#2563EB")
        self.verify_button.pack(fill=tk.X, pady=(0, 25))
        
        # Footer
        footer_frame = ctk.CTkFrame(inner_form, fg_color="transparent")
        footer_frame.pack(fill=tk.X)
        
        back_button = ctk.CTkButton(footer_frame, text="← Back to Login", font=("Segoe UI", 12), text_color=Colors.TEXT_MUTED,
                                   fg_color="transparent", hover_color=Colors.BACKGROUND, width=120, anchor="w",
                                   command=self.on_back_callback)
        back_button.pack(side=tk.LEFT)
        
        help_btn = ctk.CTkLabel(footer_frame, text="Didn't receive code?", font=("Segoe UI", 12), text_color=Colors.TEXT_MUTED)
        help_btn.pack(side=tk.RIGHT)

    def verify_email(self):
        """Verify reset code"""
        code = self.code_entry.get().strip()
        
        if not code:
            messagebox.showwarning("Input Error", "Please enter the verification code")
            return
        
        if len(code) != 6 or not code.isdigit():
            messagebox.showwarning("Invalid Code", "Verification code must be 6 digits")
            return
        
        if self.on_verify_callback:
            self.on_verify_callback(self.email, code)
