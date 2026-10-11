"""Event-driven train-state watcher and announcement script generator."""

from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.config import LANGUAGE_CATALOG, settings
from backend.data_store import DataStore
from backend.models import Announcement, TrainRecord


class AnnouncementEngine:
    def __init__(self, store: DataStore) -> None:
        self.store = store
        self._snapshot = {train.train_no: train.model_dump(mode="json") for train in store.list_trains()}
        self._seen_fingerprints: set[tuple[str, str, str, str, str]] = set()
        self._scan_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        """Poll synthetic state until application shutdown."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=settings.poll_interval_seconds)
            except TimeoutError:
                await self.scan_once()

    def stop(self) -> None:
        self._stop_event.set()

    async def scan_once(self) -> list[Announcement]:
        """Compare records against the last snapshot and enqueue state-change events."""
        async with self._scan_lock:
            created: list[Announcement] = []
            for train in self.store.list_trains():
                current = train.model_dump(mode="json")
                previous = self._snapshot.get(train.train_no)
                self._snapshot[train.train_no] = current
                if previous is None:
                    continue
                changes: list[str] = []
                if train.platform != previous["platform"]:
                    changes.append(f"Platform changed from {previous['platform']} to {train.platform}")
                if train.status != previous["status"]:
                    changes.append(f"Status changed from {previous['status']} to {train.status}")
                if train.delay_minutes > previous["delay_minutes"]:
                    changes.append(
                        f"Delay increased from {previous['delay_minutes']} to {train.delay_minutes} minutes"
                    )
                if not changes:
                    continue
                trigger = "; ".join(changes)
                fingerprint = (
                    train.train_no,
                    trigger,
                    train.estimated_arrival,
                    train.platform,
                    train.status,
                )
                if fingerprint in self._seen_fingerprints:
                    continue
                self._seen_fingerprints.add(fingerprint)
                announcement = self._build_announcement(train, trigger)
                self.store.add_announcement(announcement)
                self.store.add_audit(
                    "train_state_changed",
                    trigger,
                    train_no=train.train_no,
                    announcement_id=announcement.id,
                )
                created.append(announcement)
            return created

    def create_manual(self, train: TrainRecord, reason: str) -> Announcement:
        announcement = self._build_announcement(train, reason)
        self.store.add_announcement(announcement)
        self.store.add_audit(
            "manual_trigger",
            reason,
            train_no=train.train_no,
            announcement_id=announcement.id,
        )
        return announcement

    def _build_announcement(self, train: TrainRecord, trigger: str) -> Announcement:
        scripts = {
            LANGUAGE_CATALOG[code]["name"]: self._script_for(train, code)
            for code in settings.preferred_languages
        }
        now = datetime.now(ZoneInfo(settings.timezone))
        return Announcement(
            id=str(uuid4()),
            train_no=train.train_no,
            train_name=train.train_name,
            trigger=trigger,
            scripts=scripts,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _script_for(train: TrainRecord, language_code: str) -> str:
        number = train.train_no
        name = train.train_name
        platform = train.platform
        arrival = train.estimated_arrival
        delay = train.delay_minutes

        if language_code == "bn-IN":
            return (
                f"যাত্রীদের দৃষ্টি আকর্ষণ করা হচ্ছে। {name}, ট্রেন নম্বর {number}, "
                f"আনুমানিক {arrival}-এ প্ল্যাটফর্ম নম্বর {platform}-এ আসবে। "
                f"বর্তমানে ট্রেনটি {delay} মিনিট বিলম্বে চলছে। যাত্রীদের অনুগ্রহ করে সতর্ক থাকার অনুরোধ করা হচ্ছে।"
            )
        if language_code == "hi-IN":
            return (
                f"यात्रियों कृपया ध्यान दें। {name}, गाड़ी संख्या {number}, "
                f"लगभग {arrival} बजे प्लेटफॉर्म संख्या {platform} पर आएगी। "
                f"यह गाड़ी वर्तमान में {delay} मिनट विलंब से चल रही है। कृपया अपनी यात्रा के लिए तैयार रहें।"
            )
        if language_code == "en-IN":
            return (
                f"Attention please. {name}, train number {number}, is expected to arrive at "
                f"platform number {platform} at approximately {arrival}. The train is currently "
                f"running {delay} minutes late. Passengers are requested to remain alert."
            )
        # Additional configured languages receive a clearly understandable English PA fallback.
        return (
            f"Attention please. {name}, train number {number}, is expected to arrive at "
            f"platform number {platform} at approximately {arrival}. The train is currently "
            f"running {delay} minutes late. Passengers are requested to remain alert."
        )
