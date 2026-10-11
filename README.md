# AI-Powered Indian Railways Live Platform Announcement Voice Agent

A local end-to-end prototype with a FastAPI event backend and a Streamlit operator dashboard. It uses synthetic Howrah train records, detects timetable/status changes, drafts Bengali/Hindi/English PA scripts, and supports human approval, hold, audit, and Sarvam AI Bulbul audio previews.

> **Prototype boundary:** The train feed is synthetic and all "broadcast" actions are recorded as simulated. No railway feed, station PA hardware, or live passenger announcement system is connected. Keep an operator in the loop before using any real operational integration.

## Requirements

- Python 3.11 or newer
- A Sarvam AI API key for actual audio synthesis (the rest of the prototype works without one)

## Setup (Windows PowerShell)

From the project root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Set `SARVAM_API_KEY` in `.env` to your Sarvam subscription key. Audio previews use this key from the backend only; it is not sent to the dashboard. The dashboard and API can be used without it, but audio generation will be disabled. Do not commit or share `.env`.

Defaults are station code `HWH`, station name `Howrah Junction`, timezone `Asia/Kolkata`, language order Bengali → Hindi → English, and Sarvam model `bulbul:v3`. To change supported language order, set comma-separated Sarvam language codes in `PREFERRED_LANGUAGES` (for example, `bn-IN,hi-IN,en-IN`). Script templates are currently authored in Bengali, Hindi, and English; other supported configured languages receive an English fallback script.

## Run locally

Open two terminals in the project root and activate the virtual environment in both.

Terminal 1 — start the API and its asyncio polling engine:

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 — launch the operator dashboard:

```powershell
streamlit run dashboard/app.py
```

The dashboard opens at `http://localhost:8501`; the API documentation is at `http://127.0.0.1:8000/docs` and health is at `/health`.

## Test the prototype

With the API running, use a third PowerShell terminal to inspect the seeded data and create an announcement:

```powershell
$api = "http://127.0.0.1:8000"
Invoke-RestMethod "$api/health"
Invoke-RestMethod "$api/trains"
$announcement = Invoke-RestMethod -Method Post -Uri "$api/announcements/manual" -ContentType "application/json" -Body (@{ train_no = "12301"; reason = "Audio preview test" } | ConvertTo-Json)
$announcement.id
```

Then preview speech through Sarvam and save the WAV locally (uses the configured Sarvam account):

```powershell
Invoke-WebRequest "$api/announcements/$($announcement.id)/audio?language=bn-IN" -OutFile "preview-bengali.wav"
```

Play `preview-bengali.wav`, or use the dashboard's **Audio gateway** tab. To exercise event detection, change a train record; a pending announcement is automatically queued when delay, status, or platform changes:

```powershell
Invoke-RestMethod -Method Patch -Uri "$api/trains/12301" -ContentType "application/json" -Body (@{ status = "Delayed"; delay_minutes = 8; platform = "2" } | ConvertTo-Json)
Invoke-RestMethod "$api/announcements?status=pending"
```

Finally approve or hold a pending item in the dashboard, then inspect `/audit` or the **Audit log** tab. All broadcasts are simulated and do not connect to station PA hardware.

## Operator workflow

1. In **Live monitoring**, inspect synthetic train records and change status, delay, platform, or estimated arrival to simulate a feed update.
2. The event engine detects state changes and queues announcement scripts. You can also create a manual announcement in **Review & approval**.
3. Review every language script, then **Approve & Broadcast** (simulated) or **Override / Hold**. Both outcomes are logged.
4. In **Audio gateway**, select a script language and generate a real WAV preview through the official `sarvamai` Python SDK and Sarvam Bulbul TTS.
5. Review timestamped train updates, trigger events, approvals, holds, and TTS outcomes in **Audit log**.

Train data, pending announcements, generated audio cache, and audit events live in memory and reset when the API process restarts. The event loop polls every `POLL_INTERVAL_SECONDS` (default 3); the dashboard's train update endpoint also evaluates changes immediately.

## API overview

- `GET /health`, `GET /station`
- `GET /trains`, `PATCH /trains/{train_no}`
- `GET /announcements`, `POST /announcements/manual`
- `POST /announcements/{id}/approve`, `POST /announcements/{id}/hold`
- `GET /announcements/{id}/audio?language=bn-IN`
- `GET /audit?limit=200`

## Project layout

- `backend/config.py` — station, TTS, and language configuration
- `backend/data_store.py` — thread-safe synthetic in-memory records and audit history
- `backend/engine.py` — asynchronous state-change detection, deduplication, and PA script generation
- `backend/tts_client.py` — official Sarvam SDK adapter and WAV decoding
- `backend/main.py` — FastAPI routes and poller lifecycle
- `dashboard/app.py` — four-tab Streamlit operator interface

## Deploy a hosted demo

For a private/demo deployment, create **two Python 3.11+ services** from this project (one API service and one dashboard service) on your chosen host:

1. Configure both services to install dependencies with `pip install -r requirements.txt`.
2. On the API service, set `SARVAM_API_KEY`, `SARVAM_MODEL`, `SARVAM_SPEAKER`, `STATION_CODE`, `STATION_NAME`, `STATION_TIMEZONE`, `PREFERRED_LANGUAGES`, and `POLL_INTERVAL_SECONDS` as host-managed environment variables/secrets. Never put the key in source control or a frontend environment variable.
3. Set the API start command to `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` (adjust `$PORT` to the host's required port syntax). Restrict the API to trusted users/network access; this demo does not implement authentication.
4. On the dashboard service, set `API_BASE_URL` to the API's reachable HTTPS URL and use `streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port $PORT` as its start command.
5. Open the dashboard URL, confirm the API is healthy, then follow **Test the prototype** above. Keep the API on one replica: trains, approvals, audio cache, and audit history are in-memory and reset on restart. Use a persistent database, authentication, HTTPS, and a real railway/PA integration review before any production use.

The hosted setup is for demonstration only. Do not expose an unauthenticated control dashboard publicly or connect this prototype to an operational announcement system.
