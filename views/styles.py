# views/styles.py
import tkinter as tk
from tkinter import ttk


class Colors:
    """Color palette for the application (Modern Premium Dark Theme)"""
    # Base - Richer Dark Backgrounds
    BACKGROUND = '#0B0F19' # Deep Navy/Black
    CARD_BG = '#151B2B'    # Slightly lighter Navy
    INPUT_BG = '#1A2332'   # Input field background
    
    # Brand - Electric Blue / Neon
    PRIMARY = '#3B82F6'    # Bright Blue
    PRIMARY_DARK = '#2563EB' 
    PRIMARY_LIGHT = '#60A5FA'
    SECONDARY = '#1E293B'  # Slate 800 (for secondary elements)
    ACCENT = '#64748B'     
    HOVER = '#2D3748'      # Dark Grey Blue for hovers
    
    # Text
    TEXT = '#F8FAFC'       # White-ish
    TEXT_LIGHT = '#94A3B8' # Muted Blue-Grey
    TEXT_MUTED = '#64748B' # Even more muted
    
    # State - Vibrant Indicators
    SUCCESS = '#10B981'    # Emerald
    SUCCESS_DARK = '#059669'
    WARNING = '#F59E0B'    # Amber
    WARNING_DARK = '#D97706'
    DANGER = '#EF4444'     # Red
    DANGER_DARK = '#DC2626'
    INFO = '#0EA5E9'       # Sky Blue
    INFO_DARK = '#0284C7'
    
    # Specific
    BLACK = '#000000'
    DARK_GREY = '#111827'
    WHITE = '#FFFFFF'
    
    # Border and dividers
    BORDER = '#2D3748'
    BORDER_LIGHT = '#374151'
    DIVIDER = '#1F2937'
    
    # Focus states
    FOCUS_RING = '#60A5FA'
    
    # Domain specific
    ROAD_GREEN = '#15803d'
    ROAD_DARK = '#1e293b'
    ROAD_LIGHT = '#334155'
    
    @staticmethod
    def get_status_color(status: str) -> str:
        """Get color for status indicator"""
        status_colors = {
            'active': Colors.SUCCESS,
            'warning': Colors.WARNING,
            'error': Colors.DANGER,
            'info': Colors.INFO,
            'simulated': '#8B5CF6', # Violet for simulation (Distinct)
            'offline': Colors.ACCENT
        }
        return status_colors.get(status.lower(), Colors.TEXT_LIGHT)


class Fonts:
    """Font styles for the application"""
    FAMILY = 'Segoe UI' # Modern Windows Font
    FAMILY_ALT = 'Inter'  # Alternative modern font
    
    TITLE = (FAMILY, 24, 'bold')
    HEADING = (FAMILY, 16, 'bold')
    SUBHEADING = (FAMILY, 14, 'bold')
    BODY = (FAMILY, 11)
    BODY_BOLD = (FAMILY, 11, 'bold')
    SMALL = (FAMILY, 9)
    SMALL_BOLD = (FAMILY, 9, 'bold')
    MONO = ('Consolas', 10)
    BUTTON = (FAMILY, 11, 'bold')
    INPUT = (FAMILY, 11)


