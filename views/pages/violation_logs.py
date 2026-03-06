# views/pages/violation_logs.py
import tkinter as tk
from tkinter import ttk
from ..styles import Colors, Fonts
from datetime import datetime

class ViolationLogsPage:
    """Violation logs page with traffic violations database"""
    
    def __init__(self, parent, controller=None, current_user=None):
        self.parent = parent
        self.controller = controller
        self.current_user = current_user
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.tree = None
        self.log_map = {}
        self.create_widgets()
        
        # Load data immediately
        self.refresh_data()
    
    def create_widgets(self):
        """Create violation logs page layout"""
        # Header Frame
        header_frame = tk.Frame(self.frame, bg=Colors.BACKGROUND)
        header_frame.pack(fill=tk.X, padx=20, pady=15)
        
        # Title
        title = tk.Label(header_frame, text="Violation Logs",
                        font=Fonts.TITLE, bg=Colors.BACKGROUND,
                        fg=Colors.PRIMARY)
        title.pack(side=tk.LEFT)
        
        # Refresh Button
        refresh_btn = tk.Button(header_frame, text="🔄 Refresh",
                               font=Fonts.BODY, bg=Colors.PRIMARY, fg=Colors.WHITE,
                               relief=tk.FLAT, padx=15, pady=5, cursor="hand2",
                               command=self.refresh_data)
        refresh_btn.pack(side=tk.RIGHT)
        
        # Clear Button (Admin Only)
        is_admin = self.current_user and self.current_user.get('role', '').lower() == 'admin'
        if is_admin:
            clear_btn = tk.Button(header_frame, text="🗑️ Clear All",
                                  command=self.clear_data,
                                  font=Fonts.BODY,
                                  bg=Colors.DANGER, fg="white",
                                  relief=tk.FLAT, padx=15, pady=5)
            clear_btn.pack(side=tk.RIGHT, padx=10)
        
        # Main content
        content_frame = tk.Frame(self.frame, bg=Colors.BACKGROUND)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Treeview for violations
        tree_frame = tk.Frame(content_frame, bg=Colors.CARD_BG)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create columns
        columns = ('Date', 'Time', 'Lane', 'Violation Type', 'Vehicle ID', 'Status')
        self.tree = ttk.Treeview(tree_frame, columns=columns, height=15, show='headings')
        
        # Configure column headings
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120)
        
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Style treeview
        style = ttk.Style()
        style.configure("Treeview", 
                       background=Colors.CARD_BG,
                       foreground=Colors.TEXT, 
                       fieldbackground=Colors.CARD_BG,
                       font=Fonts.BODY,
                       rowheight=30)
        style.configure("Treeview.Heading",
                       background=Colors.WHITE,
                       foreground="black",
                       font=Fonts.BODY_BOLD)
        style.map('Treeview', background=[('selected', Colors.PRIMARY)])
        
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
            
            item_id = self.tree.insert('', tk.END, values=(date_str, time_str, lane, v_type, veh_id, status))
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
        import os
        if not image_url or not os.path.exists(image_url):
            from tkinter import messagebox
            messagebox.showinfo("No Image", "No image available for this violation.", parent=self.frame)
            return
            
        self.show_image_popup(log)

    def show_image_popup(self, log):
        from tkinter import Toplevel, Label, Button, filedialog, messagebox
        from PIL import Image, ImageTk
        import os

        image_path = log.get('image_url')

        top = Toplevel(self.frame)
        top.title("Violation Snapshot")
        top.geometry("700x680")
        top.configure(bg=Colors.BACKGROUND)
        
        lbl = Label(top, text="Violation Snapshot", font=Fonts.TITLE, bg=Colors.BACKGROUND, fg=Colors.PRIMARY)
        lbl.pack(pady=10)

        try:
            img = Image.open(image_path)
            # Resize
            img.thumbnail((640, 480))
            tk_img = ImageTk.PhotoImage(img)
            
            img_lbl = Label(top, image=tk_img, bg=Colors.BACKGROUND)
            img_lbl.image = tk_img 
            img_lbl.pack(pady=10)
        except Exception as e:
            Label(top, text=f"Error loading image: {e}", bg=Colors.BACKGROUND, fg='red').pack()

        def download_pdf():
            try:
                raw_time = log.get('created_at') or log.get('timestamp', 'log')
                safe_time = raw_time.replace(':', '-').replace('.', '-')
                pdf_path = filedialog.asksaveasfilename(
                    parent=top,
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
                    messagebox.showinfo("Success", "PDF saved successfully!", parent=top)
            except Exception as e:
                messagebox.showerror("Error", f"Could not save PDF: {e}", parent=top)

        btn = Button(top, text="Download as PDF", font=Fonts.BODY_BOLD, bg=Colors.PRIMARY, fg="white", cursor="hand2", command=download_pdf, padx=20, pady=10)
        btn.pack(pady=20)
            
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
