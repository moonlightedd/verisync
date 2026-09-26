
import json
import os
import shutil
import subprocess

import streamlit as st

from database import (
    get_recent_kycs,
    search_kycs,
    get_kyc_by_id,
    delete_kyc_by_id,
    delete_all_kycs,
)


def _record_value(record, key, default=None):
    """Read a database row or dict safely."""
    try:
        value = record[key]
    except (KeyError, IndexError, TypeError):
        try:
            value = record.get(key, default)
        except AttributeError:
            return default
    return default if value is None else value


def _get_browser_video_path(video_path):
    """
    Return a browser-compatible H.264 MP4 for Admin playback.

    Older VERISYNC records may contain OpenCV mp4v video files.
    """
    if not video_path or not os.path.exists(video_path):
        return None

    browser_path = os.path.join(
        os.path.dirname(video_path),
        "video_browser.mp4",
    )

    try:
        if (
            os.path.exists(browser_path)
            and os.path.getmtime(browser_path) >= os.path.getmtime(video_path)
        ):
            return browser_path
    except Exception:
        pass

    ffmpeg_path = shutil.which("ffmpeg")

    if not ffmpeg_path:
        return video_path

    temp_path = browser_path + ".tmp.mp4"

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        video_path,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        temp_path,
    ]

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )

        if (
            completed.returncode == 0
            and os.path.exists(temp_path)
            and os.path.getsize(temp_path) > 0
        ):
            os.replace(temp_path, browser_path)
            return browser_path

    except Exception:
        pass

    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass

    return video_path


def _get_synchronized_av_path(video_path, audio_path):
    """
    Create one browser-playable MP4 containing the recorded video and
    the separately captured WAV audio on the same timeline.

    The source video and audio are both produced by the same 10-second
    verification capture. We mux them without changing their relative
    timing, so clicking Play starts the visual and audio evidence together.
    """
    if (
        not video_path
        or not audio_path
        or not os.path.exists(video_path)
        or not os.path.exists(audio_path)
    ):
        return None

    folder = os.path.dirname(video_path)
    av_path = os.path.join(folder, "verification_av.mp4")

    try:
        newest_source = max(
            os.path.getmtime(video_path),
            os.path.getmtime(audio_path),
        )
        if (
            os.path.exists(av_path)
            and os.path.getmtime(av_path) >= newest_source
            and os.path.getsize(av_path) > 0
        ):
            return av_path
    except Exception:
        pass

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return None

    temp_path = av_path + ".tmp.mp4"

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        video_path,
        "-i",
        audio_path,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-shortest",
        "-movflags",
        "+faststart",
        temp_path,
    ]

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )

        if (
            completed.returncode == 0
            and os.path.exists(temp_path)
            and os.path.getsize(temp_path) > 0
        ):
            os.replace(temp_path, av_path)
            return av_path

    except Exception:
        pass

    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass

    return None


def _load_sync_result(video_path):
    if not video_path:
        return {}

    folder = os.path.dirname(video_path)
    sync_path = os.path.join(folder, "sync_result.json")

    if not os.path.exists(sync_path):
        return {}

    try:
        with open(sync_path, "r", encoding="utf-8") as file:
            raw = json.load(file)

        nested = raw.get("cross_modal_analysis")

        if isinstance(nested, dict):
            merged = dict(raw)
            merged.update(nested)
            return merged

        return raw

    except Exception:
        return {}


def _delete_evidence(video_path=None, audio_path=None):
    """
    Remove the complete per-verification evidence folder.
    The paths are generated by VERISYNC, so we remove the
    parent verification folder rather than individual files.
    """
    candidate_paths = [video_path, audio_path]

    folders = set()

    for path in candidate_paths:
        if path:
            absolute_path = os.path.abspath(path)
            folder = os.path.dirname(absolute_path)

            if os.path.basename(folder).startswith("VS-"):
                folders.add(folder)

    deleted = []

    for folder in folders:
        if os.path.isdir(folder):
            try:
                shutil.rmtree(folder)
                deleted.append(folder)
            except Exception:
                pass

    return deleted


