"""Nonblocking local chimes, with burst limiting and a Windows fallback."""
import logging
import sys
import time

from PySide6.QtCore import QObject, QUrl, Signal
from dashboard.utils.paths import get_resource_path

LOGGER = logging.getLogger(__name__)


class AlertAudio(QObject):
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = True
        self.volume = .55
        self.last_play = -float('inf')
        self.effects = {}
        self.pending = None
        self.status = 'Loading alert sounds...'
        try:
            from PySide6.QtMultimedia import QSoundEffect, QMediaDevices
            self.media = QMediaDevices(self)
            self.media.audioOutputsChanged.connect(self._device_changed)
            for kind in ('incident', 'violation'):
                effect = QSoundEffect(self)
                effect.setLoopCount(1)
                effect.setVolume(self.volume)
                effect.statusChanged.connect(self._loaded)
                self.effects[kind] = effect
                effect.setSource(QUrl.fromLocalFile(self.path(kind)))
        except ImportError:
            LOGGER.warning('Qt audio unavailable; using native Windows playback when possible')
            self.status = 'Native Windows alert sounds' if sys.platform == 'win32' else 'Audio unavailable'

    @staticmethod
    def path(kind):
        return get_resource_path(f'assets/sounds/{kind}.wav')

    def configure(self, enabled, volume):
        self.enabled = bool(enabled)
        self.volume = max(0., min(1., float(volume)))
        for effect in self.effects.values():
            effect.setVolume(self.volume)
        if not self.enabled or self.volume == 0:
            self.stop()

    def _set_status(self, message):
        self.status = message
        self.status_changed.emit(message)

    def _device_changed(self):
        from PySide6.QtMultimedia import QMediaDevices
        for effect in self.effects.values():
            effect.setAudioDevice(QMediaDevices.defaultAudioOutput())
        self._loaded()

    def _loaded(self):
        from PySide6.QtMultimedia import QSoundEffect
        if self.effects and all(effect.status() == QSoundEffect.Status.Ready for effect in self.effects.values()):
            self._set_status('Alert sounds ready')
        elif any(effect.status() == QSoundEffect.Status.Error for effect in self.effects.values()):
            self._set_status('Audio device unavailable; check your Windows sound output')
        if self.pending:
            effect = self.effects.get(self.pending)
            if effect and effect.status() in (QSoundEffect.Status.Ready, QSoundEffect.Status.Error):
                kind, self.pending = self.pending, None
                self._play(kind)

    def play(self, kind, *, force=False):
        if not self.enabled or self.volume == 0:
            return False
        now = time.monotonic()
        if not force and now-self.last_play < 2.5:
            return False
        self.last_play = now
        self._play(kind if kind in ('incident', 'violation') else 'violation')
        return True

    def _play(self, kind):
        if not self.enabled or self.volume == 0:
            return
        effect = self.effects.get(kind)
        if effect:
            from PySide6.QtMultimedia import QSoundEffect
            if effect.status() == QSoundEffect.Status.Loading:
                self.pending = kind
                return
            if effect.status() == QSoundEffect.Status.Ready:
                for other in self.effects.values():
                    other.stop()
                effect.play()
                return
        if sys.platform == 'win32':
            try:
                import winsound
                winsound.PlaySound(self.path(kind), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                self._set_status('Native playback uses Windows system volume')
                return
            except (RuntimeError, OSError):
                LOGGER.exception('Native alert sound failed')
        self._set_status('Cannot play alert sound; check your audio output')

    def stop(self):
        self.pending = None
        for effect in self.effects.values():
            effect.stop()
        if sys.platform == 'win32':
            import winsound
            winsound.PlaySound(None, 0)
