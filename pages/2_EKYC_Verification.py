import os
import json
import time
import threading
import uuid
import shutil
import subprocess
from datetime import datetime

import av
import cv2
import numpy as np
import pandas as pd
import streamlit as st

from scipy.io import wavfile
from scipy.signal import correlate

try:
    from twilio.rest import Client as TwilioClient
except Exception:
    TwilioClient = None

from streamlit_webrtc import (
    webrtc_streamer,
    VideoProcessorBase,
    AudioProcessorBase,
    WebRtcMode,
)

from database import create_kyc_record


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="VERISYNC E-KYC Verification",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =========================================================
# UI STYLING
# =========================================================

st.markdown(
    """
    <style>
    html, body,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    .stApp {
        background: #000052 !important;
        color: #ffffff !important;
    }

    [data-testid="stHeader"] {
        background: #000052 !important;
    }

    [data-testid="stSidebar"],
    [data-testid="stSidebarNav"],
    [data-testid="collapsedControl"] {
        display: none !important;
    }

    .block-container {
        max-width: 1200px;
        padding-top: 4.5rem !important;
        padding-bottom: 2.2rem !important;
    }

    .vs-topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        min-height: 48px;
        margin-bottom: 1rem;
        position: relative;
        z-index: 10;
    }

    [data-testid="stHeader"] {
        z-index: 1000 !important;
    }

    div[data-testid="stButton"] > button {
        box-sizing: border-box !important;
        line-height: 1 !important;
    }

    .vs-brand {
        color: #72c8ff;
        font-weight: 800;
        letter-spacing: .04em;
    }

    .vs-panel {
        background: rgba(4, 4, 55, .82);
        border: 1px solid rgba(140, 190, 255, .20);
        border-radius: 15px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }

    .vs-challenge {
        text-align: center;
        padding: 1rem;
        border-radius: 14px;
        background: rgba(10, 10, 90, .94);
        border: 1px solid rgba(124,200,255,.25);
    }

    .vs-small {
        color: #b9c8e7;
        font-size: .84rem;
    }

    .camera-note {
        text-align: center;
        color: #b9c8e7;
        font-size: .82rem;
        margin-top: .4rem;
    }

    .stButton > button {
        min-height: 44px;
        border-radius: 10px;
        font-weight: 700;
    }

    @media (max-width: 700px) {
        .block-container {
            padding-left: .8rem !important;
            padding-right: .8rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# PATHS / CONSTANTS
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

CAPTURE_DIR = os.path.join(
    BASE_DIR,
    "captures",
)

MODEL_PATH = os.path.join(
    BASE_DIR,
    "models",
    "face_landmarker.task",
)

os.makedirs(CAPTURE_DIR, exist_ok=True)


VIDEO_PATH = None
AUDIO_PATH = None
EVIDENCE_PATH = None
LIP_PATH = None
FACE_PATH = None
SYNC_PATH = None
QUALITY_PATH = None


DURATION = 10
FPS = 15
MAX_VIDEO_FRAMES = 300

CHALLENGE_CODE = 4721

GRID_HZ = 20
MAX_LAG = 0.75

CAMERA_COMPONENT_KEY = "verisync-ekyc-auto"


# Mobile-friendly camera quality limits.
MIN_WIDTH = 320
MIN_HEIGHT = 240


# =========================================================
# TWILIO / WEBRTC CONFIGURATION
# =========================================================

@st.cache_resource(ttl=3000)
def get_rtc_configuration():
    """
    Load Twilio TURN credentials when available.

    STUN fallback is intentionally retained so that the existing
    working WebRTC deployment is not broken if Twilio temporarily
    becomes unavailable.
    """

    if TwilioClient is None:
        return {
            "iceServers": [
                {
                    "urls": [
                        "stun:stun.l.google.com:19302"
                    ]
                }
            ]
        }, "STUN fallback: Twilio package unavailable."

    sid = str(
        st.secrets.get(
            "TWILIO_ACCOUNT_SID",
            "",
        )
    ).strip()

    token = str(
        st.secrets.get(
            "TWILIO_AUTH_TOKEN",
            "",
        )
    ).strip()

    if not sid or not token:
        return {
            "iceServers": [
                {
                    "urls": [
                        "stun:stun.l.google.com:19302"
                    ]
                }
            ]
        }, "STUN fallback: Twilio TURN credentials are missing."

    try:
        client = TwilioClient(
            sid,
            token,
        )

        response = client.tokens.create(
            ttl=3600
        )

        ice_servers = []

        for server in (
            getattr(
                response,
                "ice_servers",
                [],
            )
            or []
        ):
            urls = server.get("urls")

            if not urls:
                continue

            entry = {
                "urls": urls
            }

            if server.get("username"):
                entry["username"] = server[
                    "username"
                ]

            if server.get("credential"):
                entry["credential"] = server[
                    "credential"
                ]

            ice_servers.append(entry)

        if not ice_servers:
            raise RuntimeError(
                "Twilio returned no ICE servers."
            )

        return (
            {
                "iceServers": ice_servers
            },
            "Twilio TURN loaded.",
        )

    except Exception as error:
        return {
            "iceServers": [
                {
                    "urls": [
                        "stun:stun.l.google.com:19302"
                    ]
                }
            ]
        }, f"STUN fallback: {error}"


# =========================================================
# CAPTURE PATHS
# =========================================================

def set_capture_paths(verification_id):

    global VIDEO_PATH
    global AUDIO_PATH
    global EVIDENCE_PATH
    global LIP_PATH
    global FACE_PATH
    global SYNC_PATH
    global QUALITY_PATH

    verification_dir = os.path.join(
        CAPTURE_DIR,
        verification_id,
    )

    os.makedirs(
        verification_dir,
        exist_ok=True,
    )

    VIDEO_PATH = os.path.join(
        verification_dir,
        "video.mp4",
    )

    AUDIO_PATH = os.path.join(
        verification_dir,
        "audio.wav",
    )

    # Final synchronized evidence file.
    EVIDENCE_PATH = os.path.join(
        verification_dir,
        "evidence.mp4",
    )

    LIP_PATH = os.path.join(
        verification_dir,
        "lip_signal.csv",
    )

    FACE_PATH = os.path.join(
        verification_dir,
        "face_status.json",
    )

    SYNC_PATH = os.path.join(
        verification_dir,
        "sync_result.json",
    )

    QUALITY_PATH = os.path.join(
        verification_dir,
        "capture_quality.json",
    )


# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "verification_id": None,
    "verification_started": False,
    "verification_finished": False,
    "database_saved": False,
    "final_decision": None,
    "final_reason": None,
    "camera_session_key": CAMERA_COMPONENT_KEY,
    "capture_complete": False,
    "capture_clock_initialized": False,
}

for key, value in defaults.items():

    if key not in st.session_state:
        st.session_state[key] = value


if st.session_state.get(
    "verification_id"
):

    set_capture_paths(
        st.session_state.verification_id
    )


# =========================================================
# VIDEO PROCESSOR
# =========================================================

class LipTrackingProcessor(VideoProcessorBase):

    def __init__(self):

        self.frames = []
        self.lip_values = []
        self.head_values = []
        self.timestamps = []

        self.face_detected_frames = 0
        self.total_processed_frames = 0

        self.width = 0
        self.height = 0

        self.brightness_values = []
        self.sharpness_values = []
        self.face_size_values = []

        self.previous_nose = None

        self.start_time = time.time()
        self.capture_start_time = self.start_time

        self.lock = threading.Lock()

        self.landmarker = None

    def reset_capture(self, capture_start_time):

        with self.lock:

            self.frames = []
            self.lip_values = []
            self.head_values = []
            self.timestamps = []

            self.face_detected_frames = 0
            self.total_processed_frames = 0

            self.width = 0
            self.height = 0

            self.brightness_values = []
            self.sharpness_values = []
            self.face_size_values = []

            self.previous_nose = None
            self.capture_start_time = capture_start_time
            self.start_time = capture_start_time

        try:

            if os.path.exists(
                MODEL_PATH
            ):

                from mediapipe.tasks import python
                from mediapipe.tasks.python import vision

                base_options = (
                    python.BaseOptions(
                        model_asset_path=MODEL_PATH
                    )
                )

                options = (
                    vision.FaceLandmarkerOptions(
                        base_options=base_options,
                        running_mode=(
                            vision.RunningMode.IMAGE
                        ),
                        num_faces=1,
                        min_face_detection_confidence=0.5,
                        min_face_presence_confidence=0.5,
                        min_tracking_confidence=0.5,
                    )
                )

                self.landmarker = (
                    vision.FaceLandmarker
                    .create_from_options(
                        options
                    )
                )

        except Exception:

            self.landmarker = None


    def recv(self, frame):

        image = frame.to_ndarray(
            format="bgr24"
        )

        current_time = (
            time.time()
            - self.capture_start_time
        )

        height, width = image.shape[:2]

        self.width = width
        self.height = height

        with self.lock:

            self.total_processed_frames += 1

            if (
                len(self.frames)
                < MAX_VIDEO_FRAMES
            ):

                self.frames.append(
                    image.copy()
                )


        # Analyze every second frame.
        if (
            self.total_processed_frames
            % 2
            == 0
        ):

            gray = cv2.cvtColor(
                image,
                cv2.COLOR_BGR2GRAY,
            )

            brightness = float(
                np.mean(gray)
            )

            sharpness = float(
                cv2.Laplacian(
                    gray,
                    cv2.CV_64F,
                ).var()
            )

            rgb = cv2.cvtColor(
                image,
                cv2.COLOR_BGR2RGB,
            )

            face_found = False
            lip_value = 0.0
            head_value = 0.0
            face_size = 0.0

            try:

                if self.landmarker:

                    import mediapipe as mp

                    mp_image = mp.Image(
                        image_format=(
                            mp.ImageFormat.SRGB
                        ),
                        data=rgb,
                    )

                    result = (
                        self.landmarker.detect(
                            mp_image
                        )
                    )

                    if result.face_landmarks:

                        face_found = True

                        landmarks = (
                            result.face_landmarks[0]
                        )

                        mouth_indices = [
                            61, 146, 91, 181,
                            84, 17, 314, 405,
                            321, 375, 291, 308,
                            324, 318, 402, 317,
                            14, 87, 178, 88,
                            95, 78, 191, 80,
                            81, 82, 13, 312,
                            311, 310, 415,
                        ]

                        xs = []
                        ys = []

                        for index in mouth_indices:

                            if index < len(
                                landmarks
                            ):

                                x = int(
                                    landmarks[
                                        index
                                    ].x
                                    * width
                                )

                                y = int(
                                    landmarks[
                                        index
                                    ].y
                                    * height
                                )

                                xs.append(x)
                                ys.append(y)


                        if xs and ys:

                            lip_value = float(
                                max(ys)
                                - min(ys)
                            )

                            for x, y in zip(
                                xs,
                                ys,
                            ):

                                cv2.circle(
                                    image,
                                    (x, y),
                                    2,
                                    (0, 255, 255),
                                    -1,
                                )


                        all_x = np.array(
                            [
                                p.x
                                for p in landmarks
                            ]
                        )

                        all_y = np.array(
                            [
                                p.y
                                for p in landmarks
                            ]
                        )

                        min_x = float(
                            np.min(all_x)
                        )

                        max_x = float(
                            np.max(all_x)
                        )

                        min_y = float(
                            np.min(all_y)
                        )

                        max_y = float(
                            np.max(all_y)
                        )

                        face_size = max(
                            (
                                max_x - min_x
                            )
                            * (
                                max_y - min_y
                            ),
                            0.0,
                        )


                        nose = landmarks[1]

                        nose_xy = np.array(
                            [
                                nose.x,
                                nose.y,
                            ],
                            dtype=float,
                        )

                        if (
                            self.previous_nose
                            is not None
                        ):

                            head_value = float(
                                np.linalg.norm(
                                    nose_xy
                                    - self.previous_nose
                                )
                            )

                        self.previous_nose = (
                            nose_xy
                        )


                        x1 = max(
                            int(min_x * width),
                            0,
                        )

                        y1 = max(
                            int(min_y * height),
                            0,
                        )

                        x2 = min(
                            int(max_x * width),
                            width - 1,
                        )

                        y2 = min(
                            int(max_y * height),
                            height - 1,
                        )

                        cv2.rectangle(
                            image,
                            (x1, y1),
                            (x2, y2),
                            (0, 200, 255),
                            1,
                        )

            except Exception:

                face_found = False
                lip_value = 0.0
                head_value = 0.0
                face_size = 0.0


            if face_found:

                self.face_detected_frames += 1

                cv2.putText(
                    image,
                    "FACE DETECTED",
                    (20, 32),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0),
                    2,
                )

                cv2.putText(
                    image,
                    "LIP + HEAD TRACKING",
                    (20, 60),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 255),
                    2,
                )

            else:

                cv2.putText(
                    image,
                    "FACE NOT DETECTED",
                    (20, 32),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 0, 255),
                    2,
                )


            with self.lock:

                self.lip_values.append(
                    lip_value
                )

                self.head_values.append(
                    head_value
                )

                self.timestamps.append(
                    current_time
                )

                self.brightness_values.append(
                    brightness
                )

                self.sharpness_values.append(
                    sharpness
                )

                self.face_size_values.append(
                    face_size
                )


        return av.VideoFrame.from_ndarray(
            image,
            format="bgr24",
        )


# =========================================================
# AUDIO PROCESSOR
# =========================================================

class AudioRecorder(AudioProcessorBase):

    def __init__(self):

        self.samples = []

        self.sample_rate = 48000
        self.capture_start_time = time.time()

        self.lock = threading.Lock()


    def reset_capture(self, capture_start_time):

        with self.lock:

            self.samples = []
            self.capture_start_time = capture_start_time


    def recv(self, frame):

        try:

            audio = frame.to_ndarray()

            if audio.ndim > 1:

                audio = np.mean(
                    audio,
                    axis=0,
                )

            audio = audio.astype(
                np.float32
            )

            with self.lock:

                self.samples.extend(
                    audio.tolist()
                )

        except Exception:

            pass

        return frame


# =========================================================
# SAVE VIDEO
# =========================================================

def save_video(processor):

    """
    Save captured frames.

    FFmpeg is used when available to create browser-compatible
    H.264 MP4 output.
    """

    if (
        processor is None
        or VIDEO_PATH is None
    ):

        return False


    with processor.lock:

        frames = list(
            processor.frames
        )


    if not frames:

        return False


    height, width = (
        frames[0].shape[:2]
    )

    raw_path = (
        VIDEO_PATH
        + ".raw.mp4"
    )


    writer = cv2.VideoWriter(
        raw_path,
        cv2.VideoWriter_fourcc(
            *"mp4v"
        ),
        FPS,
        (width, height),
    )


    if not writer.isOpened():

        return False


    try:

        for frame in frames:

            writer.write(frame)

    finally:

        writer.release()


    if (
        not os.path.exists(raw_path)
        or os.path.getsize(raw_path) == 0
    ):

        return False


    ffmpeg_path = shutil.which(
        "ffmpeg"
    )


    if ffmpeg_path:

        temp_output = (
            VIDEO_PATH
            + ".h264.tmp.mp4"
        )

        command = [
            ffmpeg_path,
            "-y",
            "-i",
            raw_path,
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
            temp_output,
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
                and os.path.exists(
                    temp_output
                )
                and os.path.getsize(
                    temp_output
                ) > 0
            ):

                os.replace(
                    temp_output,
                    VIDEO_PATH,
                )

                os.remove(
                    raw_path
                )

                return True


            if os.path.exists(
                temp_output
            ):

                os.remove(
                    temp_output
                )


        except Exception:

            if os.path.exists(
                temp_output
            ):

                try:

                    os.remove(
                        temp_output
                    )

                except Exception:

                    pass


    try:

        os.replace(
            raw_path,
            VIDEO_PATH,
        )

    except Exception:

        return False


    return os.path.exists(
        VIDEO_PATH
    )


# =========================================================
# SAVE AUDIO
# =========================================================

def save_audio(processor):

    if (
        processor is None
        or AUDIO_PATH is None
    ):

        return False


    with processor.lock:

        samples = np.asarray(
            processor.samples,
            dtype=np.float32,
        )


    if len(samples) == 0:

        return False


    maximum = float(
        np.max(
            np.abs(samples)
        )
    )


    if maximum > 0:

        samples = (
            samples / maximum
        )


    samples = (
        samples * 32767
    ).astype(
        np.int16
    )


    wavfile.write(
        AUDIO_PATH,
        processor.sample_rate,
        samples,
    )


    return os.path.exists(
        AUDIO_PATH
    )


# =========================================================
# CREATE SYNCHRONIZED EVIDENCE VIDEO
# =========================================================

def mux_evidence_video():

    """
    Combine the captured video and microphone audio into one
    browser-compatible MP4.

    Result:
        evidence.mp4

    This is the file used by the Admin dashboard so that selecting
    the evidence video also plays the captured audio.
    """

    if (
        not VIDEO_PATH
        or not AUDIO_PATH
        or not EVIDENCE_PATH
    ):

        return False


    if not os.path.exists(
        VIDEO_PATH
    ):

        return False


    if not os.path.exists(
        AUDIO_PATH
    ):

        return False


    ffmpeg_path = shutil.which(
        "ffmpeg"
    )


    if not ffmpeg_path:

        return False


    temp_output = (
        EVIDENCE_PATH
        + ".tmp.mp4"
    )


    command = [
        ffmpeg_path,
        "-y",
        "-i",
        VIDEO_PATH,
        "-i",
        AUDIO_PATH,
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
        "-shortest",
        "-movflags",
        "+faststart",
        temp_output,
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
            and os.path.exists(
                temp_output
            )
            and os.path.getsize(
                temp_output
            ) > 0
        ):

            os.replace(
                temp_output,
                EVIDENCE_PATH,
            )

            return True


        if os.path.exists(
            temp_output
        ):

            os.remove(
                temp_output
            )


    except Exception:

        if os.path.exists(
            temp_output
        ):

            try:

                os.remove(
                    temp_output
                )

            except Exception:

                pass


    return False


# =========================================================
# SAVE LIP / CAMERA DATA
# =========================================================

def save_lip_data(processor):

    if (
        processor is None
        or LIP_PATH is None
    ):

        return False


    with processor.lock:

        timestamps = list(
            processor.timestamps
        )

        lip_values = list(
            processor.lip_values
        )

        head_values = list(
            processor.head_values
        )

        brightness_values = list(
            processor.brightness_values
        )

        sharpness_values = list(
            processor.sharpness_values
        )

        face_size_values = list(
            processor.face_size_values
        )


    if not timestamps:

        return False


    length = min(
        len(timestamps),
        len(lip_values),
        len(head_values),
        len(brightness_values),
        len(sharpness_values),
        len(face_size_values),
    )


    pd.DataFrame(
        {
            "timestamp":
                timestamps[:length],

            "lip_signal":
                lip_values[:length],

            "head_motion":
                head_values[:length],

            "brightness":
                brightness_values[:length],

            "sharpness":
                sharpness_values[:length],

            "face_size_ratio":
                face_size_values[:length],
        }
    ).to_csv(
        LIP_PATH,
        index=False,
    )


    processed_face_checks = max(
        processor.total_processed_frames
        / 2,
        1,
    )


    face_ratio = (
        processor.face_detected_frames
        / processed_face_checks
    )


    quality = {
        "video_width":
            int(processor.width),

        "video_height":
            int(processor.height),

        "face_ratio":
            float(face_ratio),

        "average_brightness":
            float(
                np.mean(
                    brightness_values
                )
                if brightness_values
                else 0
            ),

        "average_sharpness":
            float(
                np.mean(
                    sharpness_values
                )
                if sharpness_values
                else 0
            ),

        "average_face_size_ratio":
            float(
                np.mean(
                    face_size_values
                )
                if face_size_values
                else 0
            ),

        "camera_resolution_acceptable":
            bool(
                processor.width
                >= MIN_WIDTH
                and
                processor.height
                >= MIN_HEIGHT
            ),
    }


    quality["camera_quality"] = (
        "GOOD"
        if (
            quality[
                "camera_resolution_acceptable"
            ]
            and quality["face_ratio"]
            >= 0.50
            and quality[
                "average_face_size_ratio"
            ]
            >= 0.05
            and 20
            <= quality[
                "average_brightness"
            ]
            <= 240
            and quality[
                "average_sharpness"
            ]
            >= 15
        )
        else "CHECK"
    )


    with open(
        FACE_PATH,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            {
                "face_detected_frames":
                    processor.face_detected_frames,

                "processed_frames":
                    processor.total_processed_frames,

                "face_ratio":
                    float(face_ratio),

                "camera_width":
                    processor.width,

                "camera_height":
                    processor.height,

                "camera_quality":
                    quality[
                        "camera_quality"
                    ],
            },
            file,
            indent=2,
        )


    with open(
        QUALITY_PATH,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            quality,
            file,
            indent=2,
        )


    return True


# =========================================================
# AUDIO FEATURES
# =========================================================

def audio_features(
    audio,
    sample_rate,
):

    audio = audio.astype(
        np.float32
    )


    if len(audio) == 0:

        return {
            "audio_presence": 0.0,
            "speech_activity": 0.0,
            "pause_count": 0,
            "pause_ratio": 1.0,
            "breath_proxy_events": 0,
            "voice_signature": [],
        }


    maximum = float(
        np.max(
            np.abs(audio)
        )
    )


    normalized = (
        audio / maximum
        if maximum > 0
        else audio
    )


    window = max(
        int(
            sample_rate
            / GRID_HZ
        ),
        1,
    )


    rms = []
    zcr = []
    spectral_centroid = []


    for start in range(
        0,
        len(normalized),
        window,
    ):

        chunk = normalized[
            start:
            start + window
        ]


        if len(chunk) < max(
            16,
            window // 4,
        ):

            continue


        rms.append(
            float(
                np.sqrt(
                    np.mean(
                        chunk ** 2
                    )
                )
            )
        )


        signs = np.sign(
            chunk
        )

        zcr.append(
            float(
                np.mean(
                    signs[1:]
                    != signs[:-1]
                )
            )
        )


        spectrum = np.abs(
            np.fft.rfft(
                chunk
            )
        )


        freqs = np.fft.rfftfreq(
            len(chunk),
            1 / sample_rate,
        )


        denom = (
            float(
                np.sum(
                    spectrum
                )
            )
            + 1e-9
        )


        spectral_centroid.append(
            float(
                np.sum(
                    freqs
                    * spectrum
                )
                / denom
            )
        )


    rms = np.asarray(
        rms,
        dtype=float,
    )

    zcr = np.asarray(
        zcr,
        dtype=float,
    )

    spectral_centroid = np.asarray(
        spectral_centroid,
        dtype=float,
    )


    if len(rms) < 5:

        return {
            "audio_presence": 0.0,
            "speech_activity": 0.0,
            "pause_count": 0,
            "pause_ratio": 1.0,
            "breath_proxy_events": 0,
            "voice_signature": [],
            "rms_signal": rms,
            "speech_mask":
                np.zeros(
                    len(rms),
                    dtype=bool,
                ),
            "zcr": zcr,
            "spectral_centroid":
                spectral_centroid,
            "breath_proxy_mask":
                np.zeros(
                    len(rms),
                    dtype=bool,
                ),
        }


    noise_floor = float(
        np.percentile(
            rms,
            20,
        )
    )


    upper = float(
        np.percentile(
            rms,
            85,
        )
    )


    dynamic_range = max(
        upper - noise_floor,
        1e-6,
    )


    threshold = (
        noise_floor
        + 0.22
        * dynamic_range
    )


    speech_mask = (
        rms > threshold
    )


    # Remove isolated noise and fill tiny speech gaps.
    for i in range(
        1,
        len(speech_mask) - 1,
    ):

        if (
            speech_mask[i - 1]
            and speech_mask[i + 1]
        ):

            speech_mask[i] = True


    speech_activity = float(
        np.mean(
            speech_mask
        )
        * 100
    )


    pause_ratio = float(
        1.0
        - np.mean(
            speech_mask
        )
    )


    pauses = 0

    in_pause = False
    pause_len = 0


    for active in speech_mask:

        if not active:

            if not in_pause:

                in_pause = True
                pause_len = 1

            else:

                pause_len += 1

        else:

            if (
                in_pause
                and
                pause_len
                >= int(
                    GRID_HZ
                    * 0.25
                )
            ):

                pauses += 1

            in_pause = False
            pause_len = 0


    if (
        in_pause
        and
        pause_len
        >= int(
            GRID_HZ
            * 0.25
        )
    ):

        pauses += 1


    # Lightweight pause/breath proxy.
    zcr_norm = (
        (
            zcr
            - np.min(zcr)
        )
        /
        (
            np.ptp(zcr)
            + 1e-9
        )
    )


    centroid_norm = (
        (
            spectral_centroid
            - np.min(
                spectral_centroid
            )
        )
        /
        (
            np.ptp(
                spectral_centroid
            )
            + 1e-9
        )
    )


    breath_proxy_mask = (
        (~speech_mask)
        &
        (
            0.5 * zcr_norm
            +
            0.5 * centroid_norm
            > 0.55
        )
    )


    breath_proxy_events = 0

    in_event = False
    event_len = 0


    for item in breath_proxy_mask:

        if item:

            if not in_event:

                in_event = True
                event_len = 1

            else:

                event_len += 1

        else:

            if (
                in_event
                and
                event_len >= 2
            ):

                breath_proxy_events += 1

            in_event = False
            event_len = 0


    if (
        in_event
        and
        event_len >= 2
    ):

        breath_proxy_events += 1


    speech_chunks = []


    for i, active in enumerate(
        speech_mask
    ):

        if (
            active
            and
            i
            < len(
                spectral_centroid
            )
        ):

            speech_chunks.append(
                [
                    float(
                        rms[i]
                    ),
                    float(
                        zcr[i]
                    ),
                    float(
                        spectral_centroid[i]
                    ),
                ]
            )


    if speech_chunks:

        signature = (
            np.mean(
                np.asarray(
                    speech_chunks,
                    dtype=float,
                ),
                axis=0,
            )
            .tolist()
        )

    else:

        signature = []


    return {
        "audio_presence":
            float(
                np.mean(
                    rms > noise_floor
                )
                * 100
            ),

        "speech_activity":
            speech_activity,

        "pause_count":
            int(pauses),

        "pause_ratio":
            pause_ratio,

        "breath_proxy_events":
            int(
                breath_proxy_events
            ),

        "voice_signature":
            signature,

        "rms_signal":
            rms,

        "speech_mask":
            speech_mask,

        "zcr":
            zcr,

        "spectral_centroid":
            spectral_centroid,

        "breath_proxy_mask":
            breath_proxy_mask,
    }


# =========================================================
# COSINE SIMILARITY
# =========================================================

def cosine_similarity(
    a,
    b,
):

    if not a or not b:

        return 0.0


    a = np.asarray(
        a,
        dtype=float,
    )

    b = np.asarray(
        b,
        dtype=float,
    )


    denominator = (
        np.linalg.norm(a)
        *
        np.linalg.norm(b)
    )


    if denominator <= 0:

        return 0.0


    return float(
        np.dot(a, b)
        /
        denominator
    )


# =========================================================
# CROSS-MODAL ANALYSIS
# =========================================================

def analyze_cross_modal():

    """
    Challenge-aware cross-modal analysis.

    This MVP does not claim speech recognition.

    It verifies:
    - expected speech windows
    - expected silence window
    - audio activity
    - facial/lip activity
    - temporal consistency
    - shifted alignment risk
    - lightweight voice consistency
    """

    result = {
        "score": 0.0,
        "zero_lag_correlation": 0.0,
        "best_lag": 0.0,
        "shifted_correlation": 0.0,
        "activity_overlap": 0.0,
        "audio_presence": 0.0,
        "speech_activity": 0.0,
        "pause_count": 0,
        "pause_ratio": 1.0,
        "breath_proxy_events": 0,
        "voice_signature_similarity": 0.0,
        "voice_consistency_quality": 0.0,
        "breath_alignment_quality": 0.0,
        "breath_in_window_ratio": None,
        "head_motion_activity": 0.0,
        "speech_window_1": 0.0,
        "silence_window": 0.0,
        "speech_window_2": 0.0,
        "speech_window_compliance": 0.0,
        "silence_compliance": 0.0,
        "temporal_consistency": 0.0,
        "decision": "REVIEW",
    }


    try:

        if (
            not LIP_PATH
            or not AUDIO_PATH
            or not os.path.exists(
                LIP_PATH
            )
            or not os.path.exists(
                AUDIO_PATH
            )
        ):

            return result


        lip_df = pd.read_csv(
            LIP_PATH
        )


        if (
            lip_df.empty
            or
            "timestamp"
            not in lip_df.columns
        ):

            return result


        timestamps = (
            lip_df[
                "timestamp"
            ].to_numpy(float)
        )


        lip = (
            lip_df[
                "lip_signal"
            ].to_numpy(float)
        )


        head_motion = (

            lip_df[
                "head_motion"
            ].to_numpy(float)

            if
            "head_motion"
            in lip_df.columns

            else
            np.zeros_like(
                lip
            )
        )


        sample_rate, audio = (
            wavfile.read(
                AUDIO_PATH
            )
        )


        if audio.ndim > 1:

            audio = np.mean(
                audio,
                axis=1,
            )


        audio = audio.astype(
            np.float32
        )


        if len(audio) == 0:

            return result


        features = audio_features(
            audio,
            sample_rate,
        )


        rms = features[
            "rms_signal"
        ]


        if len(rms) < 5:

            return result


        audio_times = (
            np.arange(
                len(rms)
            )
            / GRID_HZ
        )


        audio_norm = (

            (
                rms
                - np.mean(rms)
            )
            /
            np.std(rms)

            if
            np.std(rms) > 0

            else
            np.zeros_like(
                rms
            )
        )


        lip_movement = (
            np.abs(
                np.gradient(
                    lip
                )
            )
        )


        if len(
            lip_movement
        ) >= 5:

            kernel = (
                np.ones(
                    5,
                    dtype=float,
                )
                / 5.0
            )

            lip_movement = (
                np.convolve(
                    lip_movement,
                    kernel,
                    mode="same",
                )
            )


        lip_norm = (

            (
                lip_movement
                - np.mean(
                    lip_movement
                )
            )
            /
            np.std(
                lip_movement
            )

            if
            np.std(
                lip_movement
            ) > 0

            else
            np.zeros_like(
                lip_movement
            )
        )


        start = max(
            float(
                np.min(
                    timestamps
                )
            ),
            float(
                np.min(
                    audio_times
                )
            ),
        )


        end = min(
            float(
                np.max(
                    timestamps
                )
            ),
            float(
                np.max(
                    audio_times
                )
            ),
        )


        if end <= start:

            return result


        grid = np.arange(
            start,
            end,
            1 / GRID_HZ,
        )


        if len(grid) < 20:

            return result


        lip_interp = np.interp(
            grid,
            timestamps,
            lip_norm,
        )


        audio_interp = np.interp(
            grid,
            audio_times,
            audio_norm,
        )


        lip_threshold = np.percentile(
            np.abs(
                lip_interp
            ),
            50,
        )


        audio_threshold = np.percentile(
            np.abs(
                audio_interp
            ),
            50,
        )


        lip_activity = (
            np.abs(
                lip_interp
            )
            >
            max(
                lip_threshold,
                0.15,
            )
        )


        audio_activity = (
            np.abs(
                audio_interp
            )
            >
            max(
                audio_threshold,
                0.20,
            )
        )


        def window_ratio(
            mask,
            low,
            high,
        ):

            window_mask = (
                (grid >= low)
                &
                (grid < high)
            )

            if not np.any(
                window_mask
            ):

                return 0.0

            return float(
                np.mean(
                    mask[
                        window_mask
                    ]
                )
            )


        speech_1_audio = (
            window_ratio(
                audio_activity,
                1.5,
                4.0,
            )
        )


        silence_audio = (
            window_ratio(
                audio_activity,
                4.0,
                5.5,
            )
        )


        speech_2_audio = (
            window_ratio(
                audio_activity,
                5.5,
                9.0,
            )
        )


        speech_1_lip = (
            window_ratio(
                lip_activity,
                1.5,
                4.0,
            )
        )


        speech_2_lip = (
            window_ratio(
                lip_activity,
                5.5,
                9.0,
            )
        )


        speech_1_ok = (
            speech_1_audio >= 0.18
        )


        speech_2_ok = (
            speech_2_audio >= 0.18
        )


        silence_ok = (
            silence_audio <= 0.58
        )


        speech_window_compliance = (
            (
                float(
                    speech_1_ok
                )
                +
                float(
                    speech_2_ok
                )
            )
            / 2.0
        )


        silence_compliance = (
            1.0
            if silence_ok
            else 0.0
        )


        union = np.logical_or(
            lip_activity,
            audio_activity,
        )


        intersection = (
            np.logical_and(
                lip_activity,
                audio_activity,
            )
        )


        activity_overlap = (

            float(
                np.sum(
                    intersection
                )
                /
                np.sum(
                    union
                )
            )

            if
            np.sum(
                union
            ) > 0

            else
            0.0
        )


        zero_corr = (

            float(
                np.corrcoef(
                    lip_interp,
                    audio_interp,
                )[0, 1]
            )

            if
            (
                np.std(
                    lip_interp
                ) > 0
                and
                np.std(
                    audio_interp
                ) > 0
            )

            else
            0.0
        )


        intersection_n = float(
            np.sum(
                intersection
            )
        )


        precision = (

            intersection_n
            /
            float(
                np.sum(
                    audio_activity
                )
            )

            if
            np.sum(
                audio_activity
            ) > 0

            else
            0.0
        )


        recall = (

            intersection_n
            /
            float(
                np.sum(
                    lip_activity
                )
            )

            if
            np.sum(
                lip_activity
            ) > 0

            else
            0.0
        )


        activity_f1 = (

            2
            * precision
            * recall
            /
            (
                precision
                + recall
            )

            if
            (
                precision
                + recall
            ) > 0

            else
            0.0
        )


        corr = correlate(
            lip_interp,
            audio_interp,
            mode="full",
        )


        lags = np.arange(
            -len(
                audio_interp
            )
            + 1,
            len(
                lip_interp
            ),
        )


        lag_seconds = (
            lags
            / GRID_HZ
        )


        valid = (
            np.abs(
                lag_seconds
            )
            <= MAX_LAG
        )


        if np.any(valid):

            valid_corr = (
                corr[valid]
            )

            denominator = (
                np.linalg.norm(
                    lip_interp
                )
                *
                np.linalg.norm(
                    audio_interp
                )
            )


            normalized = (

                valid_corr
                /
                denominator

                if denominator > 0

                else
                np.zeros_like(
                    valid_corr
                )
            )


            best_index = int(
                np.argmax(
                    np.abs(
                        normalized
                    )
                )
            )


            best_lag = float(
                lag_seconds[
                    valid
                ][
                    best_index
                ]
            )


            shifted_corr = float(
                np.clip(
                    normalized[
                        best_index
                    ],
                    -1,
                    1,
                )
            )

        else:

            best_lag = 0.0
            shifted_corr = 0.0


        lag_quality = max(
            0.0,
            1.0
            -
            max(
                abs(
                    best_lag
                )
                - 0.20,
                0.0,
            )
            / 0.55,
        )


        lag_quality = float(
            np.clip(
                lag_quality,
                0.0,
                1.0,
            )
        )


        temporal_consistency = (
            0.60
            * activity_f1
            +
            0.20
            * (
                (
                    shifted_corr
                    + 1
                )
                / 2
            )
            +
            0.20
            * lag_quality
        )


        head_activity = float(

            np.mean(
                head_motion
                >
                np.percentile(
                    head_motion,
                    65,
                )
            )

            if
            (
                len(
                    head_motion
                ) > 2
                and
                np.ptp(
                    head_motion
                ) > 0
            )

            else
            0.0
        )


        # Lightweight captured-voice consistency.
        voice_similarity = 0.0


        speech_indices = np.where(
            features[
                "speech_mask"
            ]
        )[0]


        if len(
            speech_indices
        ) >= 8:

            midpoint = (
                len(
                    speech_indices
                )
                // 2
            )


            first_idx = (
                speech_indices[
                    :midpoint
                ]
            )


            second_idx = (
                speech_indices[
                    midpoint:
                ]
            )


            first_sig = (
                np.mean(
                    np.column_stack(
                        [
                            features[
                                "rms_signal"
                            ][
                                first_idx
                            ],

                            features[
                                "zcr"
                            ][
                                first_idx
                            ],

                            features[
                                "spectral_centroid"
                            ][
                                first_idx
                            ],
                        ]
                    ),
                    axis=0,
                )
                .tolist()
            )


            second_sig = (
                np.mean(
                    np.column_stack(
                        [
                            features[
                                "rms_signal"
                            ][
                                second_idx
                            ],

                            features[
                                "zcr"
                            ][
                                second_idx
                            ],

                            features[
                                "spectral_centroid"
                            ][
                                second_idx
                            ],
                        ]
                    ),
                    axis=0,
                )
                .tolist()
            )


            voice_similarity = (
                cosine_similarity(
                    first_sig,
                    second_sig,
                )
            )


        zero_lag_quality = float(
            np.clip(
                max(
                    zero_corr,
                    0.0,
                ),
                0.0,
                1.0,
            )
        )


        overlap_quality = float(
            np.clip(
                activity_overlap
                / 0.35,
                0.0,
                1.0,
            )
        )


        # ---------------------------------------------------
        # Voice consistency quality (third signal: VOICE).
        # Rewards a captured voice that stays consistent across
        # the capture. Neutral when there is not enough speech
        # to measure this reliably, so short/quiet genuine
        # captures are not unfairly penalised.
        # ---------------------------------------------------
        if len(speech_indices) >= 8:

            voice_consistency_quality = float(
                np.clip(
                    voice_similarity,
                    0.0,
                    1.0,
                )
            )

        else:

            voice_consistency_quality = 0.6


        # ---------------------------------------------------
        # Breath-timing alignment quality (third named signal:
        # BREATH TIMING). A live human speaking the scripted
        # challenge naturally breathes in/around the mandated
        # silence window; a spliced face-swap + separately
        # cloned voice clip has no reason for its breath-like
        # audio events to line up with *this* capture's own
        # silence window. Neutral when no breath-proxy events
        # were detected at all (quiet room / good mic), since
        # absence of a proxy signal is not itself suspicious.
        # ---------------------------------------------------
        breath_proxy_mask = features.get(
            "breath_proxy_mask",
            np.zeros_like(rms, dtype=bool),
        )

        breath_window_low = 3.6
        breath_window_high = 5.9

        total_breath_events = float(
            np.sum(breath_proxy_mask)
        )

        if total_breath_events <= 0:

            breath_alignment_quality = 0.5
            breath_in_window_ratio = None

        else:

            breath_window_mask = (
                (audio_times >= breath_window_low)
                & (audio_times < breath_window_high)
            )

            breath_in_window = float(
                np.sum(
                    breath_proxy_mask
                    & breath_window_mask
                )
            )

            breath_in_window_ratio = (
                breath_in_window
                / total_breath_events
            )

            breath_alignment_quality = float(
                np.clip(
                    breath_in_window_ratio / 0.45,
                    0.0,
                    1.0,
                )
            )


        score = (
            35.0
            * temporal_consistency

            +
            20.0
            * speech_window_compliance

            +
            15.0
            * silence_compliance

            +
            10.0
            * overlap_quality

            +
            12.0
            * zero_lag_quality

            +
            4.0
            * voice_consistency_quality

            +
            4.0
            * breath_alignment_quality
        )


        score = float(
            np.clip(
                score,
                0.0,
                100.0,
            )
        )


        audio_ok = (
            features[
                "audio_presence"
            ]
            >= 8

            and

            features[
                "speech_activity"
            ]
            >= 8
        )


        speech_windows_ok = (
            speech_1_audio >= 0.20
            and
            speech_2_audio >= 0.20
        )


        silence_ok = (
            silence_audio <= 0.50
        )


        temporal_ok = (
            activity_f1 >= 0.20
            and
            temporal_consistency >= 0.40
            and
            (
                activity_overlap
                >= 0.10

                or

                zero_corr
                >= 0.10
            )
        )


        shifted_alignment_risk = bool(
            abs(
                best_lag
            )
            > 0.35

            and

            shifted_corr
            >
            zero_corr
            + 0.12
        )


        score_ok = (
            score >= 58
        )


        review_reasons = []


        if not audio_ok:

            review_reasons.append(
                "Insufficient speech/audio activity."
            )


        if not speech_windows_ok:

            review_reasons.append(
                "One or more required speech windows were not detected."
            )


        if not silence_ok:

            review_reasons.append(
                "Required silence window contains too much audio activity."
            )


        if not temporal_ok:

            review_reasons.append(
                "Lip movement and audio were not sufficiently aligned on the same timeline."
            )


        if shifted_alignment_risk:

            review_reasons.append(
                f"Best alignment required a {best_lag:+.2f}s timing shift."
            )


        if not score_ok:

            review_reasons.append(
                f"Cross-modal score {score:.1f} is below the automatic-pass threshold."
            )


        decision = (

            "PASS"

            if (
                audio_ok
                and
                speech_windows_ok
                and
                silence_ok
                and
                temporal_ok
                and
                not shifted_alignment_risk
                and
                score_ok
            )

            else
            "REVIEW"
        )


        return {

            "score":
                score,

            "zero_lag_correlation":
                zero_corr,

            "best_lag":
                best_lag,

            "shifted_correlation":
                shifted_corr,

            "activity_overlap":
                activity_overlap,

            "temporal_consistency":
                temporal_consistency,

            "audio_presence":
                float(
                    features[
                        "audio_presence"
                    ]
                ),

            "speech_activity":
                float(
                    features[
                        "speech_activity"
                    ]
                ),

            "pause_count":
                int(
                    features[
                        "pause_count"
                    ]
                ),

            "pause_ratio":
                float(
                    features[
                        "pause_ratio"
                    ]
                ),

            "breath_proxy_events":
                int(
                    features[
                        "breath_proxy_events"
                    ]
                ),

            "voice_signature_similarity":
                voice_similarity,

            "voice_consistency_quality":
                voice_consistency_quality,

            "breath_alignment_quality":
                breath_alignment_quality,

            "breath_in_window_ratio":
                breath_in_window_ratio,

            "head_motion_activity":
                head_activity,

            "speech_window_1":
                speech_1_audio,

            "silence_window":
                silence_audio,

            "speech_window_2":
                speech_2_audio,

            "speech_window_1_lip":
                speech_1_lip,

            "speech_window_2_lip":
                speech_2_lip,

            "speech_window_compliance":
                speech_window_compliance,

            "silence_compliance":
                silence_compliance,

            "activity_f1":
                activity_f1,

            "zero_lag_quality":
                zero_lag_quality,

            "overlap_quality":
                overlap_quality,

            "shifted_alignment_risk":
                shifted_alignment_risk,

            "audio_ok":
                audio_ok,

            "speech_windows_ok":
                speech_windows_ok,

            "silence_ok":
                silence_ok,

            "temporal_ok":
                temporal_ok,

            "score_ok":
                score_ok,

            "review_reasons":
                review_reasons,

            "decision":
                decision,

            "breath_signal_note":
                "Audio pause/breath proxy; not a physiological respiration measurement.",

            "voice_signal_note":
                "Lightweight captured-voice consistency signal; not bank-grade speaker authentication.",

            "challenge_note":
                "Speech-window timing is checked; exact words are not speech-to-text verified in this MVP.",
        }


    except Exception as error:

        result["error"] = str(
            error
        )

        return result


# =========================================================
# CAMERA VALIDATION
# =========================================================

def camera_validation(
    processor
):

    if processor is None:

        return (
            False,
            "Camera stream was not available.",
        )


    if (
        not VIDEO_PATH
        or
        not os.path.exists(
            VIDEO_PATH
        )
    ):

        return (
            False,
            "Camera video was not captured.",
        )


    if (
        processor.total_processed_frames
        < 20
    ):

        return (
            False,
            "Not enough camera frames were captured.",
        )


    processed_face_checks = max(
        processor.total_processed_frames
        / 2,
        1,
    )


    face_ratio = (
        processor.face_detected_frames
        /
        processed_face_checks
    )


    if face_ratio < 0.50:

        return (
            False,
            "Face was not continuously visible.",
        )


    if (
        processor.width
        < MIN_WIDTH
        or
        processor.height
        < MIN_HEIGHT
    ):

        return (
            False,
            (
                "The phone camera stream is too low-quality. "
                "Keep your face close and centered, allow camera access, "
                "and avoid switching apps while verification starts."
            ),
        )


    with processor.lock:

        avg_brightness = (
            float(
                np.mean(
                    processor.brightness_values
                )
            )
            if
            processor.brightness_values
            else
            0
        )


        avg_sharpness = (
            float(
                np.mean(
                    processor.sharpness_values
                )
            )
            if
            processor.sharpness_values
            else
            0
        )


        avg_face_size = (
            float(
                np.mean(
                    processor.face_size_values
                )
            )
            if
            processor.face_size_values
            else
            0
        )


    if (
        avg_brightness < 20
        or
        avg_brightness > 240
    ):

        return (
            False,
            (
                "Lighting is not suitable. "
                "Move to a brighter, evenly lit area."
            ),
        )


    if avg_sharpness < 15:

        return (
            False,
            (
                "Camera image is too blurry. "
                "Clean the camera lens and keep the device steady."
            ),
        )


    if avg_face_size < 0.05:

        return (
            False,
            (
                "Face is too small in the camera frame. "
                "Move closer to the camera."
            ),
        )


    return (
        True,
        "Camera quality and face visibility are acceptable.",
    )


# =========================================================
# DATABASE SAVE
# =========================================================

def save_database_record(
    final_decision,
    reason,
    result,
    camera_valid,
):

    if st.session_state.database_saved:

        return


    try:

        country_code = (
            st.session_state.get(
                "user_country_code",
                "",
            )
        )


        phone = (
            st.session_state.get(
                "user_phone",
                "",
            )
        )


        full_phone = (
            f"{country_code} {phone}"
        ).strip()


        # Keep PASS as SUCCESSFUL for the existing admin UI.
        # Store REVIEW separately instead of converting it to FAILED.
        database_status = (

            "SUCCESSFUL"

            if
            final_decision == "PASS"

            else
            "REVIEW"
        )


        audio_presence = float(
            result.get(
                "audio_presence",
                0,
            )
        )


        # Prefer the combined evidence file.
        # Fall back to the video-only file only if muxing failed.
        admin_video_path = (

            EVIDENCE_PATH

            if
            (
                EVIDENCE_PATH
                and
                os.path.exists(
                    EVIDENCE_PATH
                )
            )

            else

            (
                VIDEO_PATH
                if
                (
                    VIDEO_PATH
                    and
                    os.path.exists(
                        VIDEO_PATH
                    )
                )

                else
                None
            )
        )


        create_kyc_record(

            verification_id=
                st.session_state.verification_id,

            full_name=
                st.session_state.get(
                    "user_full_name",
                    "Unknown User",
                ),

            phone_number=
                full_phone,

            masked_aadhaar=
                st.session_state.get(
                    "user_aadhaar",
                    "Not Available",
                ),

            status=
                database_status,

            system_status=
                "Operational",

            failure_reason=
                reason,

            video_path=
                admin_video_path,

            audio_path=
                (
                    AUDIO_PATH
                    if
                    (
                        AUDIO_PATH
                        and
                        os.path.exists(
                            AUDIO_PATH
                        )
                    )
                    else
                    None
                ),

            cross_modal_score=
                float(
                    result.get(
                        "score",
                        0,
                    )
                ),

            face_status=
                (
                    "PASS"
                    if camera_valid
                    else "FAILED"
                ),

            audio_status=
                (
                    "PASS"
                    if audio_presence >= 15
                    else "FAILED"
                ),
        )


        st.session_state.database_saved = True


    except Exception as error:

        st.warning(
            "Verification completed, but the administrative record could not be saved."
        )

        st.caption(
            str(error)
        )


# =========================================================
# TOP BAR
# =========================================================

st.markdown(
    '<div class="vs-topbar">',
    unsafe_allow_html=True,
)


left, right = st.columns(
    [10, 1],
    vertical_alignment="center",
)


with left:

    st.markdown(
        '<div class="vs-brand">🛡️ VERISYNC</div>',
        unsafe_allow_html=True,
    )


with right:

    if st.button(
        "☰",
        key="ekyc_admin_menu",
        help="Open Admin Login",
    ):

        st.session_state.page = (
            "admin_login"
        )

        st.switch_page(
            "app.py"
        )


st.markdown(
    "</div>",
    unsafe_allow_html=True,
)


# =========================================================
# MEDIA CONSTRAINTS
# =========================================================

MEDIA_CONSTRAINTS = {

    "video": {

        "width": {
            "ideal": 640,
            "min": 320,
        },

        "height": {
            "ideal": 480,
            "min": 240,
        },

        "frameRate": {
            "ideal": 15,
            "min": 8,
            "max": 20,
        },

        "facingMode":
            "user",
    },

    "audio": {

        "echoCancellation":
            True,

        "noiseSuppression":
            True,

        "autoGainControl":
            True,
    },
}


# =========================================================
# WEBRTC CONFIG
# =========================================================

rtc_config, rtc_status = (
    get_rtc_configuration()
)


# =========================================================
# RESULT PAGE
# =========================================================

if st.session_state.verification_finished:

    final_decision = (
        st.session_state.final_decision
    )

    reason = (
        st.session_state.final_reason
    )


    if final_decision == "PASS":

        st.success(
            "✅ E-KYC SUCCESSFULLY COMPLETED"
        )

        st.subheader(
            "Your identity verification was completed successfully."
        )

    else:

        st.warning(
            "⚠️ E-KYC REQUIRES REVIEW"
        )

        st.subheader(
            "Verification was not completed automatically."
        )

        st.warning(
            f"Reason: {reason}"
        )


    st.success(
        "🟢 System Status: Operational"
    )


    st.caption(
        "Verification ID: "
        +
        str(
            st.session_state.verification_id
        )
    )


    # -----------------------------------------------------
    # FINAL CHECKLIST
    # -----------------------------------------------------

    st.markdown(
        "### Verification checklist"
    )


    checklist_left, checklist_right = (
        st.columns(2)
    )


    with checklist_left:

        st.success(
            "✓ Identity details verified"
        )

        st.success(
            "✓ Mobile OTP verified"
        )

        st.success(
            "✓ Camera and microphone captured"
        )


    with checklist_right:

        st.success(
            "✓ Face and lip movement analyzed"
        )

        st.success(
            "✓ Speech and pause timing analyzed"
        )


        if final_decision == "PASS":

            st.success(
                "✓ Audio-video synchronization verified"
            )

        else:

            st.warning(
                "⚠ Audio-video consistency requires review"
            )


    st.caption(
        "Camera connection is kept ready for faster re-verification."
    )


    standby_ctx = webrtc_streamer(

        key=
            st.session_state.get(
                "camera_session_key",
                "verisync-ekyc-auto",
            ),

        mode=
            WebRtcMode.SENDRECV,

        video_processor_factory=
            LipTrackingProcessor,

        audio_processor_factory=
            AudioRecorder,

        media_stream_constraints=
            MEDIA_CONSTRAINTS,

        desired_playing_state=
            False,

        rtc_configuration=
            rtc_config,

        video_html_attrs={

            "autoPlay":
                True,

            "controls":
                False,

            "playsInline":
                True,

            "style": {

                "width":
                    "100%",

                "height":
                    "auto",

                "aspect-ratio":
                    "16 / 9",

                "object-fit":
                    "contain",

                "background":
                    "#05052f",

                "border-radius":
                    "14px",

                "display":
                    "block",
            },
        },
    )


    if "STUN fallback" in rtc_status:

        st.caption(
            rtc_status
        )


    if st.button(
        "🔄 RE-VERIFY",
        use_container_width=True,
    ):

        st.session_state.verification_finished = (
            False
        )

        st.session_state.verification_started = (
            False
        )

        st.session_state.final_decision = (
            None
        )

        st.session_state.final_reason = (
            None
        )

        st.session_state.database_saved = (
            False
        )

        st.session_state.verification_id = (
            None
        )

        st.session_state.capture_complete = (
            False
        )

        st.session_state.capture_clock_initialized = (
            False
        )

        st.rerun()


    st.stop()


# =========================================================
# NEW VERIFICATION SESSION
# =========================================================

if not st.session_state.verification_started:

    verification_id = (

        "VS-"
        +
        datetime.now().strftime(
            "%Y%m%d%H%M%S"
        )
        +
        "-"
        +
        uuid.uuid4()
        .hex[:6]
        .upper()
    )


    st.session_state.verification_id = (
        verification_id
    )


    st.session_state.verification_started = (
        True
    )


    st.session_state.verification_finished = (
        False
    )


    st.session_state.database_saved = (
        False
    )


    set_capture_paths(
        verification_id
    )


    st.rerun()


# =========================================================
# VERIFICATION UI
# =========================================================

st.success(
    "🟢 System Status: Operational"
)


with st.container(
    border=True
):

    st.subheader(
        "Live E-KYC Verification"
    )

    st.write(
        "One synchronized camera and microphone capture will run for "
        "10 seconds. Follow each instruction exactly."
    )

    st.markdown(
        "### Verification instructions"
    )

    st.info(
        "Follow the on-screen challenge. The final verification checklist "
        "will appear after the 10-second capture is analyzed."
    )


st.info(
    "For best results, keep your face centered, use good lighting, "
    "hold the device steady and speak naturally."
)


challenge_box = st.empty()

progress = st.progress(
    0
)

status_placeholder = st.empty()


if "STUN fallback" in rtc_status:

    st.warning(
        "TURN is unavailable. Camera may take longer to connect on restricted networks."
    )


st.caption(
    "Mobile camera target: 640×480. A lower 320×240 stream may be accepted "
    "when the phone/browser cannot provide higher resolution."
)


# =========================================================
# WEBRTC CAPTURE
# =========================================================

ctx = webrtc_streamer(

    key=
        CAMERA_COMPONENT_KEY,

    mode=
        WebRtcMode.SENDRECV,

    video_processor_factory=
        LipTrackingProcessor,

    audio_processor_factory=
        AudioRecorder,

    media_stream_constraints=
        MEDIA_CONSTRAINTS,

    desired_playing_state=
        True,

    video_html_attrs={

        "autoPlay":
            True,

        "controls":
            False,

        "playsInline":
            True,

        "style": {

            "width":
                "100%",

            "height":
                "auto",

            "aspect-ratio":
                "16 / 9",

            "object-fit":
                "contain",

            "background":
                "#05052f",

            "border-radius":
                "14px",

            "display":
                "block",
        },
    },

    rtc_configuration=
        rtc_config,
)


if not ctx.state.playing:

    st.warning(
        "Camera and microphone are connecting. "
        "Please select Allow if prompted and keep this page open "
        "until the camera preview appears."
    )

    st.stop()


st.success(
    "🟢 Camera & microphone connected — verification is in progress."
)


processor = (
    ctx.video_processor
)

audio_processor = (
    ctx.audio_processor
)


# =========================================================
# SHARED CAPTURE CLOCK
# =========================================================
# Reset both processors from one common timestamp immediately before
# the 10-second challenge. This prevents small WebRTC camera/mic startup
# offsets from being mistaken for cross-modal inconsistency.

if not st.session_state.get("capture_clock_initialized", False):

    capture_start_time = time.time()

    if processor is not None and hasattr(processor, "reset_capture"):
        processor.reset_capture(capture_start_time)

    if audio_processor is not None and hasattr(audio_processor, "reset_capture"):
        audio_processor.reset_capture(capture_start_time)

    st.session_state.capture_clock_initialized = True

else:

    capture_start_time = getattr(
        processor,
        "capture_start_time",
        time.time(),
    )


# =========================================================
# 10 SECOND CHALLENGE
# =========================================================

start = capture_start_time


while (
    time.time() - start
    < DURATION
):

    elapsed = (
        time.time()
        - start
    )


    progress.progress(
        min(
            elapsed
            / DURATION,
            1.0,
        )
    )


    remaining = max(
        0,
        int(
            np.ceil(
                DURATION
                - elapsed
            )
        ),
    )


    if elapsed < 1.5:

        instruction = (
            "GET READY — LOOK AT THE CAMERA"
        )

    elif elapsed < 4.0:

        instruction = (
            f"SAY CODE {CHALLENGE_CODE}"
        )

    elif elapsed < 5.5:

        instruction = (
            "REMAIN SILENT"
        )

    elif elapsed < 9.0:

        instruction = (
            "SAY: I AM VERIFYING MY IDENTITY"
        )

    else:

        instruction = (
            "FINISHING VERIFICATION"
        )


    challenge_box.markdown(

        f"""
        <div class="vs-challenge">
            <h2>{instruction}</h2>
            <div class="vs-small">
                {remaining} seconds remaining
            </div>
        </div>
        """,

        unsafe_allow_html=True,
    )


    status_placeholder.info(
        "Live signals: Face • Lip movement • Head motion • "
        "Speech • Pause/Breath proxy"
    )


    time.sleep(
        0.20
    )


progress.progress(
    1.0
)


status_placeholder.info(
    "Processing synchronized capture..."
)


# =========================================================
# SAVE CAPTURE
# =========================================================

video_saved = save_video(
    processor
)

audio_saved = save_audio(
    audio_processor
)

lip_saved = save_lip_data(
    processor
)


# =========================================================
# CREATE COMBINED EVIDENCE VIDEO
# =========================================================

evidence_saved = False


if (
    video_saved
    and
    audio_saved
):

    evidence_saved = (
        mux_evidence_video()
    )


# =========================================================
# ANALYZE
# =========================================================

result = analyze_cross_modal()


camera_valid, camera_reason = (
    camera_validation(
        processor
    )
)


# =========================================================
# FINAL DECISION
# =========================================================

if not camera_valid:

    final_decision = (
        "REVIEW"
    )

    reason = (
        camera_reason
    )


elif not video_saved:

    final_decision = (
        "REVIEW"
    )

    reason = (
        "Camera video could not be saved correctly."
    )


elif not audio_saved:

    final_decision = (
        "REVIEW"
    )

    reason = (
        "Microphone audio was not captured correctly."
    )


elif not lip_saved:

    final_decision = (
        "REVIEW"
    )

    reason = (
        "Facial movement could not be analyzed correctly."
    )


elif result.get(
    "decision"
) == "PASS":

    final_decision = (
        "PASS"
    )

    reason = None


else:

    final_decision = (
        "REVIEW"
    )

    reason = (
        "The live challenge did not meet the required "
        "audio-video timing and challenge consistency checks. "
        "Please keep your face centered, use good lighting, "
        "speak naturally and follow the timing instructions."
    )


# =========================================================
# FINAL JSON
# =========================================================

final_json = {

    "verification_id":
        st.session_state.verification_id,

    "final_decision":
        final_decision,

    "user_reason":
        reason,

    "camera_valid":
        camera_valid,

    "camera_quality":
        (
            "GOOD"
            if camera_valid
            else
            "CHECK"
        ),

    "cross_modal_analysis":
        result,

    "score":
        result.get(
            "score",
            0,
        ),

    "zero_lag_correlation":
        result.get(
            "zero_lag_correlation",
            0,
        ),

    "best_lag":
        result.get(
            "best_lag",
            0,
        ),

    "shifted_correlation":
        result.get(
            "shifted_correlation",
            0,
        ),

    "activity_overlap":
        result.get(
            "activity_overlap",
            0,
        ),

    "activity_f1":
        result.get(
            "activity_f1",
            0,
        ),

    "zero_lag_quality":
        result.get(
            "zero_lag_quality",
            0,
        ),

    "overlap_quality":
        result.get(
            "overlap_quality",
            0,
        ),

    "shifted_alignment_risk":
        result.get(
            "shifted_alignment_risk",
            False,
        ),

    "audio_ok":
        result.get(
            "audio_ok",
            False,
        ),

    "speech_windows_ok":
        result.get(
            "speech_windows_ok",
            False,
        ),

    "silence_ok":
        result.get(
            "silence_ok",
            False,
        ),

    "temporal_ok":
        result.get(
            "temporal_ok",
            False,
        ),

    "score_ok":
        result.get(
            "score_ok",
            False,
        ),

    "review_reasons":
        result.get(
            "review_reasons",
            [],
        ),

    "temporal_consistency":
        result.get(
            "temporal_consistency",
            0,
        ),

    "speech_window_1":
        result.get(
            "speech_window_1",
            0,
        ),

    "silence_window":
        result.get(
            "silence_window",
            0,
        ),

    "speech_window_2":
        result.get(
            "speech_window_2",
            0,
        ),

    "speech_window_1_lip":
        result.get(
            "speech_window_1_lip",
            0,
        ),

    "speech_window_2_lip":
        result.get(
            "speech_window_2_lip",
            0,
        ),

    "speech_window_compliance":
        result.get(
            "speech_window_compliance",
            0,
        ),

    "silence_compliance":
        result.get(
            "silence_compliance",
            0,
        ),

    "audio_presence":
        result.get(
            "audio_presence",
            0,
        ),

    "speech_activity":
        result.get(
            "speech_activity",
            0,
        ),

    "pause_count":
        result.get(
            "pause_count",
            0,
        ),

    "breath_proxy_events":
        result.get(
            "breath_proxy_events",
            0,
        ),

    "voice_signature_similarity":
        result.get(
            "voice_signature_similarity",
            0,
        ),

    "voice_consistency_quality":
        result.get(
            "voice_consistency_quality",
            0,
        ),

    "breath_alignment_quality":
        result.get(
            "breath_alignment_quality",
            0,
        ),

    "breath_in_window_ratio":
        result.get(
            "breath_in_window_ratio",
            None,
        ),

    "head_motion_activity":
        result.get(
            "head_motion_activity",
            0,
        ),

    "video_path":
        VIDEO_PATH,

    "audio_path":
        AUDIO_PATH,

    "evidence_path":
        EVIDENCE_PATH
        if evidence_saved
        else None,

    "lip_path":
        LIP_PATH,

    "face_status_path":
        FACE_PATH,

    "capture_quality_path":
        QUALITY_PATH,

    "timestamp":
        datetime.now().isoformat(),
}


# =========================================================
# SAVE ANALYSIS JSON
# =========================================================

try:

    with open(
        SYNC_PATH,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            final_json,
            file,
            indent=2,
        )

except Exception:

    pass


# =========================================================
# SAVE DATABASE RECORD
# =========================================================

save_database_record(
    final_decision,
    reason,
    result,
    camera_valid,
)


# =========================================================
# UPDATE SESSION
# =========================================================

st.session_state.final_decision = (
    final_decision
)

st.session_state.final_reason = (
    reason
)

st.session_state.verification_finished = (
    True
)

st.session_state.verification_started = (
    False
)

st.session_state.capture_complete = (
    True
)


# =========================================================
# FINAL RERUN
# =========================================================

st.rerun()