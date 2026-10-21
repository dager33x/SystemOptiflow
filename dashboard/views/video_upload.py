"""Assign and validate videos for one or all four camera panels."""
from pathlib import Path

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QGridLayout,
    QLabel, QLineEdit, QPushButton, QVBoxLayout)

from dashboard.services.video_sources import LANE_NAMES, VIDEO_FILTER, validate_video_sources


class VideoUploadDialog(QDialog):
    def __init__(self, runner, parent=None, lanes=range(4)):
        super().__init__(parent)
        self.runner = runner
        self.selected_sources = {}
        self._closed = False
        self.setWindowTitle('Upload camera videos')
        self.resize(700, 300)
        layout = QVBoxLayout(self)
        note = QLabel('Choose a local video for each camera you want to change.\n'
                      'Unselected cameras keep their current source. Videos play and loop automatically.')
        note.setWordWrap(True)
        layout.addWidget(note)
        grid = QGridLayout()
        self.paths = {}
        self.controls = []
        for row, lane in enumerate(lanes):
            grid.addWidget(QLabel(f'{LANE_NAMES[lane]} camera'), row, 0)
            field = QLineEdit()
            field.setReadOnly(True)
            field.setPlaceholderText('Keep current source')
            field.setAccessibleName(f'{LANE_NAMES[lane]} video file')
            self.paths[lane] = field
            grid.addWidget(field, row, 1)
            browse = QPushButton('Choose video…')
            browse.clicked.connect(lambda checked=False, lane=lane: self._browse(lane))
            grid.addWidget(browse, row, 2)
            clear = QPushButton('Clear')
            clear.setToolTip('Keep this camera’s current source')
            clear.clicked.connect(field.clear)
            grid.addWidget(clear, row, 3)
            self.controls.extend((browse, clear))
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        self.message = QLabel('Files stay on this computer. AI detection uses the selected footage.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.load_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.load_button.setText('Load videos')
        self.buttons.accepted.connect(self._load)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.finished.connect(self._finished)

    def _browse(self, lane):
        path, _ = QFileDialog.getOpenFileName(self, f'Choose {LANE_NAMES[lane]} camera video',
                                             self.paths[lane].text(), VIDEO_FILTER)
        if path:
            self.paths[lane].setText(path)
            self.paths[lane].setToolTip(path)
            self.message.setText(f'{LANE_NAMES[lane]}: {Path(path).name} selected. Click Load videos to start.')

    def _load(self):
        sources = {lane: field.text() for lane, field in self.paths.items() if field.text()}
        if not sources:
            self.message.setText('Choose at least one video before loading.')
            return
        self.load_button.setEnabled(False)
        for control in self.controls:
            control.setEnabled(False)
        self.message.setText('Checking that each video can play…')
        self.runner.submit(lambda: validate_video_sources(sources), self._validated)

    def _validated(self, sources, error):
        if self._closed:
            return
        self.load_button.setEnabled(True)
        for control in self.controls:
            control.setEnabled(True)
        if error:
            self.message.setText(f'{error}\nYour current camera sources have been kept.')
            return
        self.selected_sources = sources
        self.accept()

    def _finished(self, result):
        self._closed = True
