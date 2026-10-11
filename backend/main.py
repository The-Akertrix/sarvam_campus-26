"""FastAPI service for synthetic railway data and operator approvals."""

from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.config import LANGUAGE_CATALOG, settings
from backend.data_store import DataStore
from backend.engine import AnnouncementEngine
from backend.models import HoldRequest, ManualAnnouncementRequest, TrainUpdate
from backend.tts_client import SarvamTTSClient

store = DataStore()
engine = AnnouncementEngine(store)
tts_client = SarvamTTSClient()
audio_cache: dict[tuple[str, str], bytes] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    poller = asyncio.create_task(engine.run(), name="train-state-poller")
    yield
    engine.stop()
    poller.cancel()
    try:
        await poller
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Railway Announcement Voice Agent API",
    description="Synthetic live-train events, multilingual scripts, Sarvam TTS, and operator approvals.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "station": settings.station_code, "sarvam_configured": tts_client.configured}


@app.get("/station")
async def station() -> dict[str, object]:
    return {
        "code": settings.station_code,
        "name": settings.station_name,
        "timezone": settings.timezone,
        "preferred_languages": [LANGUAGE_CATALOG[code] for code in settings.preferred_languages],
        "poll_interval_seconds": settings.poll_interval_seconds,
    }


@app.get("/trains")
async def list_trains():
    return store.list_trains()


@app.patch("/trains/{train_no}")
async def update_train(train_no: str, update: TrainUpdate):
    previous = store.get_train(train_no)
    if previous is None:
        raise HTTPException(status_code=404, detail="Train not found")
    updated = store.update_train(train_no, update)
    assert updated is not None
    store.add_audit(
        "train_updated",
        "Synthetic train record updated by operator/API",
        train_no=train_no,
        details={"changed_fields": ", ".join(update.model_dump(exclude_unset=True, exclude_none=True))},
    )
    await engine.scan_once()
    return updated


@app.get("/announcements")
async def list_announcements(status: str | None = Query(default=None)):
    announcements = store.list_announcements()
    if status:
        announcements = [item for item in announcements if item.status == status]
    return announcements


@app.post("/announcements/manual", status_code=201)
async def manual_announcement(request: ManualAnnouncementRequest):
    train = store.get_train(request.train_no)
    if train is None:
        raise HTTPException(status_code=404, detail="Train not found")
    return engine.create_manual(train, request.reason)


@app.post("/announcements/{announcement_id}/approve")
async def approve_announcement(announcement_id: str):
    item = store.get_announcement(announcement_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    if item.status != "pending":
        raise HTTPException(status_code=409, detail=f"Announcement is already {item.status}")
    updated = store.set_announcement_status(announcement_id, "broadcast")
    store.add_audit(
        "broadcast_simulated",
        "Operator approved; broadcast simulated locally (no station PA hardware is connected)",
        train_no=item.train_no,
        announcement_id=announcement_id,
        details={"language_count": len(item.scripts)},
    )
    return updated


@app.post("/announcements/{announcement_id}/hold")
async def hold_announcement(announcement_id: str, request: HoldRequest):
    item = store.get_announcement(announcement_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    if item.status != "pending":
        raise HTTPException(status_code=409, detail=f"Announcement is already {item.status}")
    updated = store.set_announcement_status(announcement_id, "held")
    store.add_audit(
        "announcement_held",
        request.reason,
        train_no=item.train_no,
        announcement_id=announcement_id,
    )
    return updated


@app.get("/announcements/{announcement_id}/audio")
async def preview_audio(announcement_id: str, language: str = Query(..., description="Sarvam language code, e.g. bn-IN")):
    item = store.get_announcement(announcement_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    if language not in settings.preferred_languages:
        raise HTTPException(status_code=400, detail="Language is not in the station's preferred sequence")
    language_name = LANGUAGE_CATALOG[language]["name"]
    text = item.scripts.get(language_name)
    if not text:
        raise HTTPException(status_code=404, detail="Announcement script is unavailable for this language")
    try:
        cache_key = (announcement_id, language)
        audio = audio_cache.get(cache_key)
        if audio is None:
            audio = await tts_client.synthesize(text, language)
            audio_cache[cache_key] = audio
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # SDK/network failures are surfaced as an operator-safe API error.
        store.add_audit(
            "tts_failed",
            f"Sarvam audio generation failed for {language_name}",
            train_no=item.train_no,
            announcement_id=announcement_id,
            details={"error": str(exc)[:300]},
        )
        raise HTTPException(status_code=502, detail=f"Sarvam audio generation failed: {exc}") from exc

    store.add_audit(
        "audio_generated",
        f"Sarvam audio preview generated in {language_name}",
        train_no=item.train_no,
        announcement_id=announcement_id,
        details={"language_code": language, "bytes": len(audio)},
    )
    return StreamingResponse(
        BytesIO(audio),
        media_type="audio/wav",
        headers={"Content-Disposition": f'inline; filename="{announcement_id}-{language}.wav"'},
    )


@app.post("/announcements/{announcement_id}/audio/all")
async def generate_language_sequence(announcement_id: str):
    """Synthesize each configured language in order for a complete PA preview."""
    item = store.get_announcement(announcement_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Announcement not found")

    audios: list[dict[str, str]] = []
    for language_code in settings.preferred_languages:
        language_name = LANGUAGE_CATALOG[language_code]["name"]
        script = item.scripts.get(language_name)
        if not script:
            continue
        try:
            cache_key = (announcement_id, language_code)
            audio = audio_cache.get(cache_key)
            if audio is None:
                audio = await tts_client.synthesize(script, language_code)
                audio_cache[cache_key] = audio
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            store.add_audit(
                "tts_failed",
                f"Sarvam audio generation failed for {language_name}",
                train_no=item.train_no,
                announcement_id=announcement_id,
                details={"error": str(exc)[:300]},
            )
            raise HTTPException(status_code=502, detail=f"Sarvam audio generation failed for {language_name}: {exc}") from exc
        store.add_audit(
            "audio_generated",
            f"Sarvam audio generated in {language_name} for sequential preview",
            train_no=item.train_no,
            announcement_id=announcement_id,
            details={"language_code": language_code, "bytes": len(audio)},
        )
        audios.append(
            {"language": language_name, "language_code": language_code, "audio_base64": base64.b64encode(audio).decode("ascii")}
        )
    return {"announcement_id": announcement_id, "audios": audios}


@app.get("/audit")
async def audit_log(limit: int = Query(default=200, ge=1, le=1000)):
    return store.list_audit(limit)
