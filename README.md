# VERISYNC — Explainable e-KYC Verification Layer

> **MUSA CodeX 2026** · Problem Statement **CX0205** — *"The Deepfake That Passed Two Checks"*
> Team **VIKINGS** — *Four minds, one objective: decoding synthetic deception through unified defense*

VERISYNC is an AI-assisted video + audio e-KYC verification prototype that detects
inconsistencies between facial movement and speech activity within a single live session.

Instead of scoring the face and the voice as two separate checks, it captures **one
synchronized 10-second camera + microphone recording** and asks a single question:
*do the facial motion, the speech activity and the pauses make sense on the same timeline?*

> **ONE CAPTURE. ONE TIMELINE. ONE DECISION.**

---

## The problem

A fraudster can present a live face-swap while supplying a separately cloned or generated voice.

- Face-liveness checks score the video stream on its own.
- Voice checks score the audio stream on its own.
- OTP and Aadhaar e-KYC confirm the **number**, not the person in front of the camera.

Each check can pass independently even when the audio and the facial motion never belonged
to the same live capture. VERISYNC closes this gap by adding a **cross-modal consistency
layer** between the two signals.

---

## The approach

```
LOGIN  →  CAPTURE  →  ANALYZE  →  CROSS-MODAL ASSESSMENT  →  EXPLAINABLE RESULT
```

### 1. Login
- Phone number and Aadhaar number input
- OTP verification
- CAPTCHA challenge

Aadhaar and OTP verification are **simulated** for demonstration purposes.

### 2. Capture
A synchronized camera + microphone session runs for about 10 seconds, guided by a timed challenge:

| Time (sec) | Instruction |
|---|---|
| 0.0 – 1.5 | Get ready |
| 1.5 – 4.0 | Say the code **4721** |
| 4.0 – 5.5 | Remain silent |
| 5.5 – 9.0 | Say **"I AM VERIFYING MY IDENTITY"** |
| 9.0 – 10.0 | Finishing |

### 3. Analyze
- Face landmarks
- Lip movement and head movement
- Speech / audio activity
- Silence windows and pause timing
- Audio–video temporal consistency
- Lightweight within-capture voice consistency signal
- Audio-based pause / breath activity proxy

### 4. Cross-modal assessment
Signals are compared on a shared timeline using:

- Zero-lag correlation
- Limited-lag correlation
- Activity overlap and activity F1 agreement
- Challenge-window compliance
- Silence-window compliance
- Timing-shift risk detection
- Cross-modal consistency score

A suspicious timing mismatch routes the session to **REVIEW** instead of an automatic **PASS**.

### 5. Explainable result
- **User view** — deliberately minimal: `PASS` or `REVIEW`, reference ID and the next step only
- **Admin view** — the supporting numerical signals plus the recorded verification evidence

---

## Features

### Authentication
- Phone number and Aadhaar number capture
- OTP verification
- CAPTCHA challenge before any recording starts
- Simulated identity-verification flow for MVP demonstration

### Cross-modal verification
- Synchronized camera + microphone capture (10-second challenge)
- MediaPipe Face Landmarker
- Lip and head movement tracking
- Speech activity detection
- Silence and pause analysis
- Audio–video temporal consistency and timing-shift detection
- Explainable PASS / REVIEW decision

### Audio analysis
Lightweight audio-signal features:

- RMS audio energy
- Zero-crossing rate
- Spectral centroid
- Speech activity and pause detection
- Within-capture voice consistency

> The captured-voice signal is **not** bank-grade speaker authentication and does not replace
> enrolled-speaker verification.

### Breath / pause proxy
An audio-based pause / breath activity proxy is used as an **additional signal only**. It is
not a physiological respiration measurement.

### Admin dashboard
- Verification records and verification ID
- User information
- PASS / REVIEW status
- Cross-modal score
- Face status and audio status
- Supporting analysis information
- Recorded video / audio evidence (`evidence.mp4` combines both for easier review)

---

## Tech stack

| Component | Technology |
|---|---|
| Language | Python |
| Web application / frontend | Streamlit |
| Camera + microphone streaming | streamlit-webrtc |
| WebRTC network traversal | Twilio TURN |
| Computer vision | OpenCV |
| Face landmarks | MediaPipe Face Landmarker |
| Numerical processing | NumPy |
| Data processing | Pandas |
| Signal processing | SciPy |
| Audio processing | WAV / FFmpeg |
| Database layer | Python database module (`database.py`) |
| Deployment | Streamlit Cloud |

**Why Python?** One stack covers computer vision, audio processing, numerical analysis,
MediaPipe, OpenCV, Streamlit and the database layer — keeping the MVP lightweight and fast
to build.

**Why Twilio?** Twilio provides TURN infrastructure so the camera and microphone connection
works across networks where direct peer-to-peer WebRTC is blocked. Twilio is used **only for
connectivity** — all face, lip, audio and cross-modal analysis is done by VERISYNC itself.

---

## System workflow

```
User
 │
 ▼
Phone + Aadhaar
 │
 ▼
OTP + CAPTCHA
 │
 ▼
10-second Camera + Microphone Capture
 │
 ├───────────────┐
 ▼               ▼
Video           Audio
 │               │
 ▼               ▼
Face / Lip      Speech /
Movement        Pause Analysis
 │               │
 └───────┬───────┘
         ▼
  Shared Timeline
         │
         ▼
Cross-Modal Consistency
         │
         ▼
   PASS / REVIEW
         │
         ▼
 Database + Evidence
         │
         ▼
  Admin Dashboard
```

---

## Evidence generated

Each verification session can produce:

