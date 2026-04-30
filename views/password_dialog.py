import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
from .styles import Colors
from views.components.message_box import MessageBox

class PasswordResetDialog(ctk.CTkToplevel):
    """Custom password reset dialog with modern CustomTkinter UI"""
    
    def __init__(self, parent, title="Set New Password"):
        super().__init__(parent)
        self.result = None
        
        # Configure window
        self.title(title)
        self.configure(fg_color=Colors.CARD_BG)
        self.geometry("450x550")
        self.resizable(False, False)
        
        # Center window relative to parent
        self.update_idletasks()
        if parent:
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - 225
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - 275
            self.geometry(f"+{x}+{y}")
            self.transient(parent)
            
        self.create_widgets()
        
        # Focus on password entry
        self.password_entry.focus_set()
        
        # Bind Enter key
        self.bind('<Return>', lambda e: self.on_ok())
        self.bind('<Escape>', lambda e: self.on_cancel())
        
        # Make modal
        self.grab_set()
        
    def create_widgets(self):
        """Create dialog widgets using CustomTkinter"""
        
        # Main container with padding
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)
        
        # Icon
        ctk.CTkLabel(main_container, text="🔑", font=("Segoe UI Emoji", 55), text_color=Colors.PRIMARY).pack(pady=(0, 15))
        
        # Title
        ctk.CTkLabel(main_container, text="Set New Password", font=("Segoe UI", 24, "bold"), text_color="white").pack(pady=(0, 5))
        
        # Subtitle
        ctk.CTkLabel(main_container, text="Enter your new password (minimum 6 characters)", font=("Segoe UI", 12), text_color=Colors.TEXT_MUTED).pack(pady=(0, 25))
        
        # New Password label
        ctk.CTkLabel(main_container, text="New Password", font=("Segoe UI", 13, "bold"), text_color="white").pack(anchor=tk.W, pady=(0, 5))
        
        # New Password field wrapper
        pass_wrap = ctk.CTkFrame(main_container, fg_color="#0f1522", corner_radius=8, border_width=1, border_color="#2c3a52", height=45)
        pass_wrap.pack(fill=tk.X, pady=(0, 20))
        pass_wrap.pack_propagate(False)
        
        self.password_entry = ctk.CTkEntry(pass_wrap, show="*", height=43, border_width=0, 
                                           fg_color="transparent", font=("Segoe UI", 13))
        self.password_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.show_password = False
        self.eye_button = ctk.CTkButton(pass_wrap, text="👁️", width=30, height=30, fg_color="transparent", 
                                        hover_color="#161f33", text_color=Colors.TEXT_MUTED, font=("Segoe UI Emoji", 14), 
                                        command=self.toggle_password_visibility)
        self.eye_button.pack(side=tk.RIGHT, padx=5)
        
        # Confirm Password label
        ctk.CTkLabel(main_container, text="Confirm New Password", font=("Segoe UI", 13, "bold"), text_color="white").pack(anchor=tk.W, pady=(0, 5))
        
        # Confirm Password field wrapper
        confirm_wrap = ctk.CTkFrame(main_container, fg_color="#0f1522", corner_radius=8, border_width=1, border_color="#2c3a52", height=45)
        confirm_wrap.pack(fill=tk.X, pady=(0, 30))
        confirm_wrap.pack_propagate(False)
        
        self.confirm_entry = ctk.CTkEntry(confirm_wrap, show="*", height=43, border_width=0, 
                                           fg_color="transparent", font=("Segoe UI", 13))
        self.confirm_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.show_confirm = False
        self.confirm_eye_button = ctk.CTkButton(confirm_wrap, text="👁️", width=30, height=30, fg_color="transparent", 
                                        hover_color="#161f33", text_color=Colors.TEXT_MUTED, font=("Segoe UI Emoji", 14), 
                                        command=self.toggle_confirm_visibility)
        self.confirm_eye_button.pack(side=tk.RIGHT, padx=5)
        
        # Reset Password button (blue)
        ok_button = ctk.CTkButton(
            main_container,
            text="Reset Password",
            font=("Segoe UI", 14, "bold"),
            fg_color=Colors.PRIMARY,
            hover_color="#2563EB",
            height=45,
            corner_radius=8,
            command=self.on_ok
        )
        ok_button.pack(fill=tk.X, pady=(0, 10))
        
        # Cancel button
        cancel_button = ctk.CTkButton(
            main_container,
            text="Cancel",
            font=("Segoe UI", 14, "bold"),
            fg_color="transparent",
            text_color="#94a3b8",
            hover_color="#1e293b",
            height=45,
            corner_radius=8,
            command=self.on_cancel
        )
        cancel_button.pack(fill=tk.X)
    
    def toggle_password_visibility(self):
        """Toggle new password visibility"""
        self.show_password = not self.show_password
        show_char = "" if self.show_password else "*"
        self.password_entry.configure(show=show_char)
    
    def toggle_confirm_visibility(self):
        """Toggle confirm password visibility"""
        self.show_confirm = not self.show_confirm
        show_char = "" if self.show_confirm else "*"
        self.confirm_entry.configure(show=show_char)
    
    def on_ok(self):
        """Handle OK button"""
        password = self.password_entry.get()
        confirm = self.confirm_entry.get()
        
        if not password:
            MessageBox.showwarning("Input Error", "Please enter a password", parent=self)
            self.password_entry.focus_set()
            return
        
        if len(password) < 6:
            MessageBox.showwarning("Input Error", "Password must be at least 6 characters", parent=self)
            self.password_entry.focus_set()
            return
        
        if password != confirm:
            MessageBox.showwarning("Input Error", "Passwords do not match", parent=self)
            self.confirm_entry.delete(0, tk.END)
            self.confirm_entry.focus_set()
            return
        
        self.result = password
        self.grab_release()
        self.destroy()
    
    def on_cancel(self):
        """Handle Cancel button"""
        self.result = None
        self.grab_release()
        self.destroy()
    
    def show(self):
        """Show dialog and return result"""
        self.wait_window()
        return self.result
