import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
from .styles import Colors

class ForgotPasswordPage(ctk.CTkFrame):
    """Modern Forgot password page using CustomTkinter"""
    
    def __init__(self, parent, on_reset_callback=None, on_back_callback=None):
        super().__init__(parent, fg_color=Colors.BACKGROUND)
        self.on_reset_callback = on_reset_callback
        self.on_back_callback = on_back_callback
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create forgot password page widgets"""
        
        # Header with back button
        header_frame = ctk.CTkFrame(self, fg_color="transparent", height=60)
        header_frame.pack(fill=tk.X, pady=(15, 0), padx=20)
        
        back_button = ctk.CTkButton(header_frame, text="← Back", font=("Segoe UI", 12, "bold"), text_color="white",
                                    fg_color="transparent", hover_color=Colors.CARD_BG, width=80,
                                    command=self.on_back_callback)
        back_button.pack(side=tk.LEFT)
        
        # Form container - centered card
        form_card = ctk.CTkFrame(self, fg_color=Colors.CARD_BG, corner_radius=15, border_width=1, border_color="#2c3a52")
        form_card.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        # Internal padding
        inner = ctk.CTkFrame(form_card, fg_color="transparent")
        inner.pack(padx=50, pady=50, fill=tk.BOTH, expand=True)
        
        # Title
        ctk.CTkLabel(inner, text="Reset Password", font=("Segoe UI", 26, "bold"), text_color="white").pack(pady=(0, 5))
        ctk.CTkLabel(inner, text="Enter your details to receive reset code", font=("Segoe UI", 12), text_color=Colors.TEXT_MUTED).pack(pady=(0, 35))
        
        # Username field
        self.username_entry = ctk.CTkEntry(inner, placeholder_text="Username", width=280, height=45, corner_radius=8, 
                                           border_width=1, border_color="#2c3a52", fg_color="#0f1522", font=("Segoe UI", 13))
        self.username_entry.pack(fill=tk.X, pady=(0, 20))
        
        # Email field
        self.email_entry = ctk.CTkEntry(inner, placeholder_text="Email Address", width=280, height=45, corner_radius=8, 
                                        border_width=1, border_color="#2c3a52", fg_color="#0f1522", font=("Segoe UI", 13))
        self.email_entry.pack(fill=tk.X, pady=(0, 30))
        
        # Send code button
        reset_button = ctk.CTkButton(inner, text="SEND RESET CODE", command=self.handle_reset,
                                      height=45, corner_radius=8, font=("Segoe UI", 14, "bold"),
                                      fg_color=Colors.PRIMARY, hover_color="#2563EB")
        reset_button.pack(fill=tk.X)
        
    def handle_reset(self):
        """Handle password reset request"""
        username = self.username_entry.get().strip()
        email = self.email_entry.get().strip()
        
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
