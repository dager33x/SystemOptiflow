# views/main_window.py
"""
Modern shell layout
════════════════════════════════════════════════════════
 ┌──────────────────────────────────────────────────────┐
 │  TOP BAR  (48 px) — breadcrumb | clock | user | logout │
 ├──────┬───────────────────────────────────────────────┤
 │Side  │                                               │
 │bar   │          CONTENT AREA                         │
 │(col.)│                                               │
 └──────┴───────────────────────────────────────────────┘

The sidebar is collapsible (‹ / › toggle built into it).
No separate footer — cleaner layout.
"""
import tkinter as tk
from tkinter import messagebox
from datetime import datetime

from .components.sidebar import Sidebar
from .styles import Colors, Fonts


_TOPBAR_BG  = '#090D14'   # darkest possible — almost pure black
_TOPBAR_H   = 48
_BORDER_CLR = '#1C2333'
_ACCENT     = Colors.PRIMARY
_TEXT       = Colors.TEXT
_MUTED      = Colors.TEXT_LIGHT


class MainWindow:
    """Main application shell."""

    def __init__(self, root, controllers, current_user=None):
        self.root         = root
        self.controllers  = controllers
        self.current_user = current_user

        self.content_area = None
        self.sidebar      = None
        self._page_title_var: tk.StringVar = None

        self._setup_window()
        self._create_layout()

    # ═══════════════════════════════════════════════════════════════════════
    def _setup_window(self):
        self.root.configure(bg=Colors.BACKGROUND)

    # ═══════════════════════════════════════════════════════════════════════
    def _create_layout(self):
        # ── 1. Top bar ───────────────────────────────────────────────────
        self._build_topbar()

        # ── 2. Thin accent separator ─────────────────────────────────────
        tk.Frame(self.root, bg=_ACCENT, height=2).pack(fill=tk.X)

        # ── 3. Body row (sidebar + content) ──────────────────────────────
        body = tk.Frame(self.root, bg=Colors.BACKGROUND)
        body.pack(fill=tk.BOTH, expand=True)

        # Sidebar
        cameras_data = self._get_cameras_data()
        nav_callback = (self.controllers['main'].handle_navigation
                        if self.controllers and 'main' in self.controllers
                        else None)
        is_admin = (self.current_user or {}).get('role') == 'admin'

        self.sidebar = Sidebar(
            body,
            cameras_data=cameras_data,
            on_nav_click=self._on_nav,
            is_admin=is_admin,
        )

        # Content area
        self.content_area = tk.Frame(body, bg=Colors.BACKGROUND)
        self.content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ── Top bar ──────────────────────────────────────────────────────────
    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=_TOPBAR_BG, height=_TOPBAR_H)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        # bottom border line
        tk.Frame(bar, bg=_BORDER_CLR, height=1).place(
            relx=0, rely=1.0, relwidth=1.0, anchor='sw')

        # ── Left: breadcrumb ─────────────────────────────────────────────
        left = tk.Frame(bar, bg=_TOPBAR_BG)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=16)

        tk.Label(left, text='SystemOptiflow',
                 font=('Segoe UI', 10, 'bold'),
                 bg=_TOPBAR_BG, fg=_TEXT).pack(side=tk.LEFT, pady=14)

        tk.Label(left, text=' / ',
                 font=('Segoe UI', 10),
                 bg=_TOPBAR_BG, fg=_MUTED).pack(side=tk.LEFT)

        self._page_title_var = tk.StringVar(value='Dashboard')
        tk.Label(left, textvariable=self._page_title_var,
                 font=('Segoe UI', 10),
                 bg=_TOPBAR_BG, fg=_MUTED).pack(side=tk.LEFT)

        # ── Right: clock + user pill + logout ────────────────────────────
        right = tk.Frame(bar, bg=_TOPBAR_BG)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=14)

        # Logout button
        if self.controllers and 'main' in self.controllers:
            logout_btn = tk.Label(right, text='⏻  Logout',
                                  font=('Segoe UI', 9, 'bold'),
                                  bg='#2D0000', fg='#EF4444',
                                  padx=10, pady=4, cursor='hand2')
            logout_btn.pack(side=tk.RIGHT, pady=12)
            logout_btn.bind('<Button-1>', lambda e: self._logout())
            logout_btn.bind('<Enter>',
                            lambda e: logout_btn.config(bg='#4D0000'))
            logout_btn.bind('<Leave>',
                            lambda e: logout_btn.config(bg='#2D0000'))

        # Separator
        tk.Frame(right, bg=_BORDER_CLR, width=1).pack(
            side=tk.RIGHT, fill=tk.Y, pady=10, padx=8)

        # User pill
        if self.current_user:
            uname = self.current_user.get('username', 'User')
            role  = self.current_user.get('role', 'operator').upper()
            role_color = '#F59E0B' if role == 'ADMIN' else Colors.INFO

            user_frame = tk.Frame(right, bg='#0D1520', padx=10, pady=4, cursor='hand2')
            user_frame.pack(side=tk.RIGHT, pady=10)

            icon_lbl = tk.Label(user_frame, text='👤',
                                font=('Segoe UI Emoji', 11),
                                bg='#0D1520', fg=_TEXT, cursor='hand2')
            icon_lbl.pack(side=tk.LEFT, padx=(0, 6))

            col = tk.Frame(user_frame, bg='#0D1520', cursor='hand2')
            col.pack(side=tk.LEFT)
            name_lbl = tk.Label(col, text=uname,
                                font=('Segoe UI', 9, 'bold'),
                                bg='#0D1520', fg=_TEXT, cursor='hand2')
            name_lbl.pack(anchor='w')
            role_lbl = tk.Label(col, text=role,
                                font=('Segoe UI', 7),
                                bg='#0D1520', fg=role_color, cursor='hand2')
            role_lbl.pack(anchor='w')

            # Bind clicks to show profile
            for w in (user_frame, icon_lbl, col, name_lbl, role_lbl):
                w.bind('<Button-1>', lambda e: self.show_profile_info())

        # Separator
        tk.Frame(right, bg=_BORDER_CLR, width=1).pack(
            side=tk.RIGHT, fill=tk.Y, pady=10, padx=8)

        # Clock
        self._clock_lbl = tk.Label(right,
                                   font=('Consolas', 12),
                                   bg=_TOPBAR_BG, fg=_TEXT)
        self._clock_lbl.pack(side=tk.RIGHT, pady=14)
        self._tick_clock()

    def _tick_clock(self):
        now = datetime.now().strftime('%H:%M:%S')
        self._clock_lbl.config(text=now)
        self.root.after(1000, self._tick_clock)

    # ═══════════════════════════════════════════════════════════════════════
    # Navigation
    # ═══════════════════════════════════════════════════════════════════════
    _PAGE_TITLES = {
        'dashboard':       'Live Dashboard',
        'issue_reports':   'Issue Reports',
        'traffic_reports': 'Traffic Reports',
        'incident_history':'Incident History',
        'violation_logs':  'Violation Logs',
        'settings':        'Settings',
        'admin_users':     'Manage Users',
    }

    def _on_nav(self, page_name: str):
        """Update breadcrumb then delegate to main controller."""
        title = self._PAGE_TITLES.get(page_name, page_name.replace('_', ' ').title())
        if self._page_title_var:
            self._page_title_var.set(title)
        if self.sidebar:
            self.sidebar._set_active(page_name)
        if self.controllers and 'main' in self.controllers:
            self.controllers['main'].handle_navigation(page_name)

    def _logout(self):
        if messagebox.askyesno("Logout", "Are you sure you want to log-out?"):
            if self.controllers and 'main' in self.controllers:
                self.controllers['main'].logout()

    # ═══════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════
    def _get_cameras_data(self) -> list:
        try:
            data = self.controllers['main'].get_active_cameras()
            if data:
                return data
        except Exception:
            pass
        return [
            {'name': 'North Gate',     'status': 'inactive'},
            {'name': 'South Junction', 'status': 'inactive'},
            {'name': 'East Portal',    'status': 'inactive'},
            {'name': 'West Avenue',    'status': 'inactive'},
        ]

    def show_page(self, page_widget):
        """Swap content area."""
        for w in self.content_area.winfo_children():
            w.destroy()
        page_widget.pack(fill=tk.BOTH, expand=True)

    def show_profile_info(self):
        """Show dialog with full user information"""
        if not self.current_user:
            return
            
        dialog = tk.Toplevel(self.root)
        dialog.title("User Profile")
        dialog.geometry("400x500")
        dialog.configure(bg=Colors.BACKGROUND)
        dialog.transient(self.root.winfo_toplevel())
        
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
        
        icon_cont = tk.Frame(header, bg=Colors.PRIMARY)
        icon_cont.pack(expand=True)
        tk.Label(icon_cont, text="👤", font=("Segoe UI Emoji", 48),
                 bg=Colors.PRIMARY, fg="white").pack()
        
        # Content
        content = tk.Frame(dialog, bg=Colors.BACKGROUND, padx=30, pady=30)
        content.pack(fill=tk.BOTH, expand=True)
        
        def add_field(label, value, is_bold=False):
            frame = tk.Frame(content, bg=Colors.BACKGROUND)
            frame.pack(fill=tk.X, pady=8)
            tk.Label(frame, text=label.upper(), font=("Segoe UI", 8, "bold"),
                     bg=Colors.BACKGROUND, fg=Colors.TEXT_LIGHT).pack(anchor=tk.W)
            val_font = ("Segoe UI", 12, "bold") if is_bold else ("Segoe UI", 11)
            tk.Label(frame, text=value if value else "Not set", font=val_font,
                     bg=Colors.BACKGROUND, fg=Colors.TEXT).pack(anchor=tk.W)
            tk.Frame(frame, height=1, bg=Colors.SECONDARY).pack(fill=tk.X, pady=(5, 0))

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
                created = created.split('T')[0]
            except Exception:
                pass
        add_field("Member Since", created)
        
        tk.Frame(content, bg=Colors.BACKGROUND, height=20).pack()
        tk.Button(content, text="Close", font=("Segoe UI", 10),
                  bg=Colors.SECONDARY, fg="white", relief=tk.FLAT,
                  command=dialog.destroy, cursor="hand2", pady=8).pack(fill=tk.X)

    def logout(self):
        self._logout()
