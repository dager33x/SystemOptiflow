# views/pages/dashboard.py
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
import cv2
from ..styles import Colors, Fonts

# ─────────────────────────────────────────────
#  Color constants specific to the dashboard
# ─────────────────────────────────────────────
_BG        = Colors.BACKGROUND       # #0B0F19
_CARD      = '#161F33'               # Slightly brighter than before for distinct cards
_HEADER_BG = '#0B111D'               # Very dark for header
_ACCENT    = Colors.PRIMARY          # #3B82F6
_TEXT      = Colors.TEXT
_MUTED     = Colors.TEXT_LIGHT
_SUCCESS   = Colors.SUCCESS
_WARN      = Colors.WARNING
_DANGER    = Colors.DANGER

_SIGNAL_COLORS = {
    'GREEN':    {'bright': '#22C55E', 'dim': '#052E16'},
    'YELLOW':   {'bright': '#EAB308', 'dim': '#1C1A00'},
    'RED':      {'bright': '#EF4444', 'dim': '#2D0000'},
    'ALL_RED':  {'bright': '#EF4444', 'dim': '#2D0000'},
}

# Direction metadata
_DIR_META = {
    'north': {'icon': '▲', 'label': 'NORTH GATE'},
    'south': {'icon': '▼', 'label': 'SOUTH JUNCTION'},
    'east':  {'icon': '▶', 'label': 'EAST PORTAL'},
    'west':  {'icon': '◀', 'label': 'WEST AVENUE'},
}

