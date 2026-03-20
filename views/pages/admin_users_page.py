import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from ..styles import Colors, Fonts

class AdminUsersPage:
    """Admin User Management Page using CustomTkinter"""
    
    def __init__(self, parent, auth_controller):
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.auth = auth_controller
        self.selected_user = None
        
        # Initialize CTk explicitly for rendering mode (dark)
        ctk.set_appearance_mode("dark")
        self.create_widgets()
        
    def create_widgets(self):
        """Create page content"""
        # Title section
        title_section = ctk.CTkFrame(self.frame, fg_color="transparent")
        title_section.pack(fill=tk.X, pady=(30, 15), padx=40)
        
        title_container = ctk.CTkFrame(title_section, fg_color="transparent")
        title_container.pack(side=tk.LEFT)
        ctk.CTkLabel(title_container, text="User Management", font=('Segoe UI', 24, 'bold'), text_color=Colors.TEXT).pack(anchor=tk.W)
        ctk.CTkLabel(title_container, text="Manage operator and admin accounts across the system.", font=('Segoe UI', 14), text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(5, 0))

        # Action buttons
        buttons_frame = ctk.CTkFrame(title_section, fg_color="transparent")
        buttons_frame.pack(side=tk.RIGHT)
        
        self.create_button(buttons_frame, "+ Add User", Colors.SUCCESS, Colors.SUCCESS_DARK, self.show_add_user_dialog)
        self.create_button(buttons_frame, "✏️ Edit", Colors.INFO, Colors.INFO_DARK, self.show_edit_user_dialog)
        self.create_button(buttons_frame, "🗑️ Delete", Colors.DANGER, Colors.DANGER_DARK, self.delete_selected_user)
        self.create_button(buttons_frame, "🔄 Refresh", "#1E293B", "#334155", self.load_users)
        
        # Treeview Container
        card_frame = ctk.CTkFrame(self.frame, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        card_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=(10, 30))
        
        # Inner padding frame
        table_frame = ctk.CTkFrame(card_frame, fg_color="transparent")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Create treeview
        columns = ("ID", "Username", "Email", "Role", "Status", "Created")
        self.users_tree = ttk.Treeview(table_frame, columns=columns, height=15, show="headings")
        
        column_widths = {
            "ID": 100, "Username": 150, "Email": 250, 
            "Role": 100, "Status": 100, "Created": 150
        }
        
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

        for col, width in column_widths.items():
            self.users_tree.heading(col, text=col)
            if col == 'Email' or col == 'Username':
                self.users_tree.column(col, width=width, anchor=tk.W)
            else:
                self.users_tree.column(col, width=width, anchor=tk.CENTER)
            
        scrollbar = ctk.CTkScrollbar(table_frame, orientation="vertical", command=self.users_tree.yview)
        self.users_tree.configure(yscroll=scrollbar.set)
        
        self.users_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        
        self.users_tree.bind("<<TreeviewSelect>>", self.on_user_select)
        
        # Initial load
        self.load_users()
        
    def create_button(self, parent, text, bg_col, hover_col, command):
        btn = ctk.CTkButton(parent, text=text, font=('Segoe UI', 13, 'bold'), 
                            fg_color=bg_col, hover_color=hover_col, text_color="white",
                            corner_radius=8, height=36, command=command)
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
                                     values=(user_id, f" {username}", f" {email}", role, status, created),
                                     tags=("admin",) if role == "ADMIN" else ("operator",))
                                     
        self.users_tree.tag_configure("admin", foreground=Colors.DANGER)
        self.users_tree.tag_configure("operator", foreground=Colors.INFO)

    def on_user_select(self, event):
        selection = self.users_tree.selection()
        if selection:
            self.selected_user = selection[0]

    def show_add_user_dialog(self):
        dialog = ctk.CTkToplevel(self.frame)
        dialog.title("Add New User")
        dialog.geometry("450x600")
        dialog.configure(fg_color=Colors.BACKGROUND)
        
        dialog.attributes('-topmost', True)
        dialog.transient(self.frame)
        dialog.grab_set()
        
        container = ctk.CTkFrame(dialog, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        container.pack(fill=tk.BOTH, expand=True, padx=30, pady=30)
        
        # Inner Frame
        inner = ctk.CTkFrame(container, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        header_frame = ctk.CTkFrame(inner, fg_color="transparent")
        header_frame.pack(fill=tk.X, pady=(0, 25))
        
        ctk.CTkLabel(header_frame, text="Add New User", font=('Segoe UI', 20, 'bold'), text_color=Colors.PRIMARY).pack(side=tk.LEFT)
        ctk.CTkLabel(header_frame, text="Create a new account", font=('Segoe UI', 12), text_color=Colors.TEXT_MUTED).pack(side=tk.LEFT, padx=10, pady=(6, 0))
        
        # Fields
        entries = {}
        for field, icon, is_pwd in [("Username", "👤", False), ("Email", "✉️", False), ("Password", "🔑", True)]:
            frame = ctk.CTkFrame(inner, fg_color="transparent")
            frame.pack(fill=tk.X, pady=(0, 15))
            ctk.CTkLabel(frame, text=f"{icon} {field}", font=('Segoe UI', 12, 'bold'), text_color=Colors.TEXT).pack(anchor=tk.W, pady=(0, 5))
            
            entry = ctk.CTkEntry(frame, font=('Segoe UI', 14), fg_color="#0B111D", border_color="#2c3a52", border_width=1, show="*" if is_pwd else "")
            entry.pack(fill=tk.X, ipady=5)
            entries[field.lower()] = entry
            
        # Role
        role_frame = ctk.CTkFrame(inner, fg_color="transparent")
        role_frame.pack(fill=tk.X, pady=(0, 25))
        ctk.CTkLabel(role_frame, text="🛡️ Role", font=('Segoe UI', 12, 'bold'), text_color=Colors.TEXT).pack(anchor=tk.W, pady=(0, 5))
        
        role_var = tk.StringVar(value="operator")
        
        radio_frame = ctk.CTkFrame(role_frame, fg_color="transparent")
        radio_frame.pack(fill=tk.X)
        ctk.CTkRadioButton(radio_frame, text="Operator", variable=role_var, value="operator", font=('Segoe UI', 13)).pack(side=tk.LEFT, padx=(0, 20))
        ctk.CTkRadioButton(radio_frame, text="Admin", variable=role_var, value="admin", font=('Segoe UI', 13)).pack(side=tk.LEFT)
        
        def save():
            u = entries['username'].get().strip()
            e = entries['email'].get().strip()
            p = entries['password'].get()
            r = role_var.get()
            
            if not u or not e or not p:
                messagebox.showerror("Error", "All fields are required", parent=dialog)
                return
                
            if self.auth.add_user(u, e, p, r):
                dialog.attributes('-topmost', False)
                dialog.destroy()
                self.load_users()
                
        def safely_close():
             # Drop topmost locking rule
             dialog.attributes('-topmost', False)
             dialog.destroy()
        
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        
        ctk.CTkButton(btn_frame, text="Save User", command=save, font=('Segoe UI', 13, 'bold'), fg_color=Colors.SUCCESS, hover_color=Colors.SUCCESS_DARK, corner_radius=8, height=36).pack(side=tk.RIGHT)
        ctk.CTkButton(btn_frame, text="Cancel", command=safely_close, font=('Segoe UI', 13, 'bold'), fg_color='transparent', hover_color='#334155', border_color='#334155', border_width=1, corner_radius=8, height=36).pack(side=tk.RIGHT, padx=10)

    def show_edit_user_dialog(self):
        if not self.selected_user:
            return
            
        item = self.users_tree.item(self.selected_user)
        vals = item['values']
        username_clean = vals[1].strip()
        email_clean = vals[2].strip()
        
        dialog = ctk.CTkToplevel(self.frame)
        dialog.title("Edit User")
        dialog.geometry("450x450")
        dialog.configure(fg_color=Colors.BACKGROUND)
        
        dialog.attributes('-topmost', True)
        dialog.transient(self.frame)
        dialog.grab_set()
        
        container = ctk.CTkFrame(dialog, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        container.pack(fill=tk.BOTH, expand=True, padx=30, pady=30)
        
        # Inner Frame
        inner = ctk.CTkFrame(container, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        header_frame = ctk.CTkFrame(inner, fg_color="transparent")
        header_frame.pack(fill=tk.X, pady=(0, 25))
        
        ctk.CTkLabel(header_frame, text="Edit User", font=('Segoe UI', 20, 'bold'), text_color=Colors.INFO).pack(side=tk.LEFT)
        ctk.CTkLabel(header_frame, text=username_clean, font=('Segoe UI', 12), text_color=Colors.TEXT_MUTED).pack(side=tk.LEFT, padx=10, pady=(6, 0))
        
        # Email
        ctk.CTkLabel(inner, text="✉️ Email", font=('Segoe UI', 12, 'bold'), text_color=Colors.TEXT).pack(anchor=tk.W, pady=(0, 5))
        email_entry = ctk.CTkEntry(inner, font=('Segoe UI', 14), fg_color="#0B111D", border_color="#2c3a52", border_width=1)
        email_entry.insert(0, email_clean)
        email_entry.pack(fill=tk.X, ipady=5, pady=(0, 20))
        
        # Role
        ctk.CTkLabel(inner, text="🛡️ Role", font=('Segoe UI', 12, 'bold'), text_color=Colors.TEXT).pack(anchor=tk.W, pady=(0, 5))
        role_var = tk.StringVar(value=vals[3].lower())
        
        role_frame = ctk.CTkFrame(inner, fg_color="transparent")
        role_frame.pack(fill=tk.X, pady=(0, 25))
        ctk.CTkRadioButton(role_frame, text="Operator", variable=role_var, value="operator", font=('Segoe UI', 13)).pack(side=tk.LEFT, padx=(0, 20))
        ctk.CTkRadioButton(role_frame, text="Admin", variable=role_var, value="admin", font=('Segoe UI', 13)).pack(side=tk.LEFT)
        
        def save():
            if self.auth.edit_user(self.selected_user, email_entry.get().strip(), role_var.get()):
                dialog.attributes('-topmost', False)
                dialog.destroy()
                self.load_users()
                
        def safely_close():
             # Drop topmost locking rule
             dialog.attributes('-topmost', False)
             dialog.destroy()
             
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        ctk.CTkButton(btn_frame, text="Save Changes", command=save, font=('Segoe UI', 13, 'bold'), fg_color=Colors.INFO, hover_color=Colors.INFO_DARK, corner_radius=8, height=36).pack(side=tk.RIGHT)
        ctk.CTkButton(btn_frame, text="Cancel", command=safely_close, font=('Segoe UI', 13, 'bold'), fg_color='transparent', hover_color='#334155', border_color='#334155', border_width=1, corner_radius=8, height=36).pack(side=tk.RIGHT, padx=10)

    def delete_selected_user(self):
        if not self.selected_user:
            return
            
        item = self.users_tree.item(self.selected_user)
        username = item['values'][1].strip() if item['values'] else "Unknown"
        
        dialog = ctk.CTkToplevel(self.frame)
        dialog.title("Confirm Delete")
        dialog.geometry("400x250")
        dialog.configure(fg_color=Colors.BACKGROUND)
        
        dialog.attributes('-topmost', True)
        dialog.transient(self.frame)
        dialog.grab_set()
        
        container = ctk.CTkFrame(dialog, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(container, text="⚠️ Delete User", font=('Segoe UI', 20, 'bold'), text_color=Colors.DANGER).pack(anchor=tk.W, padx=20, pady=(20, 10))
        ctk.CTkLabel(container, text=f"Are you sure you want to permanently delete\nuser '{username}'?", font=('Segoe UI', 14), text_color=Colors.TEXT, justify=tk.LEFT).pack(anchor=tk.W, padx=20, pady=(0, 20))
        
        def confirm():
            if self.auth.delete_user(self.selected_user):
                dialog.attributes('-topmost', False)
                dialog.destroy()
                self.load_users()

        def safely_close():
             # Drop topmost locking rule
             dialog.attributes('-topmost', False)
             dialog.destroy()
             
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=20)
        
        ctk.CTkButton(btn_frame, text="Delete", command=confirm, font=('Segoe UI', 13, 'bold'), fg_color=Colors.DANGER, hover_color=Colors.DANGER_DARK, corner_radius=8, height=36).pack(side=tk.RIGHT)
        ctk.CTkButton(btn_frame, text="Cancel", command=safely_close, font=('Segoe UI', 13, 'bold'), fg_color='transparent', hover_color='#334155', border_color='#334155', border_width=1, corner_radius=8, height=36).pack(side=tk.RIGHT, padx=10)

    def get_widget(self):
        return self.frame
