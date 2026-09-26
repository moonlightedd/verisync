import random
import string


# =========================================================
# CAPTCHA
# =========================================================

def generate_captcha():

    return "".join(
        random.choices(
            string.digits,
            k=4
        )
    )


# =========================================================
# MASK AADHAAR
# =========================================================

def mask_aadhaar(aadhaar):

    digits = "".join(
        ch for ch in aadhaar
        if ch.isdigit()
    )

    if len(digits) < 4:
        return "XXXX"

    return "XXXX XXXX " + digits[-4:]


# =========================================================
# PHONE VALIDATION
# =========================================================

def validate_phone(phone):

    digits = "".join(
        ch for ch in phone
        if ch.isdigit()
    )

    return 7 <= len(digits) <= 15


# =========================================================
# AADHAAR FORMAT VALIDATION
# =========================================================

def validate_aadhaar(aadhaar):

    digits = "".join(
        ch for ch in aadhaar
        if ch.isdigit()
    )

    return len(digits) == 12


# =========================================================
# USER-FRIENDLY FAILURE REASON
# =========================================================

def get_user_friendly_failure_reason(
    face_status=None,
    audio_status=None,
    sync_status=None,
    camera_status=None
):

    if camera_status == "Failed":

        return (
            "Camera input could not be verified. "
            "Please check your camera permissions "
            "and try again."
        )

    if face_status == "Failed":

        return (
            "Your face was not clearly visible "
            "during verification. Please position "
            "your face inside the camera frame "
            "and try again."
        )

    if audio_status == "Failed":

        return (
            "Your voice could not be detected "
            "clearly. Please check your microphone "
            "and try again."
        )

    if sync_status == "Failed":

        return (
            "Your speech and facial movement "
            "could not be verified as synchronized. "
            "Please try the verification again."
        )

    return (
        "E-KYC could not be completed. "
        "Please try again."
    )