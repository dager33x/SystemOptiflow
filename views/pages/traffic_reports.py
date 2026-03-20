# views/pages/traffic_reports.py
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
import logging
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from ..styles import Colors, Fonts

class TrafficReportsPage:
    """Traffic reports page with dynamic statistics and glowing line graphs using CustomTkinter"""
    
    def __init__(self, parent):
        self.parent = parent
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.cards = {} # Store references to update labels
        
        # Initialize CTk explicitly for rendering mode (dark)
        ctk.set_appearance_mode("dark")
        self.create_widgets()
        
    def create_widgets(self):
        """Create traffic reports page layout"""
        # Header
        header_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        header_frame.pack(fill=tk.X, padx=40, pady=(30, 15))
        
        title_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_container.pack(side=tk.LEFT)
        
        ctk.CTkLabel(title_container, text="Traffic Analysis Report",
                     font=('Segoe UI', 24, 'bold'),
                     text_color=Colors.TEXT).pack(anchor=tk.W)
                
        ctk.CTkLabel(title_container, text="Real-time breakdown of traffic density and historical data.",
                     font=('Segoe UI', 14),
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(5, 0))
        
        # 1. Stats Cards Container (Top)
        stats_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        stats_frame.pack(fill=tk.X, padx=35, pady=(0, 15))
        
        stats_frame.columnconfigure((0,1,2,3), weight=1, uniform="statgroup")
        
        # Create Dynamic Cards
        self.create_dynamic_card(stats_frame, "total_cam", "Active Cameras", "0/4", Colors.INFO, 0)
        self.create_dynamic_card(stats_frame, "total_vehicles", "Total Traffic Load", "0", Colors.SUCCESS, 1)
        self.create_dynamic_card(stats_frame, "peak_lane", "Busiest Lane", "N/A", Colors.WARNING, 2)
        self.create_dynamic_card(stats_frame, "violations", "Violations Today", "0", Colors.DANGER, 3)
        
        # 2. Graph Section (Main)
        graphs_container = ctk.CTkFrame(self.frame, fg_color="transparent")
        graphs_container.pack(fill=tk.BOTH, expand=True, padx=35, pady=(0, 30))
        
        # Split into two columns: Left for Bar Chart (Realtime), Right for Line Chart (24H Historical)
        graphs_container.columnconfigure(0, weight=1, uniform="g_group")
        graphs_container.columnconfigure(1, weight=2, uniform="g_group") # Line chart wider
        
        bar_card = ctk.CTkFrame(graphs_container, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        bar_card.grid(row=0, column=0, sticky="nsew", padx=5)
        
        line_card = ctk.CTkFrame(graphs_container, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        line_card.grid(row=0, column=1, sticky="nsew", padx=5)

        # ── REALTIME BAR CHART ──
        # Matplotlib Figure - Bar Chart
        self.fig_bar = Figure(figsize=(4, 4), dpi=100, facecolor='#161F33')
        self.ax_bar = self.fig_bar.add_subplot(111)
        self.ax_bar.set_facecolor('#161F33')
        
        self.lanes = ['North', 'South', 'East', 'West']
        self.counts = [0, 0, 0, 0]
        self.bar_colors = [Colors.PRIMARY, Colors.INFO, Colors.SUCCESS, Colors.WARNING]
        
        self.bars = self.ax_bar.bar(self.lanes, self.counts, color=self.bar_colors, width=0.6, edgecolor='none', alpha=0.9)
        
        self.ax_bar.set_title("Current Volume (by Lane)", color=Colors.TEXT, pad=15, fontsize=12, fontweight='bold', fontfamily='Segoe UI')
        self.ax_bar.tick_params(axis='x', colors=Colors.TEXT_MUTED, labelsize=10)
        self.ax_bar.tick_params(axis='y', colors=Colors.TEXT_MUTED, labelsize=10)
        self.ax_bar.spines['bottom'].set_color('#2c3a52')
        self.ax_bar.spines['top'].set_visible(False)
        self.ax_bar.spines['right'].set_visible(False)
        self.ax_bar.spines['left'].set_color('#2c3a52')
        self.ax_bar.grid(axis='y', color='#2c3a52', linestyle='-', alpha=0.3)
        self.fig_bar.tight_layout(pad=2.0)
        
        self.canvas_bar = FigureCanvasTkAgg(self.fig_bar, master=bar_card)
        self.canvas_bar.draw()
        
        # Tkinter requires placing the native widget
        bar_widget = self.canvas_bar.get_tk_widget()
        bar_widget.config(bg="#161F33", highlightthickness=0)
        bar_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)


        # ── HISTORICAL 24H NEON LINE GRAPH ──
        self.fig_line = Figure(figsize=(6, 4), dpi=100, facecolor='#161F33')
        self.ax_line = self.fig_line.add_subplot(111)
        self.ax_line.set_facecolor('#161F33')
        
        # Simulated 24H data
        hours = np.arange(24)
        np.random.seed(42) # Consistent shape
        base_volume = 200 + 150 * np.sin(np.pi * hours / 12 - np.pi/2) # Wave pattern
        noise = np.random.normal(0, 30, 24)
        simulated_history = np.clip(base_volume + noise, 50, 500)
        
        # Neon line glow effect (Draw multiple lines with decreasing alpha/increasing width)
        import matplotlib.patheffects as pe
        
        self.ax_line.plot(hours, simulated_history, color=Colors.PRIMARY, linewidth=2, 
                          path_effects=[pe.SimpleLineShadow(shadow_color=Colors.PRIMARY, alpha=0.4, offset=(0,0)), pe.Normal()])
                          
        # Fill area under curve
        self.ax_line.fill_between(hours, simulated_history, 0, color=Colors.PRIMARY, alpha=0.1)

        self.ax_line.set_title("Traffic Volume (Last 24 Hours)", color=Colors.TEXT, pad=15, fontsize=12, fontweight='bold', fontfamily='Segoe UI')
        self.ax_line.set_xticks([0, 6, 12, 18, 23])
        self.ax_line.set_xticklabels(['12 AM', '6 AM', '12 PM', '6 PM', 'Now'])
        
        self.ax_line.tick_params(axis='x', colors=Colors.TEXT_MUTED, labelsize=10)
        self.ax_line.tick_params(axis='y', colors=Colors.TEXT_MUTED, labelsize=10)
        
        self.ax_line.spines['bottom'].set_color('#2c3a52')
        self.ax_line.spines['top'].set_visible(False)
        self.ax_line.spines['right'].set_visible(False)
        self.ax_line.spines['left'].set_color('#2c3a52')
        self.ax_line.grid(True, color='#2c3a52', linestyle='-', alpha=0.3)
        self.ax_line.set_ylim(bottom=0)
        
        self.fig_line.tight_layout(pad=2.0)
        
        self.canvas_line = FigureCanvasTkAgg(self.fig_line, master=line_card)
        self.canvas_line.draw()
        
        line_widget = self.canvas_line.get_tk_widget()
        line_widget.config(bg="#161F33", highlightthickness=0)
        line_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)


    def create_dynamic_card(self, parent, key, title, value, color, col):
        """Create a rounded card that can be updated"""
        card = ctk.CTkFrame(parent, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        card.grid(row=0, column=col, sticky="nsew", padx=5)
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(inner, text=title, font=('Segoe UI', 13, 'bold'), 
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W)
        
        val_lbl = ctk.CTkLabel(inner, text=value, font=('Segoe UI', 28, 'bold'), 
                               text_color=color)
        val_lbl.pack(anchor=tk.W, pady=(5, 0))
        
        self.cards[key] = val_lbl

    def update_report(self, data):
        """
        Update the report with real-time data
        """
        lane_data = data.get('lane_data', {})
        
        # 1. Update Graph
        counts = [
            lane_data.get('north', 0),
            lane_data.get('south', 0),
            lane_data.get('east', 0),
            lane_data.get('west', 0)
        ]
        
        # Update bar heights
        for bar, height in zip(self.bars, counts):
            bar.set_height(height)
            
        # Rescale Y axis if needed
        max_height = max(counts) if counts else 0
        self.ax_bar.set_ylim(0, max(max_height + 5, 10))
        self.canvas_bar.draw_idle()
        
        # 2. Update Statistics
        total_load = sum(counts)
        active_cams = data.get('active_cameras', 0)
        violations = data.get('violations', 0)
        
        # Determine Busiest Lane
        if total_load > 0:
            max_lane_idx = np.argmax(counts)
            busiest_lane = self.lanes[max_lane_idx]
        else:
            busiest_lane = "None"
        
        # Update Labels
        if 'total_cam' in self.cards:
             self.cards['total_cam'].configure(text=f"{active_cams}/4")
        
        if 'total_vehicles' in self.cards:
            self.cards['total_vehicles'].configure(text=str(total_load))
            
        if 'peak_lane' in self.cards:
            self.cards['peak_lane'].configure(text=busiest_lane)
            
        if 'violations' in self.cards:
            self.cards['violations'].configure(text=str(violations))

    def get_widget(self):
        return self.frame
