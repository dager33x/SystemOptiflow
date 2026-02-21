# views/pages/dashboard.py
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw
import threading
import numpy as np
import cv2
from ..styles import Colors, Fonts

class DashboardPage:
    """Dashboard page with 4-way camera feed and real-time statistics"""
    
    def __init__(self, parent):
        self.parent = parent
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.camera_labels = {}
        self.stat_labels = {}
        self.light_canvases = {}
        self.timer_labels = {}
        self.lamp_ids = {} # {direction: {color: id}}
        self.is_running = True
        self.create_widgets()
    
    def create_widgets(self):
        """Create dashboard layout with 2x2 grid for intersections"""
        # Title
        title = tk.Label(self.frame, text="Intersection Dashboard (North-South-East-West)",
                        font=Fonts.TITLE, bg=Colors.BACKGROUND,
                        fg=Colors.PRIMARY)
        title.pack(pady=10)
        
        # Main content frame for 2x2 grid
        grid_frame = tk.Frame(self.frame, bg=Colors.BACKGROUND)
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Configure 2x2 grid
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)
        grid_frame.grid_rowconfigure(0, weight=1)
        grid_frame.grid_rowconfigure(1, weight=1)
        
        directions = ['North', 'South', 'East', 'West']
        coords = [(0, 0), (0, 1), (1, 0), (1, 1)] # Row, Col
        
        for i, direction in enumerate(directions):
            row, col = coords[i]
            self.create_camera_widget(grid_frame, direction.lower(), row, col)

    def create_camera_widget(self, parent, direction, row, col):
        """create a single camera/traffic widget pair"""
        container = tk.Frame(parent, bg=Colors.CARD_BG, relief=tk.RAISED, bd=1)
        container.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
        container.grid_columnconfigure(0, weight=3) # Camera gets more space
        container.grid_columnconfigure(1, weight=1) # Lights/Stats
        container.grid_rowconfigure(0, weight=1) # Content row

        # Left Side: Header + Camera
        left_panel = tk.Frame(container, bg=Colors.CARD_BG)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Header - Larger and clear
        header = tk.Label(left_panel, text=direction.upper(), 
                         font=Fonts.TITLE, bg=Colors.CARD_BG, fg=Colors.PRIMARY)
        header.pack(fill=tk.X, pady=(5, 2))
        
        # Camera Feed
        cam_frame = tk.Frame(left_panel, bg=Colors.BLACK)
        cam_frame.pack(fill=tk.BOTH, expand=True)
        
        cam_label = tk.Label(cam_frame, bg=Colors.BLACK, text="No Signal", fg=Colors.WHITE)
        cam_label.pack(fill=tk.BOTH, expand=True)
        self.camera_labels[direction] = cam_label
        
        # Right Side: Controls/Lights
        control_frame = tk.Frame(container, bg=Colors.CARD_BG)
        control_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        # Traffic Light Canvas
        canvas = tk.Canvas(control_frame, width=60, height=140, bg=Colors.DARK_GREY, highlightthickness=0)
        canvas.pack(pady=10)
        self.light_canvases[direction] = canvas
        self.draw_traffic_light_box(direction)
        
        # Timer
        timer = tk.Label(control_frame, text="00s", font=(Fonts.FAMILY, 24, "bold"),
                        bg=Colors.CARD_BG, fg=Colors.TEXT)
        timer.pack(pady=5)
        self.timer_labels[direction] = timer
        
        # Stats
        stats_frame = tk.Frame(control_frame, bg=Colors.CARD_BG)
        stats_frame.pack(fill=tk.X, pady=5)
        
        self.stat_labels[f'{direction}_vehicles'] = self.create_mini_stat(stats_frame, "Vehicles", "0")
        self.stat_labels[f'{direction}_state'] = self.create_mini_stat(stats_frame, "Status", "RED")
        
    def create_mini_stat(self, parent, label_text, value_text):
        f = tk.Frame(parent, bg=Colors.CARD_BG)
        f.pack(fill=tk.X, padx=2, pady=2)
        
        # Stacked layout for meaningful stats
        tk.Label(f, text=label_text, font=Fonts.SMALL, bg=Colors.CARD_BG, fg=Colors.TEXT_LIGHT).pack(anchor="w")
        v = tk.Label(f, text=value_text, font=Fonts.BODY_BOLD, bg=Colors.CARD_BG, fg=Colors.PRIMARY)
        v.pack(anchor="e")
        return v

    def draw_traffic_light_box(self, direction):
        """Draw smaller traffic light"""
        c = self.light_canvases[direction]
        # Housing
        c.create_rectangle(5, 5, 55, 135, fill=Colors.BLACK, outline=Colors.SECONDARY, width=2)
        
        self.lamp_ids[direction] = {}
        # Red
        self.lamp_ids[direction]['red'] = c.create_oval(15, 15, 45, 45, fill="#330000", outline=Colors.BLACK)
        # Yellow
        self.lamp_ids[direction]['yellow'] = c.create_oval(15, 55, 45, 85, fill="#333300", outline=Colors.BLACK)
        # Green
        self.lamp_ids[direction]['green'] = c.create_oval(15, 95, 45, 125, fill="#003300", outline=Colors.BLACK)

    def update_camera_feed(self, frame, detection_data=None, direction='north'):
        """Update camera feed display for specific direction"""
        try:
            if direction not in self.camera_labels:
                return

            if frame is not None:
                # Resize for grid display (Larger view as requested)
                frame = cv2.resize(frame, (560, 420))
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                photo = ImageTk.PhotoImage(img)
                
                label = self.camera_labels[direction]
                label.config(image=photo, text="")
                label.image = photo
                
            if detection_data:
                self.update_live_stats(detection_data, direction)
        except Exception as e:
            pass # Avoid spamming errors

    def update_live_stats(self, data, direction):
        """Update visuals for a specific direction"""
        # Check if we have the labels for this direction
        vehicle_key = f'{direction}_vehicles'
        if vehicle_key not in self.stat_labels:
            return 

            
        vehicle_count = data.get('vehicle_count', 0)
        signal_state = data.get('signal_state', 'RED')
        time_left = data.get('time_remaining', 0)
        
        # Update text
        self.stat_labels[f'{direction}_vehicles'].config(text=str(vehicle_count))
        self.stat_labels[f'{direction}_state'].config(text=signal_state)
        self.timer_labels[direction].config(text=f"{int(time_left)}s")
        
        # Update Lamps
        dim = {'red': '#330000', 'yellow': '#333300', 'green': '#003300'}
        bright = {'red': '#ff0000', 'yellow': '#ffff00', 'green': '#00ff00'}
        
        c = self.light_canvases[direction]
        ids = self.lamp_ids[direction]
        
        for color_name, item_id in ids.items():
            c.itemconfig(item_id, fill=dim[color_name])
            
        active_color = signal_state.lower()
        if active_color in ids:
            c.itemconfig(ids[active_color], fill=bright[active_color])
    
    def get_widget(self):
        return self.frame
    
    def cleanup(self):
        self.is_running = False
