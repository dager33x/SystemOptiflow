# views/pages/dashboard.py
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import cv2
from ..styles import Colors, Fonts

# ─────────────────────────────────────────────
#  Color constants specific to the dashboard
# ─────────────────────────────────────────────
_BG        = Colors.BACKGROUND       # #0B0F19
_CARD      = Colors.CARD_BG          # #151B2B
_BORDER    = '#1E2D45'
_HEADER_BG = '#0D1520'
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
    """Enhanced command-center style dashboard with 2×2 camera grid."""

    def __init__(self, parent):
        self.parent = parent
        self.frame = tk.Frame(parent, bg=_BG)
        self.camera_labels  = {}
        self.stat_labels    = {}
        self.light_canvases = {}
        self.timer_labels   = {}
        self.lamp_ids       = {}   # {direction: {color: canvas_id}}
        self.signal_badges  = {}   # {direction: tk.Label}
        self.is_running = True
        self._create_widgets()

    # ─────────────────────────────────────────
    #  Layout construction
    # ─────────────────────────────────────────
    def _create_widgets(self):
        # ── Camera grid (fills full area — top bar handles the title) ─────
        grid_frame = tk.Frame(self.frame, bg=_BG)
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)
        grid_frame.grid_rowconfigure(0, weight=1)
        grid_frame.grid_rowconfigure(1, weight=1)

        directions = ['north', 'south', 'east', 'west']
        coords     = [(0, 0), (0, 1), (1, 0), (1, 1)]

        for direction, (row, col) in zip(directions, coords):
            self._build_camera_card(grid_frame, direction, row, col)

    def _build_camera_card(self, parent, direction, row, col):
        """Build a single camera card: header strip + video + right sidebar with traffic light."""
        meta = _DIR_META[direction]

        # Outer card with border effect
        border_frame = tk.Frame(parent, bg=_BORDER, padx=1, pady=1)
        border_frame.grid(row=row, column=col, sticky='nsew', padx=4, pady=4)

        card = tk.Frame(border_frame, bg=_CARD)
        card.pack(fill=tk.BOTH, expand=True)

        # ── Card header strip ─────────────────────────────────────
        card_header = tk.Frame(card, bg='#0D1825', height=36)
        card_header.pack(fill=tk.X)
        card_header.pack_propagate(False)

        tk.Label(card_header, text=f" {meta['icon']}  {meta['label']}",
                 font=('Segoe UI', 10, 'bold'),
                 bg='#0D1825', fg=_ACCENT).pack(side=tk.LEFT, padx=10, pady=6)

        # Signal state badge
        badge = tk.Label(card_header, text='● RED', font=('Segoe UI', 9, 'bold'),
                         bg='#2D0000', fg='#EF4444', padx=8, pady=2)
        badge.pack(side=tk.RIGHT, padx=8, pady=6)
        self.signal_badges[direction] = badge

        # Body row: camera (left) + traffic light panel (right)
        body = tk.Frame(card, bg=_CARD)
        body.pack(fill=tk.BOTH, expand=True)

        # ── RIGHT sidebar packed FIRST ── (Tkinter rule: fixed-size widgets must be
        # packed before the expanding widget, otherwise expand grabs all available space)
        sidebar = tk.Frame(body, bg='#0A1220', width=88)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # ── Camera feed packed AFTER sidebar so it only fills remaining space ──
        cam_outer = tk.Frame(body, bg='#050A10')
        cam_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        cam_label = tk.Label(cam_outer, bg='#050A10',
                             text='◌  No Signal', fg='#1E3A5F',
                             font=('Segoe UI', 13, 'bold'))
        cam_label.pack(fill=tk.BOTH, expand=True)
        self.camera_labels[direction] = cam_label

        # ── Realistic traffic light ───────────────────────────────
        # Pole top label
        tk.Label(sidebar, text='SIGNAL', font=('Segoe UI', 7, 'bold'),
                 bg='#0A1220', fg=_MUTED).pack(pady=(10, 2))

        # Canvas housing
        tl_canvas = tk.Canvas(sidebar, width=64, height=160,
                              bg='#0A1220', highlightthickness=0)
        tl_canvas.pack(pady=(0, 4))
        self.light_canvases[direction] = tl_canvas
        self._draw_realistic_light(direction)

        # Thin divider
        tk.Frame(sidebar, bg=_BORDER, height=1).pack(fill=tk.X, padx=6)

        # Timer block
        tk.Label(sidebar, text='TIMER', font=('Segoe UI', 7, 'bold'),
                 bg='#0A1220', fg=_MUTED).pack(pady=(8, 0))
        timer_lbl = tk.Label(sidebar, text='--s',
                             font=('Consolas', 18, 'bold'),
                             bg='#0A1220', fg=_TEXT)
        timer_lbl.pack()
        self.timer_labels[direction] = timer_lbl

        # Thin divider
        tk.Frame(sidebar, bg=_BORDER, height=1).pack(fill=tk.X, padx=6, pady=(8, 0))

        # Vehicle count block
        tk.Label(sidebar, text='VEHICLES', font=('Segoe UI', 7, 'bold'),
                 bg='#0A1220', fg=_MUTED).pack(pady=(8, 0))
        v_lbl = tk.Label(sidebar, text='0',
                         font=('Segoe UI', 20, 'bold'),
                         bg='#0A1220', fg=_TEXT)
        v_lbl.pack()
        self.stat_labels[f'{direction}_vehicles'] = v_lbl

        # State text
        s_lbl = tk.Label(sidebar, text='RED',
                         font=('Segoe UI', 10, 'bold'),
                         bg='#0A1220', fg=_DANGER)
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

        # Mounting bolt top
        c.create_oval(29, 2, 35, 8, fill='#2A2A2A', outline='#444444')

        # Each lamp: (color_name, center_x, center_y, dim_fill)
        lamps = [
            ('red',    32, 34,  '#2D0000'),
            ('yellow', 32, 82,  '#1C1A00'),
            ('green',  32, 130, '#052E16'),
        ]

        for color, cx, cy, dim_fill in lamps:
            r = 18
            # Outer glow ring (subtle dark ring for depth)
            c.create_oval(cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3,
                          fill='#0D0D0D', outline='#0D0D0D')
            # Lamp body
            oid = c.create_oval(cx - r, cy - r, cx + r, cy + r,
                                fill=dim_fill, outline='#2A2A2A', width=1)
            # Visor hood above each lamp
            c.create_rectangle(cx - r, cy - r - 5, cx + r, cy - r + 4,
                                fill='#1A1A1A', outline='#1A1A1A')
            # Highlight glint (valid 6-char hex only — no alpha in Tkinter)
            c.create_oval(cx - r + 5, cy - r + 5, cx - r + 11, cy - r + 11,
                          fill='#2A2A2A', outline='#2A2A2A')
            self.lamp_ids[direction][color] = oid

        # Bottom bolt
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
        self.stat_labels[f'{direction}_vehicles'].config(text=str(vehicle_count))

        state_lbl = self.stat_labels[f'{direction}_state']
        sig_colors = {
            'GREEN':   _SUCCESS,
            'YELLOW':  _WARN,
            'RED':     _DANGER,
            'ALL_RED': _DANGER,
        }
        state_lbl.config(text=signal_state, fg=sig_colors.get(signal_state, _MUTED))

        # ── Timer ─────────────────────────────────────────────────
        t = int(time_left)
        timer_fg = _SUCCESS if signal_state == 'GREEN' else (_WARN if signal_state == 'YELLOW' else _DANGER)
        self.timer_labels[direction].config(text=f'{t:>3}s', fg=timer_fg)

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
            badge.config(text=f'● {signal_state}', bg=bg_c, fg=fg_c)

        # ── Traffic light lamps ───────────────────────────────────
        c   = self.light_canvases[direction]
        ids = self.lamp_ids[direction]
        dim = {'red': '#2D0000', 'yellow': '#1C1A00', 'green': '#052E16'}

        # Dim all first
        for color_name, item_id in ids.items():
            c.itemconfig(item_id, fill=dim[color_name])

        # Light active lamp
        active = signal_state.lower()
        if active == 'all_red':
            active = 'red'
        if active in ids:
            # Vivid glow colors that look like a real illuminated lamp
            bright = {
                'red':    '#FF2020',   # Vivid red
                'yellow': '#FFD600',   # Bright amber/yellow
                'green':  '#00E676',   # Bright green
            }
            c.itemconfig(ids[active], fill=bright[active])

    # ─────────────────────────────────────────
    #  Boilerplate
    # ─────────────────────────────────────────
    def get_widget(self):
        return self.frame

    def cleanup(self):
        self.is_running = False
