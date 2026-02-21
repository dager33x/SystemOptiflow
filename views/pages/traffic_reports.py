# views/pages/traffic_reports.py
import tkinter as tk
from tkinter import ttk
import logging
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from ..styles import Colors, Fonts, WidgetStyles

class TrafficReportsPage:
    """Traffic reports page with dynamic statistics and bar graphs"""
    
    def __init__(self, parent):
        self.parent = parent
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.cards = {} # Store references to update labels
        self.create_widgets()
        
    def create_widgets(self):
        """Create traffic reports page layout"""
        # Header
        header_frame = tk.Frame(self.frame, bg=Colors.BACKGROUND)
        header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        tk.Label(header_frame, text="Traffic Analysis Report",
                font=Fonts.TITLE, bg=Colors.BACKGROUND,
                fg=Colors.PRIMARY).pack(anchor=tk.W)
                
        tk.Label(header_frame, text="Real-time breakdown of traffic density and system metrics.",
                font=Fonts.BODY, bg=Colors.BACKGROUND,
                fg=Colors.TEXT_MUTED).pack(anchor=tk.W)
        
        # 1. Stats Cards Container (Top)
        stats_frame = tk.Frame(self.frame, bg=Colors.BACKGROUND)
        stats_frame.pack(fill=tk.X, padx=15, pady=10)
        
        # Create Dynamic Cards
        self.create_dynamic_card(stats_frame, "total_cam", "Active Cameras", "0/4", Colors.INFO)
        self.create_dynamic_card(stats_frame, "total_vehicles", "Total Traffic Load", "0", Colors.SUCCESS)
        self.create_dynamic_card(stats_frame, "peak_lane", "Busiest Lane", "N/A", Colors.WARNING)
        self.create_dynamic_card(stats_frame, "violations", "Violations Today", "0", Colors.DANGER)
        
        # 2. Graph Section (Main)
        graph_container = tk.Frame(self.frame, bg=Colors.CARD_BG, padx=10, pady=10)
        graph_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Matplotlib Figure - Bar Chart
        self.fig = Figure(figsize=(6, 4), dpi=100, facecolor=Colors.CARD_BG)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(Colors.CARD_BG)
        
        # Initial Plot
        self.lanes = ['North', 'South', 'East', 'West']
        self.counts = [0, 0, 0, 0]
        self.bar_colors = [Colors.PRIMARY, Colors.INFO, Colors.SUCCESS, Colors.WARNING]
        
        self.bars = self.ax.bar(self.lanes, self.counts, color=self.bar_colors)
        
        # Styling
        self.ax.set_title("Current Traffic Volume by Lane", color=Colors.TEXT, pad=15, fontsize=12)
        self.ax.set_ylabel("Vehicles Detected", color=Colors.TEXT_LIGHT)
        self.ax.tick_params(axis='x', colors=Colors.TEXT)
        self.ax.tick_params(axis='y', colors=Colors.TEXT_LIGHT)
        self.ax.spines['bottom'].set_color(Colors.BORDER)
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['left'].set_color(Colors.BORDER)
        
        # Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_container)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def create_dynamic_card(self, parent, key, title, value, color):
        """Create a card that can be updated"""
        card = tk.Frame(parent, bg=Colors.CARD_BG, padx=20, pady=15)
        card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        tk.Label(card, text=title, font=Fonts.BODY, bg=Colors.CARD_BG, 
                fg=Colors.TEXT_LIGHT).pack(anchor=tk.W)
        
        val_lbl = tk.Label(card, text=value, font=Fonts.TITLE, bg=Colors.CARD_BG, 
                          fg=color)
        val_lbl.pack(anchor=tk.W, pady=(5, 0))
        
        self.cards[key] = val_lbl

    def update_report(self, data):
        """
        Update the report with real-time data
        data: {
            'lane_data': {'north': 5, 'south': 2, ...},
            'active_cameras': 4,
            'violations': 10
        }
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
        self.ax.set_ylim(0, max(max_height + 5, 10))
        self.canvas.draw_idle()
        
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
             self.cards['total_cam'].config(text=f"{active_cams}/4")
        
        if 'total_vehicles' in self.cards:
            self.cards['total_vehicles'].config(text=str(total_load))
            
        if 'peak_lane' in self.cards:
            self.cards['peak_lane'].config(text=busiest_lane)
            
        if 'violations' in self.cards:
            self.cards['violations'].config(text=str(violations))

    def get_widget(self):
        return self.frame
