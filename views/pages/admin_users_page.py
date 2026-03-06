
import tkinter as tk
from tkinter import ttk, messagebox
from ..styles import Colors, Fonts, WidgetStyles

class AdminUsersPage:
    """Admin User Management Page"""
    
    def __init__(self, parent, auth_controller):
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.auth = auth_controller
        self.selected_user = None
        self.create_widgets()
        
    def create_widgets(self):
        """Create page content"""
        # Title section
        title_section = tk.Frame(self.frame, bg=Colors.BACKGROUND)
        title_section.pack(fill=tk.X, pady=(0, 15), padx=15)
        
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
        
        self.create_button(buttons_frame, "+ Add User", Colors.SUCCESS, self.show_add_user_dialog)
        self.create_button(buttons_frame, "✏️ Edit", Colors.INFO, self.show_edit_user_dialog)
        self.create_button(buttons_frame, "🗑️ Delete", Colors.DANGER, self.delete_selected_user)
        self.create_button(buttons_frame, "🔄 Refresh", Colors.SECONDARY, self.load_users)
        
        # Table frame
        table_frame = tk.Frame(self.frame, bg=Colors.CARD_BG)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # Create treeview
        columns = ("ID", "Username", "Email", "Role", "Status", "Created")
        self.users_tree = ttk.Treeview(table_frame, columns=columns, height=15, show="headings")
        
        column_widths = {
            "ID": 50, "Username": 120, "Email": 200, 
            "Role": 80, "Status": 80, "Created": 150
        }
        
        for col, width in column_widths.items():
            self.users_tree.heading(col, text=col)
            self.users_tree.column(col, width=width)
            
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.users_tree.yview)
        self.users_tree.configure(yscroll=scrollbar.set)
        
        self.users_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)
        
        self.users_tree.bind("<<TreeviewSelect>>", self.on_user_select)
        
        # Initial load
        self.load_users()
        
    def create_button(self, parent, text, color, command):
        btn = tk.Button(parent, text=text, font=("Arial", 10, "bold"), bg=color, fg="white",
                       relief=tk.FLAT, bd=0, cursor="hand2", command=command, padx=15, pady=8)
        btn.pack(side=tk.LEFT, padx=5)
        return btn

    def load_users(self):
        # Clear existing
        for item in self.users_tree.get_children():
            self.users_tree.delete(item)
            
        users = self.auth.get_all_users()
        if users:
            for user in users:
                user_id = user.get("user_id", "")[:8]
                username = user.get("username", "")
                email = user.get("email", "")
                role = user.get("role", "").upper()
                status = "✓ Active" if user.get("is_active", True) else "✗ Inactive"
                created = user.get("created_at", "")[:10]
                
                self.users_tree.insert("", tk.END, iid=user.get("user_id"),
                                     values=(user_id, username, email, role, status, created),
                                     tags=("admin",) if role == "ADMIN" else ("operator",))
                                     
        self.users_tree.tag_configure("admin", foreground=Colors.DANGER)
        self.users_tree.tag_configure("operator", foreground=Colors.INFO)

    def on_user_select(self, event):
        selection = self.users_tree.selection()
        if selection:
            self.selected_user = selection[0]

    def center_dialog(self, dialog, width, height):
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def show_add_user_dialog(self):
        dialog = tk.Toplevel(self.frame)
        dialog.title("Add New User")
        dialog.configure(bg=Colors.BACKGROUND)
        self.center_dialog(dialog, 420, 540)
        dialog.grab_set()
        
        container = tk.Frame(dialog, bg=Colors.CARD_BG)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        header_frame = tk.Frame(container, bg=Colors.CARD_BG)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        tk.Label(header_frame, text="Add New User", font=Fonts.TITLE, bg=Colors.CARD_BG, fg=Colors.PRIMARY).pack(side=tk.LEFT)
        tk.Label(header_frame, text="Create a new account", font=Fonts.BODY, bg=Colors.CARD_BG, fg=Colors.TEXT_MUTED).pack(side=tk.LEFT, padx=10, pady=(0, 4))
        
        # Fields
        entries = {}
        for field, icon, is_pwd in [("Username", "👤", False), ("Email", "✉️", False), ("Password", "🔑", True)]:
            frame = tk.Frame(container, bg=Colors.CARD_BG)
            frame.pack(fill=tk.X, pady=(0, 15))
            tk.Label(frame, text=f"{icon} {field}", font=Fonts.BODY_BOLD, bg=Colors.CARD_BG, fg=Colors.TEXT).pack(anchor=tk.W, pady=(0, 5))
            
            # Simulated padded entry via a frame background
            input_container = tk.Frame(frame, bg=Colors.INPUT_BG, padx=2, pady=2)
            input_container.pack(fill=tk.X)
            
            entry = tk.Entry(input_container, font=Fonts.INPUT, bg=Colors.INPUT_BG, fg=Colors.TEXT, 
                             insertbackground=Colors.PRIMARY, relief=tk.FLAT, bd=8)
            entry.pack(fill=tk.X)
            
            if is_pwd: entry.config(show="•")
            entries[field.lower()] = entry
            
        # Role
        role_frame = tk.Frame(container, bg=Colors.CARD_BG)
        role_frame.pack(fill=tk.X, pady=(0, 25))
        tk.Label(role_frame, text="🛡️ Role", font=Fonts.BODY_BOLD, bg=Colors.CARD_BG, fg=Colors.TEXT).pack(anchor=tk.W, pady=(0, 5))
        
        role_var = tk.StringVar(value="operator")
        style = ttk.Style()
        style.configure('Dark.TRadiobutton', background=Colors.CARD_BG, foreground=Colors.TEXT, font=Fonts.BODY)
        style.map('Dark.TRadiobutton', background=[('active', Colors.CARD_BG)], foreground=[('active', Colors.PRIMARY)])
        
        ttk.Radiobutton(role_frame, text="Operator", variable=role_var, value="operator", style='Dark.TRadiobutton', cursor="hand2").pack(side=tk.LEFT, padx=(0, 20))
        ttk.Radiobutton(role_frame, text="Admin", variable=role_var, value="admin", style='Dark.TRadiobutton', cursor="hand2").pack(side=tk.LEFT)
        
        def save():
            u = entries['username'].get().strip()
            e = entries['email'].get().strip()
            p = entries['password'].get()
            r = role_var.get()
            
            if not u or not e or not p:
                messagebox.showerror("Error", "All fields are required", parent=dialog)
                return
                
            if self.auth.add_user(u, e, p, r):
                dialog.destroy()
                self.load_users()
        
        btn_frame = tk.Frame(container, bg=Colors.CARD_BG)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        
        WidgetStyles.create_modern_button(btn_frame, "Save User", command=save, style='success').pack(side=tk.RIGHT, padx=(10, 0))
        WidgetStyles.create_modern_button(btn_frame, "Cancel", command=dialog.destroy, style='secondary').pack(side=tk.RIGHT)

    def show_edit_user_dialog(self):
        if not self.selected_user:
            return
            
        item = self.users_tree.item(self.selected_user)
        vals = item['values']
        
        dialog = tk.Toplevel(self.frame)
        dialog.title("Edit User")
        dialog.configure(bg=Colors.BACKGROUND)
        self.center_dialog(dialog, 420, 380)
        dialog.grab_set()
        
        container = tk.Frame(dialog, bg=Colors.CARD_BG)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        header_frame = tk.Frame(container, bg=Colors.CARD_BG)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        tk.Label(header_frame, text="Edit User", font=Fonts.TITLE, bg=Colors.CARD_BG, fg=Colors.INFO).pack(side=tk.LEFT)
        tk.Label(header_frame, text=vals[1], font=Fonts.BODY, bg=Colors.CARD_BG, fg=Colors.TEXT_MUTED).pack(side=tk.LEFT, padx=10, pady=(0, 4))
        
        # Email
        tk.Label(container, text="✉️ Email", font=Fonts.BODY_BOLD, bg=Colors.CARD_BG, fg=Colors.TEXT).pack(anchor=tk.W, pady=(0, 5))
        
        input_container = tk.Frame(container, bg=Colors.INPUT_BG, padx=2, pady=2)
        input_container.pack(fill=tk.X, pady=(0, 20))
        
        email_entry = tk.Entry(input_container, font=Fonts.INPUT, bg=Colors.INPUT_BG, fg=Colors.TEXT, insertbackground=Colors.PRIMARY, relief=tk.FLAT, bd=8)
        email_entry.insert(0, vals[2])
        email_entry.pack(fill=tk.X)
        
        # Role
        tk.Label(container, text="🛡️ Role", font=Fonts.BODY_BOLD, bg=Colors.CARD_BG, fg=Colors.TEXT).pack(anchor=tk.W, pady=(0, 5))
        role_var = tk.StringVar(value=vals[3].lower())
        
        role_frame = tk.Frame(container, bg=Colors.CARD_BG)
        role_frame.pack(fill=tk.X, pady=(0, 25))
        
        style = ttk.Style()
        style.configure('Dark.TRadiobutton', background=Colors.CARD_BG, foreground=Colors.TEXT, font=Fonts.BODY)
        
        ttk.Radiobutton(role_frame, text="Operator", variable=role_var, value="operator", style='Dark.TRadiobutton', cursor="hand2").pack(side=tk.LEFT, padx=(0, 20))
        ttk.Radiobutton(role_frame, text="Admin", variable=role_var, value="admin", style='Dark.TRadiobutton', cursor="hand2").pack(side=tk.LEFT)
        
        def save():
            if self.auth.edit_user(self.selected_user, email_entry.get().strip(), role_var.get()):
                dialog.destroy()
                self.load_users()
                
        btn_frame = tk.Frame(container, bg=Colors.CARD_BG)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        WidgetStyles.create_modern_button(btn_frame, "Save Changes", command=save, style='info').pack(side=tk.RIGHT, padx=(10, 0))
        WidgetStyles.create_modern_button(btn_frame, "Cancel", command=dialog.destroy, style='secondary').pack(side=tk.RIGHT)

    def delete_selected_user(self):
        if not self.selected_user:
            return
            
        item = self.users_tree.item(self.selected_user)
        username = item['values'][1] if item['values'] else "Unknown"
        
        dialog = tk.Toplevel(self.frame)
        dialog.title("Confirm Delete")
        dialog.configure(bg=Colors.BACKGROUND)
        self.center_dialog(dialog, 400, 220)
        dialog.grab_set()
        
        container = tk.Frame(dialog, bg=Colors.CARD_BG)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        tk.Label(container, text="⚠️ Delete User", font=Fonts.TITLE, bg=Colors.CARD_BG, fg=Colors.DANGER).pack(anchor=tk.W, pady=(0, 10))
        tk.Label(container, text=f"Are you sure you want to permanently delete\nuser '{username}'?", font=Fonts.BODY, bg=Colors.CARD_BG, fg=Colors.TEXT, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 20))
        
        def confirm():
            if self.auth.delete_user(self.selected_user):
                dialog.destroy()
                self.load_users()
                
        btn_frame = tk.Frame(container, bg=Colors.CARD_BG)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        WidgetStyles.create_modern_button(btn_frame, "Delete", command=confirm, style='danger').pack(side=tk.RIGHT, padx=(10, 0))
        WidgetStyles.create_modern_button(btn_frame, "Cancel", command=dialog.destroy, style='secondary').pack(side=tk.RIGHT)

    def get_widget(self):
        return self.frame