```
captures/
└── VS-<verification-id>/
    ├── video.mp4
    ├── audio.wav
    ├── evidence.mp4
    ├── lip_signal.csv
    ├── face_status.json
    ├── capture_quality.json
    └── sync_result.json
```

| File | Purpose |
|---|---|
| `video.mp4` | Captured video |
| `audio.wav` | Captured microphone audio |
| `evidence.mp4` | Combined video + audio evidence |
| `lip_signal.csv` | Facial / lip movement measurements |
| `face_status.json` | Face visibility information |
| `capture_quality.json` | Camera quality measurements |
| `sync_result.json` | Cross-modal analysis and decision data |

---

## Project structure

```
verisync/
├── app.py
├── auth.py
├── database.py
├── admin_ui.py
├── user_ui.py
├── utils.py
├── pages/
│   └── 2_EKYC_Verification.py
├── models/
│   └── face_landmarker.task
├── .streamlit/
├── .gitignore
├── requirements.txt
└── packages.txt
```

---

## Getting started

### Prerequisites
- Python 3.9 or newer
- Webcam and microphone
- Git
- Internet connection (for WebRTC)

### Installation

```bash
git clone https://github.com/moonlightedd/verisync.git
cd verisync
```

Create a virtual environment:

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Run

```bash
streamlit run app.py
```

Streamlit will print the local URL, normally `http://localhost:8501`.

### Twilio configuration

For reliable WebRTC connectivity, add Twilio credentials to `.streamlit/secrets.toml`
(or to Streamlit Cloud → App settings → Secrets):

```toml
TWILIO_ACCOUNT_SID = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
TWILIO_AUTH_TOKEN  = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

> ⚠️ **Never commit `secrets.toml` or real Twilio credentials to GitHub.** Make sure
> `.streamlit/secrets.toml` is listed in `.gitignore`.

---

## How the decision is made

VERISYNC does not rely on a single correlation value. The MVP combines several checks:

1. Audio activity must be present.
2. Required speech windows must contain sufficient activity.
3. The required silence window must stay sufficiently quiet.
4. Facial / lip activity and audio activity are compared on the same timeline.
5. Activity overlap and F1 agreement are evaluated.
6. Zero-lag correlation provides additional temporal evidence.
7. Limited-lag correlation looks for possible timing shifts.
8. A significant shifted-alignment advantage triggers **REVIEW**.
9. The resulting cross-modal score feeds the final decision.

**PASS** — all required conditions are satisfied.
**REVIEW** — the capture does not meet the automatic verification conditions.

The user never sees the raw numbers — only the outcome and the next step. Administrators see
the full breakdown and the evidence.

---

## Current MVP scope

### Implemented
- Phone + Aadhaar + OTP + CAPTCHA flow (simulated)
- 10-second synchronized capture
- Face landmark detection
- Lip and head movement tracking
- Speech activity and pause / silence analysis
- Breath activity proxy
- Cross-modal temporal analysis and timing-shift detection
- Explainable PASS / REVIEW
- Database record creation
- Admin dashboard
- Recorded verification evidence
- WebRTC camera / microphone connectivity

### Not claimed
- Complete deepfake detection
- Bank-grade speaker authentication
- Physiological respiration measurement
- Real UIDAI integration
- Real telecom OTP integration
- Production banking deployment

---

## Roadmap

**Phase 1 — Stronger detection**
- Advanced deepfake / face-swap detection
- Stronger anti-spoofing and liveness
- Larger real-world attack datasets
- Robustness testing across devices and lighting conditions

**Phase 2 — Identity & document verification**
- Enrolled-speaker voice verification using speaker embeddings
- OCR and document analysis
- Real Aadhaar / bank API integration where authorized

**Phase 3 — Trust & security**
- Source and provenance verification
- Digital signatures
- Encrypted evidence storage
- Retention policies, access controls and audit logging

**Phase 4 — Production deployment**
- REST APIs
- Mobile integration and browser optimization
- Enterprise KYC workflows
- Scalable cloud deployment
- Performance benchmarking on low-end devices

---

## Security & privacy

This repository is a prototype. A production deployment would additionally need:

- Secure database infrastructure and encrypted object storage
- Encryption in transit and at rest
- Authentication, authorization and role-based admin access
- Evidence retention policies and audit logging
- Secure secrets management
- Privacy and regulatory compliance

Raw video and audio should never be treated as ordinary application data in a production
banking environment.

---

## Disclaimer

VERISYNC is a **prototype built for demonstration and validation only**. It is **not a
production banking or KYC replacement**.

- Aadhaar number capture and OTP verification are **simulated** — no real UIDAI or telecom
  service is connected.
- The voice signal is a lightweight within-capture consistency measurement, **not**
  enrolled-speaker identity authentication.
- The breath-related signal is an audio-based proxy, **not** a medical or physiological
  measurement.
- No real customer data should be processed with this prototype.

---

## Team VIKINGS

| Member | Role |
|---|---|
| **Sahil Bhomia** | Team Leader · Computer Vision |
| **Shubham Mandavkar** | Audio / ML Analysis |
| **Harshal Malwande** | UI · System Integration |
| **Soham Mahdeshwar** | Backend · Testing · Documentation |

---

## References

- MUSA CodeX 2026 — Problem Statement CX0205: *"The Deepfake That Passed Two Checks"*
- [Google MediaPipe — Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)
- [OpenCV documentation](https://docs.opencv.org/)
- [Streamlit documentation](https://docs.streamlit.io/)
- [streamlit-webrtc](https://github.com/whitphx/streamlit-webrtc)
- UIDAI and RBI Video-KYC guidance — referred to only for process and terminology context

---

## License

This project was built for MUSA CodeX 2026. A license has not been added yet.
