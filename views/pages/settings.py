import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from ..styles import Colors
from utils.app_config import SETTINGS
from utils.public_url import get_public_base_url


class _LocalSettingsProvider:
    def get(self, key, default=None):
        return SETTINGS.get(key, default)

    def set(self, key, value):
        SETTINGS[key] = value
        return value


_PHONE_PRESETS = [
    "Simulated",
    "Camera 0",
    "Camera 1",
    "Camera 2",
    "Camera 3",
    "http://192.168.1.2:8080/video",
    "http://192.168.1.3:8080/video",
    "http://192.168.1.4:8080/video",
    "http://192.168.1.5:8080/video",
    "rtsp://192.168.1.2:8554/unicast",
    "rtsp://192.168.1.3:8554/unicast",
    "rtsp://192.168.1.4:8554/unicast",
    "rtsp://192.168.1.5:8554/unicast",
]


class SettingsPage:
    """Settings page for runtime preferences plus local desktop connection options."""

    def __init__(self, parent, settings_provider=None, connection_profile=None):
        self.parent = parent
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.toggles = {}
        self.settings_provider = settings_provider or _LocalSettingsProvider()
        self.connection_profile = connection_profile
        self.connection_entry = None
        self.connection_status = None
        self.prefill_switch = None
        self.create_widgets()

    def create_widgets(self):
        header_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        header_frame.pack(fill=tk.X, padx=40, pady=(30, 20))

        title_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_container.pack(side=tk.LEFT)

        ctk.CTkLabel(
            title_container,
            text="System Preferences",
            font=("Segoe UI", 24, "bold"),
            text_color=Colors.TEXT,
        ).pack(anchor=tk.W)

        ctk.CTkLabel(
            title_container,
            text="Manage runtime behavior and this desktop client's connection profile.",
            font=("Segoe UI", 14),
            text_color=Colors.TEXT_MUTED,
        ).pack(anchor=tk.W, pady=(5, 0))

        content_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=35)
        content_frame.columnconfigure(0, weight=1, uniform="group1")
        content_frame.columnconfigure(1, weight=1, uniform="group1")

        visual_options = [
            ("Show Bounding Boxes", "show_bounding_boxes"),
            ("Show Confidence Scores", "show_confidence"),
            ("Show Simulation Overlay", "show_simulation_text"),
        ]
        system_options = [
            ("Enable AI Detection", "enable_detection"),
            ("Violations & Accident Simulator", "enable_sim_events"),
            ("Camera Filter (Invert)", "dark_mode_cam"),
            ("Enhance Video (CPU Heavy)", "enable_video_enhancement"),
        ]
        notification_options = [
            ("Enable Notifications", "enable_notifications"),
        ]
        phone_camera_options = [
            ("North Lane", "camera_source_north"),
            ("South Lane", "camera_source_south"),
            ("East Lane", "camera_source_east"),
            ("West Lane", "camera_source_west"),
        ]

        self.create_settings_card(content_frame, "Visual & Display", "Display", visual_options, row=0, col=0)
        self.create_settings_card(content_frame, "System & Performance", "Runtime", system_options, row=0, col=1)
        self.create_settings_card(content_frame, "Notifications", "Alerts", notification_options, row=1, col=0)
        self.create_phone_camera_card(content_frame, phone_camera_options, row=1, col=1)

        if self.connection_profile is not None:
            self.create_connection_card(content_frame, row=2, col=0, columnspan=2)

        footer_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=40, pady=25)
        ctk.CTkLabel(
            footer_frame,
            text="Runtime settings apply immediately. Connection settings are local to this desktop app only.",
            font=("Segoe UI", 12),
            text_color=Colors.TEXT_MUTED,
        ).pack(side=tk.RIGHT)

    def create_settings_card(self, parent, title, subtitle, options, row, col):
        card = ctk.CTkFrame(parent, fg_color="#161F33", corner_radius=15)
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            inner,
            text=title,
            font=("Segoe UI", 16, "bold"),
            text_color=Colors.TEXT,
        ).pack(anchor=tk.W)
        ctk.CTkLabel(
            inner,
            text=subtitle,
            font=("Segoe UI", 11),
            text_color=Colors.TEXT_MUTED,
        ).pack(anchor=tk.W, pady=(2, 0))
        ctk.CTkFrame(inner, fg_color="#2c3a52", height=1).pack(fill=tk.X, pady=(8, 15))

        for label_text, config_key in options:
            self.create_modern_toggle(inner, label_text, config_key)

    def create_modern_toggle(self, parent, label_text, config_key):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill=tk.X, pady=8)

        ctk.CTkLabel(
            container,
            text=label_text,
            font=("Segoe UI", 14),
            text_color=Colors.TEXT_LIGHT,
        ).pack(side=tk.LEFT)

        current_val = self.settings_provider.get(config_key, False)

        def on_toggle():
            try:
                self.settings_provider.set(config_key, bool(switch.get()))
            except Exception as exc:
                messagebox.showerror("Settings Error", str(exc), parent=self.frame)
                if self.settings_provider.get(config_key, False):
                    switch.select()
                else:
                    switch.deselect()

        switch = ctk.CTkSwitch(
            container,
            text="",
            command=on_toggle,
            progress_color=Colors.PRIMARY,
            button_color="#FFFFFF",
            button_hover_color="#E0E0E0",
        )
        if current_val:
            switch.select()
        else:
            switch.deselect()

        self.toggles[config_key] = switch
        switch.pack(side=tk.RIGHT)

    def create_phone_camera_card(self, parent, options, row, col):
        card = ctk.CTkFrame(parent, fg_color="#161F33", corner_radius=15)
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            inner,
            text="Phone Camera Sources",
            font=("Segoe UI", 16, "bold"),
            text_color=Colors.TEXT,
        ).pack(anchor=tk.W)
        ctk.CTkLabel(
            inner,
            text="Per-lane ingest sources for the local runtime or the live backend settings API.",
            font=("Segoe UI", 11),
            text_color=Colors.TEXT_MUTED,
        ).pack(anchor=tk.W, pady=(2, 0))
        ctk.CTkFrame(inner, fg_color="#2c3a52", height=1).pack(fill=tk.X, pady=(8, 10))

        hint = (
            "Type or paste a stream URL, or choose a preset.\n"
            "Examples: http://192.168.x.x:8080/video or rtsp://192.168.x.x:8554/unicast"
        )
        ctk.CTkLabel(
            inner,
            text=hint,
            font=("Segoe UI", 10),
            text_color="#5B7FA6",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 12))

        for label_text, config_key in options:
            self._create_phone_source_row(inner, label_text, config_key)

    def _create_phone_source_row(self, parent, label_text, config_key):
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.pack(fill=tk.X, pady=5)

        ctk.CTkLabel(
            row_frame,
            text=label_text,
            font=("Segoe UI", 13),
            text_color=Colors.TEXT_LIGHT,
            width=110,
            anchor="w",
        ).pack(side=tk.LEFT)

        current_val = self.settings_provider.get(config_key, "Simulated")

        def save_value(new_val):
            try:
                value = (new_val or "").strip() or "Simulated"
                self.settings_provider.set(config_key, value)
            except Exception as exc:
                messagebox.showerror("Settings Error", str(exc), parent=self.frame)
                combo.set(self.settings_provider.get(config_key, "Simulated"))

        combo = ctk.CTkComboBox(
            row_frame,
            values=_PHONE_PRESETS,
            command=save_value,
            width=270,
            fg_color="#1E293B",
            border_color="#334155",
            button_color="#334155",
            button_hover_color="#475569",
            dropdown_fg_color="#1E293B",
            dropdown_hover_color="#334155",
            font=("Segoe UI", 12),
        )
        combo.set(current_val)
        combo.pack(side=tk.RIGHT)

        def on_focus_out(_event=None):
            save_value(combo.get())

        combo.bind("<FocusOut>", on_focus_out)
        combo.bind("<Return>", on_focus_out)

        self.toggles[config_key] = combo

    def create_connection_card(self, parent, row, col, columnspan=1):
        card = ctk.CTkFrame(parent, fg_color="#161F33", corner_radius=15)
        card.grid(row=row, column=col, columnspan=columnspan, padx=10, pady=10, sticky="nsew")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            inner,
            text="SystemOptiflow Server URL",
            font=("Segoe UI", 16, "bold"),
            text_color=Colors.TEXT,
        ).pack(anchor=tk.W)
        ctk.CTkLabel(
            inner,
            text="This controls the live web server used by the desktop app. Camera source URLs remain separate runtime settings.",
            font=("Segoe UI", 11),
            text_color=Colors.TEXT_MUTED,
        ).pack(anchor=tk.W, pady=(2, 0))
        ctk.CTkFrame(inner, fg_color="#2c3a52", height=1).pack(fill=tk.X, pady=(8, 14))

        form_row = ctk.CTkFrame(inner, fg_color="transparent")
        form_row.pack(fill=tk.X, pady=(0, 10))
        form_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            form_row,
            text="Server URL",
            font=("Segoe UI", 13),
            text_color=Colors.TEXT_LIGHT,
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        self.connection_entry = ctk.CTkEntry(
            form_row,
            placeholder_text="https://optiflow.example.com",
            height=40,
            fg_color="#0f1522",
            border_color="#2c3a52",
            font=("Segoe UI", 12),
        )
        self.connection_entry.grid(row=0, column=1, sticky="ew")
        saved_url = self.connection_profile.last_server_url()
        default_url = saved_url or get_public_base_url()
        if default_url:
            self.connection_entry.insert(0, default_url)

        action_row = ctk.CTkFrame(inner, fg_color="transparent")
        action_row.pack(fill=tk.X, pady=(0, 12))

        save_button = ctk.CTkButton(
            action_row,
            text="Save Server",
            command=self._save_connection_profile,
            height=38,
            width=140,
            fg_color=Colors.PRIMARY,
            hover_color="#2563EB",
            font=("Segoe UI", 12, "bold"),
        )
        save_button.pack(side=tk.LEFT)

        clear_button = ctk.CTkButton(
            action_row,
            text="Clear Saved Server",
            command=self._clear_connection_profile,
            height=38,
            width=160,
            fg_color="#1E293B",
            hover_color="#334155",
            font=("Segoe UI", 12),
        )
        clear_button.pack(side=tk.LEFT, padx=(12, 0))

        self.connection_status = ctk.CTkLabel(
            inner,
            text="Saved URLs appear on the desktop login screen automatically. Clear the field to start in local demo mode.",
            font=("Segoe UI", 11),
            text_color=Colors.TEXT_MUTED,
            justify=tk.LEFT,
        )
        self.connection_status.pack(anchor=tk.W, pady=(12, 0))
        if not saved_url and default_url:
            self._set_connection_status(
                "Using PUBLIC_BASE_URL as the default live server until you save a desktop-specific URL.",
                Colors.PRIMARY,
            )

    def _normalize_server_url(self, value):
        normalized = (value or "").strip()
        if normalized and not normalized.startswith(("http://", "https://")):
            normalized = f"https://{normalized}"
        return normalized.rstrip("/")

    def _set_connection_status(self, text, color=None):
        if self.connection_status is not None:
            self.connection_status.configure(text=text, text_color=color or Colors.TEXT_MUTED)

    def _toggle_connection_prefill(self):
        if self.prefill_switch is None:
            return
        enabled = bool(self.prefill_switch.get())
        self.connection_profile.set_prefer_remote(enabled)
        if enabled and not self.connection_profile.last_server_url():
            self._set_connection_status("Save a live server URL first before enabling startup prefill.", "#F59E0B")
        elif enabled:
            self._set_connection_status("Live server prefill enabled for the next desktop launch.", Colors.PRIMARY)
        else:
            self._set_connection_status("Startup will default to local mode. The saved live URL is kept.", Colors.TEXT_MUTED)

    def _save_connection_profile(self):
        if self.connection_entry is None:
            return
        normalized = self._normalize_server_url(self.connection_entry.get())
        if not normalized:
            self._set_connection_status("Enter a server URL or use Clear Saved Server to remove it.", "#F59E0B")
            return
        self.connection_profile.set_last_server_url(normalized)
        self.connection_entry.delete(0, tk.END)
        self.connection_entry.insert(0, normalized)
        self._set_connection_status("Saved. Future desktop logins will prefill this SystemOptiflow server URL.", Colors.PRIMARY)

    def _clear_connection_profile(self):
        self.connection_profile.clear_last_server_url()
        if self.connection_entry is not None:
            self.connection_entry.delete(0, tk.END)
        fallback_url = get_public_base_url()
        if self.connection_entry is not None and fallback_url:
            self.connection_entry.insert(0, fallback_url)
            self._set_connection_status("Desktop-specific URL cleared. PUBLIC_BASE_URL is now the default live server hint.", Colors.TEXT_MUTED)
            return
        self._set_connection_status("Saved server URL cleared. Future launches will start in local demo mode.", Colors.TEXT_MUTED)

    def create_combobox_card(self, parent, title, icon, options, row, col):
        self.create_phone_camera_card(parent, options, row, col)

    def create_modern_combobox(self, parent, label_text, config_key):
        self._create_phone_source_row(parent, label_text, config_key)

    def get_widget(self):
        return self.frame
