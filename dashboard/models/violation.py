# models/violation.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Violation:
    violation_id: Optional[str]
    vehicle_id: Optional[str]
    violation_type: str
    lane: int
    source: str
    timestamp: datetime
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Violation':
        return cls(
            violation_id=data.get('violation_id'),
            vehicle_id=data.get('vehicle_id'),
            violation_type=data.get('violation_type', 'Unknown'),
            lane=data.get('lane', 1),
            source=data.get('source', 'SYSTEM'),
            timestamp=datetime.fromisoformat(data.get('timestamp')) if data.get('timestamp') else datetime.now()
        )