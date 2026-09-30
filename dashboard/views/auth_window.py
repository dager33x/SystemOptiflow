"""Authentication forms for the Qt interface."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPixmap, QIcon
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QScrollArea, QMessageBox)
from dashboard.utils.paths import get_resource_path
from dashboard.views.auth_styles import AUTH_STYLE


class BrandPanel(QWidget):
    """Quiet geometric background behind the welcome message."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#0b111c'))
        painter.setPen(QPen(QColor('#172537'), 24))
        painter.drawEllipse(QRectF(self.width() - 175, -90, 300, 300))
        painter.setPen(QPen(QColor('#1c334a'), 1))
        painter.drawEllipse(QRectF(-155, self.height() - 245, 370, 370))
        painter.drawEllipse(QRectF(-125, self.height() - 215, 310, 310))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#25354b'))
        for row in range(5):
            for column in range(6):
                painter.drawEllipse(self.width() - 136 + column * 17,
                                    self.height() - 145 + row * 17, 3, 3)


class AuthWindow(QMainWindow):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.setWindowTitle('Optiflow — Sign in')
        self.setStyleSheet(AUTH_STYLE)
        self.setWindowIcon(QIcon(get_resource_path('assets/logo.png')))
        self.resize(1100, 700)
        self.setMinimumSize(860, 600)
        self.email = ''
        self.mode = 'login'
        self.show_form('login')

    def show_form(self, mode):
        self.mode = mode
        titles = {'login': 'Welcome to Optiflow', 'signup': 'Create your account',
                  'forgot': 'Reset your password', 'verify': 'Verify your email', 'reset': 'Set a new password'}
        widget = QWidget()
        widget.setObjectName('authRoot')
        split = QHBoxLayout(widget)
        split.setContentsMargins(12, 12, 12, 12)
        split.setSpacing(0)

        brand = BrandPanel()
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(52, 22, 52, 38)
        logo = QLabel()
        logo.setAccessibleName('Optiflow logo')
        logo.setPixmap(QPixmap(get_resource_path('assets/logo.png')).scaled(
            280, 280, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        brand_layout.addStretch(1)
        welcome = QLabel('Hello,\nwelcome!')
        welcome.setObjectName('heroTitle')
        brand_layout.addWidget(welcome)
        brand_layout.addSpacing(18)
        description = QLabel('A clearer view. A smarter flow.\nTraffic monitoring and intelligent\nsignal control, in one place.')
        description.setObjectName('heroDescription')
        description.setWordWrap(True)
        brand_layout.addWidget(description)
        brand_layout.addStretch(2)
        caption = QLabel('OPTIFLOW  /  TRAFFIC MANAGEMENT')
        caption.setObjectName('eyebrow')
        brand_layout.addWidget(caption)
        split.addWidget(brand, 55)

        panel = QWidget()
        panel.setObjectName('formPanel')
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(32, 32, 32, 32)
        panel_layout.addStretch()
        content = QWidget()
        content.setObjectName('formContent')
        content.setMaximumWidth(350)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        title = QLabel(titles[mode])
        title.setObjectName('formTitle')
        title.setWordWrap(True)
        layout.addWidget(title)
        subtitles = {'login': 'Sign in to your traffic control workspace.',
                     'signup': 'Verify your email, then wait for administrator approval before signing in.',
                     'forgot': 'Enter your account details to receive a reset code.',
                     'verify': 'Enter the verification code sent to your email.',
                     'reset': 'Enter your reset code and choose a new password.'}
        subtitle = QLabel(subtitles[mode])
        subtitle.setObjectName('formSubtitle')
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(18)
        fields = {'login': [('username', 'Username'), ('password', 'Password')],
                  'signup': [('first_name', 'First name'), ('last_name', 'Last name'), ('username', 'Username'), ('email', 'Email'), ('password', 'Password')],
                  'forgot': [('username', 'Username'), ('email', 'Email')],
                  'verify': [('code', 'Verification code')],
                  'reset': [('code', 'Verification code'), ('new_password', 'New password')]}
        self.inputs = {}
        for key, label in fields[mode]:
            field_label = QLabel(label)
            field_label.setObjectName('fieldLabel')
            entry = QLineEdit()
            entry.setFixedHeight(44)
            entry.setPlaceholderText('Enter ' + label.lower())
            entry.setAccessibleName(label)
            field_label.setBuddy(entry)
            if 'password' in key:
                entry.setEchoMode(QLineEdit.EchoMode.Password)
            entry.returnPressed.connect(self.submit)
            layout.addWidget(field_label)
            layout.addWidget(entry)
            self.inputs[key] = entry
        self.links = []
        if mode == 'login':
            options = QHBoxLayout()
            reveal = QCheckBox('Show password')
            password_entry = self.inputs['password']
            reveal.toggled.connect(lambda checked: password_entry.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
            options.addWidget(reveal)
            options.addStretch()
            forgot = self._link('Forgot password?', 'forgot', 'textLink')
            options.addWidget(forgot)
            layout.addLayout(options)
        self.status = QLabel('Connecting to database…' if self.manager.auth is None else '')
        self.status.setWordWrap(True)
        self.status.setObjectName('authStatus')
        self.status.setMinimumHeight(32)
        layout.addWidget(self.status)
        self.submit_button = QPushButton({'login': 'Sign in', 'signup': 'Create account', 'forgot': 'Send reset code', 'verify': 'Verify', 'reset': 'Reset password'}[mode])
        self.submit_button.setObjectName('primary')
        self.submit_button.setFixedHeight(44)
        self.submit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_button.clicked.connect(self.submit)
        self.submit_button.setEnabled(self.manager.auth is not None)
        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addWidget(self.submit_button, 1)
        if mode == 'login':
            signup = self._link('Sign up', 'signup', 'secondary')
            signup.setFixedHeight(44)
            actions.addWidget(signup, 1)
        layout.addLayout(actions)
        if mode != 'login':
            back = self._link('Back to sign in', 'login', 'textLink')
            back.setMinimumHeight(32)
            layout.addWidget(back)
        panel_layout.addWidget(content, 0, Qt.AlignmentFlag.AlignHCenter)
        panel_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(panel)
        split.addWidget(scroll, 45)
        previous = self.takeCentralWidget()
        self.setCentralWidget(widget)
        if previous:
            previous.deleteLater()
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
