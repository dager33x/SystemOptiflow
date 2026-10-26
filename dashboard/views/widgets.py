"""Qt widgets only. Workers never access these objects."""
import math
import time
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QPushButton, QComboBox,
    QSpinBox, QCheckBox, QVBoxLayout, QHBoxLayout, QGridLayout, QInputDialog, QSizePolicy,
)

from dashboard.models.dashboard import DIRECTIONS, active_detections, live_detections
from dashboard.services.accident_display import AccidentEvidenceDisplay
from dashboard.models.stop_line import StopLine
from dashboard.models.detection.vehicle_classes import count_queue_vehicles
from dashboard.services.video_sources import is_video_source

COLORS = {'RED': '#ff3238', 'YELLOW': '#ffcf33', 'GREEN': '#00d084', 'OFF': '#8796a8'}
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
        self.message = 'Off'
        self.frame_updates = 0
        self.stop_line = None
        self.signal = 'RED'
        self.evidence_age = None
        self.evidence_image = QImage()
        self.live_detections = self.evidence_detections = ()
        self.evidence_token = None
        self._evidence_frame = QImage()
        self.accident_display = AccidentEvidenceDisplay()

    def present(self, lane, now, show_boxes):
        self.stop_line = lane.stop_line if lane.source != 'simulation' else None
        self.signal = lane.signal
        packet = lane.frame
        self.evidence_age = None
        self.evidence_image = QImage()
        self.live_detections = self.evidence_detections = ()
        if packet is None or now - packet.captured_at > 1:
            self.image = QImage()
            self.token = None
            self.message = lane.status if packet is None else 'No fresh frames'
            self.detections = ()
        else:
            evidence_packet = self.accident_display.present(lane, now) if show_boxes else None
            learned = evidence_packet.detections if evidence_packet is not None else ()
            traffic = ()
            if show_boxes and lane.source != 'simulation':
                traffic = live_detections(lane, now)
                if lane.live_result is None and lane.result is not None and now-lane.result.captured_at <= .5:
                    traffic = tuple(d for d in active_detections(lane, now)
                                    if d.get('class_name') not in ('possible_accident', 'possible_jaywalking'))
            self.live_detections = traffic
            if learned:
                self.evidence_detections = learned
            if evidence_packet is not None and self.evidence_detections and evidence_packet.frame is not None:
                # Preserve continuous live video. Delayed boxes belong to an
                # evidence inset, never a replacement for the camera frame.
                evidence_token = (evidence_packet.generation, evidence_packet.sequence, id(evidence_packet))
                if evidence_token != self.evidence_token:
                    evidence = evidence_packet.frame
                    h, w = evidence.shape[:2]
                    self._evidence_frame = QImage(evidence.data, w, h, evidence.strides[0], QImage.Format.Format_BGR888).copy()
                    self.evidence_token = evidence_token
                self.evidence_image = self._evidence_frame
                self.evidence_age = now-evidence_packet.captured_at
            token = (packet.generation, packet.sequence)
            if token != self.token:
                frame = packet.frame
                h, w = frame.shape[:2]
                # Copy gives Qt independent ownership after NumPy packet replacement.
                self.image = QImage(frame.data, w, h, frame.strides[0], QImage.Format.Format_BGR888).copy()
                self.token = token
                self.frame_updates += 1
            self.detections = self.live_detections + self.evidence_detections
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor('#000000'))
        if self.image.isNull():
            painter.setPen(QColor('#93a5bb'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        # Fill the viewport without stretching vehicles. Center-crop excess
        # image edges and use the same transform for every camera overlay.
        # Portrait clips must retain the full road scene: filling a landscape
        # card would otherwise cut off vehicles near the top of the image.
        scale_fn = min if self.image.height() > self.image.width() else max
        scale = scale_fn(self.width() / self.image.width(), self.height() / self.image.height())
        width, height = self.image.width() * scale, self.image.height() * scale
        x, y = (self.width() - width) / 2, (self.height() - height) / 2
        painter.drawImage(QRectF(x, y, width, height), self.image)
        if self.stop_line is not None:
            line = self.stop_line
            first, second = line.endpoints((self.image.height(), self.image.width()))
            lx, ly = x + first[0]*scale, y + first[1]*scale
            rx, ry = x + second[0]*scale, y + second[1]*scale
            color = QColor(COLORS.get(self.signal, '#ff3238'))
            painter.setPen(QPen(QColor('#070d15'), 6))
            painter.drawLine(int(lx), int(ly), int(rx), int(ry))
            painter.setPen(QPen(color, 3, Qt.PenStyle.DashLine))
            painter.drawLine(int(lx), int(ly), int(rx), int(ry))
            # Arrow points from the approach side into the restricted side.
            cx, cy = (lx+rx)/2, (ly+ry)/2
            delta = 16 if line.direction in ('down', 'right') else -16
            if line.vertical:
                painter.drawLine(int(cx-delta), int(cy), int(cx+delta), int(cy))
                for offset in (-5, 5):
                    painter.drawLine(int(cx+delta), int(cy), int(cx+delta*.6), int(cy+offset))
                    if line.direction == 'both_vertical':
                        painter.drawLine(int(cx-delta), int(cy), int(cx-delta*.6), int(cy+offset))
            else:
                painter.drawLine(int(cx), int(cy-delta), int(cx), int(cy+delta))
                for offset in (-5, 5):
                    painter.drawLine(int(cx), int(cy+delta), int(cx+offset), int(cy+delta*.6))
                    if line.direction == 'both':
                        painter.drawLine(int(cx), int(cy-delta), int(cx+offset), int(cy-delta*.6))
            label = 'STOP LINE / APP ' + self.signal
            metrics = painter.fontMetrics()
            label_width = metrics.horizontalAdvance(label) + 12
            if 0 <= ly <= self.height():
                label_x = max(0, min(lx, self.width()-label_width))
                label_y = max(0, ly-metrics.height()-12)
                painter.fillRect(QRectF(label_x, label_y, label_width, metrics.height()+6), QColor('#070d15'))
                painter.setPen(color)
                painter.drawText(int(label_x+6), int(label_y+metrics.ascent()+3), label)
        painter.save()
        self._draw_boxes(painter, self.live_detections, x, y, scale)
        if not self.evidence_image.isNull():
            scale = min(min(240, self.width()*.4)/self.evidence_image.width(),
                        self.height()*.4/self.evidence_image.height())
            width, height = self.evidence_image.width()*scale, self.evidence_image.height()*scale
            x, y = self.width()-width-8, self.height()-height-32
            inset = QRectF(x, y, width, height)
            painter.fillRect(inset.adjusted(-2, -2, 2, 2), QColor('#ffb347'))
            painter.drawImage(inset, self.evidence_image)
            painter.setClipRect(inset)
            self._draw_boxes(painter, self.evidence_detections, x, y, scale)
        painter.restore()
        if self.evidence_age is not None:
            label = f'Possible accident • {self.evidence_age:.1f}s ago'
            metrics = painter.fontMetrics()
            painter.fillRect(QRectF(4, self.height()-metrics.height()-12,
                                    metrics.horizontalAdvance(label)+12, metrics.height()+8), QColor('#070d15'))
            painter.setPen(QColor('#ffb347'))
            painter.drawText(10, self.height()-8, label)

    def _draw_boxes(self, painter, detections, x, y, scale):
        for det in detections:
            accident = det['class_name'] == 'possible_accident'
            emergency = det['class_name'] == 'emergency_vehicle'
            violation = det['class_name'] == 'possible_jaywalking'
            painter.setPen(QPen(QColor('#ffb347' if accident else '#ff555b' if violation else
                                      '#5daaff' if emergency else '#34d399'), 2))
            x1, y1, x2, y2 = det['bbox']
            painter.drawRect(QRectF(x + x1 * scale, y + y1 * scale, (x2-x1)*scale, (y2-y1)*scale))
            name = ('Possible accident' if accident else 'Possible jaywalking' if violation else
                    'Emergency vehicle' if emergency else det['class_name'])
            label = f'{name} {det.get("confidence", 0):.0%}'
            metrics = painter.fontMetrics()
            label = metrics.elidedText(label, Qt.TextElideMode.ElideRight, max(1, self.width()-12))
            label_width = metrics.horizontalAdvance(label)+8
            label_x = max(2, min(x+x1*scale, self.width()-label_width-2))
            label_y = max(2, min(y+y1*scale-metrics.height()-6, self.height()-metrics.height()-6))
            painter.fillRect(QRectF(label_x, label_y, label_width, metrics.height()+4), QColor('#070d15'))
            painter.drawText(int(label_x+4), int(label_y+metrics.ascent()+2), label)


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
    video_upload_requested = Signal(int)
    settings_requested = Signal(int)
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
        self.source.addItem('Off', 'off')
        self.source.addItem('Simulated road', 'simulation')
        for index in range(5):
            self.source.addItem(f'PC / USB camera {index}', index)
        self.source.setToolTip('Built-in PC webcams and USB cameras use numbers 0–4. The first camera is usually 0.')
        for index in range(5, 9):
            self.source.addItem(f'Remote camera {index}', index)
        self.source.currentIndexChanged.connect(self._select_source)
        source_row.addWidget(self.source, 1)
        self.video_button = QPushButton('Upload video…')
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
        video_row = QHBoxLayout()
        self.source_label = QLabel('Off')
        self.source_label.setObjectName('muted')
        self.source_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        video_row.addWidget(self.source_label, 1)
        self.calibrate_button = QPushButton('Stop line…')
        self.calibrate_button.setToolTip('Set the road boundary and vehicle travel direction for red-light detection')
        self.calibrate_button.clicked.connect(lambda: self.settings_requested.emit(self.lane_id))
        video_row.addWidget(self.calibrate_button)
        self.upload_button = QPushButton('Upload video…')
        self.upload_button.setToolTip(f'Play a local video in {LANE_NAMES[lane_id]}')
        self.upload_button.clicked.connect(self._choose_video)
        video_row.addWidget(self.upload_button)
        self.upload_button.hide()
        layout.addLayout(video_row)
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
                ('Line position', self.line_height, 5, 95, 80),
                ('Start', self.line_left, 0, 99, 25),
                ('End', self.line_right, 1, 100, 75)):
            line_layout.addWidget(QLabel(caption))
            spin.setRange(minimum, maximum)
            spin.setSuffix('%')
            spin.setValue(value)
            line_layout.addWidget(spin)
            spin.valueChanged.connect(self._change_stop_line)
        self.line_direction = QComboBox()
        self.line_direction.addItem('Horizontal: either direction', 'both')
        self.line_direction.addItem('Vertical: either direction', 'both_vertical')
        self.line_direction.addItem('Travel down', 'down')
        self.line_direction.addItem('Travel up', 'up')
        self.line_direction.addItem('Travel right', 'right')
        self.line_direction.addItem('Travel left', 'left')
        self.line_direction.currentIndexChanged.connect(self._change_stop_line)
        line_layout.addWidget(self.line_direction)
        self.line_controls.setToolTip('Place the line on the road stop boundary. Left/right travel uses a vertical line. A tracked vehicle must cross in the selected direction while Optiflow\'s application signal is red; the light in the footage is not read.')
        self.line_controls.setEnabled(False)
        settings_layout.addWidget(self.line_controls)
        self.telemetry = QLabel('Starting…')
        self.telemetry.setObjectName('muted')
        layout.addWidget(self.telemetry)
        self.telemetry.hide()
        self.settings_widget.hide()
        self._fps_start, self._fps_frames, self.fps = time.monotonic(), 0, 0.0
        self._ai_token, self._ai_captured_at, self.ai_interval = None, None, 0.

    def _select_source(self):
        source = self.source.currentData()
        simulation = source == 'simulation'
        self.source_label.setText(self.source.currentText())
        self.source_label.setToolTip(str(source))
        self.reconnect_button.setText('Restart video' if is_video_source(source) else 'Reconnect')
        self.reconnect_button.setToolTip('Play this video from the beginning' if is_video_source(source)
                                        else 'Reopen this camera or stream')
        self.line_controls.setEnabled(source not in ('off', 'simulation'))
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
        self.video_upload_requested.emit(self.lane_id)

    def select_source(self, source):
        """Select a validated/restored source; reselecting a video restarts it."""
        blocked = self.source.blockSignals(True)
        index = self.source.findData(source)
        if index < 0:
            label = f'Video: {Path(source).name}' if is_video_source(source) else 'Network stream'
            self.source.addItem(label, source)
            index = self.source.count() - 1
        self.source.setCurrentIndex(index)
        self.source.blockSignals(blocked)
        self._select_source()

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
        self.timer.setText('—' if lane.signal == 'OFF' else f'{max(0, math.ceil(lane.remaining))}s')
        self.count.setText(str(count_queue_vehicles(active_detections(lane, now))))
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
            token = (lane.result.generation, lane.result.sequence)
            if token != self._ai_token:
                if self._ai_token and self._ai_token[0] == token[0]:
                    self.ai_interval = lane.result.captured_at-self._ai_captured_at
                self._ai_token, self._ai_captured_at = token, lane.result.captured_at
            rate = f' • {1/self.ai_interval:.1f} AI updates/s' if self.ai_interval > 0 else ''
            live = bool(live_detections(lane, now))
            detail = (f'Live boxes • model {age:.1f}s ago{rate}' if live else
                      f'AI {age:.1f}s ago{rate}' if now-lane.result.completed_at <= 2 else
                      'Waiting for a fresh vehicle detection')
        self.telemetry.setText(f'{lane.status}  •  {self.fps:.0f} display FPS  •  {detail}')