class ModernStyles:
    """Modern TTK and widget styling configuration"""
    
    @staticmethod
    def configure_ttk_styles(root):
        """Configure TTK styles for modern appearance"""
        style = ttk.Style(root)
        
        # Use 'clam' theme as base for better customization
        try:
            style.theme_use('clam')
        except:
            pass
        
        # Configure Treeview (for tables)
        style.configure(
            'Modern.Treeview',
            background=Colors.CARD_BG,
            foreground=Colors.TEXT,
            fieldbackground=Colors.CARD_BG,
            borderwidth=0,
            relief='flat',
            rowheight=35,
            font=Fonts.BODY
        )
        
        style.configure(
            'Modern.Treeview.Heading',
            background=Colors.SECONDARY,
            foreground=Colors.WHITE,
            borderwidth=0,
            relief='flat',
            font=Fonts.BODY_BOLD
        )
        
        style.map(
            'Modern.Treeview',
            background=[('selected', Colors.PRIMARY)],
            foreground=[('selected', Colors.WHITE)]
        )
        
        style.map(
            'Modern.Treeview.Heading',
            background=[('active', Colors.HOVER)],
            foreground=[('active', Colors.WHITE)]
        )
        
        # Configure Scrollbar
        style.configure(
            'Modern.Vertical.TScrollbar',
            background=Colors.SECONDARY,
            troughcolor=Colors.BACKGROUND,
            borderwidth=0,
            arrowcolor=Colors.TEXT_LIGHT
        )
        
        style.map(
            'Modern.Vertical.TScrollbar',
            background=[('active', Colors.ACCENT)]
        )
        
        # Configure Combobox
        style.configure(
            'Modern.TCombobox',
            fieldbackground=Colors.INPUT_BG,
            background=Colors.INPUT_BG,
            foreground=Colors.TEXT,
            borderwidth=1,
            relief='flat',
            arrowcolor=Colors.TEXT_LIGHT
        )
        
        # Configure Radiobutton
        style.configure(
            'Modern.TRadiobutton',
            background=Colors.CARD_BG,
            foreground=Colors.TEXT,
            font=Fonts.BODY,
            indicatorcolor=Colors.PRIMARY
        )
        
        style.map(
            'Modern.TRadiobutton',
            background=[('active', Colors.CARD_BG)],
            foreground=[('active', Colors.PRIMARY)]
        )
        
        # Configure Checkbutton
        style.configure(
            'Modern.TCheckbutton',
            background=Colors.CARD_BG,
            foreground=Colors.TEXT,
            font=Fonts.BODY
        )
        
        style.map(
            'Modern.TCheckbutton',
            background=[('active', Colors.CARD_BG)],
            foreground=[('active', Colors.PRIMARY)]
        )
        
        return style


