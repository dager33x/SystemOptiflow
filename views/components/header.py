# views/components/header.py
import tkinter as tk
from datetime import datetime
from ..styles import Colors, Fonts

class Header:
    """Header component with enhanced design, user info, and controls"""
    
    def __init__(self, parent, current_user=None, on_logout=None):
        self.parent = parent
        self.current_user = current_user
        self.on_logout = on_logout
        
        # Main header container
        self.frame = tk.Frame(parent, bg=Colors.PRIMARY, height=80)
        self.frame.pack(fill=tk.X, side=tk.TOP)
        self.frame.pack_propagate(False)
        
        self.time_label = None
        self.create_widgets()
    
    def create_widgets(self):
        # Left Section: Brand
        left_frame = tk.Frame(self.frame, bg=Colors.PRIMARY)
        left_frame.pack(side=tk.LEFT, padx=30, fill=tk.Y)
        
        # Logo Icon (Text based for now)
        icon_label = tk.Label(left_frame, 
                            text="🛡️", 
                            font=("Segoe UI", 28),
                            bg=Colors.PRIMARY,
                            fg="white")
        icon_label.pack(side=tk.LEFT, padx=(0, 15))
        
        # Title Container
        title_box = tk.Frame(left_frame, bg=Colors.PRIMARY)
        title_box.pack(side=tk.LEFT, pady=15)
        
        # Main Title
        main_title = tk.Label(title_box, 
                             text="OPTIFLOW", 
                             font=("Segoe UI", 20, "bold"),
                             bg=Colors.PRIMARY,
                             fg="white")
        main_title.pack(anchor=tk.W)
        
        # Subtitle
        sub_title = tk.Label(title_box, 
                            text="INTELLIGENT TRAFFIC CONTROL", 
                            font=("Segoe UI", 9, "bold"),
                            bg=Colors.PRIMARY,
                            fg=Colors.INFO,
                            pady=0)
        sub_title.pack(anchor=tk.W)
        
        # Right Section: Info & Controls
        right_frame = tk.Frame(self.frame, bg=Colors.PRIMARY)
        right_frame.pack(side=tk.RIGHT, padx=30, fill=tk.Y)
        
        # Time Display
        self.time_label = tk.Label(right_frame,
                                  font=("Segoe UI", 14),
                                  bg=Colors.PRIMARY,
                                  fg="white")
        self.time_label.pack(side=tk.LEFT, padx=(0, 30))
        self.update_time()
        
        # User Profile
        if self.current_user:
            user_frame = tk.Frame(right_frame, bg=Colors.PRIMARY_DARK, padx=15, pady=8, cursor="hand2")
            user_frame.pack(side=tk.LEFT, padx=(0, 15))
            
            # Use a class variable or helper to bind events easily
            user_frame.bind("<Button-1>", self.show_profile_info)
            
            # Role Badge
            role = self.current_user.get('role', 'operator').upper()
            role_fg = Colors.WARNING if role == 'ADMIN' else Colors.INFO
            
            name_label = tk.Label(user_frame, 
                    text=f"👤 {self.current_user.get('username')}", 
                    font=("Segoe UI", 11, "bold"),
                    bg=Colors.PRIMARY_DARK,
                    fg="white",
                    cursor="hand2")
            name_label.pack(side=tk.LEFT, padx=(0, 10))
            name_label.bind("<Button-1>", self.show_profile_info)
            
            role_label = tk.Label(user_frame, 
                    text=role, 
                    font=("Segoe UI", 9, "bold"),
                    bg=Colors.PRIMARY_DARK,
                    fg=role_fg,
                    cursor="hand2")
            role_label.pack(side=tk.LEFT)
            role_label.bind("<Button-1>", self.show_profile_info)
        
        # Logout Button
        if self.on_logout:
            logout_btn = tk.Button(right_frame,
                                 text="LOGOUT",
                                 font=("Segoe UI", 10, "bold"),
                                 bg=Colors.DANGER,
                                 fg="white",
                                 activebackground="#dc2626", # Red 600
                                 activeforeground="white",
                                 relief=tk.FLAT,
                                 cursor="hand2",
                                 command=self.on_logout,
                                 padx=20,
                                 pady=8)
            logout_btn.pack(side=tk.LEFT)
            
            # Button hover effect
            def on_enter(e):
                logout_btn.config(bg="#b91c1c") # Red 700
            def on_leave(e):
                logout_btn.config(bg=Colors.DANGER)
            logout_btn.bind("<Enter>", on_enter)
            logout_btn.bind("<Leave>", on_leave)

    def show_profile_info(self, event=None):
        """Show dialog with full user information"""
        if not self.current_user:
            return
            
        dialog = tk.Toplevel(self.parent)
        dialog.title("User Profile")
        dialog.geometry("400x500")
        dialog.configure(bg=Colors.BACKGROUND)
        dialog.transient(self.parent.winfo_toplevel())
        
        # Center dialog
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - 400) // 2
        y = (screen_height - 500) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Header
        header = tk.Frame(dialog, bg=Colors.PRIMARY, height=100)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        
        # Manual centering of icon
        icon_cont = tk.Frame(header, bg=Colors.PRIMARY)
        icon_cont.pack(expand=True)
        tk.Label(
            icon_cont,
            text="👤",
            font=("Segoe UI", 48),
            bg=Colors.PRIMARY,
            fg="white"
        ).pack()
        
        # Content
        content = tk.Frame(dialog, bg=Colors.BACKGROUND, padx=30, pady=30)
        content.pack(fill=tk.BOTH, expand=True)
        
        # Helper for fields
        def add_field(label, value, is_bold=False):
            frame = tk.Frame(content, bg=Colors.BACKGROUND)
            frame.pack(fill=tk.X, pady=8)
            
            tk.Label(
                frame,
                text=label.upper(),
                font=("Segoe UI", 8, "bold"),
                bg=Colors.BACKGROUND,
                fg=Colors.TEXT_LIGHT
            ).pack(anchor=tk.W)
            
            val_font = ("Segoe UI", 12, "bold") if is_bold else ("Segoe UI", 11)
            tk.Label(
                frame,
                text=value if value else "Not set",
                font=val_font,
                bg=Colors.BACKGROUND,
                fg=Colors.TEXT
            ).pack(anchor=tk.W)
            
            tk.Frame(frame, height=1, bg=Colors.SECONDARY).pack(fill=tk.X, pady=(5, 0))

        # Full Name
        first = self.current_user.get('first_name', '')
        last = self.current_user.get('last_name', '')
        full_name = f"{first} {last}".strip() or self.current_user.get('username')
        
        add_field("Full Name", full_name, is_bold=True)
        add_field("Username", self.current_user.get('username'))
        add_field("Email", self.current_user.get('email'))
        add_field("Role", self.current_user.get('role', '').upper())
        
        created = self.current_user.get('created_at', '')
        if created:
            try:
                # Basic parsing if string, or just show as is
                created = created.split('T')[0]
            except:
                pass
        add_field("Member Since", created)
        
        
        tk.Frame(content, bg=Colors.BACKGROUND, height=20).pack() # Spacer
        
        tk.Button(
            content,
            text="Close",
            font=("Segoe UI", 10),
            bg=Colors.SECONDARY,
            fg="white",
            relief=tk.FLAT,
            command=dialog.destroy,
            cursor="hand2",
            pady=8
        ).pack(fill=tk.X)
        

    
    def update_time(self):
        current_time = datetime.now().strftime("%H:%M:%S")
        if self.time_label:
            self.time_label.config(text=current_time)
        self.frame.after(1000, self.update_time)
    
    def get_widget(self):
        return self.frame
