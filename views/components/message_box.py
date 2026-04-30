import tkinter as tk
import customtkinter as ctk
from ..styles import Colors, Fonts

class CustomMessageBox(ctk.CTkToplevel):
    """Custom styled message box for CustomTkinter that fixes system freeze bugs"""
    
    def __init__(self, title, message, type_="info", buttons=None, parent=None):
        super().__init__(parent)
        self.title(title)
        
        # Determine colors and icon based on type
        self.type_config = {
            "info": {"icon": "ℹ️", "color": Colors.INFO, "title": "Information"},
            "success": {"icon": "✅", "color": Colors.SUCCESS, "title": "Success"},
            "warning": {"icon": "⚠️", "color": Colors.WARNING, "title": "Warning"},
            "error": {"icon": "🚫", "color": Colors.DANGER, "title": "Error"},
            "question": {"icon": "❓", "color": Colors.PRIMARY, "title": "Question"}
        }
        
        config = self.type_config.get(type_, self.type_config["info"])
        self.result = None
        
        self.geometry("460x280")
        self.resizable(False, False)
        self.configure(fg_color=Colors.CARD_BG)
        # We keep the window OS chrome so the user can easily close it or drag it safely without weird lag freezing.
        
        # Top frame for icon and title
        top_frame = ctk.CTkFrame(self, fg_color="transparent", height=50)
        top_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        ctk.CTkLabel(top_frame, text=config["icon"], font=("Segoe UI Emoji", 28), text_color=config["color"]).pack(side=tk.LEFT, padx=(0, 15))
        ctk.CTkLabel(top_frame, text=title or config["title"], font=("Segoe UI", 18, "bold"), text_color="white").pack(side=tk.LEFT)
        
        # Buttons bottom (packed FIRST with tk.BOTTOM, so they don't get squished)
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 20))
        
        # Message content
        msg_frame = ctk.CTkFrame(self, fg_color="transparent")
        msg_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=30, pady=(0, 10))
        
        ctk.CTkLabel(msg_frame, text=message, font=("Segoe UI", 14), text_color=Colors.TEXT_MUTED, wraplength=400, justify="left").pack(anchor="nw", fill=tk.BOTH, expand=True)
        
        if not buttons:
            buttons = [("OK", "ok", Colors.PRIMARY)]
            
        for text, value, color in buttons:
            btn = ctk.CTkButton(self.btn_frame, 
                           text=text,
                           font=("Segoe UI", 13, "bold"),
                           fg_color=color,
                           hover_color="#2c3a52",
                           width=100, height=35,
                           command=lambda v=value: self.on_btn_click(v))
            btn.pack(side=tk.RIGHT, padx=(10, 0))

        self.update_idletasks()
        if parent:
            # Center relative to parent
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
            self.geometry(f"+{x}+{y}")
            self.transient(parent)
            
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Grab and wait (Modal)
        self.grab_set()
        self.wait_window(self)

    def on_btn_click(self, value):
        self.result = value
        self.grab_release()
        self.destroy()
        
    def on_close(self):
        self.result = None
        self.grab_release()
        self.destroy()


class MessageBox:
    @staticmethod
    def showinfo(title, message, parent=None):
        if parent is None and tk._default_root:
            parent = tk._default_root
        dialog = CustomMessageBox(title, message, "info", parent=parent)
        return dialog.result

    @staticmethod
    def showwarning(title, message, parent=None):
        if parent is None and tk._default_root:
            parent = tk._default_root
        dialog = CustomMessageBox(title, message, "warning", parent=parent)
        return dialog.result
        
    @staticmethod
    def showerror(title, message, parent=None):
        if parent is None and tk._default_root:
            parent = tk._default_root
        dialog = CustomMessageBox(title, message, "error", parent=parent)
        return dialog.result
        
    @staticmethod
    def showsuccess(title, message, parent=None):
        if parent is None and tk._default_root:
            parent = tk._default_root
        dialog = CustomMessageBox(title, message, "success", [("OK", "ok", Colors.SUCCESS)], parent=parent)
        return dialog.result

    @staticmethod
    def askyesno(title, message, parent=None):
        if parent is None and tk._default_root:
            parent = tk._default_root
        buttons = [
            ("No", False, "#4c566a"),
            ("Yes", True, Colors.PRIMARY)
        ]
        dialog = CustomMessageBox(title, message, "question", buttons, parent=parent)
        return dialog.result
