# views/main_window.py
import tkinter as tk
from .components.header import Header
from .components.sidebar import Sidebar
from .components.footer import Footer
from .styles import Colors

class MainWindow:
    """Main application window with header, sidebar, content area, and footer"""
    
    def __init__(self, root, controllers, current_user=None):
        self.root = root
        self.controllers = controllers
        self.current_user = current_user
        self.content_area = None
        self.header = None
        self.sidebar = None
        self.footer = None
        
        self.setup_window()
        self.create_widgets()
    
    def setup_window(self):
        """Configure root frame"""
        self.root.configure(bg=Colors.BACKGROUND)
    
    
    def logout(self):
        """Handle logout"""
        if self.controllers and self.controllers.get('main'):
            self.controllers['main'].logout()

    def create_widgets(self):
        """Create main window layout"""
        
        
        # Header (top)
        header_frame = tk.Frame(self.root, bg=Colors.PRIMARY)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        self.header = Header(header_frame, 
                             current_user=self.current_user, 
                             on_logout=self.logout)
        
        # Footer (bottom)
        footer_frame = tk.Frame(self.root, bg=Colors.PRIMARY)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.footer = Footer(footer_frame, self.controllers)
        
        # Main container for sidebar and content
        main_container = tk.Frame(self.root, bg=Colors.BACKGROUND)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Sidebar (left)
        # Sidebar (left)
        cameras_data = []
        if self.controllers and 'main' in self.controllers:
            try:
                cameras_data = self.controllers['main'].get_active_cameras()
            except AttributeError:
                pass
        
        if not cameras_data:
            # Fallback if controller not ready or method missing
            cameras_data = [
                {"name": "North Gate", "status": "inactive"},
                {"name": "South Junction", "status": "inactive"},
                {"name": "East Portal", "status": "inactive"},
                {"name": "West Avenue", "status": "inactive"}
            ]
        
        sidebar_frame = tk.Frame(main_container, bg=Colors.PRIMARY)
        sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        # Prepare navigation callback
        nav_callback = None
        if self.controllers and 'main' in self.controllers:
            nav_callback = self.controllers['main'].handle_navigation
        
        # Determine if admin
        is_admin = False
        if self.current_user and self.current_user.get('role') == 'admin':
            is_admin = True
            
        self.sidebar = Sidebar(
            sidebar_frame,
            cameras_data,
            on_nav_click=nav_callback,
            is_admin=is_admin
        )
        
        # Content area (center)
        self.content_area = tk.Frame(main_container, bg=Colors.BACKGROUND)
        self.content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        

    
    def show_page(self, page_widget):
        """Show a page widget in content area"""
        # Clear content area
        for widget in self.content_area.winfo_children():
            widget.destroy()
        
        # Add new page
        page_widget.pack(fill=tk.BOTH, expand=True)
