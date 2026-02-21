# views/pages/settings.py
import tkinter as tk
from tkinter import ttk
from ..styles import Colors, Fonts, WidgetStyles
from utils.app_config import SETTINGS

class SettingsPage:
    """Settings page for system preferences"""
    
    def __init__(self, parent):
        self.parent = parent
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        
        # Store variables to prevent garbage collection
        self.toggles = {} 
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create settings page layout"""
        print("Initializing Settings Page Widgets...")
        
        # 1. Header Area with Title and Description
        header_frame = tk.Frame(self.frame, bg=Colors.BACKGROUND)
        header_frame.pack(fill=tk.X, padx=40, pady=(30, 20))
        
        title_container = tk.Frame(header_frame, bg=Colors.BACKGROUND)
        title_container.pack(side=tk.LEFT)
        
        tk.Label(title_container, text="System Preferences",
                font=Fonts.TITLE, bg=Colors.BACKGROUND,
                fg=Colors.TEXT).pack(anchor=tk.W)
                
        tk.Label(title_container, text="Manage your visual, system, and notification settings.",
                font=Fonts.BODY, bg=Colors.BACKGROUND,
                fg=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(5, 0))

        # 2. Main Grid Container for Cards
        # Using a frame with grid layout for responsive-like cards
        content_frame = tk.Frame(self.frame, bg=Colors.BACKGROUND)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=35)
        
        content_frame.columnconfigure(0, weight=1, uniform="group1")
        content_frame.columnconfigure(1, weight=1, uniform="group1")

        # Define Settings Groups
        visual_options = [
            ("Show Bounding Boxes", "show_bounding_boxes"),
            ("Show Confidence Scores", "show_confidence"),
            ("Show Simulation Overlay", "show_simulation_text"),
        ]
        
        system_options = [
            ("Enable AI Detection", "enable_detection"),
            ("Simulate Events", "enable_sim_events"), 
            ("Camera Filter (Invert)", "dark_mode_cam"),
        ]
        
        notification_options = [
            ("Enable Notifications", "enable_notifications"),
        ]

        # Create Cards in Grid
        self.create_settings_card(content_frame, "Visual & Display", "👁️", visual_options, row=0, col=0)
        self.create_settings_card(content_frame, "System & Performance", "⚡", system_options, row=0, col=1)
        self.create_settings_card(content_frame, "Notifications", "🔔", notification_options, row=1, col=0)

        # 3. Footer / Status
        footer_frame = tk.Frame(self.frame, bg=Colors.BACKGROUND)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=40, pady=25)
        
        status_lbl = tk.Label(footer_frame, text="* Changes are applied automatically and immediately.", 
                           font=("Segoe UI", 9), bg=Colors.BACKGROUND, fg=Colors.TEXT_MUTED)
        status_lbl.pack(side=tk.RIGHT)

    def create_settings_card(self, parent, title, icon, options, row, col):
        """Create a card-style section for settings"""
        # Card Container
        card = WidgetStyles.create_card(parent)
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        
        # Header
        header = tk.Frame(card, bg=Colors.CARD_BG)
        header.pack(fill=tk.X, pady=(0, 15))
        
        # Title with Icon
        full_title = f"{icon}  {title}"
        tk.Label(header, text=full_title, font=Fonts.SUBHEADING, 
                bg=Colors.CARD_BG, fg=Colors.TEXT).pack(anchor=tk.W)
        
        # Subtle Divider
        tk.Frame(card, bg=Colors.DIVIDER, height=1).pack(fill=tk.X, pady=(0, 15))
        
        # Options List
        for label_text, config_key in options:
            self.create_modern_toggle(card, label_text, config_key)

    def create_modern_toggle(self, parent, label_text, config_key):
        """Create a modern row with label on left and toggle on right"""
        container = tk.Frame(parent, bg=Colors.CARD_BG)
        container.pack(fill=tk.X, pady=8)
        
        # Label (Left)
        tk.Label(container, text=label_text, font=Fonts.BODY, 
                bg=Colors.CARD_BG, fg=Colors.TEXT_LIGHT).pack(side=tk.LEFT)
        
        # Toggle (Right)
        current_val = SETTINGS.get(config_key, False)
        var = tk.BooleanVar(value=current_val)
        self.toggles[config_key] = var
        
        def on_toggle():
            new_val = self.toggles[config_key].get()
            SETTINGS[config_key] = new_val
            print(f"Setting '{config_key}' toggled to {new_val}")
            
            # Update visuals if needed (optional visual feedback)
            if new_val:
                chk.config(bg=Colors.CARD_BG, selectcolor=Colors.PRIMARY)
            else:
                chk.config(bg=Colors.CARD_BG, selectcolor=Colors.BACKGROUND)

        # Styled Checkbutton
        chk = tk.Checkbutton(container, variable=var, command=on_toggle,
                            bg=Colors.CARD_BG,
                            activebackground=Colors.CARD_BG,
                            selectcolor=Colors.PRIMARY if current_val else Colors.BACKGROUND,
                            bd=0, highlightthickness=0,
                            indicatoron=True) # Standard box style
        chk.pack(side=tk.RIGHT)
    
    def get_widget(self):
        return self.frame
