"""Offscreen check of stop-line scaling, visibility, and calibration controls."""
import os
from pathlib import Path
import sys
import time
from dataclasses import replace

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

import numpy as np
import cv2
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from dashboard.models.dashboard import FramePacket, DetectionPacket, LaneState
from dashboard.models.stop_line import StopLine
from dashboard.views.widgets import VideoCanvas, CameraCard

app = QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
frame = np.full((360, 640, 3), 45, dtype=np.uint8)
for x in (210, 430):
    for y in range(0, 360, 60):
        cv2.rectangle(frame, (x, y), (x+4, y+30), (150, 150, 150), -1)
cv2.rectangle(frame, (275, 150), (355, 240), (90, 110, 120), -1)
now = time.monotonic()
lane = LaneState(source=0, frame=FramePacket(0, 1, now, frame), signal='RED')
canvas = VideoCanvas()
canvas.resize(640, 480)
canvas.present(lane, now, False)
canvas.show()
app.processEvents()
image = canvas.grab().toImage()
# Fill scale is 480/360; horizontal excess is cropped, with no black bars.
assert any(image.pixelColor(x, 384).red() > 220 for x in range(120, 180))
for x, y in ((1, 1), (638, 1), (1, 478), (638, 478)):
    assert image.pixelColor(x, y).red() == 45, 'Video must reach every corner'
image.save(str(root / 'screenshots' / 'stop-line-preview.png'))
# Wider viewport crops vertically; overlays must follow that same transform.
canvas.resize(960, 360)
boxes = ({'bbox': (275, 150, 355, 240), 'class_name': 'car', 'confidence': .9},)
lane = replace(lane, result=DetectionPacket(0, 1, now, now, boxes, .1))
canvas.present(lane, now, True)
app.processEvents()
wide = canvas.grab().toImage()
assert wide.pixelColor(1, 1).red() == 45
assert wide.pixelColor(958, 358).red() == 45
assert any(wide.pixelColor(x, 342).red() > 220 for x in range(250, 290))
assert wide.pixelColor(412, 160).green() > 180, 'Vehicle box must follow cropped video coordinates'
canvas.present(replace(lane, source='simulation'), now, False)
app.processEvents()
assert canvas.stop_line is None
card = CameraCard(0, 8)
received = []
card.stop_line_changed.connect(lambda lane_id, line: received.append(line))
card.source.setCurrentIndex(card.source.findData(0))
assert card.line_controls.isEnabled()
card.line_height.setValue(65)
assert received[-1].height == .65
card.set_stop_line(StopLine(.7, .1, .9, 'up'))
assert card.line_direction.currentData() == 'up'
canvas.close()
card.close()
print('Video fills both viewport shapes; stop-line and vehicle-box alignment and calibration controls passed.')
