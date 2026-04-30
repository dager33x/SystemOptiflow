# views/components/controls.py
import tkinter as tk
from ..styles import Colors, Fonts

class Controls:
    """Component for control buttons"""
    def __init__(self, parent, on_start=None, on_stop=None):
        self.parent = parent
        self.on_start = on_start
        self.on_stop = on_stop
        self.frame = None
        self.create_widgets()
    
    def create_widgets(self):
        self.frame = tk.Frame(self.parent, bg=Colors.CARD_BG, relief=tk.RAISED)
        self.frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Start button
        start_btn = tk.Button(self.frame, text="Start",
                            font=Fonts.BODY, bg=Colors.SUCCESS,
                            fg='white', padx=20, pady=10,
                            command=self.on_start if self.on_start else lambda: None)
        start_btn.pack(side=tk.LEFT, padx=5)
        
        # Stop button
        stop_btn = tk.Button(self.frame, text="Stop",
                           font=Fonts.BODY, bg=Colors.DANGER,
                           fg='white', padx=20, pady=10,
                           command=self.on_stop if self.on_stop else lambda: None)
        stop_btn.pack(side=tk.LEFT, padx=5)
    
    def get_widget(self):
        return self.frame
