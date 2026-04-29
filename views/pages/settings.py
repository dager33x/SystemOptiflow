# views/pages/settings.py
import tkinter as tk
import customtkinter as ctk
from ..styles import Colors, Fonts
from utils.app_config import SETTINGS

# Common phone camera stream presets shown in the dropdown
_PHONE_PRESETS = [
    "Simulated",
    "Camera 0",
    "Camera 1",
    "Camera 2",
    "Camera 3",
    "http://192.168.1.2:8080/video",    # IP Webcam (Android) - Phone 1
    "http://192.168.1.3:8080/video",    # IP Webcam (Android) - Phone 2
    "http://192.168.1.4:8080/video",    # IP Webcam (Android) - Phone 3
    "http://192.168.1.5:8080/video",    # IP Webcam (Android) - Phone 4
    "rtsp://192.168.1.2:8554/unicast",  # DroidCam RTSP - Phone 1
    "rtsp://192.168.1.3:8554/unicast",  # DroidCam RTSP - Phone 2
    "rtsp://192.168.1.4:8554/unicast",  # DroidCam RTSP - Phone 3
    "rtsp://192.168.1.5:8554/unicast",  # DroidCam RTSP - Phone 4
]


class SettingsPage:
    """Settings page for system preferences using CustomTkinter"""

    def __init__(self, parent):
        self.parent = parent
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.toggles = {}
        self.create_widgets()

    def create_widgets(self):
        """Create settings page layout"""

        # ── Header ──────────────────────────────────────────────────────────
        header_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        header_frame.pack(fill=tk.X, padx=40, pady=(30, 20))

        title_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_container.pack(side=tk.LEFT)

        ctk.CTkLabel(title_container, text="System Preferences",
                     font=('Segoe UI', 24, 'bold'),
                     text_color=Colors.TEXT).pack(anchor=tk.W)

        ctk.CTkLabel(title_container,
                     text="Manage your visual, system, and notification settings.",
                     font=('Segoe UI', 14),
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(5, 0))

        # ── Grid container ───────────────────────────────────────────────────
        content_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=35)
        content_frame.columnconfigure(0, weight=1, uniform="group1")
        content_frame.columnconfigure(1, weight=1, uniform="group1")

        # Settings group definitions
        visual_options = [
            ("Show Bounding Boxes",     "show_bounding_boxes"),
            ("Show Confidence Scores",  "show_confidence"),
            ("Show Simulation Overlay", "show_simulation_text"),
        ]
        system_options = [
            ("Enable AI Detection",              "enable_detection"),
            ("Violations & Accident Simulator",  "enable_sim_events"),
            ("Camera Filter (Invert)",           "dark_mode_cam"),
            ("Enhance Video (CPU Heavy)",        "enable_video_enhancement"),
        ]
        notification_options = [
            ("Enable Notifications", "enable_notifications"),
        ]
        phone_camera_options = [
            ("📱 North Lane", "camera_source_north"),
            ("📱 South Lane", "camera_source_south"),
            ("📱 East Lane",  "camera_source_east"),
            ("📱 West Lane",  "camera_source_west"),
        ]

        # ── Footer hint ──────────────────────────────────────────────────────
        footer_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=40, pady=25)
        ctk.CTkLabel(footer_frame,
                     text="* Changes are applied automatically and immediately.",
                     font=("Segoe UI", 12),
                     text_color=Colors.TEXT_MUTED).pack(side=tk.RIGHT)

        # ── Build cards ──────────────────────────────────────────────────────
        self.create_settings_card(content_frame, "Visual & Display",       "👁️", visual_options,       row=0, col=0)
        self.create_settings_card(content_frame, "System & Performance",   "⚡", system_options,       row=0, col=1)
        self.create_settings_card(content_frame, "Notifications",          "🔔", notification_options, row=1, col=0)
        self.create_phone_camera_card(content_frame, phone_camera_options,                             row=1, col=1)

    # ── Toggle card ──────────────────────────────────────────────────────────

    def create_settings_card(self, parent, title, icon, options, row, col):
        """Create a beautifully rounded card-style section for toggle settings"""
        card = ctk.CTkFrame(parent, fg_color='#161F33', corner_radius=15)
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ctk.CTkLabel(inner, text=f"{icon}  {title}",
                     font=('Segoe UI', 16, 'bold'),
                     text_color=Colors.TEXT).pack(anchor=tk.W)
        ctk.CTkFrame(inner, fg_color='#2c3a52', height=1).pack(fill=tk.X, pady=(8, 15))

        for label_text, config_key in options:
            self.create_modern_toggle(inner, label_text, config_key)

    def create_modern_toggle(self, parent, label_text, config_key):
        """Create a modern row with label on left and an iOS-style switch on right"""
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill=tk.X, pady=8)

        ctk.CTkLabel(container, text=label_text, font=('Segoe UI', 14),
                     text_color=Colors.TEXT_LIGHT).pack(side=tk.LEFT)

        current_val = SETTINGS.get(config_key, False)

        def on_toggle():
            SETTINGS[config_key] = bool(switch.get())

        switch = ctk.CTkSwitch(container, text="",
                               command=on_toggle,
                               progress_color=Colors.PRIMARY,
                               button_color="#FFFFFF",
                               button_hover_color="#E0E0E0")
        if current_val:
            switch.select()
        else:
            switch.deselect()

        self.toggles[config_key] = switch
        switch.pack(side=tk.RIGHT)

    # ── Phone Camera card ─────────────────────────────────────────────────────

    def create_phone_camera_card(self, parent, options, row, col):
        """
        Card for configuring phone/IP camera stream sources per lane.

        Each lane shows a free-text CTkComboBox that accepts:
          • "Simulated"            — built-in traffic simulator (no hardware)
          • "Camera 0" / "Camera 1" — local USB webcam by index
          • "http://<ip>:8080/video" — IP Webcam MJPEG stream (Android app)
          • "rtsp://<ip>:8554/..." — DroidCam / Larix RTSP stream
          • Any URL supported by cv2.VideoCapture
        """
        card = ctk.CTkFrame(parent, fg_color='#161F33', corner_radius=15)
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Header
        ctk.CTkLabel(inner, text="📱  Phone Camera Sources",
                     font=('Segoe UI', 16, 'bold'),
                     text_color=Colors.TEXT).pack(anchor=tk.W)
        ctk.CTkFrame(inner, fg_color='#2c3a52', height=1).pack(fill=tk.X, pady=(8, 10))

        # Usage hint
        hint = (
            "Type or paste a phone stream URL, or choose a preset:\n"
            "  http://192.168.x.x:8080/video  \u2192 IP Webcam app (Android)\n"
            "  rtsp://192.168.x.x:8554/unicast \u2192 DroidCam / Larix"
        )
        ctk.CTkLabel(inner, text=hint,
                     font=('Segoe UI', 10), text_color='#5B7FA6',
                     justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 12))

        # Per-lane rows
        for label_text, config_key in options:
            self._create_phone_source_row(inner, label_text, config_key)

    def _create_phone_source_row(self, parent, label_text, config_key):
        """
        One row: lane label on the left, editable combobox on the right.
        The combobox has preset values but also accepts free-text input so
        the user can type any valid URL directly.
        """
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill=tk.X, pady=5)

        ctk.CTkLabel(row_frame, text=label_text,
                     font=('Segoe UI', 13), text_color=Colors.TEXT_LIGHT,
                     width=110, anchor="w").pack(side=tk.LEFT)

        current_val = SETTINGS.get(config_key, "Simulated")

        def on_select(new_val):
            SETTINGS[config_key] = new_val.strip()
            print(f"[Settings] {config_key} \u2192 {new_val.strip()}")

        combo = ctk.CTkComboBox(
            row_frame,
            values=_PHONE_PRESETS,
            command=on_select,
            width=270,
            fg_color="#1E293B",
            border_color="#334155",
            button_color="#334155",
            button_hover_color="#475569",
            dropdown_fg_color="#1E293B",
            dropdown_hover_color="#334155",
            font=('Segoe UI', 12),
        )
        combo.set(current_val)
        combo.pack(side=tk.RIGHT)

        # Capture typed input when user presses Enter or moves focus away
        def on_focus_out(event=None):
            val = combo.get().strip()
            if val:
                SETTINGS[config_key] = val
                print(f"[Settings] {config_key} \u2192 {val}")

        combo.bind("<FocusOut>", on_focus_out)
        combo.bind("<Return>",   on_focus_out)

        self.toggles[config_key] = combo

    # ── Legacy helpers (kept for backwards-compatibility) ─────────────────────

    def create_combobox_card(self, parent, title, icon, options, row, col):
        """Legacy combobox card — delegates to phone camera card."""
        self.create_phone_camera_card(parent, options, row, col)

    def create_modern_combobox(self, parent, label_text, config_key):
        """Legacy single combobox row."""
        self._create_phone_source_row(parent, label_text, config_key)

    def get_widget(self):
        return self.frame
