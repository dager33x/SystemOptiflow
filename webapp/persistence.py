import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


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
        self.local_history_limit = 200
        self._json_cache: Dict[str, Any] = {}
        self._json_cache_mtime: Dict[str, int] = {}
        self._json_index_cache: Dict[tuple[str, str], Dict[str, Dict[str, Any]]] = {}
        if self.is_connected():
            self._sync_local_to_supabase()

    def is_connected(self) -> bool:
        return bool(self.db and self.db.is_connected())

    def _sync_local_to_supabase(self) -> None:
        """Push any JSON-fallback records that were written during Supabase downtime."""
        synced = 0
        for filename, table, id_key in [
            ("violations.json", "violations", "violation_id"),
            ("accidents.json", "accidents", "accident_id"),
            ("reports.json", "reports", "report_id"),
        ]:
            records: List[Dict[str, Any]] = self._read_json(filename, [])
            if not records:
                continue
            for record in records:
                rid = record.get(id_key)
                if not rid:
                    continue
                try:
                    existing = (
                        self.db.supabase.table(table)
                        .select(id_key)
                        .eq(id_key, rid)
                        .execute()
                    )
                    if existing.data:
                        continue
                    self.db.supabase.table(table).insert(record).execute()
                    synced += 1
                except Exception as exc:
                    self.logger.debug("Sync skipped %s %s: %s", table, rid, exc)
        if synced:
            self.logger.info("Synced %d local fallback record(s) to Supabase.", synced)

    def _json_path(self, name: str) -> Path:
        return self.data_dir / name

    def _read_json(self, name: str, default: Any) -> Any:
        path = self._json_path(name)
        if not path.exists():
            return default
        try:
            mtime = path.stat().st_mtime_ns
            if name in self._json_cache and self._json_cache_mtime.get(name) == mtime:
                return self._json_cache[name]
            payload = json.loads(path.read_text(encoding="utf-8"))
            self._json_cache[name] = payload
            self._json_cache_mtime[name] = mtime
            self._invalidate_index_cache(name)
            return payload
        except Exception as exc:
            self.logger.warning("Failed to read %s: %s", path, exc)
            return default

    def _write_json(self, name: str, payload: Any) -> None:
        path = self._json_path(name)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._json_cache[name] = payload
        self._json_cache_mtime[name] = path.stat().st_mtime_ns
        self._invalidate_index_cache(name)

    def _invalidate_index_cache(self, filename: str) -> None:
        for key in [cache_key for cache_key in self._json_index_cache if cache_key[0] == filename]:
            self._json_index_cache.pop(key, None)

    def upload_evidence_image(self, image_bytes: bytes, filename: str) -> str:
        if self.is_connected():
            try:
                storage = self.db.storage.from_(self.bucket_name)
                storage.upload(
                    filename,
                    image_bytes,
                    {"content-type": "image/jpeg", "upsert": "true"},
                )
                return storage.get_public_url(filename)
            except Exception as exc:
                self.logger.warning("Supabase Storage upload failed, using local fallback: %s", exc)

        target = self.evidence_dir / Path(filename).name
        target.write_bytes(image_bytes)
        return str(target).replace("\\", "/")

    def _sort_records(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            items,
            key=lambda item: item.get("timestamp") or item.get("created_at") or "",
            reverse=True,
        )

    def _evidence_filename(self, category: str, lane: int, extension: str = "jpg") -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        return f"{category}/{stamp}_lane{lane}.{extension}"

    def persist_evidence_image(self, category: str, lane: int, image_bytes: Optional[bytes]) -> Optional[str]:
        if not image_bytes:
            return None
        return self.upload_evidence_image(image_bytes, self._evidence_filename(category, lane))

    def get_violation(self, violation_id: str) -> Optional[Dict[str, Any]]:
        if self.is_connected():
            try:
                response = (
                    self.db.supabase.table("violations")
                    .select("*")
                    .eq("violation_id", violation_id)
                    .limit(1)
                    .execute()
                )
                return (response.data or [None])[0]
            except Exception as exc:
                self.logger.warning("Failed to fetch violation from Supabase: %s", exc)
        return self._get_local_record("violations.json", "violation_id", violation_id)

    def get_accident(self, accident_id: str) -> Optional[Dict[str, Any]]:
        if self.is_connected():
            try:
                response = (
                    self.db.supabase.table("accidents")
                    .select("*")
                    .eq("accident_id", accident_id)
                    .limit(1)
                    .execute()
                )
                return (response.data or [None])[0]
            except Exception as exc:
                self.logger.warning("Failed to fetch accident from Supabase: %s", exc)
        return self._get_local_record("accidents.json", "accident_id", accident_id)

    def list_violations(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.is_connected():
            try:
                response = (
                    self.db.supabase.table("violations")
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                return response.data or []
            except Exception as exc:
                self.logger.warning("Failed to fetch violations from Supabase: %s", exc)
        return self._sort_records(self._read_json("violations.json", []))[:limit]

    def list_accidents(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.is_connected():
            try:
                response = (
                    self.db.supabase.table("accidents")
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                return response.data or []
            except Exception as exc:
                self.logger.warning("Failed to fetch accidents from Supabase: %s", exc)
        return self._sort_records(self._read_json("accidents.json", []))[:limit]

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
        return self._sort_records(self._read_json("reports.json", []))[:limit]

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
        return self._get_local_record("reports.json", "report_id", report_id)

    def _get_local_record(self, filename: str, key_field: str, key_value: str) -> Optional[Dict[str, Any]]:
        cache_key = (filename, key_field)
        if cache_key not in self._json_index_cache:
            records = self._read_json(filename, [])
            self._json_index_cache[cache_key] = {
                str(record.get(key_field)): record
                for record in records
                if isinstance(record, dict) and record.get(key_field) is not None
            }
        return self._json_index_cache[cache_key].get(str(key_value))

    def _append_local(self, filename: str, record: Dict[str, Any], limit: int = 200) -> Dict[str, Any]:
        records = self._read_json(filename, [])
        records.insert(0, record)
        self._write_json(filename, self._sort_records(records)[:limit])
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
        image_url = self.persist_evidence_image("violations", lane, image_bytes)
        record = {
            "violation_id": str(uuid.uuid4()),
            "vehicle_id": None,
            "violation_type": violation_type,
            "lane": lane,
            "source": "SYSTEM",
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
        image_url = self.persist_evidence_image("accidents", lane, image_bytes)
        record = {
            "accident_id": str(uuid.uuid4()),
            "lane": lane,
            "severity": {"high": "Severe", "critical": "Severe", "low": "Minor", "medium": "Moderate"}.get(severity.lower(), severity.capitalize()),
            "detection_type": "SYSTEM",
            "description": description,
            "reported_by": None,
            "resolved": False,
            "image_url": image_url,
        }
        if self.is_connected():
            try:
                response = self.db.supabase.table("accidents").insert(record).execute()
                return (response.data or [record])[0]
            except Exception as exc:
                self.logger.warning("Failed to persist accident to Supabase: %s", exc)
        return self._append_local("accidents.json", record)

    def log_emergency_event(self, lane: int, vehicle_type: str, action_taken: str) -> Dict[str, Any]:
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
        updated = False
        for record in records:
            if record.get("verification_id") == verification_id:
                record["consumed_at"] = consumed_at
                updated = True
                break
        if updated:
            self._write_json("verification_codes.json", records)
