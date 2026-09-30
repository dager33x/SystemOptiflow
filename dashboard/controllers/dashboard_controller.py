"""Qt-facing coordinator; signal and detection algorithms stay in workers."""
from dashboard.models.dashboard import DashboardStore
from dashboard.services.workers import DashboardWorkers
from dashboard.models.stop_line import StopLine
from dashboard.models.notification import Notification


class DashboardController:
    def __init__(self, db=None, configured=False, current_user=None):
        self.store = DashboardStore()
        self.workers = DashboardWorkers(self.store)
        if db is not None:
            from dashboard.controllers.violation_controller import ViolationController
            from dashboard.controllers.accident_controller import AccidentController
            from dashboard.services.events import EventRecorder
            self.violations = ViolationController(db)
            self.accidents = AccidentController(db, current_user=current_user)
            self.workers.recorder = EventRecorder(self.violations, self.accidents, self.store.notify)
        if configured:
            from PySide6.QtCore import QSettings
            from dashboard.utils.app_config import SETTINGS
            saved = QSettings('Optiflow', 'Dashboard')
            for i, direction in enumerate(('north', 'south', 'east', 'west')):
                source = saved.value(f'source/{direction}', SETTINGS[f'camera_source_{direction}'])
                if source in ('Simulated', 'simulation'):
                    source = 'simulation'
                elif str(source).startswith('Camera '):
                    source = int(source.split()[-1])
                elif str(source).isdigit():
                    source = int(source)
                self.store.set_source(i, source)
                try:
                    self.store.set_stop_line(i, StopLine(
                        saved.value(f'stop_line/{i}/height', .8, type=float),
                        saved.value(f'stop_line/{i}/left', .25, type=float),
                        saved.value(f'stop_line/{i}/right', .75, type=float),
                        saved.value(f'stop_line/{i}/direction', 'down')))
                except (ValueError, TypeError):
                    self.store.set_stop_line(i, StopLine())
            self.store.set_ai(saved.value('ai_enabled', True, type=bool))

    def start(self):
        self.workers.start()

    def stop(self):
        self.workers.stop()

    def set_source(self, lane, source):
        self.store.set_source(lane, source)

    def set_simulation(self, lane, density, emergency):
        self.store.set_simulation(lane, density=density, emergency=emergency)

    def set_simulation_events(self, lane, accident, violation):
        previous = self.store.snapshot()[lane]
        self.store.set_simulation(lane, accident=accident, violation=violation)
        if previous.source != 'simulation':
            return
        for kind, active, old in (('incident', accident, previous.accident),
                                  ('violation', violation, previous.violation)):
            if active and not old:
                self.store.notify(Notification(kind, lane,
                    'Simulated collision' if kind == 'incident' else 'Simulated violation',
                    'Simulation only. No real incident or violation record is created.', True))
