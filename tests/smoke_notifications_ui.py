"""Exercise worker delivery, toast/history UI, and local audio loading offscreen."""
import os
from pathlib import Path
import sys
from threading import Thread
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtMultimedia import QSoundEffect
from dashboard.controllers.dashboard_controller import DashboardController
from dashboard.models.notification import Notification
from dashboard.views.main_window import DashboardWindow

app = QApplication([])
for font in ('segoeui.ttf', 'segoeuib.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
controller = DashboardController()
window = DashboardWindow(controller, autostart=False)
window.timer.stop()
window.resize(1300, 860)
window.sound_alerts.setChecked(False)
window.show()
app.processEvents()
center = window.notifications
events = [Notification('violation', 0, 'Red-light violation', 'A vehicle crossed the stop line during a red signal.'),
          Notification('incident', 2, 'Possible collision', 'Vehicles made apparent contact and stopped. Review the camera footage; this is not a confirmed crash.')]
worker = Thread(target=lambda: [controller.store.notify(event) for event in events])
worker.start()
worker.join()
window.refresh()
QTest.qWait(260)
assert len(center.cards) == 2
assert len(center.history) == 2
assert center.unread == 2
assert window.alerts_button.text() == 'Alerts (2)'
assert center.stack.isVisible()
assert all(card.height() >= 160 for card in center.cards)
window.refresh()
assert len(center.history) == 2, 'Drained events must not replay'
window.grab().save(str(root / 'screenshots' / 'notification-preview.png'))
window.alerts_button.click()
assert center.dialog.isVisible() and center.unread == 0
center.dialog.hide()
window.popup_alerts.setChecked(False)
assert not center.cards
controller.store.notify(events[0])
window.refresh()
assert len(center.history) == 3 and not center.cards
window.popup_alerts.setChecked(True)
for _ in range(6):
    controller.store.notify(events[0])
window.refresh()
assert len(center.cards) == 3
center.cards[-1].expiry.timeout.emit()
assert len(center.cards) == 2
center._open_history_item(Notification('incident', 0, 'Simulation', 'Test', True))
assert window.stack.currentWidget() is window.pages['dashboard']

audio = center.audio
for _ in range(100):
    if all(effect.status() == QSoundEffect.Status.Ready for effect in audio.effects.values()):
        break
    QTest.qWait(30)
assert len(audio.effects) == 2
assert all(effect.status() == QSoundEffect.Status.Ready for effect in audio.effects.values()), audio.status
audio.configure(True, .1)
with patch.object(audio, '_play') as play:
    assert audio.play('incident')
    assert not audio.play('violation'), 'A burst should not layer repeated chimes'
    assert play.call_count == 1
    audio.configure(False, .1)
    assert not audio.play('incident', force=True)
    audio.configure(True, 0)
    assert not audio.play('violation', force=True)
if '--play' in sys.argv:
    audio.configure(True, .15)
    audio.play('incident', force=True)
    QTest.qWait(100)
    assert audio.effects['incident'].isPlaying()
    QTest.qWait(1800)
    assert not audio.effects['incident'].isPlaying()
window.close()
assert not center.cards and not center.stack.isVisible()
print('Worker delivery, visible toasts, history, dismissal, mute/volume, burst limiting and both WAV audio loads passed.')
