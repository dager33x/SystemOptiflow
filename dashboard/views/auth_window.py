"""Responsive reference-matched login with native accessible Qt controls."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPixmap, QIcon, QLinearGradient, QPen
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QScrollArea, QMessageBox)
from dashboard.utils.paths import get_resource_path


class AuthBackdrop(QWidget):
    def __init__(self):
        super().__init__()
        self.art = QPixmap(get_resource_path('assets/login_reference.png'))
        self.setAccessibleName('Optiflow. Keep traffic moving. Monitor traffic, manage signals, and respond to incidents in real time.')
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.panel = QWidget()
        self.panel.setObjectName('formContent')
        self.layout = QVBoxLayout(self.panel)
        self.scroll.setWidget(self.panel)

    def scale(self):
        return min(self.width()/1672, self.height()/941)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        s = self.scale()
        x, y = (self.width()-1672*s)/2, (self.height()-941*s)/2
        self.scroll.setGeometry(round(x+951*s), round(y+94*s), round(650*s), round(765*s))
        self.layout.setContentsMargins(round(66*s), round(70*s), round(66*s), round(50*s))
        self.layout.setSpacing(max(4, round(12*s)))
        self.setStyleSheet(style(s))
        for child in self.panel.findChildren(QWidget):
            height = child.property('designHeight')
            if height:
                child.setFixedHeight(max(24, round(height*s)))
        self.update()

    def paintEvent(self, event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        gradient=QLinearGradient(0,0,self.width(),self.height())
        gradient.setColorAt(0,QColor('#0c1a30'))
        gradient.setColorAt(1,QColor('#060e1c'))
        painter.fillRect(self.rect(),gradient)
        s=self.scale()
        x,y=(self.width()-1672*s)/2,(self.height()-941*s)/2
        # Only the illustrated half is painted. All form text and fields are native.
        painter.drawPixmap(QRectF(x,y,951*s,941*s),self.art,
                           QRectF(0,0,self.art.width()*951/1672,self.art.height()))


def field_icon(password):
    pixmap=QPixmap(32,32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor('#8ca5c5'),2))
    if password:
        painter.drawRoundedRect(QRectF(7,14,18,15),2,2)
        painter.drawArc(QRectF(10,3,12,20),0,180*16)
        painter.drawLine(16,20,16,24)
    else:
        painter.drawEllipse(QRectF(10,3,12,12))
        painter.drawArc(QRectF(5,18,22,20),0,180*16)
        painter.drawLine(5,28,27,28)
    painter.end()
    return QIcon(pixmap)


def style(scale):
    def px(n): return max(10,round(n*scale))
    return f"""
    QWidget {{color:#f5f7fc; font-family:'Segoe UI'; font-size:{px(19)}px;}}
    QScrollArea {{border:none; background:transparent;}}
    QWidget#formContent {{background:#0b1628; border:1px solid #234366; border-radius:14px;}}
    QLabel,QCheckBox {{background:transparent;}}
    QLabel#formTitle {{font-size:{px(46)}px; font-weight:700;}}
    QLabel#formSubtitle {{color:#adc5e5; font-size:{px(23)}px;}}
    QLabel#fieldLabel {{color:#c1d5ee; font-size:{px(19)}px;}}
    QLabel#authStatus {{color:#e7b27b; font-size:{px(15)}px;}}
    QLineEdit {{background:#080f1d; border:1px solid #315781; border-radius:8px;
        padding:0 {px(20)}px; color:#eff5ff; selection-background-color:#1769ce;}}
    QLineEdit:focus {{border:2px solid #269aff;}}
    QPushButton {{border-radius:9px; padding:0 10px; font-weight:600;}}
    QPushButton#primary {{background:#187cff; border:1px solid #2890ff; font-size:{px(23)}px;}}
    QPushButton#primary:hover {{background:#3090ff;}}
    QPushButton#secondary {{background:#080f1d; border:1px solid #315781; font-size:{px(22)}px;}}
    QPushButton#secondary:hover {{background:#132540;}}
    QPushButton#textLink {{background:transparent; border:none; color:#2cafff; padding:0; font-weight:400;}}
    QPushButton:disabled {{color:#7f96b2; background:#193250;}}
    QPushButton:focus {{border:1px solid #92caff;}}
    QCheckBox {{color:#b9d0ed; spacing:10px;}}
    QCheckBox::indicator {{width:{px(22)}px; height:{px(22)}px; border:1px solid #8ca5c5; border-radius:3px; background:#0a1322;}}
    QCheckBox::indicator:checked {{background:#187cff; border-color:#55baff;}}
    QScrollBar:vertical {{background:#0b1628; width:6px;}}
    QScrollBar::handle:vertical {{background:#315781; min-height:20px;}}
    QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
    """


class AuthWindow(QMainWindow):
    def __init__(self,manager):
        super().__init__()
        self.manager=manager
        self.email=''
        self.mode='login'
        self.setWindowTitle('Optiflow — Sign in')
        self.setWindowIcon(QIcon(get_resource_path('assets/logo.png')))
        self.resize(1240,720)
        self.setMinimumSize(1000,640)
        self.show_form('login')

    def show_form(self,mode):
        self.mode=mode
        root=AuthBackdrop()
        layout=root.layout
        titles={'login':'Welcome to Optiflow','signup':'Create your account','forgot':'Reset your password',
                'verify':'Verify your email','reset':'Set a new password'}
        subtitles={'login':'Sign in to your traffic control workspace.',
                   'signup':'Verify your email, then wait for administrator approval before signing in.',
                   'forgot':'Enter your account details to receive a reset code.',
                   'verify':'Enter the verification code sent to your email.',
                   'reset':'Enter your reset code and choose a new password.'}
        title=QLabel(titles[mode]); title.setObjectName('formTitle'); title.setWordWrap(True)
        layout.addWidget(title)
        subtitle=QLabel(subtitles[mode]); subtitle.setObjectName('formSubtitle'); subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        fields={'login':[('username','Username'),('password','Password')],
                'signup':[('first_name','First name'),('last_name','Last name'),('username','Username'),('email','Email'),('password','Password')],
                'forgot':[('username','Username'),('email','Email')], 'verify':[('code','Verification code')],
                'reset':[('code','Verification code'),('new_password','New password')]}
        self.inputs={}; self.links=[]
        for key,label in fields[mode]:
            label_widget=QLabel(label); label_widget.setObjectName('fieldLabel')
            entry=QLineEdit(); entry.setProperty('designHeight',66)
            entry.setPlaceholderText('Enter '+label.lower()); entry.setAccessibleName(label)
            label_widget.setBuddy(entry)
            if 'password' in key: entry.setEchoMode(QLineEdit.EchoMode.Password)
            if key in ('username', 'password', 'new_password'):
                entry.addAction(field_icon('password' in key), QLineEdit.ActionPosition.LeadingPosition)
            entry.returnPressed.connect(self.submit)
            layout.addWidget(label_widget); layout.addWidget(entry)
            self.inputs[key]=entry
        if mode=='login':
            options=QHBoxLayout()
            reveal=QCheckBox('Show password')
            entry=self.inputs['password']
            reveal.toggled.connect(lambda checked: entry.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
            options.addWidget(reveal); options.addStretch()
            options.addWidget(self._link('Forgot password?','forgot','textLink'))
            layout.addLayout(options)
        self.status=QLabel('Connecting to database…' if self.manager.auth is None else '')
        self.status.setWordWrap(True); self.status.setObjectName('authStatus')
        layout.addWidget(self.status)
        captions={'login':'Sign in  →','signup':'Create account','forgot':'Send reset code','verify':'Verify','reset':'Reset password'}
        self.submit_button=QPushButton(captions[mode]); self.submit_button.setObjectName('primary')
        self.submit_button.setProperty('designHeight',68)
        self.submit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_button.clicked.connect(self.submit)
        self.submit_button.setEnabled(self.manager.auth is not None)
        layout.addWidget(self.submit_button)
        if mode=='login':
            signup=self._link('Sign up','signup','secondary'); signup.setProperty('designHeight',62)
            layout.addWidget(signup)
        else:
            layout.addWidget(self._link('Back to sign in','login','textLink'))
        previous=self.takeCentralWidget()
        self.setCentralWidget(root)
        if previous: previous.deleteLater()
        next(iter(self.inputs.values())).setFocus()

    def _link(self, caption, destination, style):
        button = QPushButton(caption)
        button.setObjectName(style)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda checked=False: self.show_form(destination))
        self.links.append(button)
        return button

    def submit(self):
        if self.manager.auth is None or not self.submit_button.isEnabled():
            return
        data = {key: entry.text() if 'password' in key else entry.text().strip() for key, entry in self.inputs.items()}
        if not all(data.values()):
            self.status.setText('Complete every field.')
            return
        password = data.get('new_password', data.get('password', ''))
        if self.mode in ('signup', 'reset') and len(password) < 6:
            self.status.setText('Password must contain at least 6 characters.')
            return
        mode, auth = self.mode, self.manager.auth
        if mode in ('signup', 'forgot'):
            self.email = data['email']
        self.submit_button.setEnabled(False)
        for link in self.links:
            link.setEnabled(False)
        self.status.setText('Please wait…')
        operations = {'login': auth.login, 'signup': auth.register_user, 'forgot': auth.reset_password,
                      'verify': auth.verify_email, 'reset': auth.verify_reset_code}
        if mode in ('verify', 'reset'):
            data['email'] = self.email
        def perform():
            auth.messages.items.clear()
            result = operations[mode](**data)
            return result, list(auth.messages.items)
        def complete(result, error):
            self.submit_button.setEnabled(True)
            for link in self.links:
                link.setEnabled(True)
            if error:
                self.status.setText('Unable to complete request: ' + error)
                return
            success, messages = result
            self.status.setText(messages[-1][2] if messages else ('' if success else 'Request failed.'))
            if not success:
                return
            for severity, title, message in messages:
                QMessageBox.information(self, title, message)
            if mode == 'login':
                self.inputs['password'].clear()
                self.manager.show_dashboard()
            else:
                if mode == 'forgot':
                    pending = next((v for k, v in auth.pending_verification.items() if k.startswith('reset_') and v['username'] == data['username']), None)
                    if pending:
                        self.email = pending['email']
                self.show_form({'signup': 'verify', 'forgot': 'reset', 'verify': 'login', 'reset': 'login'}[mode])
        self.manager.runner.submit(perform, complete)
