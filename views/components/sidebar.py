# views/components/sidebar.py
import tkinter as tk
from ..styles import Colors, Fonts

class Sidebar:
    """Sidebar with navigation menu and camera list"""
    
    def __init__(self, parent, cameras_data=None, on_nav_click=None, is_admin=False):
        self.parent = parent
        self.cameras_data = cameras_data or []
        self.on_nav_click = on_nav_click
        self.is_admin = is_admin
        self.frame = None
        self.create_widgets()
    
    def create_widgets(self):
        self.frame = tk.Frame(self.parent, bg=Colors.CARD_BG, width=250)
        self.frame.pack(side=tk.LEFT, fill=tk.Y, padx=0)
        self.frame.pack_propagate(False)
        
        # Navigation section
        nav_title = tk.Label(self.frame,
                            text="NAVIGATION",
                            font=Fonts.SMALL,
                            bg=Colors.CARD_BG,
                            fg=Colors.TEXT_LIGHT)
        nav_title.pack(anchor=tk.W, pady=(20, 10), padx=20)
        
        # Navigation buttons
        nav_items = [
            ("📊 Dashboard", "dashboard"),
            ("⚠️ Issue Reports", "issue_reports"),
            ("🚦 Traffic Reports", "traffic_reports"),
            ("📜 Incident History", "incident_history"),
            ("📋 Violation Logs", "violation_logs"),
            ("⚙️ Settings", "settings")
        ]
        
        if self.is_admin:
            nav_items.insert(6, ("👥 Manage Users", "admin_users"))
        
        for label, page_name in nav_items:
            self.create_nav_button(label, page_name)
        
        # Separator
        separator = tk.Frame(self.frame, height=1, bg=Colors.SECONDARY)
        separator.pack(fill=tk.X, pady=20, padx=20)
        
        # Cameras section
        cameras_title = tk.Label(self.frame,
                                text="ACTIVE CAMERAS",
                                font=Fonts.SMALL,
                                bg=Colors.CARD_BG,
                                fg=Colors.TEXT_LIGHT)
        cameras_title.pack(anchor=tk.W, pady=(0, 10), padx=20)
        
        # Container for camera list to allow updates
        self.camera_list_container = tk.Frame(self.frame, bg=Colors.CARD_BG)
        self.camera_list_container.pack(fill=tk.BOTH, expand=False)
        
        self.render_cameras()
            
    def render_cameras(self):
        """Render the list of cameras"""
        for widget in self.camera_list_container.winfo_children():
            widget.destroy()
            
        for camera in self.cameras_data:
            self.create_camera_card(camera)

    def update_cameras(self, new_data):
        """Update camera list dynamically"""
        self.cameras_data = new_data
        self.render_cameras()

    def create_nav_button(self, text, page_name):
        """Create a hoverable navigation button"""
        btn = tk.Button(self.frame,
                       text=text,
                       font=Fonts.BODY,
                       bg=Colors.CARD_BG,
                       fg=Colors.TEXT,
                       activebackground=Colors.HOVER,
                       activeforeground=Colors.WHITE,
                       anchor=tk.W,
                       padx=20,
                       pady=8, # Reduced from 12
                       relief=tk.FLAT,
                       bd=0,
                       cursor="hand2",
                       command=lambda: self.on_nav_click(page_name) if self.on_nav_click else None)
        btn.pack(fill=tk.X, pady=1)
        
        # Hover effects
        def on_enter(e):
            btn.config(bg=Colors.HOVER, fg=Colors.WHITE)
        def on_leave(e):
            btn.config(bg=Colors.CARD_BG, fg=Colors.TEXT)
            
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)

    def create_camera_card(self, camera):
        """Create a card for each camera"""
        # Outer container for minimal border effect
        # FIX: Use camera_list_container if available, else fallback (though container should exist)
        parent = getattr(self, 'camera_list_container', self.frame)
        card = tk.Frame(parent, bg=Colors.SECONDARY, padx=1, pady=1)
        card.pack(fill=tk.X, pady=3, padx=15) # Reduced pady from 5 to 3
        
        # Inner content
        content = tk.Frame(card, bg=Colors.SECONDARY)
        content.pack(fill=tk.BOTH)
        
        # Camera name
        name_label = tk.Label(content, text=camera.get('name', 'Camera'),
                            font=Fonts.BODY_BOLD, bg=Colors.SECONDARY, fg=Colors.TEXT)
        name_label.pack(anchor=tk.W, padx=10, pady=(6, 1)) # Reduced from (8, 2)
        
        # Status
        status = camera.get('status', 'unknown')
        status_color = Colors.get_status_color(status)
        
        # Status indicator (Circle + Text) frame
        status_frame = tk.Frame(content, bg=Colors.SECONDARY)
        status_frame.pack(anchor=tk.W, padx=10, pady=(0, 6)) # Reduced from (0, 8)
        
        # Canvas for dot
        canv = tk.Canvas(status_frame, width=10, height=10, bg=Colors.SECONDARY, highlightthickness=0)
        canv.pack(side=tk.LEFT, padx=(0, 5))
        canv.create_oval(2, 2, 8, 8, fill=status_color, outline="")
        
        status_label = tk.Label(status_frame, text=status.upper(),
                              font=Fonts.SMALL, bg=Colors.SECONDARY,
                              fg=Colors.TEXT_LIGHT)
        status_label.pack(side=tk.LEFT)
    
    def get_widget(self):
        return self.frame
