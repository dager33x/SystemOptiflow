"""Small immutable alert passed from detection workers to the UI."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Notification:
    kind: str
    lane: int
    title: str
    message: str
    simulated: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def page(self):
        return 'incident_history' if self.kind == 'incident' else 'violation_logs'
