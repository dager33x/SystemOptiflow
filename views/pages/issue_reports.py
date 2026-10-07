# views/pages/issue_reports.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk
from views.components.message_box import MessageBox
from ..styles import Colors, Fonts
from datetime import datetime

class IssueReportsPage:
    """Page for managing and viewing issue reports with CustomTkinter styling"""
    
    def __init__(self, parent, db=None, current_user=None):
        self.parent = parent
        self.db = db
        self.current_user = current_user
        self.frame = tk.Frame(parent, bg=Colors.BACKGROUND)
        self.create_widgets()
        
    def create_widgets(self):
        """Create page layout"""
        # Header
        header_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        header_frame.pack(fill=tk.X, padx=40, pady=(30, 15))
        
        # Title
        title_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_container.pack(side=tk.LEFT)
        
        ctk.CTkLabel(title_container, text="Issue Reports",
                     font=('Segoe UI', 24, 'bold'),
                     text_color=Colors.TEXT).pack(anchor=tk.W)
                
        ctk.CTkLabel(title_container, text="Submit, track, and resolve system issues directly.",
                     font=('Segoe UI', 14),
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(5, 0))
        
        # New Report Button
        new_btn = ctk.CTkButton(header_frame, text="+ NEW REPORT",
                                font=('Segoe UI', 13, 'bold'),
                                fg_color=Colors.PRIMARY, 
                                hover_color=Colors.PRIMARY_DARK,
                                corner_radius=8,
                                width=140, height=36,
                                command=self.show_create_report_dialog)
        new_btn.pack(side=tk.RIGHT)
        
        # Reports List Card (Treeview)
        # Main content - Premium card styling
        card_frame = ctk.CTkFrame(self.frame, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        card_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=(10, 30))
        
        # Inner padding frame
        list_frame = ctk.CTkFrame(card_frame, fg_color="transparent")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Style for Treeview matching dashboard theme
        style = ttk.Style()
        style.theme_use('default')
        style.configure("Reports.Treeview", 
                        background="#0B111D",
                        foreground=Colors.TEXT,
                        fieldbackground="#0B111D",
                        rowheight=45,
                        borderwidth=0,
                        font=('Segoe UI', 11))
        
        style.configure("Reports.Treeview.Heading",
                        font=('Segoe UI', 12, 'bold'),
                        background="#1A2332",
                        foreground=Colors.TEXT_LIGHT,
                        relief="flat", borderwidth=0)
                       
        style.map("Reports.Treeview", 
                  background=[('selected', Colors.PRIMARY)],
                  foreground=[('selected', 'white')])
        
        style.map('Reports.Treeview.Heading', background=[('active', '#2c3a52')])
        
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
        self.tree.column("title", width=400, anchor="w")
        self.tree.column("priority", width=100, anchor="center")
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("author", width=150, anchor="center")
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Modern Scrollbar
        scrollbar = ctk.CTkScrollbar(list_frame, orientation="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        
        # Priority row colors
        self.tree.tag_configure('priority_low',    background='#0D2B20', foreground='#10B981')
        self.tree.tag_configure('priority_medium', background='#2B2207', foreground='#F59E0B')
        self.tree.tag_configure('priority_high',   background='#2B0D0D', foreground='#EF4444')

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
                    
                priority_tag = {'Low': 'priority_low', 'Medium': 'priority_medium', 'High': 'priority_high'}.get(
                    report.get('priority', 'Medium'), 'priority_medium')
                self.tree.insert("", tk.END, values=(
                    report.get('report_id'),
                    date_str,
                    f" {report.get('title')}",
                    report.get('priority', 'Medium').upper(),
                    report.get('status', 'Open').upper(),
                    report.get('author_name', 'Unknown')
                ), tags=(priority_tag,))
    
    def show_create_report_dialog(self):
        """Show modern CTk dialog to create new report"""
        dialog = ctk.CTkToplevel(self.parent)
        dialog.title("Create New Report")
        dialog.geometry("600x740")
        dialog.configure(fg_color=Colors.BACKGROUND)

        dialog.attributes('-topmost', True)
        dialog.transient(self.parent)
        dialog.grab_set()

        container = ctk.CTkFrame(dialog, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        container.pack(fill=tk.BOTH, expand=True, padx=30, pady=30)

        inner = ctk.CTkFrame(container, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=30, pady=30)

        ctk.CTkLabel(inner, text="Create Issue Report", font=('Segoe UI', 22, 'bold'),
                     text_color=Colors.TEXT).pack(pady=(0, 25), anchor="w")

        # Title
        ctk.CTkLabel(inner, text="Title / Subject", font=('Segoe UI', 12, 'bold'),
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(0, 5))
        title_entry = ctk.CTkEntry(inner, font=('Segoe UI', 14),
                                   fg_color="#0B111D", border_color="#2c3a52", border_width=1,
                                   text_color=Colors.TEXT, placeholder_text="Describe the core issue simply...")
        title_entry.pack(fill=tk.X, ipady=6, pady=(0, 20))

        # Priority
        ctk.CTkLabel(inner, text="Priority", font=('Segoe UI', 12, 'bold'),
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(0, 5))
        priority_cb = ctk.CTkOptionMenu(inner, values=["Low", "Medium", "High"],
                                        fg_color="#0B111D", button_color="#1E293B",
                                        button_hover_color="#334155", dropdown_fg_color="#0B111D",
                                        dropdown_hover_color="#1E293B", font=('Segoe UI', 13))
        priority_cb.set("Medium")
        priority_cb.pack(fill=tk.X, ipady=6, pady=(0, 20))

        # Description
        ctk.CTkLabel(inner, text="Description", font=('Segoe UI', 12, 'bold'),
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(0, 5))
        desc_text = ctk.CTkTextbox(inner, font=('Segoe UI', 14),
                                   fg_color="#0B111D", border_color="#2c3a52", border_width=1,
                                   text_color=Colors.TEXT, corner_radius=6, height=140)
        desc_text.pack(fill=tk.X, pady=(0, 20))

        # PDF Attachment
        ctk.CTkLabel(inner, text="Attach PDF (Optional)", font=('Segoe UI', 12, 'bold'),
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(0, 5))

        attach_row = ctk.CTkFrame(inner, fg_color="transparent")
        attach_row.pack(fill=tk.X, pady=(0, 20))

        selected_pdf = {"path": None}  # mutable container for the closure

        attach_name_lbl = ctk.CTkLabel(attach_row, text="No file selected",
                                       font=('Segoe UI', 12), text_color=Colors.TEXT_MUTED,
                                       anchor="w")
        attach_name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def browse_pdf():
            path = filedialog.askopenfilename(
                parent=dialog,
                title="Select PDF to attach",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
            )
            if path:
                selected_pdf["path"] = path
                import os
                attach_name_lbl.configure(
                    text=os.path.basename(path),
                    text_color=Colors.TEXT
                )

        def clear_pdf():
            selected_pdf["path"] = None
            attach_name_lbl.configure(text="No file selected", text_color=Colors.TEXT_MUTED)

        ctk.CTkButton(attach_row, text="Browse…", command=browse_pdf,
                      font=('Segoe UI', 12), fg_color="#1E293B", hover_color="#334155",
                      text_color=Colors.TEXT, corner_radius=6,
                      width=80, height=32).pack(side=tk.RIGHT, padx=(8, 0))
        ctk.CTkButton(attach_row, text="Clear", command=clear_pdf,
                      font=('Segoe UI', 12), fg_color="transparent", hover_color="#334155",
                      text_color=Colors.TEXT_MUTED, border_width=1, border_color="#334155",
                      corner_radius=6, width=55, height=32).pack(side=tk.RIGHT)

        def submit():
            import os, shutil
            title = title_entry.get().strip()
            desc  = desc_text.get("1.0", tk.END).strip()
            priority = priority_cb.get()

            if not title:
                MessageBox.showwarning("Required", "Please enter a title", parent=dialog)
                return

            # Copy PDF to local attachments folder before DB insert
            attachment_path = None
            if selected_pdf["path"]:
                try:
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    dest_dir = os.path.join(base_dir, "attachments", "reports")
                    os.makedirs(dest_dir, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in title)[:30]
                    dest = os.path.join(dest_dir, f"report_{safe}_{ts}.pdf")
                    shutil.copy2(selected_pdf["path"], dest)
                    attachment_path = dest
                except Exception as e:
                    MessageBox.showwarning("Attachment Warning",
                                           f"Could not save attachment:\n{e}\n\nReport will be created without it.",
                                           parent=dialog)

            if self.db:
                success = self.db.create_report(
                    title=title,
                    description=desc,
                    priority=priority,
                    author_id=self.current_user.get('user_id') if self.current_user else None,
                    author_name=self.current_user.get('username') if self.current_user else 'Anonymous',
                    attachment_path=attachment_path
                )
                if success:
                    MessageBox.showsuccess("Success", "Report created successfully", parent=dialog)
                    dialog.attributes('-topmost', False)
                    dialog.destroy()
                    self.load_reports()
                else:
                    MessageBox.showerror("Error", "Failed to create report", parent=dialog)
            else:
                MessageBox.showerror("Error", "Database connection not available", parent=dialog)

        def safely_close():
            dialog.attributes('-topmost', False)
            dialog.destroy()

        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ctk.CTkButton(btn_frame, text="Submit Report", command=submit,
                      font=('Segoe UI', 13, 'bold'), fg_color=Colors.PRIMARY,
                      hover_color=Colors.PRIMARY_DARK,
                      corner_radius=8, width=140, height=40).pack(side=tk.RIGHT)
        ctk.CTkButton(btn_frame, text="Cancel", command=safely_close,
                      font=('Segoe UI', 13, 'bold'), fg_color='transparent',
                      hover_color='#334155', text_color=Colors.TEXT,
                      border_width=1, border_color='#334155',
                      corner_radius=8, width=100, height=40).pack(side=tk.RIGHT, padx=15)

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
        """Show modern CTk dialog to view report details"""
        dialog = ctk.CTkToplevel(self.parent)
        dialog.title(f"Report: {report.get('title')}")
        dialog.geometry("600x620")
        dialog.configure(fg_color=Colors.BACKGROUND)

        dialog.attributes('-topmost', True)

        scrollable_frame = ctk.CTkScrollableFrame(dialog, fg_color="transparent", bg_color="transparent")
        scrollable_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        card = ctk.CTkFrame(scrollable_frame, fg_color='#161F33', corner_radius=15, border_width=1, border_color='#2c3a52')
        card.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=30, pady=30)

        ctk.CTkLabel(inner, text=report.get('title'), font=('Segoe UI', 24, 'bold'),
                     text_color=Colors.TEXT, wraplength=480, justify="left").pack(anchor=tk.W, pady=(0, 25))

        meta_frame = ctk.CTkFrame(inner, fg_color='#0B111D', corner_radius=10)
        meta_frame.pack(fill=tk.X, pady=(0, 30))

        inner_meta = ctk.CTkFrame(meta_frame, fg_color="transparent")
        inner_meta.pack(padx=20, pady=20, fill=tk.X)

        def create_meta_block(parent, label, value, val_color=Colors.TEXT):
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            frame.pack(side=tk.LEFT, expand=True, anchor="w")
            ctk.CTkLabel(frame, text=label, font=('Segoe UI', 10, 'bold'), text_color=Colors.TEXT_MUTED).pack(anchor="w")
            ctk.CTkLabel(frame, text=value, font=('Segoe UI', 14, 'bold'), text_color=val_color).pack(anchor="w", pady=(2, 0))

        priority_color = Colors.WARNING if report.get('priority') == 'Medium' else (Colors.DANGER if report.get('priority') == 'High' else Colors.SUCCESS)
        status_color = Colors.PRIMARY if report.get('status') == 'Open' else Colors.SUCCESS

        create_meta_block(inner_meta, "STATUS", report.get('status', 'Open').upper(), status_color)
        create_meta_block(inner_meta, "PRIORITY", report.get('priority', 'Medium').upper(), priority_color)
        create_meta_block(inner_meta, "AUTHOR", report.get('author_name', 'Unknown'))
        create_meta_block(inner_meta, "DATE", (report.get('created_at') or '')[:10])

        ctk.CTkLabel(inner, text="DESCRIPTION", font=('Segoe UI', 11, 'bold'),
                     text_color=Colors.TEXT_MUTED).pack(anchor=tk.W, pady=(0, 8))

        ctk.CTkLabel(inner, text=report.get('description', ''), font=('Segoe UI', 15),
                     text_color=Colors.TEXT, wraplength=480, justify="left").pack(anchor=tk.W)

        def download_pdf():
            try:
                safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in report.get('title', 'report'))[:40]
                pdf_path = filedialog.asksaveasfilename(
                    parent=dialog,
                    defaultextension=".pdf",
                    filetypes=[("PDF files", "*.pdf")],
                    title="Save Report as PDF",
                    initialfile=f"issue_report_{safe_title}.pdf"
                )
                if pdf_path:
                    self._generate_report_pdf(report, pdf_path)
                    messagebox.showinfo("Success", "PDF saved successfully!", parent=dialog)
            except Exception as e:
                messagebox.showerror("Error", f"Could not save PDF:\n{e}", parent=dialog)

        def safely_close():
            dialog.attributes('-topmost', False)
            dialog.destroy()

        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(fill=tk.X, pady=(35, 0))

        ctk.CTkButton(btn_frame, text="Download PDF", command=download_pdf,
                      font=('Segoe UI', 13, 'bold'),
                      fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_DARK,
                      corner_radius=8, width=145, height=40).pack(side=tk.RIGHT)

        ctk.CTkButton(btn_frame, text="Close", command=safely_close,
                      font=('Segoe UI', 13, 'bold'),
                      fg_color='transparent', hover_color='#334155',
                      text_color=Colors.TEXT, border_width=1, border_color='#334155',
                      corner_radius=8, width=100, height=40).pack(side=tk.RIGHT, padx=(0, 12))

    def _generate_report_pdf(self, report: dict, save_path: str):
        """Render the issue report as a PDF page using Pillow."""
        from PIL import Image, ImageDraw, ImageFont

        W, H = 850, 1100
        MARGIN = 60
        img = Image.new("RGB", (W, H), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        def _font(name, size):
            for candidate in [name, "arial.ttf", "DejaVuSans.ttf"]:
                try:
                    return ImageFont.truetype(candidate, size)
                except Exception:
                    pass
            return ImageFont.load_default()

        f_header  = _font("arialbd.ttf", 20)
        f_title   = _font("arialbd.ttf", 26)
        f_label   = _font("arialbd.ttf", 13)
        f_value   = _font("arialbd.ttf", 15)
        f_body    = _font("arial.ttf",   14)
        f_small   = _font("arial.ttf",   11)

        # ── Header bar ───────────────────────────────────────────────────────
        draw.rectangle([(0, 0), (W, 68)], fill=(11, 17, 29))
        draw.text((MARGIN, 20), "SystemOptiflow", fill=(255, 255, 255), font=f_header)
        draw.text((W - MARGIN - 130, 20), "ISSUE REPORT", fill=(100, 160, 255), font=f_header)

        y = 90

        # ── Report ID + date ─────────────────────────────────────────────────
        report_id = report.get('report_id', '')
        created   = (report.get('created_at') or '')[:10]
        draw.text((MARGIN, y), f"Report #{report_id}", fill=(140, 150, 170), font=f_small)
        id_label = f"Date: {created}"
        try:
            id_w = draw.textlength(id_label, font=f_small)
        except Exception:
            id_w = len(id_label) * 6
        draw.text((W - MARGIN - id_w, y), id_label, fill=(140, 150, 170), font=f_small)

        y += 22
        draw.line([(MARGIN, y), (W - MARGIN, y)], fill=(220, 225, 235), width=1)
        y += 18

        # ── Title ─────────────────────────────────────────────────────────────
        title = report.get('title', 'Untitled Report')
        # Simple word-wrap for title
        words, line, title_lines = title.split(), '', []
        for w in words:
            test = f"{line} {w}".strip()
            try:
                tw = draw.textlength(test, font=f_title)
            except Exception:
                tw = len(test) * 13
            if tw > W - 2 * MARGIN and line:
                title_lines.append(line)
                line = w
            else:
                line = test
        if line:
            title_lines.append(line)
        for tl in title_lines:
            draw.text((MARGIN, y), tl, fill=(15, 25, 60), font=f_title)
            y += 34
        y += 10

        # ── Metadata badges ───────────────────────────────────────────────────
        priority = report.get('priority', 'Medium').upper()
        status   = report.get('status',   'Open').upper()
        author   = report.get('author_name', 'Unknown')

        p_colors = {'HIGH': (200, 50, 50), 'MEDIUM': (190, 130, 20), 'LOW': (40, 140, 70)}
        s_colors = {'OPEN': (30, 110, 210), 'CLOSED': (40, 140, 70), 'IN PROGRESS': (160, 90, 20)}
        p_col = p_colors.get(priority, (100, 100, 100))
        s_col = s_colors.get(status,   (80,  80,  80))

        meta_bg_y1, meta_bg_y2 = y - 8, y + 62
        draw.rectangle([(MARGIN - 15, meta_bg_y1), (W - MARGIN + 15, meta_bg_y2)],
                       fill=(245, 247, 252), outline=(220, 225, 235))

        blocks = [("STATUS", status, s_col), ("PRIORITY", priority, p_col), ("AUTHOR", author, (50, 50, 50))]
        col_w = (W - 2 * MARGIN) // len(blocks)
        for i, (lbl, val, col) in enumerate(blocks):
            bx = MARGIN + i * col_w
            draw.text((bx, y),      lbl, fill=(140, 150, 170), font=f_label)
            draw.text((bx, y + 20), val, fill=col,             font=f_value)

        y = meta_bg_y2 + 22
        draw.line([(MARGIN, y), (W - MARGIN, y)], fill=(220, 225, 235), width=1)
        y += 20

        # ── Description ───────────────────────────────────────────────────────
        draw.text((MARGIN, y), "DESCRIPTION", fill=(140, 150, 170), font=f_label)
        y += 24

        description = report.get('description', '')
        for paragraph in (description or '(No description provided)').split('\n'):
            words = paragraph.split()
            if not words:
                y += 10
                continue
            line = ''
            for w in words:
                test = f"{line} {w}".strip()
                try:
                    tw = draw.textlength(test, font=f_body)
                except Exception:
                    tw = len(test) * 7
                if tw > W - 2 * MARGIN and line:
                    draw.text((MARGIN, y), line, fill=(30, 35, 50), font=f_body)
                    y += 22
                    line = w
                    if y > H - 100:
                        break
                else:
                    line = test
            if line and y <= H - 100:
                draw.text((MARGIN, y), line, fill=(30, 35, 50), font=f_body)
                y += 22
            if y > H - 100:
                draw.text((MARGIN, y), "  [content continues — description truncated]",
                          fill=(180, 180, 180), font=f_small)
                break

        # ── Footer ────────────────────────────────────────────────────────────
        draw.rectangle([(0, H - 48), (W, H)], fill=(245, 247, 252))
        draw.line([(0, H - 48), (W, H - 48)], fill=(220, 225, 235), width=1)
        draw.text((MARGIN, H - 30),
                  "SystemOptiflow Traffic Management System — Confidential",
                  fill=(180, 185, 200), font=f_small)
        ts = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        try:
            ts_w = draw.textlength(ts, font=f_small)
        except Exception:
            ts_w = len(ts) * 6
        draw.text((W - MARGIN - ts_w, H - 30), ts, fill=(180, 185, 200), font=f_small)

        img.save(save_path, "PDF", resolution=100.0)
    
    def get_widget(self):
        return self.frame
