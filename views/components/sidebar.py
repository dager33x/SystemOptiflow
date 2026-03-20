# views/components/sidebar.py
"""
Modern collapsible sidebar with smooth toggle animation.

Expanded  → 220 px wide, shows icon + label + page names + camera pills
Collapsed → 58 px wide, shows icons only with tooltip on hover

Toggle: click the ‹ / › arrow button pinned at top-right of sidebar.
"""
import tkinter as tk
from ..styles import Colors, Fonts


# ── Constants ────────────────────────────────────────────────────────────────
_EXPANDED_W  = 220
_COLLAPSED_W = 58
_ANIM_STEPS  = 6          # frames for the slide animation
_ANIM_MS     = 8          # ms per frame  (~130ms total, feels instant)

_SIDEBAR_BG  = '#0D1117'  # near-black — slightly darker than body
_ACTIVE_BG   = '#1A2740'  # subtle blue tint when selected
_HOVER_BG    = '#161D28'
_PILL_BG     = '#1E2D45'
_ACCENT      = Colors.PRIMARY
_TEXT        = Colors.TEXT
_MUTED       = Colors.TEXT_LIGHT
_BORDER      = '#1C2333'


class Sidebar:
    """Collapsible navigation sidebar."""

    def __init__(self, parent, cameras_data=None, on_nav_click=None,
                 is_admin=False):
        self.parent        = parent
        self.cameras_data  = cameras_data or []
        self.on_nav_click  = on_nav_click
        self.is_admin      = is_admin

        self.nav_buttons: dict      = {}   # page_name → (btn, label_widget)
        self.active_page: str       = 'dashboard'
        self._expanded: bool        = True
        self._animating: bool       = False
        self._tooltip_wins: list    = []   # open tooltip windows

        self.frame = None
        self._create_widgets()

    # ═══════════════════════════════════════════════════════════════════════
    # Build
    # ═══════════════════════════════════════════════════════════════════════
    def _create_widgets(self):
        # Outer frame — fixed width, controlled by toggle
        self.frame = tk.Frame(self.parent, bg=_SIDEBAR_BG,
                              width=_EXPANDED_W)
        self.frame.pack(side=tk.LEFT, fill=tk.Y)
        self.frame.pack_propagate(False)

        # ── Thin right border ────────────────────────────────────────────
        border = tk.Frame(self.frame, bg=_BORDER, width=1)
        border.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Inner scroll canvas (allows future scroll if too many items) ─
        self._inner = tk.Frame(self.frame, bg=_SIDEBAR_BG)
        self._inner.pack(fill=tk.BOTH, expand=True)

        self._build_brand()
        self._build_toggle_btn()
        self._build_nav()
        self._build_cameras_section()

    # ── Brand logo row ───────────────────────────────────────────────────
    def _build_brand(self):
        brand_row = tk.Frame(self._inner, bg=_SIDEBAR_BG, height=64)
        brand_row.pack(fill=tk.X)
        brand_row.pack_propagate(False)

        # Icon
        icon_lbl = tk.Label(brand_row, text='🚦',
                            font=('Segoe UI Emoji', 20),
                            bg=_SIDEBAR_BG, fg=_ACCENT)
        icon_lbl.place(x=12, rely=0.5, anchor='w')
        self._brand_icon = icon_lbl

        # Text
        text_lbl = tk.Label(brand_row, text='Optiflow',
                            font=('Segoe UI', 13, 'bold'),
                            bg=_SIDEBAR_BG, fg=_TEXT)
        text_lbl.place(x=48, rely=0.5, anchor='w')
        self._brand_text = text_lbl

        sub_lbl = tk.Label(brand_row, text='Traffic AI',
                           font=('Segoe UI', 8),
                           bg=_SIDEBAR_BG, fg=_MUTED)
        sub_lbl.place(x=48, rely=0.72, anchor='w')
        self._brand_sub = sub_lbl

        # Bottom separator
        tk.Frame(brand_row, bg=_BORDER, height=1).place(
            relx=0, rely=1.0, relwidth=1.0, anchor='sw')

    # ── Toggle button (‹ / ›) ────────────────────────────────────────────
    def _build_toggle_btn(self):
        tog = tk.Label(self._inner, text='‹',
                       font=('Segoe UI', 12, 'bold'),
                       bg='#1C2333', fg=_MUTED,
                       cursor='hand2', padx=6, pady=3)
        tog.pack(anchor='e', padx=6, pady=(6, 2))
        tog.bind('<Button-1>', lambda e: self._toggle())
        tog.bind('<Enter>', lambda e: tog.config(fg=_ACCENT))
        tog.bind('<Leave>', lambda e: tog.config(fg=_MUTED))
        self._toggle_btn = tog

    # ── Navigation section ───────────────────────────────────────────────
    def _build_nav(self):
        # Section label
        self._nav_section_lbl = tk.Label(self._inner,
                                         text='MENU',
                                         font=('Segoe UI', 7, 'bold'),
                                         bg=_SIDEBAR_BG, fg=_MUTED,
                                         anchor='w')
        self._nav_section_lbl.pack(fill=tk.X, padx=16, pady=(10, 4))

        nav_items = [
            ('📊', 'Traffic Live Camera', 'dashboard'),
            ('⚠️', 'Issue Reports',    'issue_reports'),
            ('🚦', 'Traffic Reports',  'traffic_reports'),
            ('📜', 'Incident History', 'incident_history'),
            ('📋', 'Violation Logs',   'violation_logs'),
            ('⚙️', 'Settings',         'settings'),
        ]
        if self.is_admin:
            nav_items.insert(6, ('👥', 'Manage Users', 'admin_users'))

        for icon, label, page_name in nav_items:
            self._create_nav_row(icon, label, page_name)

    def _create_nav_row(self, icon: str, label: str, page_name: str):
        """One nav row: left-accent bar + icon + label text."""
        # Container row
        row = tk.Frame(self._inner, bg=_SIDEBAR_BG, height=40, cursor='hand2')
        row.pack(fill=tk.X, pady=1)
        row.pack_propagate(False)

        # Left accent bar (hidden until active)
        accent = tk.Frame(row, bg=_ACCENT, width=3)
        accent.pack(side=tk.LEFT, fill=tk.Y)
        accent.pack_propagate(False)

        # Icon
        icon_lbl = tk.Label(row, text=icon,
                            font=('Segoe UI Emoji', 13),
                            bg=_SIDEBAR_BG, fg=_MUTED,
                            width=3, anchor='center')
        icon_lbl.pack(side=tk.LEFT, padx=(6, 0))

        # Label text
        text_lbl = tk.Label(row, text=label,
                            font=Fonts.BODY,
                            bg=_SIDEBAR_BG, fg=_MUTED,
                            anchor='w')
        text_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 10))
        
        # Badge canvas (Real Red Dot Notification)
        badge_canvas = tk.Canvas(row, width=20, height=20, bg=_SIDEBAR_BG, highlightthickness=0)
        circle_id = badge_canvas.create_oval(1, 1, 19, 19, fill=Colors.DANGER, outline='')
        text_id = badge_canvas.create_text(10, 10, text="", fill="white", font=('Segoe UI', 8, 'bold'))

        # Store references
        self.nav_buttons[page_name] = {
            'row': row, 'accent': accent,
            'icon': icon_lbl, 'text': text_lbl,
            'badge_canvas': badge_canvas,
            'badge_text_id': text_id
        }

        # Events helper
        widgets = [row, icon_lbl, text_lbl]

        def _click(_e, pn=page_name):
            self._set_active(pn)
            if self.on_nav_click:
                self.on_nav_click(pn)

        def _enter(_e):
            if page_name != self.active_page:
                row.config(bg=_HOVER_BG)
                icon_lbl.config(bg=_HOVER_BG)
                text_lbl.config(bg=_HOVER_BG, fg=_TEXT)
                badge_canvas.config(bg=_HOVER_BG)
            # Show tooltip when collapsed
            if not self._expanded:
                self._show_tooltip(row, label)

        def _leave(_e):
            if page_name != self.active_page:
                row.config(bg=_SIDEBAR_BG)
                icon_lbl.config(bg=_SIDEBAR_BG)
                text_lbl.config(bg=_SIDEBAR_BG, fg=_MUTED)
                badge_canvas.config(bg=_SIDEBAR_BG)
            self._hide_tooltips()

        for w in widgets:
            w.bind('<Button-1>', _click)
            w.bind('<Enter>',    _enter)
            w.bind('<Leave>',    _leave)

        # Hide accent bar if not active
        accent.config(bg=_SIDEBAR_BG)

    def _set_active(self, page_name: str):
        """Highlight the active nav item."""
        for pn, refs in self.nav_buttons.items():
            if pn == page_name:
                refs['row'].config(bg=_ACTIVE_BG)
                refs['icon'].config(bg=_ACTIVE_BG, fg=_ACCENT)
                refs['text'].config(bg=_ACTIVE_BG, fg=_TEXT)
                refs['accent'].config(bg=_ACCENT)
                refs['badge_canvas'].config(bg=_ACTIVE_BG)
            else:
                refs['row'].config(bg=_SIDEBAR_BG)
                refs['icon'].config(bg=_SIDEBAR_BG, fg=_MUTED)
                refs['text'].config(bg=_SIDEBAR_BG, fg=_MUTED)
                refs['accent'].config(bg=_SIDEBAR_BG)
                refs['badge_canvas'].config(bg=_SIDEBAR_BG)
        self.active_page = page_name

    # ── Cameras section ──────────────────────────────────────────────────
    def _build_cameras_section(self):
        # Separator
        tk.Frame(self._inner, bg=_BORDER, height=1).pack(
            fill=tk.X, padx=12, pady=(12, 0))

        self._cam_section_lbl = tk.Label(self._inner,
                                         text='ACTIVE CAMERAS',
                                         font=('Segoe UI', 7, 'bold'),
                                         bg=_SIDEBAR_BG, fg=_MUTED,
                                         anchor='w')
        self._cam_section_lbl.pack(fill=tk.X, padx=16, pady=(8, 4))

        self._cam_container = tk.Frame(self._inner, bg=_SIDEBAR_BG)
        self._cam_container.pack(fill=tk.X)
        self.render_cameras()

    def render_cameras(self):
        for w in self._cam_container.winfo_children():
            w.destroy()

        for cam in self.cameras_data:
            self._create_camera_pill(cam)

    def _create_camera_pill(self, camera: dict):
        status       = camera.get('status', 'unknown').lower()
        name         = camera.get('name', 'Camera')
        status_color = Colors.get_status_color(status)

        pill = tk.Frame(self._cam_container, bg=_PILL_BG,
                        padx=10, pady=6)
        pill.pack(fill=tk.X, padx=10, pady=2)

        # Dot
        dot_c = tk.Canvas(pill, width=8, height=8,
                          bg=_PILL_BG, highlightthickness=0)
        dot_c.pack(side=tk.LEFT, padx=(0, 6))
        dot_c.create_oval(1, 1, 7, 7, fill=status_color, outline='')

        # Name
        tk.Label(pill, text=name, font=('Segoe UI', 9),
                 bg=_PILL_BG, fg=_TEXT,
                 anchor='w').pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Status tag (hidden in collapsed mode)
        tag = tk.Label(pill, text=status.upper(),
                       font=('Segoe UI', 7, 'bold'),
                       bg=_PILL_BG, fg=status_color)
        tag.pack(side=tk.RIGHT)
        tag._cam_tag = True

    # ═══════════════════════════════════════════════════════════════════════
    # Toggle / animation
    # ═══════════════════════════════════════════════════════════════════════
    def _toggle(self):
        self._expanded  = not self._expanded

        target_w  = _EXPANDED_W if self._expanded else _COLLAPSED_W

        self._toggle_btn.config(text='\u2039' if self._expanded else '\u203a')

        if not self._expanded:
            self._set_text_visible(False)
            self.frame.config(width=target_w)
        else:
            self.frame.config(width=target_w)
            self._set_text_visible(True)

    def _set_text_visible(self, visible: bool):
        """Show or hide all text-heavy elements instantly (no intermediate layout)."""
        if visible:
            self._brand_text.place(x=48, rely=0.5, anchor='w')
            self._brand_sub.place(x=48, rely=0.72, anchor='w')
            self._nav_section_lbl.pack(fill=tk.X, padx=16, pady=(10, 4))
            self._cam_section_lbl.pack(fill=tk.X, padx=16, pady=(8, 4))
            for refs in self.nav_buttons.values():
                refs['text'].pack(side=tk.LEFT, fill=tk.X,
                                  expand=True, padx=(6, 10))
                # Check if badge has a count to show
                if refs['badge_canvas'].itemcget(refs['badge_text_id'], 'text') not in ('', '0'):
                    refs['badge_canvas'].pack(side=tk.RIGHT, padx=(0, 15))
            self._cam_container.pack(fill=tk.X)
        else:
            self._brand_text.place_forget()
            self._brand_sub.place_forget()
            self._nav_section_lbl.pack_forget()
            self._cam_section_lbl.pack_forget()
            for refs in self.nav_buttons.values():
                refs['text'].pack_forget()
                refs['badge_canvas'].pack_forget()
            self._cam_container.pack_forget()

    # ═══════════════════════════════════════════════════════════════════════
    # Tooltip (icons-only mode)
    # ═══════════════════════════════════════════════════════════════════════
    def _show_tooltip(self, widget: tk.Widget, text: str):
        self._hide_tooltips()
        try:
            x = widget.winfo_rootx() + _COLLAPSED_W + 4
            y = widget.winfo_rooty() + widget.winfo_height() // 2
        except Exception:
            return

        tip = tk.Toplevel(widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f'+{x}+{y - 14}')
        tip.config(bg=_ACCENT)

        tk.Label(tip, text=text, font=('Segoe UI', 10),
                 bg=_ACCENT, fg='white', padx=10, pady=5).pack()

        self._tooltip_wins.append(tip)

    def _hide_tooltips(self):
        for w in self._tooltip_wins:
            try:
                w.destroy()
            except Exception:
                pass
        self._tooltip_wins.clear()

    # ═══════════════════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════════════════
    def update_cameras(self, new_data: list):
        self.cameras_data = new_data
        self.render_cameras()

    def update_nav_badge(self, page_name: str, count: int):
        """Update notification badge circle with count"""
        if page_name in self.nav_buttons:
            refs = self.nav_buttons[page_name]
            canvas = refs['badge_canvas']
            text_id = refs['badge_text_id']
            if count > 0:
                canvas.itemconfig(text_id, text=str(count))
                if self._expanded:
                    canvas.pack(side=tk.RIGHT, padx=(0, 15))
            else:
                canvas.itemconfig(text_id, text="0")
                canvas.pack_forget()

    def get_widget(self) -> tk.Frame:
        return self.frame
