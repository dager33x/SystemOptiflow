# views/pages/settings.py
import tkinter as tk
import customtkinter as ctk
from ..styles import Colors, Fonts
from utils.app_config import SETTINGS

class SettingsPage:
    """Settings page for system preferences using CustomTkinter"""
    
    def __init__(self, parent):
        self.parent = parent
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        
        # Store variables to prevent garbage collection
        self.toggles = {} 
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create settings page layout"""
        
        # 1. Header Area with Title and Description
        header_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        header_frame.pack(fill=tk.X, padx=40, pady=(30, 20))
        
        title_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_container.pack(side=tk.LEFT)
        
        ctk.CTkLabel(title_container, text="System Preferences",
                     font=('Segoe UI', 24, 'bold'),
                     text_color=Colors.TEXT).pack(anchor=tk.W)
                
        ctk.CTkLabel(title_container, text="Manage your visual, system, and notification settings.",
                     font=('Segoe UI', 14),
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(5, 0))

        # 2. Main Grid Container for Cards
        content_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
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
            ("Enhance Video (CPU Heavy)", "enable_video_enhancement"),
        ]
        
        notification_options = [
            ("Enable Notifications", "enable_notifications"),
        ]

        camera_source_options = [
            ("North Lane Source", "camera_source_north"),
            ("South Lane Source", "camera_source_south"),
            ("East Lane Source", "camera_source_east"),
            ("West Lane Source", "camera_source_west"),
        ]

        # 3. Footer / Status (Create it here to be packed at the bottom)
        footer_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=40, pady=25)
        
        status_lbl = ctk.CTkLabel(footer_frame, text="* Changes are applied automatically and immediately.", 
                                  font=("Segoe UI", 12), text_color=Colors.TEXT_MUTED)
        status_lbl.pack(side=tk.RIGHT)

        # Create Cards in Grid
        self.create_settings_card(content_frame, "Visual & Display", "👁️", visual_options, row=0, col=0)
        self.create_settings_card(content_frame, "System & Performance", "⚡", system_options, row=0, col=1)
        self.create_settings_card(content_frame, "Notifications", "🔔", notification_options, row=1, col=0)
        self.create_combobox_card(content_frame, "Camera Sources", "🎥", camera_source_options, row=1, col=1)


    def create_settings_card(self, parent, title, icon, options, row, col):
        """Create a beautifully rounded card-style section for settings"""
        # Card Container
        card = ctk.CTkFrame(parent, fg_color='#161F33', corner_radius=15)
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        
        # Internal padding frame
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header
        header = ctk.CTkFrame(inner, fg_color="transparent")
        header.pack(fill=tk.X, pady=(0, 15))
        
        # Title with Icon
        full_title = f"{icon}  {title}"
        ctk.CTkLabel(header, text=full_title, font=('Segoe UI', 16, 'bold'), 
                     text_color=Colors.TEXT).pack(anchor=tk.W)
        
        # Subtle Divider
        ctk.CTkFrame(inner, fg_color='#2c3a52', height=1).pack(fill=tk.X, pady=(0, 15))
        
        # Options List
        for label_text, config_key in options:
            self.create_modern_toggle(inner, label_text, config_key)

    def create_modern_toggle(self, parent, label_text, config_key):
        """Create a modern row with label on left and an iOS-style switch on right"""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill=tk.X, pady=8)
        
        # Label (Left)
        ctk.CTkLabel(container, text=label_text, font=('Segoe UI', 14), 
                     text_color=Colors.TEXT_LIGHT).pack(side=tk.LEFT)
        
        # Toggle (Right)
        current_val = SETTINGS.get(config_key, False)
        
        def on_toggle():
            val = switch.get()
            SETTINGS[config_key] = bool(val)
            print(f"Setting '{config_key}' toggled to {val}")

        # Styled CustomTkinter Switch
        switch = ctk.CTkSwitch(container, text="", 
                               command=on_toggle,
                               progress_color=Colors.PRIMARY,
                               button_color="#FFFFFF",
                               button_hover_color="#E0E0E0")
        
        if current_val:
            switch.select()
        else:
            switch.deselect()
            
        self.toggles[config_key] = switch
        switch.pack(side=tk.RIGHT)
    
    def create_combobox_card(self, parent, title, icon, options, row, col):
        """Create a card-style section for settings with comboboxes"""
        # Card Container
        card = ctk.CTkFrame(parent, fg_color='#161F33', corner_radius=15)
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        
        # Internal padding frame
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header
        header = ctk.CTkFrame(inner, fg_color="transparent")
        header.pack(fill=tk.X, pady=(0, 15))
        
        # Title with Icon
        full_title = f"{icon}  {title}"
        ctk.CTkLabel(header, text=full_title, font=('Segoe UI', 16, 'bold'), 
                     text_color=Colors.TEXT).pack(anchor=tk.W)
        
        # Subtle Divider
        ctk.CTkFrame(inner, fg_color='#2c3a52', height=1).pack(fill=tk.X, pady=(0, 15))
        
        # Options List
        for label_text, config_key in options:
            self.create_modern_combobox(inner, label_text, config_key)

    def create_modern_combobox(self, parent, label_text, config_key):
        """Create a modern row with label on left and combobox on right"""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill=tk.X, pady=8)
        
        # Label (Left)
        ctk.CTkLabel(container, text=label_text, font=('Segoe UI', 14), 
                     text_color=Colors.TEXT_LIGHT).pack(side=tk.LEFT)
        
        # Combobox (Right)
        current_val = SETTINGS.get(config_key, "Simulated")
        
        def on_combo_change(new_val):
            SETTINGS[config_key] = new_val
            print(f"Setting '{config_key}' changed to {new_val}")

        combo = ctk.CTkOptionMenu(container, values=["Simulated", "Camera 0", "Camera 1", "Camera 2", "Camera 3"],
                                  command=on_combo_change,
                                  fg_color="#1E293B",
                                  button_color="#334155",
                                  button_hover_color="#475569",
                                  dropdown_fg_color="#1E293B",
                                  dropdown_hover_color="#334155",
                                  font=('Segoe UI', 13))
        combo.set(current_val)
        combo.pack(side=tk.RIGHT)
        self.toggles[config_key] = combo
    
    def get_widget(self):
        return self.frame
