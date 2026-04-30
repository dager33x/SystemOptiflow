# views/components/footer.py
import tkinter as tk
from ..styles import Colors, Fonts

class Footer:
    """Footer component with status and controls"""
    def __init__(self, parent, controllers):
        self.parent = parent
        self.controllers = controllers
        self.frame = None
        self.status_label = None
        self.create_widgets()
    
    def create_widgets(self):
        self.frame = tk.Frame(self.parent, bg=Colors.PRIMARY, height=40)
        self.frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.frame.pack_propagate(False)
        
        # Status message
        self.status_label = tk.Label(self.frame,
                                    text="System Status: All systems operational",
                                    font=("Consolas", 10),
                                    bg=Colors.PRIMARY,
                                    fg='white')
        self.status_label.pack(side=tk.TOP, pady=10)

    
    def logout(self):
        """Handle logout"""
        if self.controllers and self.controllers.get('main'):
            self.controllers['main'].logout()
    
    def update_status(self, message):
        """Update status message"""
        if self.status_label:
            self.status_label.config(text=message)
    
    def get_widget(self):
        return self.frame
