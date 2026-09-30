"""Qt widgets only. Workers never access these objects."""
import math
import time

from PySide6.QtCore import Qt, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QPushButton, QComboBox,
    QSpinBox, QCheckBox, QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog, QInputDialog,
)

from dashboard.models.dashboard import DIRECTIONS, active_detections
from dashboard.models.stop_line import StopLine

COLORS = {'RED': '#ff3238', 'YELLOW': '#ffcf33', 'GREEN': '#00d084'}
LANE_NAMES = ('North Gate', 'South Junction', 'East Portal', 'West Avenue')
STYLE = '''
QWidget { background: #0b111c; color: #e6edf5; font-family: "Segoe UI"; font-size: 12px; }
QFrame#card { background: #131e2d; border: 1px solid #25354b; border-radius: 12px; }
QFrame#card QLabel { background: transparent; }
QLabel#muted { color: #93a5bb; }
QLabel#title { font-size: 23px; font-weight: 700; }
QLabel#cardTitle { font-size: 15px; font-weight: 700; }
QComboBox, QSpinBox { background: #1c2b3f; border: 1px solid #34485f; border-radius: 5px; padding: 5px; }
QComboBox QAbstractItemView { background: #172537; selection-background-color: #285f84; }
QPushButton { background: #1c334a; border: 1px solid #33546f; border-radius: 6px; padding: 8px 14px; }
QPushButton:hover { background: #294b68; }
QPushButton:checked { background: #17604e; border-color: #34d399; }
QCheckBox { spacing: 5px; }
QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #627991; border-radius: 3px; background: #172537; }
QCheckBox::indicator:checked { background: #34d399; border-color: #34d399; }
'''


class VideoCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(230, 130)
        self.image = QImage()
        self.token = None
        self.detections = ()
        self.message = 'Starting…'
        self.frame_updates = 0
        self.stop_line = None
        self.signal = 'RED'

    def present(self, lane, now, show_boxes):
        self.stop_line = lane.stop_line if lane.source != 'simulation' else None
        self.signal = lane.signal
        packet = lane.frame
        if packet is None or now - packet.captured_at > 1:
            self.image = QImage()
            self.token = None
            self.message = lane.status if packet is None else 'No fresh frames'
            self.detections = ()
        else:
            token = (packet.generation, packet.sequence)
            if token != self.token:
                frame = packet.frame
                h, w = frame.shape[:2]
                # Copy gives Qt independent ownership after NumPy packet replacement.
                self.image = QImage(frame.data, w, h, frame.strides[0], QImage.Format.Format_BGR888).copy()
                self.token = token
                self.frame_updates += 1
            self.detections = active_detections(lane, now) if show_boxes and lane.source != 'simulation' else ()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor('#070d15'))
        if self.image.isNull():
            painter.setPen(QColor('#93a5bb'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        # Fill the viewport without stretching vehicles. Center-crop excess
        # image edges and use the same transform for every camera overlay.
        scale = max(self.width() / self.image.width(), self.height() / self.image.height())
        width, height = self.image.width() * scale, self.image.height() * scale
        x, y = (self.width() - width) / 2, (self.height() - height) / 2
        painter.drawImage(QRectF(x, y, width, height), self.image)
        if self.stop_line is not None:
            line = self.stop_line
            lx, rx = x + width*line.left, x + width*line.right
            ly = y + height*line.height
            color = QColor(COLORS.get(self.signal, '#ff3238'))
            painter.setPen(QPen(QColor('#070d15'), 6))
            painter.drawLine(int(lx), int(ly), int(rx), int(ly))
            painter.setPen(QPen(color, 3, Qt.PenStyle.DashLine))
            painter.drawLine(int(lx), int(ly), int(rx), int(ly))
            # Arrow points from the approach side into the restricted side.
            cx = (lx+rx)/2
            delta = 16 if line.direction == 'down' else -16
            painter.drawLine(int(cx), int(ly-delta), int(cx), int(ly+delta))
            for dx in (-5, 5):
                painter.drawLine(int(cx), int(ly+delta), int(cx+dx), int(ly+delta*.6))
            label = 'STOP LINE / ' + self.signal
            metrics = painter.fontMetrics()
            label_width = metrics.horizontalAdvance(label) + 12
            if 0 <= ly <= self.height():
                label_x = max(0, min(lx, self.width()-label_width))
                label_y = max(0, ly-metrics.height()-12)
                painter.fillRect(QRectF(label_x, label_y, label_width, metrics.height()+6), QColor('#070d15'))
                painter.setPen(color)
                painter.drawText(int(label_x+6), int(label_y+metrics.ascent()+3), label)
        painter.setPen(QPen(QColor('#34d399'), 2))
        for det in self.detections:
            x1, y1, x2, y2 = det['bbox']
            painter.drawRect(QRectF(x + x1 * scale, y + y1 * scale, (x2-x1)*scale, (y2-y1)*scale))
            painter.drawText(int(x + x1 * scale), max(int(y + y1 * scale - 5), 15),
                             f'{det["class_name"]} {det.get("confidence", 0):.0%}')


class SignalLamp(QWidget):
    def __init__(self):
        super().__init__()
        self.signal = 'RED'
        self.setFixedSize(44, 116)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#070d15'))
        painter.drawRoundedRect(self.rect(), 12, 12)
        for i, state in enumerate(('RED', 'YELLOW', 'GREEN')):
            painter.setBrush(QColor(COLORS[state] if state == self.signal else '#27303d'))
            painter.drawEllipse(9, 10 + i * 34, 26, 26)


class CameraCard(QFrame):
    stop_line_changed = Signal(int, object)
    source_changed = Signal(int, object)
    simulation_changed = Signal(int, int, bool)
    events_changed = Signal(int, bool, bool)

    def __init__(self, lane_id, density):
        super().__init__()
        self.lane_id = lane_id
        self.setObjectName('card')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)
        title_row = QHBoxLayout()
        title = QLabel(f'{("▲", "▼", "▸", "◂")[lane_id]}  {LANE_NAMES[lane_id].upper()}')
        title.setObjectName('cardTitle')
        title.setStyleSheet('color: #3987ff; font-weight: 700;')
        title_row.addWidget(title)
        title_row.addStretch()
        self.badge = QLabel('RED')
        title_row.addWidget(self.badge)
        layout.addLayout(title_row)
        source_row = QHBoxLayout()
        self.source = QComboBox()
        self.source.addItem('Simulated road', 'simulation')
        for index in range(5):
            self.source.addItem(f'USB camera {index}', index)
        for index in range(5, 9):
            self.source.addItem(f'Remote camera {index}', index)
        self.source.currentIndexChanged.connect(self._select_source)
        source_row.addWidget(self.source, 1)
        self.video_button = QPushButton('Video file…')
        self.video_button.clicked.connect(self._choose_video)
        source_row.addWidget(self.video_button)
        stream_button = QPushButton('Stream URL…')
        stream_button.clicked.connect(self._choose_stream)
        source_row.addWidget(stream_button)
        self.reconnect_button = QPushButton('Reconnect')
        self.reconnect_button.setToolTip('Reopen this camera or stream without restarting the dashboard')
        self.reconnect_button.clicked.connect(self._select_source)
        source_row.addWidget(self.reconnect_button)
        self.settings_widget = QWidget()
        settings_layout = QVBoxLayout(self.settings_widget)
        settings_layout.addWidget(QLabel(LANE_NAMES[lane_id]))
        settings_layout.addLayout(source_row)
        body = QHBoxLayout()
        self.canvas = VideoCanvas()
        body.addWidget(self.canvas, 1)
        signal_panel = QFrame()
        signal_panel.setObjectName('signalPanel')
        signal_panel.setFixedWidth(94)
        signal_column = QVBoxLayout(signal_panel)
        signal_column.addStretch()
        label = QLabel('SIGNAL')
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setObjectName('muted')
        signal_column.addWidget(label)
        self.lamp = SignalLamp()
        signal_column.addWidget(self.lamp, alignment=Qt.AlignmentFlag.AlignHCenter)
        label = QLabel('TIMER')
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setObjectName('muted')
        signal_column.addWidget(label)
        self.timer = QLabel('--s')
        self.timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer.setStyleSheet('font: 700 23px "Consolas";')
        signal_column.addWidget(self.timer)
        label = QLabel('VEHICLES')
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setObjectName('muted')
        signal_column.addWidget(label)
        self.count = QLabel('0 vehicles')
        self.count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        signal_column.addWidget(self.count)
        self.signal_text = QLabel('RED')
        self.signal_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        signal_column.addWidget(self.signal_text)
        signal_column.addStretch()
        body.addWidget(signal_panel)
        layout.addLayout(body, 1)
        controls = QHBoxLayout()
        self.density_label = QLabel('Simulated vehicles')
        controls.addWidget(self.density_label)
        self.density = QSpinBox()
        self.density.setRange(0, 30)
        self.density.setValue(density)
        self.density.valueChanged.connect(self._change_simulation)
        controls.addWidget(self.density)
        self.emergency = QCheckBox('Emergency vehicle')
        self.emergency.toggled.connect(self._change_simulation)
        controls.addWidget(self.emergency)
        controls.addStretch()
        settings_layout.addLayout(controls)
        event_controls = QHBoxLayout()
        self.accident = QCheckBox('Simulate accident')
        self.violation = QCheckBox('Simulate pedestrian violation')
        for control in (self.accident, self.violation):
            event_controls.addWidget(control)
            control.toggled.connect(lambda: self.events_changed.emit(self.lane_id, self.accident.isChecked(), self.violation.isChecked()))
        event_controls.addStretch()
        settings_layout.addLayout(event_controls)
        self.line_controls = QWidget()
        line_layout = QHBoxLayout(self.line_controls)
        line_layout.setContentsMargins(0, 0, 0, 0)
        self.line_height, self.line_left, self.line_right = QSpinBox(), QSpinBox(), QSpinBox()
        for caption, spin, minimum, maximum, value in (
                ('Stop line height', self.line_height, 5, 95, 80),
                ('Left', self.line_left, 0, 99, 25),
                ('Right', self.line_right, 1, 100, 75)):
            line_layout.addWidget(QLabel(caption))
            spin.setRange(minimum, maximum)
            spin.setSuffix('%')
            spin.setValue(value)
            line_layout.addWidget(spin)
            spin.valueChanged.connect(self._change_stop_line)
        self.line_direction = QComboBox()
        self.line_direction.addItem('Travel down', 'down')
        self.line_direction.addItem('Travel up', 'up')
        self.line_direction.currentIndexChanged.connect(self._change_stop_line)
        line_layout.addWidget(self.line_direction)
        self.line_controls.setToolTip('Place the line on the road stop boundary. Direction is the vehicle travel direction in the image. A vehicle bottom-center must cross it during red.')
        self.line_controls.setEnabled(False)
        settings_layout.addWidget(self.line_controls)
        self.telemetry = QLabel('Starting…')
        self.telemetry.setObjectName('muted')
        settings_layout.addWidget(self.telemetry)
        self.settings_widget.hide()
        self._fps_start, self._fps_frames, self.fps = time.monotonic(), 0, 0.0

    def _select_source(self):
        source = self.source.currentData()
        simulation = source == 'simulation'
        self.line_controls.setEnabled(not simulation)
        for widget in (self.density_label, self.density, self.emergency, self.accident, self.violation):
            widget.setEnabled(simulation)
        self.source_changed.emit(self.lane_id, source)

    def set_stop_line(self, line):
        for spin, value in ((self.line_height, line.height), (self.line_left, line.left),
                            (self.line_right, line.right)):
            spin.blockSignals(True)
            spin.setValue(round(value*100))
            spin.blockSignals(False)
        self.line_direction.blockSignals(True)
        self.line_direction.setCurrentIndex(self.line_direction.findData(line.direction))
        self.line_direction.blockSignals(False)

    def _change_stop_line(self):
        if self.line_left.value() >= self.line_right.value():
            self.line_right.setValue(self.line_left.value()+1)
        line = StopLine(self.line_height.value()/100, self.line_left.value()/100,
                        self.line_right.value()/100, self.line_direction.currentData())
        self.stop_line_changed.emit(self.lane_id, line)

    def _choose_video(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose traffic video', '', 'Videos (*.mp4 *.avi *.mkv *.mov);;All files (*)')
        if path:
            self.source.addItem(f'Video: {path.replace(chr(92), "/").rsplit("/", 1)[-1]}', path)
            self.source.setCurrentIndex(self.source.count() - 1)

    def _choose_stream(self):
        source, accepted = QInputDialog.getText(self, 'Network camera', 'RTSP or HTTP stream URL')
        if accepted and source.strip().startswith(('rtsp://', 'http://', 'https://')):
            self.source.addItem('Network stream', source.strip())
            self.source.setCurrentIndex(self.source.count() - 1)

    def _change_simulation(self):
        self.simulation_changed.emit(self.lane_id, self.density.value(), self.emergency.isChecked())

    def present(self, lane, now, show_boxes):
        self.canvas.present(lane, now, show_boxes)
        self.badge.setText(lane.signal)
        self.badge.setStyleSheet(f'color: {COLORS[lane.signal]}; font-weight: 700;')
        self.lamp.signal = lane.signal
        self.lamp.update()
        self.timer.setText(f'{max(0, math.ceil(lane.remaining))}s')
        self.count.setText(str(lane.vehicles))
        self.count.setStyleSheet('font-size: 24px; font-weight: 700;')
        self.timer.setStyleSheet(f'color: {COLORS[lane.signal]}; font: 700 22px "Consolas";')
        self.signal_text.setText(lane.signal)
        self.signal_text.setStyleSheet(f'color: {COLORS[lane.signal]}; font-weight: 700;')
        self.badge.setStyleSheet(f'color: {COLORS[lane.signal]}; background: #101e24; border-radius: 7px; padding: 6px 16px; font-weight: 700;')
        if now - self._fps_start >= 1:
            self.fps = (self.canvas.frame_updates - self._fps_frames) / (now - self._fps_start)
            self._fps_start, self._fps_frames = now, self.canvas.frame_updates
        if lane.source == 'simulation':
            detail = 'Known simulated counts'
        elif lane.result is None:
            detail = 'Waiting for detection'
        else:
            age = now - lane.result.captured_at
            detail = f'AI age {age:.1f}s' if age <= 2 else 'AI stale — counts cleared'
        self.telemetry.setText(f'{lane.status}  •  {self.fps:.0f} display FPS  •  {detail}')
