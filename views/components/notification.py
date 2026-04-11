import tkinter as tk
import customtkinter as ctk
from ..styles import Colors, Fonts

class NotificationToast(ctk.CTkFrame):
    """A single non-blocking compact notification toast leveraging CustomTkinter"""
    
    def __init__(self, parent, title, message, type_="info", duration=4000, on_close=None):
        self.type_config = {
            "info": {"icon": "ℹ️", "color": Colors.INFO},
            "success": {"icon": "✅", "color": Colors.SUCCESS},
            "warning": {"icon": "⚠️", "color": Colors.WARNING},
            "error": {"icon": "🚫", "color": Colors.DANGER},
            "violation": {"icon": "🚨", "color": Colors.DANGER}
        }
        
        config = self.type_config.get(type_, self.type_config["info"])
        self.on_close = on_close
        self._is_closing = False
        self.target_x = 0
        self.current_x = 0
        
        # Compact dimensions (wide rectangle)
        accent_color = config["color"]
        super().__init__(parent, width=340, height=55, fg_color='#161F33', corner_radius=10, border_width=1, border_color=accent_color)
        
        # Icon Section (Left)
        icon_lbl = ctk.CTkLabel(self, text=config["icon"], font=("Segoe UI Emoji", 20), text_color="white", width=40)
        icon_lbl.place(x=10, rely=0.5, anchor=tk.W)
        
        # Text block (Middle)
        text_frame = ctk.CTkFrame(self, fg_color="transparent", width=260, height=45)
        text_frame.place(x=50, rely=0.5, anchor=tk.W)
        text_frame.pack_propagate(False)
        
        # We put Title and Message stacked vertically inside the text block
        ctk.CTkLabel(text_frame, text=title, font=('Segoe UI', 13, 'bold'), text_color="white").pack(anchor=tk.W, pady=(2, 0))
        ctk.CTkLabel(text_frame, text=message, font=('Segoe UI', 11), text_color=Colors.TEXT_MUTED, wraplength=250, justify="left").pack(anchor=tk.W)
        
        # Close Button (Right)
        close_btn = ctk.CTkButton(self, text="✕", width=24, height=24, fg_color="transparent", hover_color="#2c3a52", 
                                  text_color=Colors.TEXT_MUTED, font=('Segoe UI', 12, 'bold'), corner_radius=4,
                                  command=self.close)
        close_btn.place(x=325, rely=0.5, anchor=tk.E)
        
        # Allow clicking anywhere on the toast to dismiss
        self.fast_dismiss_binds()
        
        # Auto-close timer
        if duration > 0:
            self.after(duration, self.close)

    def fast_dismiss_binds(self):
        """Binds click event to all children so clicking the toast anywhere dismisses it"""
        def dismiss(e):
            self.close()
        
        self.bind("<Button-1>", dismiss)
        for child in self.winfo_children():
            child.bind("<Button-1>", dismiss)
            for inner in child.winfo_children():
                inner.bind("<Button-1>", dismiss)

    def animate_slide_in(self, target_y, right_margin):
        """Starts off-screen to the right and slides in rapidly, immune to screen resizing"""
        try:
            self.target_offset = -right_margin
            self.current_offset = 20  # Start slightly off screen
            
            self.place(relx=1.0, x=self.current_offset, y=target_y, anchor="ne")
            self.lift()
            self._slide_in()
        except:
            # Fallback
            self.place(relx=1.0, x=-right_margin, y=target_y, anchor="ne")

    def _slide_in(self):
        if self._is_closing: return
        try:
            if self.current_offset > self.target_offset:
                self.current_offset -= 35  # slide speed
                if self.current_offset <= self.target_offset:
                    self.current_offset = self.target_offset
                    self.place(relx=1.0, x=self.current_offset, anchor="ne")
                    return
                self.place(relx=1.0, x=self.current_offset, anchor="ne")
                self.after(10, self._slide_in)
        except:
            pass

    def close(self):
        if self._is_closing: 
            return
            
        self._is_closing = True
        
        # Immediately tell Manager to rearrange the queue
        if self.on_close:
            self.on_close(self)
            
        # Start the slide out animation
        self._slide_out()

    def _slide_out(self):
        """Slide off screen to the right before destroying"""
        try:
            if hasattr(self, 'current_offset'):
                if self.current_offset < 50: # Arbitrary point where it's visibly offscreen
                    self.current_offset += 30
                    self.place(relx=1.0, x=self.current_offset, anchor="ne")
                    self.after(10, self._slide_out)
                else:
                    self.destroy()
            else:
                self.destroy()
        except Exception:
            try:
                self.destroy()
            except tk.TclError:
                pass


class NotificationManager:
    """Manages the queue and floating display of premium notifications"""
    
    def __init__(self, root):
        self.root = root
        self.notifications = []
        self.start_y = 60            # Padding from top of the window
        self.spacing = 10            # Space between toasts
        self.right_margin = 20       # Padding from right edge
        self.width = 340             # Wider rectangle
        self.height = 55             # Shorter height
        
    def show(self, title, message, type_="info", duration=5000):
        """Display a new notification toast, stacking it correctly"""
        from utils.app_config import SETTINGS
        if not SETTINGS.get("enable_notifications", True):
            return

        toast = NotificationToast(self.root, title, message, type_, duration, on_close=self._remove_toast)
        
        # Calculate vertical position
        count = len(self.notifications)
        offset_y = self.start_y + (count * (self.height + self.spacing))
        
        # Slide in animation using purely relative placement
        toast.animate_slide_in(offset_y, self.right_margin)
        
        self.notifications.append(toast)
        
        # Generic chime sound for specific priority alerts
        if type_ in ["error", "violation", "warning"]:
            try:
                self.root.bell()
            except:
                pass
                
    def _remove_toast(self, toast):
        """Removes a toast and shifts remaining ones upward"""
        if toast in self.notifications:
            self.notifications.remove(toast)
            self._rearrange()
            
    def _rearrange(self):
        """Snap remaining notifications upwards"""
        for i, toast in enumerate(self.notifications):
            target_y = self.start_y + (i * (self.height + self.spacing))
            try:
                # We update just the y coordinate (relx and x are retained)
                if hasattr(toast, 'current_offset'):
                    toast.place(relx=1.0, x=toast.current_offset, y=target_y, anchor="ne")
                else:
                    toast.place(y=target_y)
            except tk.TclError:
                pass