class DashboardPage:
    """Beautiful CustomTkinter command-center 2x2 camera grid."""

    def __init__(self, parent):
        self.parent = parent
        self.frame = tk.Frame(parent, bg=_BG) # Keep standard tk.Frame as root mount point
        self.camera_labels  = {}
        self.stat_labels    = {}
        self.light_canvases = {}
        self.timer_labels   = {}
        self.lamp_ids       = {}   # {direction: {color: canvas_id}}
        self.signal_badges  = {}   # {direction: ctk.CTkLabel}
        self.is_running = True
        
        # Initialize CTk explicitly for rendering mode (dark)
        ctk.set_appearance_mode("dark")
        self._create_widgets()

    # ─────────────────────────────────────────
    #  Layout construction
    # ─────────────────────────────────────────
    def _create_widgets(self):
        # ── Camera grid (fills full area) ─────
        grid_frame = ctk.CTkFrame(self.frame, fg_color=_BG, corner_radius=0)
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        grid_frame.grid_columnconfigure(0, weight=1, uniform="col")
        grid_frame.grid_columnconfigure(1, weight=1, uniform="col")
        grid_frame.grid_rowconfigure(0, weight=1, uniform="row")
        grid_frame.grid_rowconfigure(1, weight=1, uniform="row")

        directions = ['north', 'south', 'east', 'west']
        coords     = [(0, 0), (0, 1), (1, 0), (1, 1)]

        for direction, (row, col) in zip(directions, coords):
            self._build_camera_card(grid_frame, direction, row, col)

    def _build_camera_card(self, parent, direction, row, col):
        """Build a single camera card using modern CTkFrames with rounded corners."""
        meta = _DIR_META[direction]

        # Use CustomTkinter for beautiful rounded corners and subtle shadow/color differences
        card = ctk.CTkFrame(parent, fg_color=_CARD, corner_radius=15, border_width=1, border_color='#2c3a52')
        card.grid(row=row, column=col, sticky='nsew', padx=10, pady=10)

        # ── Card header strip ─────────────────────────────────────
        card_header = ctk.CTkFrame(card, fg_color=_HEADER_BG, corner_radius=0, height=45)
        card_header.pack(fill=tk.X, side=tk.TOP, anchor='n')
        card_header.pack_propagate(False)

        # Title
        ctk.CTkLabel(card_header, text=f"{meta['icon']}  {meta['label']}",
                     font=('Segoe UI', 13, 'bold'),
                     text_color=_ACCENT).pack(side=tk.LEFT, padx=15, pady=0)

        # Signal state badge (CTkLabel)
        badge = ctk.CTkLabel(card_header, text='● RED', font=('Segoe UI', 12, 'bold'),
                             corner_radius=8, fg_color='#2D0000', text_color='#EF4444', padx=8, pady=2)
        badge.pack(side=tk.RIGHT, padx=15, pady=5)
        self.signal_badges[direction] = badge

        # Body row: camera (left) + traffic light panel (right)
        body = ctk.CTkFrame(card, fg_color='transparent', corner_radius=0)
        body.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ── RIGHT sidebar packed FIRST ──
        sidebar = ctk.CTkFrame(body, fg_color='#101726', corner_radius=10, width=95)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 5), pady=5)
        sidebar.pack_propagate(False)

        # ── Camera feed packed AFTER sidebar so it fills remaining space ──
        cam_outer = ctk.CTkFrame(body, fg_color='#050A10', corner_radius=10)
        cam_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        cam_outer.pack_propagate(False)

        # We keep tk.Label for the camera output as it handles PhotoImage updates very efficiently
        cam_label = tk.Label(cam_outer, bg='#050A10',
                             text='◌  No Signal', fg='#1E3A5F',
                             font=('Segoe UI', 14, 'bold'))
        cam_label.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.camera_labels[direction] = cam_label

        # ── Realistic traffic light sidebar ───────────────────────────────
        ctk.CTkLabel(sidebar, text='SIGNAL', font=('Segoe UI', 10, 'bold'),
                     text_color=_MUTED).pack(pady=(12, 2))

        # We keep tk.Canvas for drawing circles/rectangles easily
        tl_canvas = tk.Canvas(sidebar, width=64, height=160,
                              bg='#101726', highlightthickness=0)
        tl_canvas.pack(pady=(0, 6))
        self.light_canvases[direction] = tl_canvas
        self._draw_realistic_light(direction)

        # Timer block
        ctk.CTkLabel(sidebar, text='TIMER', font=('Segoe UI', 10, 'bold'),
                     text_color=_MUTED).pack(pady=(5, 0))
        timer_lbl = ctk.CTkLabel(sidebar, text='--s',
                                 font=('Consolas', 22, 'bold'),
                                 text_color=_TEXT)
        timer_lbl.pack()
        self.timer_labels[direction] = timer_lbl

        # Vehicle count block
        ctk.CTkLabel(sidebar, text='VEHICLES', font=('Segoe UI', 10, 'bold'),
                     text_color=_MUTED).pack(pady=(12, 0))
        v_lbl = ctk.CTkLabel(sidebar, text='0',
                             font=('Segoe UI', 24, 'bold'),
                             text_color=_TEXT)
        v_lbl.pack()
        self.stat_labels[f'{direction}_vehicles'] = v_lbl

        # State text
        s_lbl = ctk.CTkLabel(sidebar, text='RED',
                             font=('Segoe UI', 12, 'bold'),
                             text_color=_DANGER)
        s_lbl.pack(pady=(2, 8))
        self.stat_labels[f'{direction}_state'] = s_lbl

    # ─────────────────────────────────────────
    #  Realistic vertical traffic light
    # ─────────────────────────────────────────
    def _draw_realistic_light(self, direction):
        """Draw a realistic vertical traffic light with housing and visor hoods."""
        c = self.light_canvases[direction]
        self.lamp_ids[direction] = {}

        # Housing (rounded rectangle effect with two rectangles)
        c.create_rectangle(8, 4, 56, 156, fill='#1A1A1A', outline='#333333', width=2)
        c.create_rectangle(10, 6, 54, 154, fill='#111111', outline='#111111')  # inner shadow
        c.create_oval(29, 2, 35, 8, fill='#2A2A2A', outline='#444444')

        # Each lamp: (color_name, center_x, center_y, dim_fill)
        lamps = [
            ('red',    32, 34,  '#2D0000'),
            ('yellow', 32, 82,  '#1C1A00'),
            ('green',  32, 130, '#052E16'),
        ]

        for color, cx, cy, dim_fill in lamps:
            r = 18
            c.create_oval(cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3,
                          fill='#0D0D0D', outline='#0D0D0D')
            oid = c.create_oval(cx - r, cy - r, cx + r, cy + r,
                                fill=dim_fill, outline='#2A2A2A', width=1)
            c.create_rectangle(cx - r, cy - r - 5, cx + r, cy - r + 4,
                                fill='#1A1A1A', outline='#1A1A1A')
            c.create_oval(cx - r + 5, cy - r + 5, cx - r + 11, cy - r + 11,
                          fill='#2A2A2A', outline='#2A2A2A')
            self.lamp_ids[direction][color] = oid

        c.create_oval(29, 150, 35, 156, fill='#2A2A2A', outline='#444444')

    # ─────────────────────────────────────────
    #  Live update callbacks (same signatures)
    # ─────────────────────────────────────────
    def update_camera_feed(self, frame, detection_data=None, direction='north'):
        """Update camera feed display for specific direction."""
        try:
            if direction not in self.camera_labels:
                return

            if frame is not None:
                label = self.camera_labels[direction]
                cam_frame = label.master

                w = cam_frame.winfo_width()
                h = cam_frame.winfo_height()
                if w < 50 or h < 50:
                    w, h = 480, 320

                frame_resized = cv2.resize(frame, (w, h))
                frame_rgb     = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                img   = Image.fromarray(frame_rgb)
                photo = ImageTk.PhotoImage(img)

                label.config(image=photo, text='')
                label.image = photo

            if detection_data:
                self.update_live_stats(detection_data, direction)

        except Exception:
            pass

    def update_live_stats(self, data, direction):
        """Update stats and traffic light indicators for a direction."""
        vehicle_key = f'{direction}_vehicles'
        if vehicle_key not in self.stat_labels:
            return

        vehicle_count = data.get('vehicle_count', 0)
        signal_state  = data.get('signal_state', 'RED').upper()
        time_left     = data.get('time_remaining', 0)

        # ── Text stats ────────────────────────────────────────────
        self.stat_labels[f'{direction}_vehicles'].configure(text=str(vehicle_count))

        state_lbl = self.stat_labels[f'{direction}_state']
        sig_colors = {
            'GREEN':   _SUCCESS,
            'YELLOW':  _WARN,
            'RED':     _DANGER,
            'ALL_RED': _DANGER,
        }
        state_lbl.configure(text=signal_state, text_color=sig_colors.get(signal_state, _MUTED))

        # ── Timer ─────────────────────────────────────────────────
        t = int(time_left)
        timer_fg = _SUCCESS if signal_state == 'GREEN' else (_WARN if signal_state == 'YELLOW' else _DANGER)
        self.timer_labels[direction].configure(text=f'{t:>3}s', text_color=timer_fg)

        # ── Signal badge (top-right of card) ─────────────────────
        badge = self.signal_badges.get(direction)
        if badge:
            badge_styles = {
                'GREEN':   ('#052E16', '#22C55E'),
                'YELLOW':  ('#1C1A00', '#EAB308'),
                'RED':     ('#2D0000', '#EF4444'),
                'ALL_RED': ('#2D0000', '#EF4444'),
            }
            bg_c, fg_c = badge_styles.get(signal_state, ('#1A2332', _MUTED))
            badge.configure(text=f'● {signal_state}', fg_color=bg_c, text_color=fg_c)

        # ── Traffic light lamps ───────────────────────────────────
        c   = self.light_canvases[direction]
        ids = self.lamp_ids[direction]
        dim = {'red': '#2D0000', 'yellow': '#1C1A00', 'green': '#052E16'}

        for color_name, item_id in ids.items():
            c.itemconfig(item_id, fill=dim[color_name])

        active = signal_state.lower()
        if active == 'all_red':
            active = 'red'
        if active in ids:
            bright = {
                'red':    '#FF2020',
                'yellow': '#FFD600',
                'green':  '#00E676',
            }
            c.itemconfig(ids[active], fill=bright[active])

    def get_widget(self):
        return self.frame

    def cleanup(self):
        self.is_running = False
