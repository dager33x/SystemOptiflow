# models/vehicle.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Vehicle:
    vehicle_id: Optional[str]
    vehicle_type: str
    lane: int
    detected_at: datetime
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Vehicle':
        return cls(
            vehicle_id=data.get('vehicle_id'),
            vehicle_type=data.get('vehicle_type', 'Unknown'),
            lane=data.get('lane', 1),
            detected_at=datetime.fromisoformat(data.get('detected_at')) if data.get('detected_at') else datetime.now()
        )