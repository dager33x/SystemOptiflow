"""Nonmodal alert cards and a bounded, session-local notification history."""
from collections import deque

from PySide6.QtCore import QObject, Signal, QTimer, QEvent, Qt, QPropertyAnimation
from PySide6.QtWidgets import (QFrame, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QDialog, QScrollArea, QGraphicsOpacityEffect)
from dashboard.views.widgets import LANE_NAMES
from dashboard.services.alert_audio import AlertAudio


class AlertCard(QFrame):
    dismissed = Signal(object)
    opened = Signal(object)

    def __init__(self, notification, parent=None):
        super().__init__(parent)
        self.notification = notification
        self.setObjectName('alertCard')
        self.setMinimumHeight(160)
        accent = '#ffbf69' if notification.kind == 'incident' else '#ff747c'
        self.setStyleSheet(f'''
            QFrame#alertCard {{ background: #172337; border: 1px solid #33465f;
                border-left: 4px solid {accent}; border-radius: 9px; }}
            QLabel {{ background: transparent; border: none; color: #b8c9df; }}
            QPushButton {{ background: transparent; border: none; color: #8db9ff;
                padding: 4px 0; text-align: left; }}
            QPushButton:hover {{ color: #e8eef9; }}
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 14, 12)
        layout.setSpacing(7)
        header = QHBoxLayout()
        icon = QLabel('!')
        icon.setFixedSize(24, 24)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f'color: {accent}; background: #293349; border-radius: 12px; font-weight: 700;')
        header.addWidget(icon)
        title = QLabel(notification.title)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setStyleSheet('color: #eef4ff; font-size: 14px; font-weight: 600;')
        header.addWidget(title, 1)
        close = QPushButton('×')
        close.setAccessibleName('Dismiss notification')
        close.setFixedSize(24, 24)
        close.setStyleSheet('font-size: 19px; padding: 0; text-align: center; color: #93a5bb;')
        close.clicked.connect(lambda: self.dismissed.emit(self))
        header.addWidget(close)
        layout.addLayout(header)
        lane_name = LANE_NAMES[notification.lane] if 0 <= notification.lane < len(LANE_NAMES) else 'Traffic camera'
        meta = QLabel(f'{lane_name}  /  {notification.timestamp:%H:%M:%S}' + ('  /  SIMULATION' if notification.simulated else ''))
        meta.setStyleSheet(f'font-size: 11px; color: {accent};')
        layout.addWidget(meta)
        message = QLabel(notification.message)
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.setWordWrap(True)
        layout.addWidget(message)
        action = QPushButton('View camera' if notification.simulated else
                             'Review incident  →' if notification.kind == 'incident' else 'View violations  →')
        action.setCursor(Qt.CursorShape.PointingHandCursor)
        action.clicked.connect(lambda: self.opened.emit(notification))
        layout.addWidget(action)


class NotificationCenter(QObject):
    open_requested = Signal(object)

    def __init__(self, window, button):
        super().__init__(window)
        self.window, self.button = window, button
        self.audio = AlertAudio(self)
        self.history = deque(maxlen=100)
        self.cards = []
        self.unread = 0
        self.popups_enabled = True
        self.dialog = None
        self.stack = QWidget(window)
        self.stack.setObjectName('notificationStack')
        self.stack.setStyleSheet('QWidget#notificationStack { background: transparent; }')
        self.layout = QVBoxLayout(self.stack)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self.stack.hide()
        self.window.installEventFilter(self)
        button.clicked.connect(self.show_history)

    def receive(self, notifications):
        if not notifications:
            return
        for notification in notifications:
            self.history.appendleft(notification)
            self.unread += 1
        self.button.setText(f'Alerts ({self.unread})')
        if self.popups_enabled:
            for notification in notifications[-3:]:
                self._toast(notification)
        self.audio.play('incident' if any(n.kind == 'incident' for n in notifications) else 'violation')
        if self.dialog and self.dialog.isVisible():
            self._fill_history()

    def _toast(self, notification):
        while len(self.cards) >= 3:
            self.dismiss(self.cards[0])
        card = AlertCard(notification, self.stack)
        card.dismissed.connect(self.dismiss)
        card.opened.connect(self.open_requested.emit)
        self.layout.addWidget(card)
        self.cards.append(card)
        effect = QGraphicsOpacityEffect(card)
        card.setGraphicsEffect(effect)
        card.animation = QPropertyAnimation(effect, b'opacity', card)
        card.animation.setDuration(220)
        card.animation.setStartValue(0.)
        card.animation.setEndValue(1.)
        card.animation.start()
        card.expiry = QTimer(card)
        card.expiry.setSingleShot(True)
        card.expiry.timeout.connect(lambda: self.dismiss(card))
        card.expiry.start(12000)
        self.stack.show()
        self._position()
        self.stack.raise_()

    def dismiss(self, card):
        if card not in self.cards:
            return
        self.cards.remove(card)
        card.expiry.stop()
        self.layout.removeWidget(card)
        card.hide()
        card.deleteLater()
        if not self.cards:
            self.stack.hide()
        else:
            self._position()

    def _position(self):
        self.stack.setFixedWidth(min(410, self.window.width()-32))
        for card in self.cards:
            card.setFixedWidth(self.stack.width())
            height = max(160, card.layout().totalHeightForWidth(self.stack.width()))
            card.setFixedHeight(height)
        height = sum(card.height() for card in self.cards) + 10*max(0, len(self.cards)-1)
        self.stack.setFixedHeight(max(1, height))
        self.layout.activate()
        self.stack.move(self.window.width()-self.stack.width()-20, 62)

    def eventFilter(self, watched, event):
        if watched is self.window and event.type() == QEvent.Type.Resize:
            self._position()
        return False

    def show_history(self):
        if self.dialog is None:
            self.dialog = QDialog(self.window)
            self.dialog.setWindowTitle('Optiflow alerts')
            self.dialog.resize(490, 610)
            layout = QVBoxLayout(self.dialog)
            title = QLabel('Recent alerts')
            title.setStyleSheet('font-size: 22px; font-weight: 600; padding: 8px;')
            layout.addWidget(title)
            note = QLabel('This session • Latest 100 alerts')
            note.setStyleSheet('color: #93a5bb; padding: 0 8px 8px;')
            layout.addWidget(note)
            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(True)
            layout.addWidget(self.scroll)
        self._fill_history()
        self.dialog.show()
        self.dialog.raise_()

    def _fill_history(self):
        self.unread = 0
        self.button.setText('Alerts')
        content = QWidget()
        layout = QVBoxLayout(content)
        if not self.history:
            empty = QLabel('All clear. New accident and violation alerts will appear here.')
            empty.setWordWrap(True)
            layout.addWidget(empty)
        for notification in self.history:
            card = AlertCard(notification)
            card.opened.connect(self._open_history_item)
            card.dismissed.connect(lambda card: card.hide())
            layout.addWidget(card)
        layout.addStretch()
        self.scroll.setWidget(content)

    def _open_history_item(self, notification):
        self.dialog.hide()
        self.open_requested.emit(notification)

    def stop(self):
        self.audio.stop()
        for card in list(self.cards):
            self.dismiss(card)
        if self.dialog:
            self.dialog.close()
