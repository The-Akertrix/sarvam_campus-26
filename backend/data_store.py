"""Thread-safe in-memory synthetic train and audit store."""

from __future__ import annotations

from datetime import datetime, timedelta
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.config import settings
from backend.models import Announcement, AuditEntry, TrainRecord, TrainUpdate


class DataStore:
    """Small in-memory harness; replace with a railway feed/database in production."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._trains: dict[str, TrainRecord] = self._seed_trains()
        self._announcements: dict[str, Announcement] = {}
        self._audit: list[AuditEntry] = []
        self.add_audit("system_started", "Synthetic timetable loaded", details={"train_count": len(self._trains)})

    @staticmethod
    def _seed_trains() -> dict[str, TrainRecord]:
        now = datetime.now(ZoneInfo(settings.timezone))
        seed = [
            ("12301", "Howrah Rajdhani Express", "Howrah", "New Delhi", 18, 1, "On Time", 0),
            ("12841", "Coromandel Express", "Shalimar", "Chennai Central", 34, 6, "Delayed", 25),
            ("12905", "Howrah–Porbandar Express", "Howrah", "Porbandar", 52, 9, "Approaching", 10),
            ("12022", "Bardhaman–Howrah Shatabdi", "Bardhaman", "Howrah", 67, 3, "On Time", 0),
        ]
        trains: dict[str, TrainRecord] = {}
        for number, name, origin, destination, offset, platform, status, delay in seed:
            scheduled = now + timedelta(minutes=offset)
            estimated = scheduled + timedelta(minutes=delay)
            trains[number] = TrainRecord(
                train_no=number,
                train_name=name,
                origin=origin,
                destination=destination,
                scheduled_arrival=scheduled.strftime("%H:%M"),
                estimated_arrival=estimated.strftime("%H:%M"),
                delay_minutes=delay,
                platform=str(platform),
                status=status,
                updated_at=now,
            )
        return trains

    def list_trains(self) -> list[TrainRecord]:
        with self._lock:
            return sorted(self._trains.values(), key=lambda train: train.scheduled_arrival)

    def get_train(self, train_no: str) -> TrainRecord | None:
        with self._lock:
            return self._trains.get(train_no)

    def update_train(self, train_no: str, update: TrainUpdate) -> TrainRecord | None:
        with self._lock:
            existing = self._trains.get(train_no)
            if existing is None:
                return None
            changes = update.model_dump(exclude_unset=True, exclude_none=True)
            changes["updated_at"] = datetime.now(ZoneInfo(settings.timezone))
            updated = existing.model_copy(update=changes)
            self._trains[train_no] = updated
            return updated

    def add_announcement(self, announcement: Announcement) -> None:
        with self._lock:
            self._announcements[announcement.id] = announcement
            self._audit.append(
                AuditEntry(
                    id=str(uuid4()),
                    timestamp=announcement.created_at,
                    action="announcement_created",
                    message=f"Announcement queued: {announcement.trigger}",
                    train_no=announcement.train_no,
                    announcement_id=announcement.id,
                )
            )

    def list_announcements(self) -> list[Announcement]:
        with self._lock:
            return sorted(self._announcements.values(), key=lambda item: item.created_at, reverse=True)

    def get_announcement(self, announcement_id: str) -> Announcement | None:
        with self._lock:
            return self._announcements.get(announcement_id)

    def set_announcement_status(self, announcement_id: str, status: str) -> Announcement | None:
        with self._lock:
            existing = self._announcements.get(announcement_id)
            if existing is None:
                return None
            updated = existing.model_copy(
                update={"status": status, "updated_at": datetime.now(ZoneInfo(settings.timezone))}
            )
            self._announcements[announcement_id] = updated
            return updated

    def add_audit(
        self,
        action: str,
        message: str,
        *,
        train_no: str | None = None,
        announcement_id: str | None = None,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            id=str(uuid4()),
            timestamp=datetime.now(ZoneInfo(settings.timezone)),
            action=action,
            message=message,
            train_no=train_no,
            announcement_id=announcement_id,
            details=details or {},
        )
        with self._lock:
            self._audit.append(entry)
        return entry

    def list_audit(self, limit: int = 200) -> list[AuditEntry]:
        with self._lock:
            return list(reversed(self._audit[-limit:]))
