# views/pages/violation_logs.py
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from ..styles import Colors, Fonts
from datetime import datetime
import os

class ViolationLogsPage:
    """Violation logs page with traffic violations database mapped to CustomTkinter"""
    
    def __init__(self, parent, controller=None, current_user=None):
        self.parent = parent
        self.controller = controller
        self.current_user = current_user
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.tree = None
        self.log_map = {}
        
        ctk.set_appearance_mode("dark")
        self.create_widgets()
        
        # Load data immediately
        self.refresh_data()
    
    def create_widgets(self):
        """Create violation logs page layout"""
        # Header Frame
        header_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        header_frame.pack(fill=tk.X, padx=40, pady=(30, 15))
        
        title_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_container.pack(side=tk.LEFT)
        
        ctk.CTkLabel(title_container, text="Violation Logs",
                     font=('Segoe UI', 24, 'bold'),
                     text_color=Colors.TEXT).pack(anchor=tk.W)
                
        ctk.CTkLabel(title_container, text="Review captured snapshots of traffic infractions.",
                     font=('Segoe UI', 14),
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(5, 0))
        
        
        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.pack(side=tk.RIGHT)
        
        # Clear Button (Admin Only)
        is_admin = self.current_user and self.current_user.get('role', '').lower() == 'admin'
        if is_admin:
            clear_btn = ctk.CTkButton(btn_frame, text="🗑️ Clear All",
                                      command=self.clear_data,
                                      font=('Segoe UI', 13, 'bold'),
                                      fg_color=Colors.DANGER, 
                                      hover_color=Colors.DANGER_DARK,
                                      corner_radius=8,
                                      width=120, height=36)
            clear_btn.pack(side=tk.RIGHT, padx=(10, 0))
            
        # Refresh Button
        refresh_btn = ctk.CTkButton(btn_frame, text="🔄 Refresh",
                                    command=self.refresh_data,
                                    font=('Segoe UI', 13, 'bold'),
                                    fg_color='#1E293B', # Secondary color 
                                    hover_color='#334155',
                                    text_color=Colors.TEXT,
                                    corner_radius=8,
                                    width=120, height=36)
        refresh_btn.pack(side=tk.RIGHT)


        # Main content Card
        content_frame = ctk.CTkFrame(self.frame, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=(10, 30))
        
        tree_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Create columns
        columns = ('Date', 'Time', 'Lane', 'Violation Type', 'Vehicle ID', 'Status')
        self.tree = ttk.Treeview(tree_frame, columns=columns, height=15, show='headings')
        
        # Configure column headings
        for col in columns:
            self.tree.heading(col, text=col)
            if col in ['Date', 'Time', 'Lane', 'Status']:
                self.tree.column(col, width=120, anchor=tk.CENTER)
            else:
                self.tree.column(col, width=150, anchor=tk.W)
        
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # Style treeview
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

        scrollbar = ctk.CTkScrollbar(tree_frame, orientation="vertical", command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        
        # Bind double-click event
        self.tree.bind("<Double-1>", self.on_item_double_click)

    def refresh_data(self):
        """Fetch and display logs from controller"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        self.log_map.clear()
            
        if not self.controller:
            return
            
        logs = self.controller.get_logs()
        
        for log in logs:
            # Parse timestamp safely
            try:
                date_str_raw = log.get('created_at') or log.get('timestamp', '')
                dt_obj = datetime.fromisoformat(date_str_raw.replace('Z', '+00:00'))
                date_str = dt_obj.strftime('%Y-%m-%d')
                time_str = dt_obj.strftime('%H:%M:%S')
            except:
                date_str = "Unknown"
                time_str = "Unknown"
                
            # Map lane ID to Direction Name
            lane_id = log.get('lane', '?')
            lane_map = {0: 'North', 1: 'South', 2: 'East', 3: 'West', '0': 'North', '1': 'South', '2': 'East', '3': 'West'}
            lane = lane_map.get(lane_id, f"Lane {lane_id}")
            
            v_type = log.get('violation_type', 'Unknown')
            veh_id = log.get('vehicle_id', 'N/A')
            
            image_url = log.get('image_url')
            if image_url:
                status = "📷 View Image"
            else:
                status = "Recorded"
            
            # Padding for text alignment
            item_id = self.tree.insert('', tk.END, values=(date_str, time_str, lane, f" {v_type}", f" {veh_id}", status))
            self.log_map[item_id] = log

    def on_item_double_click(self, event):
        selection = self.tree.selection()
        if not selection:
            return
            
        item_id = selection[0]
        log = self.log_map.get(item_id)
        if not log:
            return
            
        image_url = log.get('image_url')
        if not image_url or not os.path.exists(image_url):
            from tkinter import messagebox
            messagebox.showinfo("No Image", "No image available for this violation.", parent=self.frame)
            return
            
        self.show_image_popup(log)

    def show_image_popup(self, log):
        from tkinter import filedialog, messagebox
        from PIL import Image, ImageTk

        image_path = log.get('image_url')

        dialog = ctk.CTkToplevel(self.frame)
        dialog.title("Violation Snapshot")
        dialog.geometry("700x700")
        dialog.configure(fg_color=Colors.BACKGROUND)
        
        dialog.attributes('-topmost', True)
        dialog.transient(self.frame)
        dialog.grab_set()

        card = ctk.CTkFrame(dialog, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        card.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(inner, text="Violation Snapshot", font=('Segoe UI', 22, 'bold'), text_color=Colors.PRIMARY).pack(pady=(0, 10))
        
        # Frame just to hold image centered
        img_frame = ctk.CTkFrame(inner, fg_color="#0B111D", corner_radius=10)
        img_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 20), padx=20)
        
        try:
            img = Image.open(image_path)
            # Resize
            img.thumbnail((640, 480))
            tk_img = ImageTk.PhotoImage(img)
            
            # Raw tk.Label specifically for PhotoImage 
            img_lbl = tk.Label(img_frame, image=tk_img, bg="#0B111D")
            img_lbl.image = tk_img 
            img_lbl.pack(expand=True)
        except Exception as e:
            ctk.CTkLabel(img_frame, text=f"Error loading image: {e}", text_color=Colors.DANGER).pack(expand=True)

        def download_pdf():
            try:
                raw_time = log.get('created_at') or log.get('timestamp', 'log')
                safe_time = raw_time.replace(':', '-').replace('.', '-')
                pdf_path = filedialog.asksaveasfilename(
                    parent=dialog,
                    defaultextension=".pdf",
                    filetypes=[("PDF files", "*.pdf")],
                    title="Save as PDF",
                    initialfile=f"violation_{safe_time}.pdf"
                )
                if pdf_path:
                    pdf_img = Image.open(image_path)
                    if pdf_img.mode == 'RGBA':
                        pdf_img = pdf_img.convert('RGB')
                    pdf_img.save(pdf_path, "PDF", resolution=100.0)
                    messagebox.showinfo("Success", "PDF saved successfully!", parent=dialog)
            except Exception as e:
                messagebox.showerror("Error", f"Could not save PDF: {e}", parent=dialog)

        def safely_close():
             # Drop topmost locking rule
             dialog.attributes('-topmost', False)
             dialog.destroy()
             
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill=tk.X)
        
        ctk.CTkButton(btn_frame, text="Download as PDF", command=download_pdf, font=('Segoe UI', 13, 'bold'), fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_DARK, corner_radius=8, height=40).pack(side=tk.RIGHT)
        ctk.CTkButton(btn_frame, text="Close", command=safely_close, font=('Segoe UI', 13, 'bold'), fg_color='transparent', hover_color='#334155', border_color='#334155', border_width=1, corner_radius=8, height=40).pack(side=tk.RIGHT, padx=10)

    def clear_data(self):
        """Clear all violation data if admin"""
        from tkinter import messagebox
        if messagebox.askyesno("Confirm", "Are you sure you want to completely clear all violation logs? This cannot be undone.", parent=self.frame):
            if self.controller and hasattr(self.controller, 'clear_logs'):
                if self.controller.clear_logs():
                    messagebox.showinfo("Success", "Violation logs cleared successfully.", parent=self.frame)
                    self.refresh_data()
                else:
                    messagebox.showerror("Error", "Failed to clear violation logs.", parent=self.frame)
            
    def get_widget(self):
        # Refresh when shown
        self.refresh_data()
        return self.frame
