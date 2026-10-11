"""Streamlit operator dashboard for review, approval, and audio preview."""

from __future__ import annotations

import base64
import os

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
LANGUAGE_CODES = {
    "Bengali": "bn-IN",
    "Hindi": "hi-IN",
    "English": "en-IN",
    "Tamil": "ta-IN",
    "Telugu": "te-IN",
    "Marathi": "mr-IN",
    "Gujarati": "gu-IN",
    "Kannada": "kn-IN",
    "Malayalam": "ml-IN",
    "Punjabi": "pa-IN",
    "Odia": "od-IN",
}

st.set_page_config(page_title="Railway PA Control Room", page_icon="🚉", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(145deg, #f5f8fc 0%, #eef3f9 100%); }
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }
    .hero { padding: 1.4rem 1.6rem; border-radius: 18px; color: #fff;
            background: linear-gradient(115deg, #102a43, #176b87 68%, #28a5a1);
            margin-bottom: 1.2rem; box-shadow: 0 12px 32px rgba(16,42,67,.15); }
    .hero h1 { margin: 0; font-size: 2rem; }
    .hero p { margin: .4rem 0 0; opacity: .88; }
    div[data-testid="stMetric"] { background: white; padding: 14px 16px; border-radius: 14px;
                                    border: 1px solid #e2e9f0; }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_request(method: str, path: str, **kwargs):
    try:
        response = requests.request(method, f"{API_BASE}{path}", timeout=15, **kwargs)
        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            st.error(f"API error ({response.status_code}): {detail}")
            return None
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.content
    except requests.RequestException as exc:
        st.error(f"Cannot reach the FastAPI service at {API_BASE}: {exc}")
        return None


health = api_request("GET", "/health")
station = api_request("GET", "/station")
station_name = station.get("name", "Railway Station") if station else "Railway Station"
station_code = station.get("code", "—") if station else "—"

st.markdown(
    f'<div class="hero"><h1>🚉 Railway PA Control Room</h1>'
    f'<p>AI-assisted multilingual announcements · {station_name} ({station_code}) · Human approval required</p></div>',
    unsafe_allow_html=True,
)

if health:
    left, middle, right = st.columns(3)
    left.metric("Station", station_code)
    middle.metric("Sarvam TTS", "Connected" if health.get("sarvam_configured") else "API key not set")
    right.metric("Workflow", "Operator approval")
else:
    st.warning("Start the FastAPI backend to connect the dashboard.")

if not health:
    st.stop()

live_tab, approval_tab, audio_tab, audit_tab = st.tabs(
    ["🚆 Live monitoring", "🗣️ Review & approval", "🎧 Audio gateway", "📜 Audit log"]
)

with live_tab:
    st.subheader("Live train status")
    st.caption("Synthetic feed for local demonstration. Use the controls below to inject timetable events.")
    trains = api_request("GET", "/trains") or []
    if trains:
        st.dataframe(
            trains,
            use_container_width=True,
            hide_index=True,
            column_config={
                "train_no": st.column_config.TextColumn("Train no."),
                "train_name": st.column_config.TextColumn("Train"),
                "scheduled_arrival": st.column_config.TextColumn("Scheduled"),
                "estimated_arrival": st.column_config.TextColumn("Estimated"),
                "delay_minutes": st.column_config.NumberColumn("Delay (min)", format="%d"),
                "platform": st.column_config.TextColumn("Platform"),
                "updated_at": st.column_config.DatetimeColumn("Last update", format="HH:mm:ss"),
            },
        )
        st.markdown("#### Simulate a live update")
        train_options = {f"{row['train_no']} · {row['train_name']}": row for row in trains}
        with st.form("train_update_form"):
            selected_label = st.selectbox("Train", list(train_options))
            selected_train = train_options[selected_label]
            col1, col2, col3 = st.columns(3)
            status = col1.selectbox(
                "Status",
                ["On Time", "Delayed", "Approaching", "Platform Changed"],
                index=["On Time", "Delayed", "Approaching", "Platform Changed"].index(selected_train["status"]),
            )
            platform = col2.text_input("Platform", value=selected_train["platform"])
            delay = col3.number_input("Delay (minutes)", min_value=0, max_value=1440, value=selected_train["delay_minutes"])
            eta = st.text_input("Estimated arrival (HH:MM)", value=selected_train["estimated_arrival"])
            submitted = st.form_submit_button("Apply synthetic update", type="primary")
            if submitted:
                result = api_request(
                    "PATCH",
                    f"/trains/{selected_train['train_no']}",
                    json={"status": status, "platform": platform, "delay_minutes": delay, "estimated_arrival": eta},
                )
                if result:
                    st.success("Train state updated. The event engine has evaluated the change.")
                    st.rerun()
    else:
        st.info("No train records are available.")

with approval_tab:
    st.subheader("Human-in-the-loop announcement review")
    st.caption("Scripts are prepared in the configured language sequence; nothing is marked broadcast without operator approval.")
    trains_for_trigger = api_request("GET", "/trains") or []
    if trains_for_trigger:
        options = {f"{row['train_no']} · {row['train_name']}": row["train_no"] for row in trains_for_trigger}
        with st.form("manual_trigger_form"):
            trigger_train = st.selectbox("Create a manual announcement", list(options))
            reason = st.text_input("Announcement context", value="Operator requested announcement")
            manual_submit = st.form_submit_button("Generate scripts", type="primary")
            if manual_submit:
                created = api_request(
                    "POST", "/announcements/manual", json={"train_no": options[trigger_train], "reason": reason}
                )
                if created:
                    st.success("Scripts generated and queued for approval.")
                    st.rerun()

    announcements = api_request("GET", "/announcements") or []
    if not announcements:
        st.info("No announcements yet. Change a train status or create a manual trigger above.")
    for item in announcements:
        state_label = item["status"].replace("_", " ").title()
        with st.expander(f"{item['train_no']} · {item['train_name']} — {state_label} · {item['trigger']}", expanded=item["status"] == "pending"):
            st.caption(f"Created: {item['created_at']} · ID: {item['id']}")
            for language_name, script in item["scripts"].items():
                st.markdown(f"**{language_name}**")
                st.write(script)
            if item["status"] == "pending":
                approve_col, hold_col, _ = st.columns([1, 1, 4])
                if approve_col.button("✅ Approve & Broadcast", key=f"approve_{item['id']}", type="primary"):
                    result = api_request("POST", f"/announcements/{item['id']}/approve")
                    if result:
                        st.success("Approved. Local prototype recorded a simulated broadcast; no PA hardware is connected.")
                        st.rerun()
                if hold_col.button("⏸ Override / Hold", key=f"hold_{item['id']}"):
                    result = api_request("POST", f"/announcements/{item['id']}/hold", json={"reason": "Held by dashboard operator"})
                    if result:
                        st.warning("Announcement held and recorded in the audit log.")
                        st.rerun()

with audio_tab:
    st.subheader("Sarvam AI audio test gateway")
    st.caption("Preview each language independently before approval. Audio is synthesized on demand using the configured Bulbul model.")
    announcements = api_request("GET", "/announcements") or []
    if not announcements:
        st.info("Create or detect an announcement first to enable audio preview.")
    else:
        announcement_options = {
            f"{item['train_no']} · {item['train_name']} · {item['created_at']}": item for item in announcements
        }
        selected_audio_label = st.selectbox("Announcement", list(announcement_options))
        selected_announcement = announcement_options[selected_audio_label]
        available_languages = list(selected_announcement["scripts"])
        selected_language = st.selectbox("Language", available_languages)
        st.info(selected_announcement["scripts"][selected_language])
        if st.button("Generate / refresh audio preview", type="primary"):
            code = LANGUAGE_CODES.get(selected_language)
            if not code:
                st.error("No Sarvam language-code mapping is available for this script.")
            else:
                audio = api_request(
                    "GET", f"/announcements/{selected_announcement['id']}/audio", params={"language": code}
                )
                if audio:
                    st.session_state["preview_audio"] = audio
                    st.session_state["preview_audio_label"] = f"{selected_language} · {selected_announcement['train_no']}"
        if st.button("Generate full language sequence"):
            sequence = api_request("POST", f"/announcements/{selected_announcement['id']}/audio/all")
            if sequence:
                st.session_state["preview_sequence"] = sequence["audios"]
                st.session_state["preview_sequence_id"] = selected_announcement["id"]
        if st.session_state.get("preview_audio"):
            st.caption(f"Preview: {st.session_state.get('preview_audio_label', '')}")
            st.audio(st.session_state["preview_audio"], format="audio/wav")
        if st.session_state.get("preview_sequence") and st.session_state.get("preview_sequence_id") == selected_announcement["id"]:
            for clip in st.session_state["preview_sequence"]:
                st.markdown(f"**{clip['language']} ({clip['language_code']})**")
                st.audio(base64.b64decode(clip["audio_base64"]), format="audio/wav")
        elif not health.get("sarvam_configured"):
            st.warning("Set SARVAM_API_KEY in .env and restart the backend to enable real speech generation.")

with audit_tab:
    st.subheader("Timestamped audit trail")
    logs = api_request("GET", "/audit", params={"limit": 500}) or []
    if logs:
        st.dataframe(logs, use_container_width=True, hide_index=True)
    else:
        st.info("Audit entries will appear here as the system is used.")
    if st.button("Refresh dashboard data"):
        st.rerun()

st.caption("Prototype only · synthetic data · all broadcasts are simulated locally")