class WidgetStyles:
    """Helper class for creating styled widgets"""
    
    @staticmethod
    def create_modern_button(parent, text, command=None, style='primary', width=None):
        """Create a modern styled button
        
        Args:
            parent: Parent widget
            text: Button text
            command: Button command callback
            style: 'primary', 'success', 'danger', 'secondary', 'info', 'warning'
            width: Optional fixed width
        """
        style_config = {
            'primary': {
                'bg': Colors.PRIMARY,
                'fg': Colors.WHITE,
                'active_bg': Colors.PRIMARY_DARK,
                'hover_bg': Colors.PRIMARY_LIGHT
            },
            'success': {
                'bg': Colors.SUCCESS,
                'fg': Colors.WHITE,
                'active_bg': Colors.SUCCESS_DARK,
                'hover_bg': '#34D399'
            },
            'danger': {
                'bg': Colors.DANGER,
                'fg': Colors.WHITE,
                'active_bg': Colors.DANGER_DARK,
                'hover_bg': '#F87171'
            },
            'secondary': {
                'bg': Colors.SECONDARY,
                'fg': Colors.TEXT,
                'active_bg': Colors.HOVER,
                'hover_bg': Colors.ACCENT
            },
            'info': {
                'bg': Colors.INFO,
                'fg': Colors.WHITE,
                'active_bg': Colors.INFO_DARK,
                'hover_bg': '#38BDF8'
            },
            'warning': {
                'bg': Colors.WARNING,
                'fg': Colors.WHITE,
                'active_bg': Colors.WARNING_DARK,
                'hover_bg': '#FBBF24'
            }
        }
        
        config = style_config.get(style, style_config['primary'])
        
        btn = tk.Button(
            parent,
            text=text,
            font=Fonts.BUTTON,
            bg=config['bg'],
            fg=config['fg'],
            activebackground=config['active_bg'],
            activeforeground=Colors.WHITE,
            relief=tk.FLAT,
            bd=0,
            cursor='hand2',
            command=command,
            padx=20,
            pady=10
        )
        
        if width:
            btn.config(width=width)
        
        # Add hover effects
        def on_enter(e):
            btn.config(bg=config['hover_bg'])
        
        def on_leave(e):
            btn.config(bg=config['bg'])
        
        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)
        
        return btn
    
    @staticmethod
    def create_modern_entry(parent, placeholder='', is_password=False, width=None):
        """Create a modern styled entry with placeholder
        
        Returns a container frame with .entry attribute
        """
        # Container with border effect
        container = tk.Frame(parent, bg=Colors.BORDER, padx=1, pady=1)
        
        # Inner frame
        inner_frame = tk.Frame(container, bg=Colors.INPUT_BG)
        inner_frame.pack(fill=tk.BOTH, expand=True)
        
        # Entry widget
        entry = tk.Entry(
            inner_frame,
            font=Fonts.INPUT,
            bg=Colors.INPUT_BG,
            fg=Colors.TEXT_LIGHT,
            relief=tk.FLAT,
            bd=0,
            insertbackground=Colors.PRIMARY,
            highlightthickness=0
        )
        
        if width:
            entry.config(width=width)
        
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=10, padx=12)
        
        # Placeholder functionality
        if placeholder:
            entry.insert(0, placeholder)
            entry.placeholder_text = placeholder
            entry.password_visible = False
            
            def on_focus_in(event):
                if entry.get() == placeholder:
                    entry.delete(0, tk.END)
                    entry.config(fg=Colors.TEXT)
                    if is_password and not entry.password_visible:
                        entry.config(show='*')
                # Focus ring effect
                container.config(bg=Colors.FOCUS_RING)
            
            def on_focus_out(event):
                if not entry.get():
                    if is_password:
                        entry.config(show='')
                    entry.insert(0, placeholder)
                    entry.config(fg=Colors.TEXT_LIGHT)
                # Remove focus ring
                container.config(bg=Colors.BORDER)
            
            entry.bind('<FocusIn>', on_focus_in)
            entry.bind('<FocusOut>', on_focus_out)
            
            # Password visibility toggle
            if is_password:
                def toggle_visibility():
                    if entry.get() == placeholder:
                        return
                    entry.password_visible = not entry.password_visible
                    if entry.password_visible:
                        entry.config(show='')
                        eye_btn.config(text='🙈')
                    else:
                        entry.config(show='*')
                        eye_btn.config(text='👁️')
                
                eye_btn = tk.Button(
                    inner_frame,
                    text='👁️',
                    font=('Segoe UI', 12),
                    bg=Colors.INPUT_BG,
                    fg=Colors.TEXT_LIGHT,
                    relief=tk.FLAT,
                    bd=0,
                    cursor='hand2',
                    activebackground=Colors.INPUT_BG,
                    activeforeground=Colors.PRIMARY,
                    command=toggle_visibility
                )
                eye_btn.pack(side=tk.RIGHT, padx=8)
                
                def on_enter(e):
                    eye_btn.config(fg=Colors.PRIMARY)
                
                def on_leave(e):
                    eye_btn.config(fg=Colors.TEXT_LIGHT)
                
                eye_btn.bind('<Enter>', on_enter)
                eye_btn.bind('<Leave>', on_leave)
        
        container.entry = entry
        return container
    
    @staticmethod
    def create_card(parent, bg=None):
        """Create a card-style frame"""
        if bg is None:
            bg = Colors.CARD_BG
        
        card = tk.Frame(parent, bg=bg, padx=20, pady=20)
        return card
    
    @staticmethod
    def create_label(parent, text, style='body', fg=None, bg=None):
        """Create a styled label
        
        Args:
            style: 'title', 'heading', 'subheading', 'body', 'small'
        """
        font_map = {
            'title': Fonts.TITLE,
            'heading': Fonts.HEADING,
            'subheading': Fonts.SUBHEADING,
            'body': Fonts.BODY,
            'body_bold': Fonts.BODY_BOLD,
            'small': Fonts.SMALL
        }
        
        if bg is None:
            bg = Colors.CARD_BG
        
        if fg is None:
            fg = Colors.TEXT if style in ['title', 'heading', 'subheading', 'body_bold'] else Colors.TEXT_LIGHT
        
        label = tk.Label(
            parent,
            text=text,
            font=font_map.get(style, Fonts.BODY),
            bg=bg,
            fg=fg
        )
        
        return label