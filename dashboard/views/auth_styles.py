"""Authentication styling using the dashboard's existing navy and blue palette."""

AUTH_STYLE = '''
QWidget { color: #e8eef9; font-family: "Segoe UI"; font-size: 13px; }
QWidget#authRoot { background: #0b1019; }
QWidget#formPanel { background: #101725; }
QWidget#formContent, QLabel, QCheckBox { background: transparent; }
QLabel#eyebrow { color: #93a5bb; font-size: 11px; font-weight: 600; }
QLabel#heroTitle { font-size: 52px; font-weight: 700; }
QLabel#heroDescription { color: #a9bdd8; font-size: 15px; }
QLabel#formTitle { font-size: 28px; font-weight: 600; }
QLabel#formSubtitle { color: #93a5bb; font-size: 13px; }
QLabel#fieldLabel { color: #a9bdd8; font-size: 12px; }
QLabel#authStatus { color: #a9bdd8; font-size: 12px; }
QLineEdit { background: #0b1019; border: 1px solid #33546f; border-radius: 5px;
            padding: 0 14px; color: #e8eef9; selection-background-color: #285f84; }
QLineEdit:hover { border-color: #627991; }
QLineEdit:focus { border: 1px solid #3987ff; }
QPushButton { border-radius: 5px; padding: 0 16px; font-weight: 600; }
QPushButton#primary { background: #3987ff; border: 1px solid #3987ff; color: #ffffff; }
QPushButton#primary:hover { background: #2974e8; }
QPushButton#primary:pressed { background: #285f84; }
QPushButton#secondary { background: transparent; border: 1px solid #33546f; color: #e8eef9; }
QPushButton#secondary:hover { background: #1c334a; border-color: #3987ff; }
QPushButton#textLink { background: transparent; border: none; color: #7cafff;
                       padding: 0; font-size: 12px; font-weight: 400; }
QPushButton#textLink:hover { color: #b3d1ff; }
QPushButton:disabled { background: #1c334a; color: #627991; border-color: #25354b; }
QPushButton:focus { border: 1px solid #93a5bb; }
QCheckBox { color: #93a5bb; font-size: 12px; spacing: 7px; }
QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #627991;
                       border-radius: 3px; background: #0b1019; }
QCheckBox::indicator:checked { background: #3987ff; border-color: #3987ff; }
QScrollArea { background: #101725; border: none; }
QScrollBar:vertical { background: #101725; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #33546f; min-height: 30px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
'''
