import hmac
import random

import streamlit as st


# =========================================================
# ADMIN CREDENTIALS
# =========================================================
# Credentials are never stored in this file. They are read from
# Streamlit secrets:
#   - locally  -> .streamlit/secrets.toml   (git-ignored)
#   - on cloud -> App settings > Secrets
# =========================================================

def get_admin_credentials():
    admin_id = str(
        st.secrets.get(
            "ADMIN_ID",
            "",
        )
    ).strip()

    admin_password = str(
        st.secrets.get(
            "ADMIN_PASSWORD",
            "",
        )
    ).strip()

    return (
        admin_id,
        admin_password
    )


# =========================================================
# CHECK ADMIN LOGIN
# =========================================================

def check_admin_login(admin_id, password):
    expected_id, expected_password = get_admin_credentials()

    # If the secrets are missing, admin login stays closed
    # instead of silently falling back to a default password.
    if not expected_id or not expected_password:
        st.error(
            "Admin credentials are not configured on this deployment."
        )
        return False

    # Constant-time comparison so the check does not leak
    # information through its response time.
    id_ok = hmac.compare_digest(
        admin_id.strip(),
        expected_id,
    )

    password_ok = hmac.compare_digest(
        password.strip(),
        expected_password,
    )

    return id_ok and password_ok


# =========================================================
# DEMO OTP
# =========================================================

def generate_demo_otp():
    return str(
        random.randint(
            100000,
            999999
        )
    )


# =========================================================
# VERIFY OTP
# =========================================================

def verify_otp(entered_otp, generated_otp):
    return entered_otp == generated_otp
