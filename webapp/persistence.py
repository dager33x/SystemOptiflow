import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from utils.performance_monitor import timed_stage


class PersistenceService:
    """Persistence wrapper with Supabase-first behavior and local-file fallbacks."""

    def __init__(self, db):
        self.db = db
        self.logger = logging.getLogger(__name__)
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.evidence_dir = Path("assets") / "web_evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.bucket_name = os.getenv("SUPABASE_EVIDENCE_BUCKET", "evidence")

    def is_connected(self) -> bool:
        return bool(self.db and self.db.is_connected())

    def _json_path(self, name: str) -> Path:
        return self.data_dir / name

    def _read_json(self, name: str, default: Any) -> Any:
        path = self._json_path(name)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.logger.warning("Failed to read %s: %s", path, exc)
            return default

    def _write_json(self, name: str, payload: Any) -> None:
        path = self._json_path(name)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def upload_evidence_image(self, image_bytes: bytes, filename: str) -> str:
        with timed_stage("persistence_write", operation="upload_evidence"):
            if self.is_connected():
                try:
                    storage = self.db.supabase.storage.from_(self.bucket_name)
                    storage.upload(filename, image_bytes, {"content-type": "image/jpeg"})
                    return storage.get_public_url(filename)
                except Exception as exc:
                    self.logger.warning("Supabase Storage upload failed, using local fallback: %s", exc)

            target = self.evidence_dir / filename.replace("/", "_")
            target.write_bytes(image_bytes)
            return str(target).replace("\\", "/")

    def list_violations(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.is_connected():
            try:
                response = (
                    self.db.supabase.table("violations")
                    .select("*")
                    .order("timestamp", desc=True)
                    .limit(limit)
                    .execute()
                )
                return response.data or []
            except Exception as exc:
                self.logger.warning("Failed to fetch violations from Supabase: %s", exc)
        return self._read_json("violations.json", [])[:limit]

    def list_accidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.is_connected():
            try:
                response = (
                    self.db.supabase.table("accidents")
                    .select("*")
                    .order("timestamp", desc=True)
                    .limit(limit)
                    .execute()
                )
                return response.data or []
            except Exception as exc:
                self.logger.warning("Failed to fetch accidents from Supabase: %s", exc)
        return self._read_json("accidents.json", [])[:limit]

    def list_reports(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.is_connected():
            try:
                response = (
                    self.db.supabase.table("reports")
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                return response.data or []
            except Exception as exc:
                self.logger.warning("Failed to fetch reports from Supabase: %s", exc)
        return self._read_json("reports.json", [])[:limit]

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        if self.is_connected():
            try:
                response = (
                    self.db.supabase.table("reports")
                    .select("*")
                    .eq("report_id", report_id)
                    .limit(1)
                    .execute()
                )
                return (response.data or [None])[0]
            except Exception as exc:
                self.logger.warning("Failed to fetch report from Supabase: %s", exc)
        for report in self._read_json("reports.json", []):
            if report.get("report_id") == report_id:
                return report
        return None

    def _append_local(self, filename: str, record: Dict[str, Any], limit: int = 200) -> Dict[str, Any]:
        records = self._read_json(filename, [])
        records.insert(0, record)
        self._write_json(filename, records[:limit])
        return record

    def clear_violations(self) -> bool:
        if self.is_connected():
            try:
                if hasattr(self.db, "clear_violations"):
                    return bool(self.db.clear_violations())
            except Exception as exc:
                self.logger.warning("Failed to clear violations in Supabase: %s", exc)
        self._write_json("violations.json", [])
        return True

    def clear_accidents(self) -> bool:
        if self.is_connected():
            try:
                if hasattr(self.db, "clear_accidents"):
                    return bool(self.db.clear_accidents())
            except Exception as exc:
                self.logger.warning("Failed to clear accidents in Supabase: %s", exc)
        self._write_json("accidents.json", [])
        return True

    def create_report(
        self,
        title: str,
        description: str,
        priority: str,
        author_id: Optional[str] = None,
        author_name: str = "Anonymous",
    ) -> Dict[str, Any]:
        record = {
            "report_id": str(uuid.uuid4()),
            "title": title,
            "description": description,
            "priority": priority,
            "status": "Open",
            "author_id": author_id,
            "author_name": author_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.is_connected():
            try:
                response = self.db.supabase.table("reports").insert(record).execute()
                return (response.data or [record])[0]
            except Exception as exc:
                self.logger.warning("Failed to persist report to Supabase: %s", exc)
        return self._append_local("reports.json", record)

    def save_violation(self, lane: int, violation_type: str, image_bytes: Optional[bytes]) -> Dict[str, Any]:
        with timed_stage("persistence_write", lane=lane, operation="save_violation"):
            timestamp = datetime.now(timezone.utc).isoformat()
            image_url = None
            if image_bytes:
                filename = f"violations/{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_lane{lane}.jpg"
                image_url = self.upload_evidence_image(image_bytes, filename)
            record = {
                "violation_id": str(uuid.uuid4()),
                "vehicle_id": None,
                "violation_type": violation_type,
                "lane": lane,
                "source": "SYSTEM",
                "timestamp": timestamp,
                "image_url": image_url,
            }
            if self.is_connected():
                try:
                    response = self.db.supabase.table("violations").insert(record).execute()
                    return (response.data or [record])[0]
                except Exception as exc:
                    self.logger.warning("Failed to persist violation to Supabase: %s", exc)
            return self._append_local("violations.json", record)

    def save_accident(
        self,
        lane: int,
        severity: str = "Moderate",
        description: str = "",
        image_bytes: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        with timed_stage("persistence_write", lane=lane, operation="save_accident"):
            timestamp = datetime.now(timezone.utc).isoformat()
            image_url = None
            if image_bytes:
                filename = f"accidents/{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_lane{lane}.jpg"
                image_url = self.upload_evidence_image(image_bytes, filename)
            record = {
                "accident_id": str(uuid.uuid4()),
                "lane": lane,
                "severity": severity.capitalize(),
                "detection_type": "SYSTEM",
                "description": description,
                "reported_by": "system",
                "timestamp": timestamp,
                "resolved": False,
                "image_url": image_url,
            }
            if self.is_connected():
                payload = {k: v for k, v in record.items() if k != "image_url"}
                try:
                    response = self.db.supabase.table("accidents").insert(payload).execute()
                    saved = (response.data or [payload])[0]
                    saved["image_url"] = image_url
                    return saved
                except Exception as exc:
                    self.logger.warning("Failed to persist accident to Supabase: %s", exc)
            return self._append_local("accidents.json", record)

    def log_emergency_event(self, lane: int, vehicle_type: str, action_taken: str) -> Dict[str, Any]:
        with timed_stage("persistence_write", lane=lane, operation="log_emergency_event"):
            record = {
                "event_id": str(uuid.uuid4()),
                "vehicle_type": vehicle_type,
                "lane": lane,
                "action_taken": action_taken,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if self.is_connected():
                try:
                    response = self.db.supabase.table("emergency_events").insert(record).execute()
                    return (response.data or [record])[0]
                except Exception as exc:
                    self.logger.warning("Failed to persist emergency event to Supabase: %s", exc)
            return self._append_local("emergency_events.json", record)

    def store_verification_code(
        self,
        email: str,
        username: str,
        code: str,
        code_type: str,
        payload: Dict[str, Any],
        expires_minutes: int,
    ) -> Dict[str, Any]:
        record = {
            "verification_id": str(uuid.uuid4()),
            "email": email,
            "username": username,
            "code": code,
            "code_type": code_type,
            "payload": payload,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).isoformat(),
            "consumed_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.is_connected():
            try:
                response = self.db.supabase.table("verification_codes").insert(record).execute()
                return (response.data or [record])[0]
            except Exception as exc:
                self.logger.warning("Failed to persist verification code to Supabase: %s", exc)
        records = self._read_json("verification_codes.json", [])
        records.append(record)
        self._write_json("verification_codes.json", records)
        return record

    def get_verification_code(self, email: str, code: str, code_type: str) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        if self.is_connected():
            try:
                response = (
                    self.db.supabase.table("verification_codes")
                    .select("*")
                    .eq("email", email)
                    .eq("code", code)
                    .eq("code_type", code_type)
                    .is_("consumed_at", "null")
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if response.data:
                    candidate = response.data[0]
                    if datetime.fromisoformat(candidate["expires_at"]) >= now:
                        return candidate
            except Exception as exc:
                self.logger.warning("Failed to fetch verification code from Supabase: %s", exc)

        records = self._read_json("verification_codes.json", [])
        for candidate in reversed(records):
            if (
                candidate.get("email") == email
                and candidate.get("code") == code
                and candidate.get("code_type") == code_type
                and not candidate.get("consumed_at")
                and datetime.fromisoformat(candidate["expires_at"]) >= now
            ):
                return candidate
        return None

    def consume_verification_code(self, verification_id: str) -> None:
        consumed_at = datetime.now(timezone.utc).isoformat()
        if self.is_connected():
            try:
                self.db.supabase.table("verification_codes").update({"consumed_at": consumed_at}).eq(
                    "verification_id", verification_id
                ).execute()
                return
            except Exception as exc:
                self.logger.warning("Failed to consume verification code in Supabase: %s", exc)

        records = self._read_json("verification_codes.json", [])
        for record in records:
            if record.get("verification_id") == verification_id:
                record["consumed_at"] = consumed_at
        self._write_json("verification_codes.json", records)
