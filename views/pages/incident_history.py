# views/pages/incident_history.py
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from ..styles import Colors, Fonts

class IncidentHistoryPage:
    """Incident history page with past events using CustomTkinter"""
    
    def __init__(self, parent, controller=None, current_user=None):
        self.parent = parent
        self.controller = controller
        self.current_user = current_user
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.tree = None
        self.create_widgets()
        
        # Load data if controller is available
        if self.controller:
            self.load_data()
    
    def create_widgets(self):
        """Create incident history page layout"""
        # Header Frame
        header = ctk.CTkFrame(self.frame, fg_color="transparent")
        header.pack(fill=tk.X, pady=(30, 15), padx=40)
        
        # Title
        title_container = ctk.CTkFrame(header, fg_color="transparent")
        title_container.pack(side=tk.LEFT)
        
        ctk.CTkLabel(title_container, text="Incident History",
                     font=('Segoe UI', 24, 'bold'),
                     text_color=Colors.TEXT).pack(anchor=tk.W)
                
        ctk.CTkLabel(title_container, text="View and manage automated system incident detections.",
                     font=('Segoe UI', 14),
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(5, 0))
        
        # Buttons container (Right)
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side=tk.RIGHT)
        
        # Clear Button (Admin Only)
        is_admin = self.current_user and self.current_user.get('role', '').lower() == 'admin'
        if is_admin:
            clear_btn = ctk.CTkButton(btn_frame, text="🗑️ Clear All",
                                      command=self.clear_data,
                                      font=('Segoe UI', 13, 'bold'),
                                      fg_color=Colors.DANGER, 
                                      hover_color=Colors.DANGER_DARK,
                                      corner_radius=8,
                                      width=120, height=36)
            clear_btn.pack(side=tk.RIGHT, padx=(10, 0))

        # Refresh Button
        refresh_btn = ctk.CTkButton(btn_frame, text="🔄 Refresh",
                                    command=self.load_data,
                                    font=('Segoe UI', 13, 'bold'),
                                    fg_color='#1E293B', # Secondary color 
                                    hover_color='#334155',
                                    text_color=Colors.TEXT,
                                    corner_radius=8,
                                    width=120, height=36)
        refresh_btn.pack(side=tk.RIGHT)
        
        # Main content - Premium card styling
        content_frame = ctk.CTkFrame(self.frame, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=(10, 30))
        
        # Inner padding frame
        tree_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Create columns
        columns = ('Date', 'Time', 'Lane', 'Type', 'Severity', 'Description')
        self.tree = ttk.Treeview(tree_frame, columns=columns, height=15)
        
        # Style Treeview for dark theme to match CustomTkinter
        style = ttk.Style()
        style.theme_use('default')
        style.configure("Treeview", 
                        background="#0B111D",
                        foreground=Colors.TEXT,
                        rowheight=45,
                        fieldbackground="#0B111D",
                        borderwidth=0,
                        font=('Segoe UI', 11))
                        
        style.configure("Treeview.Heading",
                        background="#1A2332",
                        foreground=Colors.TEXT_LIGHT,
                        relief="flat",
                        borderwidth=0,
                        font=('Segoe UI', 12, 'bold'))

        style.map('Treeview', background=[('selected', Colors.PRIMARY)])
        style.map('Treeview.Heading', background=[('active', '#2c3a52')])

        # Configure column headings
        self.tree.heading('#0', text='ID')
        self.tree.column('#0', width=0, stretch=tk.NO) # Hide ID column
        
        headings = {
            'Date': 120,
            'Time': 100,
            'Lane': 100,
            'Type': 120,
            'Severity': 120,
            'Description': 300
        }
        
        for col, width in headings.items():
            self.tree.heading(col, text=col)
            # Center-align most columns except description
            if col == 'Description':
                self.tree.column(col, width=width, anchor=tk.W)
            else:
                self.tree.column(col, width=width, anchor=tk.CENTER)
        
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # Add modern thin scrollbar
        scrollbar = ctk.CTkScrollbar(tree_frame, orientation="vertical", command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        self.tree.configure(yscrollcommand=scrollbar.set)
        
    def load_data(self):
        """Load data from controller"""
        if not self.controller:
            return
            
        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Fetch incidents
        incidents = self.controller.get_incidents()
        
        if not incidents:
            return
            
        for inc in incidents:
            # Parse timestamp "2026-01-29T20:22:46.123456"
            try:
                dt_str = inc.get('created_at') or inc.get('timestamp', '')
                if 'T' in dt_str:
                    date_part, time_part = dt_str.split('T')
                    time_part = time_part.split('.')[0] # Remove microseconds
                else:
                    date_part = dt_str
                    time_part = ""
            except:
                date_part = "Unknown"
                time_part = "Unknown"
            
            self.tree.insert('', tk.END, values=(
                date_part,
                time_part,
                f"Lane {inc.get('lane', '?')}",
                "Accident", # Type is implicitly accident here
                inc.get('severity', 'Moderate').upper(),
                inc.get('description', '')
            ))
            
    def clear_data(self):
        """Clear all incident data if admin"""
        from tkinter import messagebox
        if messagebox.askyesno("Confirm", "Are you sure you want to completely clear all incident history? This cannot be undone.", parent=self.frame):
            if self.controller and hasattr(self.controller, 'clear_incidents'):
                if self.controller.clear_incidents():
                    messagebox.showinfo("Success", "Incident history cleared successfully.", parent=self.frame)
                    self.load_data()
                else:
                    messagebox.showerror("Error", "Failed to clear incident history.", parent=self.frame)
    
    def get_widget(self):
        return self.frame