def _delete_selected_record(verification_id):
    evidence = delete_kyc_by_id(verification_id)

    if evidence is None:
        return False

    _delete_evidence(
        video_path=evidence.get("video_path"),
        audio_path=evidence.get("audio_path"),
    )

    return True


def _delete_all_records():
    records = delete_all_kycs()

    for record in records:
        _delete_evidence(
            video_path=_record_value(record, "video_path"),
            audio_path=_record_value(record, "audio_path"),
        )

    return len(records)


def show_admin_dashboard():
    st.markdown(
        """
        <style>
        /* =====================================================
           VERISYNC ADMIN — readable, compact, responsive UI
           ===================================================== */

        .stMarkdown, .stMarkdown p, .stMarkdown li,
        [data-testid="stCaptionContainer"], label,
        .stCaption, .stAlert {
            color: #EAF2FF !important;
        }

        h1, h2, h3, h4, h5, h6 {
            color: #FFFFFF !important;
        }

        .stCaption, [data-testid="stCaptionContainer"] {
            color: #C9D8EE !important;
        }

        /* Summary cards */
        .admin-stat {
            background: linear-gradient(135deg, #102F5F 0%, #163B75 100%);
            border: 1px solid #31538A;
            border-radius: 14px;
            padding: 16px 18px;
            min-height: 105px;
        }

        .admin-stat-label {
            color: #C9D8EE !important;
            font-size: 0.82rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .admin-stat-value {
            color: #FFFFFF !important;
            font-size: 1.9rem;
            font-weight: 700;
            margin-top: 5px;
        }

        /* Verification record cards */
        .kyc-card {
            background: #071B46;
            border: 1px solid #284A82;
            border-radius: 14px;
            padding: 18px 20px 14px 20px;
            margin: 0.5rem 0 0.8rem 0;
        }

        .kyc-id {
            color: #FFFFFF !important;
            font-size: 1rem;
            font-weight: 700;
            letter-spacing: 0.01em;
        }

        .kyc-label {
            color: #AFC4E2 !important;
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 2px;
        }

        .kyc-value {
            color: #FFFFFF !important;
            font-size: 0.98rem;
            font-weight: 500;
        }

        .status-success {
            display: inline-block;
            background: #123F35;
            border: 1px solid #2C806D;
            color: #B7F7E8 !important;
            border-radius: 999px;
            padding: 5px 11px;
            font-size: 0.78rem;
            font-weight: 700;
        }

        .status-review {
            display: inline-block;
            background: #3D334C;
            border: 1px solid #75658A;
            color: #F6E9A9 !important;
            border-radius: 999px;
            padding: 5px 11px;
            font-size: 0.78rem;
            font-weight: 700;
        }

        .evidence-available {
            color: #BFE7FF !important;
            font-weight: 600;
        }

        .evidence-missing {
            color: #FFD0D0 !important;
            font-weight: 600;
        }

        /* Detail information cards */
        .detail-label {
            color: #AFC4E2 !important;
            font-size: 0.78rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .detail-value {
            color: #FFFFFF !important;
            font-size: 1rem;
            font-weight: 500;
        }

        /* Mobile */
        @media (max-width: 768px) {
            .admin-stat {
                min-height: 88px;
                padding: 12px 14px;
            }

            .admin-stat-value {
                font-size: 1.55rem;
            }

            .kyc-card {
                padding: 14px;
            }

            .kyc-value {
                font-size: 0.92rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("🧑‍💼 VERISYNC Admin Dashboard")
    st.caption(
        "E-KYC monitoring, verification review and evidence management."
    )

    # ---------------------------------------------------------
    # DATA MANAGEMENT
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    with st.expander("🗑️ Data Management", expanded=False):
        st.warning(
            "Deleted KYC records and their locally stored verification "
            "evidence cannot be recovered from this application."
        )

        confirm_all = st.checkbox(
            "I understand that deleting all records is permanent.",
            key="confirm_delete_all",
        )

        if st.button(
            "DELETE ALL KYC DATA",
            type="secondary",
            disabled=not confirm_all,
            key="delete_all_kyc_data",
        ):
            count = _delete_all_records()

            st.session_state.selected_verification = None
            st.success(
                f"{count} KYC record(s) and their stored evidence were deleted."
            )
            st.rerun()

    # ---------------------------------------------------------
    # SEARCH + SUMMARY
    # ---------------------------------------------------------
    all_records = get_recent_kycs(limit=1000)

    total_count = len(all_records)
    successful_count = sum(
        1 for item in all_records
        if _record_value(item, "status") == "SUCCESSFUL"
    )
    review_count = sum(
        1 for item in all_records
        if _record_value(item, "status") != "SUCCESSFUL"
    )

    st.subheader("📊 Verification Overview")

    s1, s2, s3 = st.columns(3)

    with s1:
        st.markdown(
            f"""
            <div class="admin-stat">
                <div class="admin-stat-label">Total Records</div>
                <div class="admin-stat-value">{total_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with s2:
        st.markdown(
            f"""
            <div class="admin-stat">
                <div class="admin-stat-label">Successful</div>
                <div class="admin-stat-value">{successful_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with s3:
        st.markdown(
            f"""
            <div class="admin-stat">
                <div class="admin-stat-label">Requires Review</div>
                <div class="admin-stat-value">{review_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    st.subheader("🔎 Search Verification Records")

    search_query = st.text_input(
        "Search by name, phone number or verification ID",
        placeholder="Enter name, phone number or verification ID...",
        label_visibility="collapsed",
    )

    f1, f2 = st.columns([3, 1])

    with f1:
        st.caption("Search across customer and verification details.")

    with f2:
        status_filter = st.selectbox(
            "Status",
            ["All", "SUCCESSFUL", "REVIEW"],
            label_visibility="collapsed",
            key="admin_status_filter",
        )

    records = (
        search_kycs(search_query.strip())
        if search_query.strip()
        else get_recent_kycs(limit=20)
    )

    if status_filter != "All":
        records = [
            item for item in records
            if _record_value(item, "status") == status_filter
        ]

    st.caption(f"{len(records)} verification record(s)")

    if not records:
        st.info("No verification records match your search.")
        return

    st.subheader("📋 Recent Verifications")

    for record in records:
        verification_id = record["verification_id"]

        full_name = _record_value(record, "full_name") or "Unknown User"
        phone_number = _record_value(record, "phone_number") or "Not available"
        timestamp = _record_value(record, "timestamp") or "Not available"
        video_path = _record_value(record, "video_path")

        video_available = bool(
            video_path and os.path.exists(video_path)
        )

        is_successful = _record_value(record, "status") == "SUCCESSFUL"

        status_html = (
            '<span class="status-success">● SUCCESSFUL</span>'
            if is_successful
            else '<span class="status-review">● REQUIRES REVIEW</span>'
        )

        evidence_html = (
            '<span class="evidence-available">● Video available</span>'
            if video_available
            else '<span class="evidence-missing">● Video unavailable</span>'
        )

        st.markdown(
            f"""
            <div class="kyc-card">
                <div class="kyc-id">VERIFICATION ID · {verification_id}</div>
                <div style="margin-top:7px;">{status_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        d1, d2, d3 = st.columns([2.2, 1.8, 1.7])

        with d1:
            st.markdown(
                '<div class="kyc-label">Customer</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="kyc-value">👤 {full_name}</div>',
                unsafe_allow_html=True,
            )

        with d2:
            st.markdown(
                '<div class="kyc-label">Mobile</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="kyc-value">📱 {phone_number}</div>',
                unsafe_allow_html=True,
            )

        with d3:
            st.markdown(
                '<div class="kyc-label">Evidence</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                evidence_html,
                unsafe_allow_html=True,
            )

        e1, e2 = st.columns([3.2, 1])

        with e1:
            st.markdown(
                '<div class="kyc-label">Verification Time</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="kyc-value">🕐 {timestamp}</div>',
                unsafe_allow_html=True,
            )

        with e2:
            if st.button(
                "VIEW VERIFICATION →",
                key=f"view_{verification_id}",
                use_container_width=True,
            ):
                st.session_state.selected_verification = verification_id
                st.session_state.confirm_delete_selected = False
                st.rerun()

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    selected_id = st.session_state.get("selected_verification")

    if not selected_id:
        return

    record = get_kyc_by_id(selected_id)

    if not record:
        st.session_state.selected_verification = None
        st.info("This KYC record no longer exists.")
        return

    st.divider()

    st.title("🔍 Verification Details")
    st.caption(f"Reviewing verification record: {selected_id}")

    close_col, delete_col = st.columns([4, 1])

    with close_col:
        if st.button("← CLOSE DETAILS"):
            st.session_state.selected_verification = None
            st.session_state.confirm_delete_selected = False
            st.rerun()

    with delete_col:
        if st.button(
            "🗑️ DELETE",
            key=f"delete_{selected_id}",
        ):
            st.session_state.confirm_delete_selected = True
            st.rerun()

    if st.session_state.get(
        "confirm_delete_selected",
        False,
    ):
        st.error(
            "Delete this KYC record and all locally stored evidence?"
        )

        st.caption(
            f"Verification ID: {selected_id}"
        )

        confirm_col, cancel_col = st.columns(2)

        with confirm_col:
            if st.button(
                "YES, DELETE PERMANENTLY",
                type="primary",
                key=f"confirm_delete_{selected_id}",
                use_container_width=True,
            ):
                if _delete_selected_record(selected_id):
                    st.session_state.selected_verification = None
                    st.session_state.confirm_delete_selected = False
                    st.success(
                        "KYC record and stored evidence deleted successfully."
                    )
                    st.rerun()
                else:
                    st.error(
                        "The selected KYC record could not be found."
                    )

        with cancel_col:
            if st.button(
                "CANCEL",
                key=f"cancel_delete_{selected_id}",
                use_container_width=True,
            ):
                st.session_state.confirm_delete_selected = False
                st.rerun()

    st.subheader("👤 User Information")

    c1, c2 = st.columns(2)

    with c1:
        st.write("**User Name**")
        st.info(_record_value(record, "full_name") or "Unknown User")

        st.write("**Phone Number**")
        st.info(_record_value(record, "phone_number") or "Not available")

        st.write("**Masked Aadhaar**")
        st.info(_record_value(record, "masked_aadhaar") or "Not Available")

    with c2:
        st.write("**Verification ID**")
        st.info(record["verification_id"])

        st.write("**Timestamp**")
        st.info(record["timestamp"])

        st.write("**E-KYC Status**")
        if record["status"] == "SUCCESSFUL":
            st.success("✓ SUCCESSFUL")
        else:
            st.warning("⚠ REVIEW")

    st.subheader("🖥️ System Status")

    if (record["system_status"] or "").lower() == "operational":
        st.success("🟢 Operational")
    else:
        st.warning(record["system_status"] or "Unknown")

    if record["failure_reason"]:
        st.subheader("⚠️ Verification Reason")
        st.warning(record["failure_reason"])

    video_path = record["video_path"]
    audio_path = record["audio_path"]

    st.subheader("🎥 Synchronized E-KYC Evidence")

    synchronized_path = _get_synchronized_av_path(
        video_path,
        audio_path,
    )

    if synchronized_path and os.path.exists(synchronized_path):
        st.info(
            "▶️ Press Play once. The recorded video and microphone audio "
            "are integrated into the same evidence file and play together."
        )

        try:
            with open(synchronized_path, "rb") as file:
                st.video(
                    file.read(),
                    format="video/mp4",
                )
        except Exception as error:
            st.error("Unable to load synchronized video/audio evidence.")
            st.caption(str(error))

    elif video_path and os.path.exists(video_path):
        # Graceful fallback when FFmpeg is unavailable on the deployment.
        browser_video_path = _get_browser_video_path(video_path)

        st.warning(
            "Synchronized playback could not be generated on this deployment. "
            "The video is available below; audio is provided separately."
        )

        try:
            with open(browser_video_path, "rb") as file:
                st.video(
                    file.read(),
                    format="video/mp4",
                )
        except Exception as error:
            st.error("Unable to load recorded video.")
            st.caption(str(error))

        if audio_path and os.path.exists(audio_path):
            st.subheader("🎙️ Recorded Audio")
            try:
                with open(audio_path, "rb") as file:
                    st.audio(
                        file.read(),
                        format="audio/wav",
                    )
            except Exception as error:
                st.warning("Audio could not be loaded.")
                st.caption(str(error))

    else:
        st.info("Recorded video is not available.")

    analysis = _load_sync_result(video_path)

    st.caption(
        "The synchronized evidence above is the same camera capture and "
        "microphone recording used by the cross-modal analysis below."
    )

    st.subheader("📊 Cross-Modal Analysis")

    score = float(
        analysis.get(
            "score",
            record["cross_modal_score"] or 0,
        )
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Cross-Modal Score", f"{score:.2f}")

    with c2:
        st.metric(
            "Face Status",
            record["face_status"] or "N/A",
        )

    with c3:
        st.metric(
            "Audio Status",
            record["audio_status"] or "N/A",
        )

    with c4:
        st.metric(
            "Decision",
            analysis.get("decision", "N/A"),
        )

    st.subheader("📷 Capture Quality")

    quality_path = None

    if video_path:
        quality_path = os.path.join(
            os.path.dirname(video_path),
            "capture_quality.json",
        )

    quality = {}

    if quality_path and os.path.exists(quality_path):
        try:
            with open(
                quality_path,
                "r",
                encoding="utf-8",
            ) as file:
                quality = json.load(file)
        except Exception:
            quality = {}

    q1, q2, q3, q4 = st.columns(4)

    with q1:
        st.metric(
            "Resolution",
            (
                f"{quality.get('video_width', 0)} × "
                f"{quality.get('video_height', 0)}"
            ),
        )

    with q2:
        st.metric(
            "Face Visibility",
            f"{float(quality.get('face_ratio', 0)) * 100:.1f}%",
        )

    with q3:
        st.metric(
            "Brightness",
            f"{float(quality.get('average_brightness', 0)):.1f}",
        )

    with q4:
        st.metric(
            "Camera Quality",
            quality.get("camera_quality", "N/A"),
        )

    st.subheader("🔬 Technical Analysis")

    technical_items = [
        ("Zero-Lag Correlation", "zero_lag_correlation", ".3f"),
        ("Best Temporal Lag", "best_lag", ".3f"),
        ("Shifted Correlation", "shifted_correlation", ".3f"),
        ("Activity Overlap", "activity_overlap", ".3f"),
        ("Activity F1", "activity_f1", ".3f"),
        ("Speech Window 1", "speech_window_1", ".2f"),
        ("Silence Window", "silence_window", ".2f"),
        ("Speech Window 2", "speech_window_2", ".2f"),
        ("Audio Presence", "audio_presence", ".1f"),
        ("Speech Activity", "speech_activity", ".1f"),
        ("Pause Count", "pause_count", "d"),
        ("Pause Ratio", "pause_ratio", ".2f"),
        ("Breath/Pause Proxy", "breath_proxy_events", "d"),
        ("Voice Consistency", "voice_signature_similarity", ".3f"),
        ("Head Motion Activity", "head_motion_activity", ".2f"),
    ]

    columns = st.columns(3)

    for index, (label, key, fmt) in enumerate(technical_items):
        value = analysis.get(key, 0)

        with columns[index % 3]:
            try:
                if fmt == "d":
                    display_value = str(int(value))
                else:
                    display_value = format(float(value), fmt)
            except Exception:
                display_value = str(value)

            st.metric(label, display_value)

    if analysis.get("breath_signal_note"):
        st.caption(
            "Breath signal: "
            + str(analysis["breath_signal_note"])
        )

    if analysis.get("voice_signal_note"):
        st.caption(
            "Voice signal: "
            + str(analysis["voice_signal_note"])
        )

    with st.expander("View Complete Technical Parameters"):
        st.json(analysis)

    st.subheader("📝 Verification Summary")

    if record["status"] == "SUCCESSFUL":
        st.success(
            "E-KYC verification successfully completed."
        )
    else:
        st.warning(
            "E-KYC verification requires review."
        )
