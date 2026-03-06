# views/pages/issue_reports.py
import tkinter as tk
from tkinter import ttk
from views.components.message_box import MessageBox
from ..styles import Colors, Fonts
from datetime import datetime

class IssueReportsPage:
    """Page for managing and viewing issue reports"""
    
    def __init__(self, parent, db=None, current_user=None):
        self.parent = parent
        self.db = db
        self.current_user = current_user
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.create_widgets()
        
    def create_widgets(self):
        """Create page layout"""
        # Header
        header_frame = tk.Frame(self.frame, bg=Colors.BACKGROUND)
        header_frame.pack(fill=tk.X, padx=20, pady=20)
        
        title = tk.Label(header_frame, text="Issue Reports", 
                        font=Fonts.TITLE, bg=Colors.BACKGROUND, 
                        fg=Colors.PRIMARY)
        title.pack(side=tk.LEFT)
        
        # New Report Button
        new_btn = tk.Button(header_frame, text="+ NEW REPORT",
                           font=Fonts.BODY_BOLD, bg=Colors.PRIMARY, 
                           fg="white", relief=tk.FLAT,
                           activebackground=Colors.PRIMARY_DARK,
                           activeforeground="white",
                           command=self.show_create_report_dialog)
        new_btn.pack(side=tk.RIGHT, ipadx=10, ipady=5)
        
        # Reports List (Treeview)
        list_frame = tk.Frame(self.frame, bg=Colors.BACKGROUND)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        # Style for Treeview
        style = ttk.Style()
        style.configure("Reports.Treeview", 
                       background=Colors.CARD_BG,
                       foreground=Colors.TEXT,
                       fieldbackground=Colors.CARD_BG,
                       rowheight=35,
                       borderwidth=0,
                       font=(Fonts.FAMILY, 10))
        
        style.configure("Reports.Treeview.Heading",
                       font=(Fonts.FAMILY, 10, "bold"),
                       background="#e2e8f0",      # Light slate (if respected)
                       foreground=Colors.BACKGROUND, # Dark text for contrast
                       relief="flat")
                       
        style.map("Reports.Treeview", 
                 background=[('selected', Colors.PRIMARY)],
                 foreground=[('selected', 'white')])
        
        columns = ("id", "date", "title", "priority", "status", "author")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", 
                                style="Reports.Treeview", selectmode="browse")
        
        # Column Headings
        self.tree.heading("id", text="ID")
        self.tree.heading("date", text="DATE")
        self.tree.heading("title", text="TITLE")
        self.tree.heading("priority", text="PRIORITY")
        self.tree.heading("status", text="STATUS")
        self.tree.heading("author", text="AUTHOR")
        
        # Column Widths
        self.tree.column("id", width=0, stretch=tk.NO) # Hidden ID
        self.tree.column("date", width=150, anchor="center")
        self.tree.column("title", width=400)
        self.tree.column("priority", width=100, anchor="center")
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("author", width=150, anchor="center")
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind double click
        self.tree.bind("<Double-1>", self.on_item_double_click)
        
        # Initial Load
        self.load_reports()
        
    def load_reports(self):
        """Load reports from database"""
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        if self.db:
            reports = self.db.get_all_reports()
            for report in reports:
                # Format date
                try:
                    dt = datetime.fromisoformat(report.get('created_at', '').replace('Z', '+00:00'))
                    date_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    date_str = report.get('created_at', '')
                    
                self.tree.insert("", tk.END, values=(
                    report.get('report_id'),
                    date_str,
                    report.get('title'),
                    report.get('priority', 'Medium'),
                    report.get('status', 'Open'),
                    report.get('author_name', 'Unknown')
                ))
    
    def show_create_report_dialog(self):
        """Show dialog to create new report"""
        dialog = tk.Toplevel(self.parent)
        dialog.title("Create New Report")
        dialog.geometry("600x650")
        dialog.configure(bg=Colors.BACKGROUND)
        
        # Center dialog
        dialog.transient(self.parent)
        dialog.grab_set()
        
        # Form Container
        container = tk.Frame(dialog, bg=Colors.CARD_BG, padx=30, pady=30)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header
        tk.Label(container, text="Create Issue Report", font=Fonts.HEADING, 
                bg=Colors.CARD_BG, fg=Colors.TEXT).pack(pady=(0, 20))
        
        # Title
        tk.Label(container, text="Title / Subject", font=(Fonts.FAMILY, 10, "bold"), 
                bg=Colors.CARD_BG, fg=Colors.TEXT_LIGHT).pack(anchor=tk.W, pady=(0, 5))
                
        title_entry = tk.Entry(container, font=(Fonts.FAMILY, 11), bg=Colors.BACKGROUND, 
                              fg=Colors.TEXT, relief=tk.FLAT, insertbackground=Colors.PRIMARY)
        title_entry.pack(fill=tk.X, ipady=8, pady=(0, 15))
        
        # Priority
        tk.Label(container, text="Priority", font=(Fonts.FAMILY, 10, "bold"), 
                bg=Colors.CARD_BG, fg=Colors.TEXT_LIGHT).pack(anchor=tk.W, pady=(0, 5))
                
        priority_cb = ttk.Combobox(container, values=["Low", "Medium", "High"], state="readonly")
        priority_cb.current(1)
        priority_cb.pack(fill=tk.X, ipady=5, pady=(0, 15))
        
        # Description
        tk.Label(container, text="Description", font=(Fonts.FAMILY, 10, "bold"), 
                bg=Colors.CARD_BG, fg=Colors.TEXT_LIGHT).pack(anchor=tk.W, pady=(0, 5))
                
        desc_text = tk.Text(container, height=10, font=(Fonts.FAMILY, 11), 
                           bg=Colors.BACKGROUND, fg=Colors.TEXT, relief=tk.FLAT,
                           insertbackground=Colors.PRIMARY)
        desc_text.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        def submit():
            title = title_entry.get().strip()
            desc = desc_text.get("1.0", tk.END).strip()
            priority = priority_cb.get()
            
            if not title:
                MessageBox.showwarning("Required", "Please enter a title", parent=dialog)
                return
                
            if self.db:
                success = self.db.create_report(
                    title=title,
                    description=desc,
                    priority=priority,
                    author_id=self.current_user.get('user_id') if self.current_user else None,
                    author_name=self.current_user.get('username') if self.current_user else 'Anonymous'
                )
                
                if success:
                    MessageBox.showsuccess("Success", "Report created successfully", parent=dialog)
                    dialog.destroy()
                    self.load_reports()
                else:
                    MessageBox.showerror("Error", "Failed to create report", parent=dialog)
            else:
                MessageBox.showerror("Error", "Database connection not available", parent=dialog)
        
        # Buttons
        btn_frame = tk.Frame(container, bg=Colors.CARD_BG)
        btn_frame.pack(fill=tk.X)
        
        tk.Button(btn_frame, text="Submit Report", command=submit,
                 bg=Colors.PRIMARY, fg="white", relief=tk.FLAT, padx=20, pady=10,
                 activebackground=Colors.PRIMARY_DARK, activeforeground="white").pack(side=tk.RIGHT)
                 
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy,
                 bg=Colors.BACKGROUND, fg=Colors.TEXT, relief=tk.FLAT, padx=20, pady=10,
                 activebackground=Colors.HOVER, activeforeground=Colors.TEXT).pack(side=tk.RIGHT, padx=10)

    def on_item_double_click(self, event):
        """View report details"""
        item = self.tree.selection()[0]
        values = self.tree.item(item, "values")
        report_id = values[0]
        
        if self.db:
            report = self.db.get_report(report_id)
            if report:
                self.show_view_report_dialog(report)
    
    def show_view_report_dialog(self, report):
        """Show dialog to view report details"""
        dialog = tk.Toplevel(self.parent)
        dialog.title(f"Report: {report.get('title')}")
        dialog.geometry("600x600")
        dialog.configure(bg=Colors.BACKGROUND)
        
        # Content Container
        container = tk.Frame(dialog, bg=Colors.BACKGROUND)
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, bg=Colors.BACKGROUND, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=Colors.BACKGROUND)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=580)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y")
        
        # Report Card
        card = tk.Frame(scrollable_frame, bg=Colors.CARD_BG, padx=30, pady=30)
        card.pack(fill=tk.BOTH, expand=True)
        
        # Title
        tk.Label(card, text=report.get('title'), font=Fonts.HEADING, 
                bg=Colors.CARD_BG, fg=Colors.TEXT, wraplength=500, justify="left").pack(anchor=tk.W, pady=(0, 20))
        
        # Metadata Frame
        meta_frame = tk.Frame(card, bg=Colors.SECONDARY, padx=15, pady=15)
        meta_frame.pack(fill=tk.X, pady=(0, 20))
        
        grid_opts = {'sticky': 'w', 'padx': 10, 'pady': 5}
        
        tk.Label(meta_frame, text="STATUS", font=Fonts.SMALL, bg=Colors.SECONDARY, fg=Colors.TEXT_LIGHT).grid(row=0, column=0, **grid_opts)
        tk.Label(meta_frame, text=report.get('status').upper(), font=Fonts.BODY_BOLD, 
                bg=Colors.SECONDARY, fg=Colors.get_status_color(report.get('status'))).grid(row=1, column=0, **grid_opts)
                
        tk.Label(meta_frame, text="PRIORITY", font=Fonts.SMALL, bg=Colors.SECONDARY, fg=Colors.TEXT_LIGHT).grid(row=0, column=1, **grid_opts)
        tk.Label(meta_frame, text=report.get('priority'), font=Fonts.BODY_BOLD, bg=Colors.SECONDARY, fg=Colors.WARNING).grid(row=1, column=1, **grid_opts)

        tk.Label(meta_frame, text="AUTHOR", font=Fonts.SMALL, bg=Colors.SECONDARY, fg=Colors.TEXT_LIGHT).grid(row=0, column=2, **grid_opts)
        tk.Label(meta_frame, text=report.get('author_name'), font=Fonts.BODY_BOLD, bg=Colors.SECONDARY, fg=Colors.TEXT).grid(row=1, column=2, **grid_opts)

        tk.Label(meta_frame, text="DATE", font=Fonts.SMALL, bg=Colors.SECONDARY, fg=Colors.TEXT_LIGHT).grid(row=0, column=3, **grid_opts)
        tk.Label(meta_frame, text=report.get('created_at')[:10], font=Fonts.BODY_BOLD, bg=Colors.SECONDARY, fg=Colors.TEXT).grid(row=1, column=3, **grid_opts)

        # Description
        tk.Label(card, text="DESCRIPTION", font=Fonts.SMALL, 
                bg=Colors.CARD_BG, fg=Colors.TEXT_LIGHT).pack(anchor=tk.W, pady=(0, 8))
        
        desc_lbl = tk.Label(card, text=report.get('description'), font=Fonts.BODY, 
                           bg=Colors.CARD_BG, fg=Colors.TEXT, wraplength=500, justify="left")
        desc_lbl.pack(anchor=tk.W)
        
        # Close Button
        tk.Button(card, text="Close", command=dialog.destroy,
                 bg=Colors.BACKGROUND, fg=Colors.TEXT, relief=tk.FLAT, padx=20, pady=8,
                 activebackground=Colors.HOVER).pack(pady=(40, 0))
    
    def get_widget(self):
        return self.frame
