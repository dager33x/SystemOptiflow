"""PySide6 shell for the existing detection and traffic engines."""
import time
from datetime import datetime
from PySide6.QtCore import Qt, QTimer, Signal, QSettings
from PySide6.QtWidgets import (QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QCheckBox, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QScrollArea, QSlider)
from dashboard.views.widgets import CameraCard, VideoCanvas, SignalLamp, LANE_NAMES, STYLE
from dashboard.views.icons import navigation_icon
from dashboard.views.notifications import NotificationCenter
from dashboard.utils.app_config import SETTINGS

STYLE += '''
QWidget { background: #0b1019; color: #e8eef9; }
QFrame#sidebar { background: #0c1118; border-right: 1px solid #202c40; }
QFrame#header { background: #090e15; border-bottom: 2px solid #3987ff; }
QFrame#card { background: #182132; border: 1px solid #2b3b55; border-radius: 12px; }
QFrame#signalPanel { background: #101725; border: none; border-radius: 12px; }
QPushButton#nav { text-align: left; background: transparent; border: none; border-radius: 0; padding: 13px 10px; color: #a9bdd8; }
QPushButton#nav:checked { background: #1b2a44; color: white; border-left: 3px solid #3987ff; }
QPushButton#nav:hover { background: #172235; }
QLineEdit, QTextEdit, QTableWidget { background: #121c2b; border: 1px solid #293a51; border-radius: 5px; padding: 7px; selection-background-color: #285386; }
QHeaderView::section { background: #1b2a40; color: #a9c1e0; border: none; padding: 10px; }
QTableWidget { gridline-color: #253247; }
QLabel#cameraStatus { background: #1c2b40; padding: 10px 5px; font-size: 11px; }
QLabel#cardTitle { font-size: 13px; }
QScrollArea { border: none; }
'''


class DashboardWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, controller, autostart=True, db=None, auth=None, current_user=None, runner=None):
        super().__init__()
        self.controller, self.db, self.auth = controller, db, auth
        self.current_user = current_user or {'username': 'Local preview', 'role': 'viewer'}
        self.setWindowTitle('SystemOptiflow — Traffic Management')
        self.resize(1600, 940)
        self.setMinimumSize(1040, 680)
        self.setStyleSheet(STYLE)
        self.saved = QSettings('Optiflow', 'Dashboard')
        self.persist = db is not None
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QFrame()
        header.setObjectName('header')
        header.setFixedHeight(48)
        top = QHBoxLayout(header)
        self.breadcrumb = QLabel('SystemOptiflow   /   Dashboard')
        top.addWidget(self.breadcrumb)
        top.addStretch()
        self.clock = QLabel()
        top.addWidget(self.clock)
        self.alerts_button = QPushButton('Alerts')
        self.alerts_button.setToolTip('Recent accident and violation notifications')
        top.addWidget(self.alerts_button)
        self.notifications = NotificationCenter(self, self.alerts_button)
        self.notifications.open_requested.connect(self._open_notification)
        top.addSpacing(20)
        top.addWidget(QLabel(self.current_user.get('username', 'User')))
        self.logout_button = QPushButton('Logout' if auth else 'Close preview')
        self.logout_button.setStyleSheet('color: #ff4148; background: #250d12; border: none;')
        self.logout_button.clicked.connect(self._logout)
        top.addWidget(self.logout_button)
        root.addWidget(header)
        body = QHBoxLayout()
        body.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setFixedWidth(218)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(8, 14, 8, 12)
        brand_row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(navigation_icon('brand').pixmap(28, 40))
        brand_row.addWidget(logo)
        self.brand = QLabel('<b style="font-size:18px">Optiflow</b><br><span style="font-size:11px;color:#a9bdd8">Traffic AI</span>')
        self.brand.setStyleSheet('padding: 10px 0;')
        brand_row.addWidget(self.brand, 1)
        side.addLayout(brand_row)
        collapse = QPushButton('<')
        collapse.setFixedWidth(30)
        collapse.setFixedHeight(30)
        collapse.setStyleSheet('padding: 0;')
        collapse.clicked.connect(self._collapse)
        side.addWidget(collapse, alignment=Qt.AlignmentFlag.AlignRight)
        side.addWidget(QLabel('MENU'))
        self.nav = {}
        self.stack = QStackedWidget()
        self.pages = {}
        body.addWidget(self.sidebar)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        dashboard = QWidget()
        layout = QVBoxLayout(dashboard)
        layout.setContentsMargins(24, 24, 24, 10)
        grid = QGridLayout()
        grid.setSpacing(20)
        self.cards = []
        for i, lane in enumerate(controller.store.snapshot()):
            card = CameraCard(i, lane.density)
            card.set_stop_line(lane.stop_line)
            card.stop_line_changed.connect(self._stop_line_changed)
            index = card.source.findData(lane.source)
            if index < 0:
                card.source.addItem(str(lane.source), lane.source)
                index = card.source.count()-1
            card.source.setCurrentIndex(index)
            card.source_changed.connect(self._source_changed)
            card.simulation_changed.connect(controller.set_simulation)
            card.events_changed.connect(controller.set_simulation_events)
            grid.addWidget(card, i//2, i%2)
            self.cards.append(card)
        for i in range(2):
            grid.setRowStretch(i, 1)
            grid.setColumnStretch(i, 1)
        layout.addLayout(grid, 1)
        self.phase = QLabel('Initializing traffic controller')
        self.phase.setObjectName('muted')
        layout.addWidget(self.phase)
        self.status = QLabel('Starting workers…')
        self.status.setObjectName('muted')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._add_page('dashboard', '▥  Traffic Live Camera', dashboard, side)
        if db is not None:
            from dashboard.views.pages import RecordsPage, TrafficPage, UsersPage
            from dashboard.views.incidents import IncidentPage
            self._add_page('issue_reports', '⚠  Issue Reports',
                RecordsPage('issues', db, controller, self.current_user, runner), side)
            self._add_page('traffic_reports', '◉  Traffic Reports', TrafficPage(controller), side)
            self._add_page('incident_history', '▤  Incident History',
                IncidentPage(db, controller, self.current_user, runner), side)
            self._add_page('violation_logs', '▧  Violation Logs',
                RecordsPage('violations', db, controller, self.current_user, runner), side)
        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        title = QLabel('System Preferences')
        title.setObjectName('title')
        settings_layout.addWidget(title)
        settings_layout.addWidget(QLabel('Camera sources, vehicle simulation and detection controls'))
        self.ai_toggle = QPushButton('AI detection on')
        self.ai_toggle.setCheckable(True)
        self.ai_toggle.setChecked(controller.store.summary()[0])
        self.ai_toggle.toggled.connect(self._toggle_ai)
        self.ai_toggle.setText('AI detection on' if self.ai_toggle.isChecked() else 'AI detection paused')
        settings_layout.addWidget(self.ai_toggle)
        self.boxes = QCheckBox('Show detection boxes and confidence scores')
        self.boxes.setChecked(self.saved.value('boxes', True, type=bool) if self.persist else True)
        self.boxes.toggled.connect(lambda value: self.saved.setValue('boxes', value) if self.persist else None)
        settings_layout.addWidget(self.boxes)
        alert_title = QLabel('Notifications & sound')
        alert_title.setStyleSheet('font-size: 16px; font-weight: 600; margin-top: 12px;')
        settings_layout.addWidget(alert_title)
        self.popup_alerts = QCheckBox('Show accident and violation pop-ups')
        self.popup_alerts.setChecked(self.saved.value('alerts/popups', True, type=bool)
                                    if self.persist else SETTINGS.get('enable_notifications', True))
        settings_layout.addWidget(self.popup_alerts)
        sound_row = QHBoxLayout()
        self.sound_alerts = QCheckBox('Play alert chimes')
        self.sound_alerts.setChecked(self.saved.value('alerts/sound', True, type=bool) if self.persist else True)
        sound_row.addWidget(self.sound_alerts)
        sound_row.addWidget(QLabel('Volume'))
        self.alert_volume = QSlider(Qt.Orientation.Horizontal)
        self.alert_volume.setRange(0, 100)
        self.alert_volume.setMaximumWidth(180)
        self.alert_volume.setValue(self.saved.value('alerts/volume', 55, type=int) if self.persist else 55)
        self.alert_volume.setAccessibleName('Alert sound volume')
        sound_row.addWidget(self.alert_volume)
        self.volume_label = QLabel()
        sound_row.addWidget(self.volume_label)
        for kind, caption in (('incident', 'Test incident sound'), ('violation', 'Test violation sound')):
            test = QPushButton(caption)
            test.clicked.connect(lambda checked=False, kind=kind: self.notifications.audio.play(kind, force=True))
            sound_row.addWidget(test)
        sound_row.addStretch()
        settings_layout.addLayout(sound_row)
        self.audio_status = QLabel(self.notifications.audio.status)
        self.audio_status.setObjectName('muted')
        self.notifications.audio.status_changed.connect(self.audio_status.setText)
        settings_layout.addWidget(self.audio_status)
        for signal in (self.popup_alerts.toggled, self.sound_alerts.toggled, self.alert_volume.valueChanged):
            signal.connect(self._notification_settings)
        self._notification_settings()
        for card in self.cards:
            settings_layout.addWidget(card.settings_widget)
            card.settings_widget.show()
        note = QLabel('Simulation uses known vehicle counts. Emergency priority uses the same signal controller as live cameras.\nNormal timing: 60–120 seconds green, 5 seconds yellow, 2 seconds all-red.')
        note.setWordWrap(True)
        settings_layout.addWidget(note)
        settings_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(settings)
        self._add_page('settings', '⚙  Settings', scroll, side)
        if db is not None and self.current_user.get('role') == 'admin':
            self._add_page('admin_users', '♟  Manage Users', UsersPage(auth, self.current_user, runner), side)
        side.addSpacing(15)
        self.camera_heading = QLabel('ACTIVE CAMERAS')
        side.addWidget(self.camera_heading)
        self.camera_labels = []
        for name in LANE_NAMES:
            label = QLabel(name)
            label.setObjectName('cameraStatus')
            side.addWidget(label)
            self.camera_labels.append(label)
        side.addStretch()
        self.navigate('dashboard')
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(33)
        self.slow_refresh = 0
        if autostart:
            QTimer.singleShot(0, controller.start)

    def _add_page(self, key, title, widget, layout):
        self.pages[key] = widget
        self.stack.addWidget(widget)
        button = QPushButton(title[3:])
        button.setIcon(navigation_icon(key))
        button.setObjectName('nav')
        button.setCheckable(True)
        button.setToolTip(title[3:])
        button.clicked.connect(lambda checked=False, key=key: self.navigate(key))
        layout.addWidget(button)
        self.nav[key] = button

    def navigate(self, key):
        self.stack.setCurrentWidget(self.pages[key])
        for name, button in self.nav.items():
            button.setChecked(name == key)
        self.breadcrumb.setText('SystemOptiflow   /   ' + self.nav[key].toolTip())
        if hasattr(self.pages[key], 'reload'):
            self.pages[key].reload()

    def _collapse(self):
        collapsed = self.sidebar.width() > 100
        self.sidebar.setFixedWidth(58 if collapsed else 218)
        self.brand.setVisible(not collapsed)
        self.camera_heading.setVisible(not collapsed)
        for label in self.camera_labels:
            label.setVisible(not collapsed)
        for button in self.nav.values():
            button.setText('' if collapsed else button.toolTip())

    def _source_changed(self, lane, source):
        self.controller.set_source(lane, source)
        if self.persist:
            self.saved.setValue('source/' + ('north', 'south', 'east', 'west')[lane], source)

    def _stop_line_changed(self, lane, line):
        self.controller.store.set_stop_line(lane, line)
        if self.persist:
            for key in ('height', 'left', 'right', 'direction'):
                self.saved.setValue(f'stop_line/{lane}/{key}', getattr(line, key))

    def _toggle_ai(self, enabled):
        self.ai_toggle.setText('AI detection on' if enabled else 'AI detection paused')
        self.controller.store.set_ai(enabled)
        if self.persist:
            self.saved.setValue('ai_enabled', enabled)

    def _notification_settings(self):
        self.notifications.popups_enabled = self.popup_alerts.isChecked()
        if not self.notifications.popups_enabled:
            for card in list(self.notifications.cards):
                self.notifications.dismiss(card)
        self.notifications.audio.configure(self.sound_alerts.isChecked(), self.alert_volume.value()/100)
        self.volume_label.setText(f'{self.alert_volume.value()}%')
        if self.persist:
            for key, value in (('popups', self.popup_alerts.isChecked()),
                               ('sound', self.sound_alerts.isChecked()), ('volume', self.alert_volume.value())):
                self.saved.setValue('alerts/' + key, value)

    def _open_notification(self, notification):
        page = 'dashboard' if notification.simulated else notification.page
        self.navigate(page if page in self.pages else 'dashboard')

    def refresh(self):
        now = time.monotonic()
        self.notifications.receive(self.controller.store.drain_notifications())
        lanes = self.controller.store.snapshot()
        if self.stack.currentWidget() is self.pages['dashboard']:
            for card, lane in zip(self.cards, lanes):
                card.present(lane, now, self.boxes.isChecked())
        if now-self.slow_refresh < .25:
            return
        self.slow_refresh = now
        self.clock.setText(datetime.now().strftime('%H:%M:%S'))
        for label, name, lane in zip(self.camera_labels, LANE_NAMES, lanes):
            fresh = lane.frame is not None and now-lane.frame.captured_at < 1
            source = 'Sim' if lane.source == 'simulation' else f'Cam {lane.source}' if isinstance(lane.source, int) else 'Video / stream'
            label.setText(f'●  {name} ({source})\n    {lane.status if fresh else "Waiting for signal"}')
            label.setStyleSheet('color: #14c997;' if fresh else 'color: #94a8c4;')
        _, ai, engine, phase = self.controller.store.summary()
        self.phase.setText(phase)
        self.status.setText(f'{engine}  |  {ai}  |  {self.controller.workers.dqn_status}')
        page = self.stack.currentWidget()
        if hasattr(page, 'update_live'):
            page.update_live(lanes)

    def _logout(self):
        if self.auth:
            self.logout_requested.emit()
        else:
            self.close()

    def closeEvent(self, event):
        self.timer.stop()
        self.notifications.stop()
        self.controller.stop()
        event.accept()
