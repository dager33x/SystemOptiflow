# views/admin_dashboard.py
import tkinter as tk
from tkinter import ttk, messagebox
from .styles import Colors, Fonts, WidgetStyles


class AdminDashboard(tk.Frame):
    """Admin dashboard with user management"""
    
    def __init__(self, parent, current_user=None, on_logout_callback=None, 
                 on_add_user_callback=None, on_edit_user_callback=None,
                 on_delete_user_callback=None, on_load_users_callback=None):
        super().__init__(parent, bg=Colors.BACKGROUND)
        self.current_user = current_user
        self.on_logout_callback = on_logout_callback
        self.on_add_user_callback = on_add_user_callback
        self.on_edit_user_callback = on_edit_user_callback
        self.on_delete_user_callback = on_delete_user_callback
        self.on_load_users_callback = on_load_users_callback
        self.selected_user = None
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create admin dashboard widgets"""
        # Header
        header_frame = tk.Frame(self, bg=Colors.PRIMARY)
        header_frame.pack(fill=tk.X)
        
        # Logo and title
        left_header = tk.Frame(header_frame, bg=Colors.PRIMARY)
        left_header.pack(side=tk.LEFT, padx=20, pady=15)
        
        title_label = tk.Label(
            left_header,
            text="🛡️ OPTIFLOW - ADMIN DASHBOARD",
            font=("Arial", 16, "bold"),
            bg=Colors.PRIMARY,
            fg="white"
        )
        title_label.pack()
        
        # User info and logout
        right_header = tk.Frame(header_frame, bg=Colors.PRIMARY)
        right_header.pack(side=tk.RIGHT, padx=20, pady=15)
        
        user_label = tk.Label(
            right_header,
            text=f"👤 {self.current_user['username']} (Admin)",
            font=("Arial", 11),
            bg=Colors.PRIMARY,
            fg="white"
        )
        user_label.pack(side=tk.LEFT, padx=10)
        
        logout_button = tk.Button(
            right_header,
            text="Logout",
            font=("Arial", 10, "bold"),
            bg=Colors.DANGER,
            fg="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=self.on_logout_callback,
            padx=15,
            pady=5
        )
        logout_button.pack(side=tk.LEFT)
        
        # Main content with sidebar
        main_container = tk.Frame(self, bg=Colors.BACKGROUND)
        main_container.pack(fill=tk.BOTH, expand=True)
        main_container.grid_rowconfigure(0, weight=1)
        main_container.grid_columnconfigure(1, weight=1)
        
        # Navigation sidebar
        sidebar = tk.Frame(main_container, bg=Colors.PRIMARY, width=180)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.pack_propagate(False)
        
        nav_title = tk.Label(
            sidebar,
            text="Navigation",
            font=("Arial", 11, "bold"),
            bg=Colors.PRIMARY,
            fg="white"
        )
        nav_title.pack(pady=15, padx=10)
        
        users_btn = tk.Button(
            sidebar,
            text="👥 Users",
            font=("Arial", 10, "bold"),
            bg=Colors.PRIMARY,
            fg="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=10,
            pady=10
        )
        users_btn.pack(fill=tk.X, padx=10, pady=5)
        
        # Content area
        content_area = tk.Frame(main_container, bg=Colors.BACKGROUND)
        content_area.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        content_area.grid_rowconfigure(0, weight=0)
        content_area.grid_rowconfigure(1, weight=1)
        content_area.grid_columnconfigure(0, weight=1)
        
        # Title section
        title_section = tk.Frame(content_area, bg=Colors.BACKGROUND)
        title_section.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        
        users_title = tk.Label(
            title_section,
            text="User Management",
            font=("Arial", 18, "bold"),
            bg=Colors.BACKGROUND,
            fg=Colors.TEXT
        )
        users_title.pack(side=tk.LEFT)
        # Action buttons
        buttons_frame = tk.Frame(title_section, bg=Colors.BACKGROUND)
        buttons_frame.pack(side=tk.RIGHT)
        
        add_button = WidgetStyles.create_modern_button(
            buttons_frame,
            text="+ Add User",
            command=self.show_add_user_dialog,
            style='success'
        )
        add_button.pack(side=tk.LEFT, padx=5)
        
        edit_button = WidgetStyles.create_modern_button(
            buttons_frame,
            text="✏️ Edit",
            command=self.show_edit_user_dialog,
            style='info'
        )
        edit_button.pack(side=tk.LEFT, padx=5)
        
        delete_button = WidgetStyles.create_modern_button(
            buttons_frame,
            text="🗑️ Delete",
            command=self.delete_selected_user,
            style='danger'
        )
        delete_button.pack(side=tk.LEFT, padx=5)
        
        refresh_button = WidgetStyles.create_modern_button(
            buttons_frame,
            text="🔄 Refresh",
            command=self.load_users,
            style='secondary'
        )
        refresh_button.pack(side=tk.LEFT, padx=5)
        
        # Table frame
        table_frame = tk.Frame(content_area, bg=Colors.CARD_BG, padx=2, pady=2)
        table_frame.grid(row=1, column=0, sticky="nsew")
        
        # Create treeview for users with modern styling
        columns = ("ID", "Username", "Email", "Role", "Status", "Created")
        self.users_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            height=15,
            show="headings",
            style='Modern.Treeview'
        )
        
        # Define column headings and width
        column_widths = {
            "ID": 50,
            "Username": 120,
            "Email": 200,
            "Role": 80,
            "Status": 80,
            "Created": 150
        }
        
        for col, width in column_widths.items():
            self.users_tree.heading(col, text=col)
            self.users_tree.column(col, width=width)
        
        # Scrollbar with modern styling
        scrollbar = ttk.Scrollbar(
            table_frame,
            orient=tk.VERTICAL,
            command=self.users_tree.yview,
            style='Modern.Vertical.TScrollbar'
        )
        self.users_tree.configure(yscroll=scrollbar.set)
        
        self.users_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)
        
        # Bind row selection
        self.users_tree.bind("<<TreeviewSelect>>", self.on_user_select)
        
        # Load users
        self.load_users()
    
    def load_users(self):
        """Load users from database"""
        # Clear existing items
        for item in self.users_tree.get_children():
            self.users_tree.delete(item)
        
        # Load users
        if self.on_load_users_callback:
            users = self.on_load_users_callback()
            if users:
                for user in users:
                    # Format data
                    user_id = user.get("user_id", "")[:8]  # Show first 8 chars
                    username = user.get("username", "")
                    email = user.get("email", "")
                    role = user.get("role", "").upper()
                    status = "✓ Active" if user.get("is_active", True) else "✗ Inactive"
                    created = user.get("created_at", "")[:10]  # Show only date
                    
                    # Insert into tree
                    self.users_tree.insert(
                        "",
                        tk.END,
                        iid=user.get("user_id"),
                        values=(user_id, username, email, role, status, created),
                        tags=("admin",) if role == "ADMIN" else ("operator",)
                    )
        
        # Configure row colors
        self.users_tree.tag_configure("admin", foreground=Colors.DANGER)
        self.users_tree.tag_configure("operator", foreground=Colors.INFO)
    
    def on_user_select(self, event):
        """Handle user selection in table"""
        selection = self.users_tree.selection()
        if selection:
            self.selected_user = selection[0]
    
    def center_dialog(self, dialog, width, height):
        """Center a dialog window on the screen"""
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x_position = (screen_width - width) // 2
        y_position = (screen_height - height) // 2
        dialog.geometry(f"{width}x{height}+{x_position}+{y_position}")
    
    def show_add_user_dialog(self):
        """Show add user dialog"""
        dialog = tk.Toplevel(self)
        dialog.title("Add New User")
        dialog.geometry("400x400")
        dialog.configure(bg=Colors.BACKGROUND)
        
        # Center dialog on screen
        self.center_dialog(dialog, 400, 400)
        
        # Make dialog modal
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        
        # Container
        container = tk.Frame(dialog, bg="white")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        title_label = tk.Label(
            container,
            text="Add New User",
            font=("Arial", 16, "bold"),
            bg="white",
            fg=Colors.TEXT
        )
        title_label.pack(pady=(0, 20))
        
        # Username
        tk.Label(
            container,
            text="Username:",
            font=("Arial", 10, "bold"),
            bg="white",
            fg=Colors.TEXT
        ).pack(anchor=tk.W)
        
        username_entry = tk.Entry(
            container,
            font=("Arial", 10),
            bg="#f5f5f5",
            fg=Colors.TEXT,
            relief=tk.SOLID,
            bd=1
        )
        username_entry.pack(fill=tk.X, pady=(0, 15))
        
        # Email
        tk.Label(
            container,
            text="Email:",
            font=("Arial", 10, "bold"),
            bg="white",
            fg=Colors.TEXT
        ).pack(anchor=tk.W)
        
        email_entry = tk.Entry(
            container,
            font=("Arial", 10),
            bg="#f5f5f5",
            fg=Colors.TEXT,
            relief=tk.SOLID,
            bd=1
        )
        email_entry.pack(fill=tk.X, pady=(0, 15))
        
        # Password
        tk.Label(
            container,
            text="Password:",
            font=("Arial", 10, "bold"),
            bg="white",
            fg=Colors.TEXT
        ).pack(anchor=tk.W)
        
        password_entry = tk.Entry(
            container,
            font=("Arial", 10),
            bg="#f5f5f5",
            fg=Colors.TEXT,
            relief=tk.SOLID,
            bd=1,
            show="*"
        )
        password_entry.pack(fill=tk.X, pady=(0, 15))
        
        # Role
        tk.Label(
            container,
            text="Role:",
            font=("Arial", 10, "bold"),
            bg="white",
            fg=Colors.TEXT
        ).pack(anchor=tk.W)
        
        role_var = tk.StringVar(value="operator")
        role_frame = tk.Frame(container, bg="white")
        role_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Radiobutton(
            role_frame,
            text="Operator",
            variable=role_var,
            value="operator",
            bg="white",
            fg=Colors.TEXT,
            selectcolor="white"
        ).pack(side=tk.LEFT)
        
        tk.Radiobutton(
            role_frame,
            text="Admin",
            variable=role_var,
            value="admin",
            bg="white",
            fg=Colors.TEXT,
            selectcolor="white"
        ).pack(side=tk.LEFT, padx=20)
        
        # Buttons
        button_frame = tk.Frame(container, bg="white")
        button_frame.pack(fill=tk.X, pady=20)
        
        def save_user():
            username = username_entry.get().strip()
            email = email_entry.get().strip()
            password = password_entry.get()
            role = role_var.get()
            
            if not username or not email or not password:
                messagebox.showwarning("Input Error", "Please fill all fields")
                return
            
            if self.on_add_user_callback:
                result = self.on_add_user_callback(username, email, password, role)
                if result:
                    messagebox.showinfo("Success", "User created successfully")
                    dialog.destroy()
                    self.load_users()
                else:
                    messagebox.showerror("Error", "Failed to create user")
        
        save_button = tk.Button(
            button_frame,
            text="Save",
            font=("Arial", 10, "bold"),
            bg=Colors.SUCCESS,
            fg="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=save_user,
            padx=20,
            pady=8
        )
        save_button.pack(side=tk.LEFT, padx=5)
        
        cancel_button = tk.Button(
            button_frame,
            text="Cancel",
            font=("Arial", 10, "bold"),
            bg=Colors.TEXT_LIGHT,
            fg="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=dialog.destroy,
            padx=20,
            pady=8
        )
        cancel_button.pack(side=tk.LEFT, padx=5)
    
    def show_edit_user_dialog(self):
        """Show edit user dialog"""
        if not self.selected_user:
            messagebox.showwarning("No Selection", "Please select a user to edit")
            return
        
        # Get selected user data
        user_data = None
        for item in self.users_tree.get_children():
            if item == self.selected_user:
                values = self.users_tree.item(item)["values"]
                user_data = values
                break
        
        if not user_data:
            return
        
        dialog = tk.Toplevel(self)
        dialog.title("Edit User")
        dialog.geometry("400x350")
        dialog.configure(bg=Colors.BACKGROUND)
        
        # Center dialog on screen
        self.center_dialog(dialog, 400, 350)
        
        # Make dialog modal
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        
        # Container
        container = tk.Frame(dialog, bg="white")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        title_label = tk.Label(
            container,
            text="Edit User",
            font=("Arial", 16, "bold"),
            bg="white",
            fg=Colors.TEXT
        )
        title_label.pack(pady=(0, 20))
        
        # Username (read-only)
        tk.Label(
            container,
            text="Username:",
            font=("Arial", 10, "bold"),
            bg="white",
            fg=Colors.TEXT
        ).pack(anchor=tk.W)
        
        username_label = tk.Label(
            container,
            text=user_data[1],
            font=("Arial", 10),
            bg="#f5f5f5",
            fg=Colors.TEXT,
            relief=tk.SOLID,
            bd=1,
            padx=10,
            pady=8
        )
        username_label.pack(fill=tk.X, pady=(0, 15))
        
        # Email
        tk.Label(
            container,
            text="Email:",
            font=("Arial", 10, "bold"),
            bg="white",
            fg=Colors.TEXT
        ).pack(anchor=tk.W)
        
        email_entry = tk.Entry(
            container,
            font=("Arial", 10),
            bg="#f5f5f5",
            fg=Colors.TEXT,
            relief=tk.SOLID,
            bd=1
        )
        email_entry.insert(0, user_data[2])
        email_entry.pack(fill=tk.X, pady=(0, 15))
        
        # Role
        tk.Label(
            container,
            text="Role:",
            font=("Arial", 10, "bold"),
            bg="white",
            fg=Colors.TEXT
        ).pack(anchor=tk.W)
        
        role_var = tk.StringVar(value=user_data[3].lower())
        role_frame = tk.Frame(container, bg="white")
        role_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Radiobutton(
            role_frame,
            text="Operator",
            variable=role_var,
            value="operator",
            bg="white",
            fg=Colors.TEXT,
            selectcolor="white"
        ).pack(side=tk.LEFT)
        
        tk.Radiobutton(
            role_frame,
            text="Admin",
            variable=role_var,
            value="admin",
            bg="white",
            fg=Colors.TEXT,
            selectcolor="white"
        ).pack(side=tk.LEFT, padx=20)
        
        # Buttons
        button_frame = tk.Frame(container, bg="white")
        button_frame.pack(fill=tk.X, pady=20)
        
        def save_changes():
            email = email_entry.get().strip()
            role = role_var.get()
            
            if not email:
                messagebox.showwarning("Input Error", "Please enter email")
                return
            
            if self.on_edit_user_callback:
                result = self.on_edit_user_callback(
                    self.selected_user,
                    email,
                    role
                )
                if result:
                    messagebox.showinfo("Success", "User updated successfully")
                    dialog.destroy()
                    self.load_users()
                else:
                    messagebox.showerror("Error", "Failed to update user")
        
        save_button = tk.Button(
            button_frame,
            text="Save",
            font=("Arial", 10, "bold"),
            bg=Colors.SUCCESS,
            fg="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=save_changes,
            padx=20,
            pady=8
        )
        save_button.pack(side=tk.LEFT, padx=5)
        
        cancel_button = tk.Button(
            button_frame,
            text="Cancel",
            font=("Arial", 10, "bold"),
            bg=Colors.TEXT_LIGHT,
            fg="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=dialog.destroy,
            padx=20,
            pady=8
        )
        cancel_button.pack(side=tk.LEFT, padx=5)
    
    def delete_selected_user(self):
        """Delete selected user"""
        if not self.selected_user:
            messagebox.showwarning("No Selection", "Please select a user to delete")
            return
        
        # Get username
        for item in self.users_tree.get_children():
            if item == self.selected_user:
                values = self.users_tree.item(item)["values"]
                username = values[1]
                break
        
        # Confirm deletion
        if messagebox.askyesno("Confirm Delete", f"Delete user '{username}'?"):
            if self.on_delete_user_callback:
                result = self.on_delete_user_callback(self.selected_user)
                if result:
                    messagebox.showinfo("Success", "User deleted successfully")
                    self.load_users()
                else:
                    messagebox.showerror("Error", "Failed to delete user")
