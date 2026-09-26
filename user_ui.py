import streamlit as st

from auth import generate_demo_otp, verify_otp
from utils import (
    generate_captcha,
    validate_phone,
    validate_aadhaar,
    mask_aadhaar,
)

COUNTRY_CODES = {
    "India (+91)": "+91",
    "United States (+1)": "+1",
    "United Kingdom (+44)": "+44",
    "Australia (+61)": "+61",
    "Canada (+1)": "+1",
    "Singapore (+65)": "+65",
    "UAE (+971)": "+971",
}


def show_user_topbar():
    """
    User-side top bar.
    Admin access is intentionally kept small and separate
    from the customer verification workflow.
    """

    st.markdown(
        """
        <style>
        .user-topbar {
            width: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 18px;
        }

        .user-brand {
            color: #72c8ff;
            font-size: 19px;
            font-weight: 800;
            letter-spacing: .04em;
        }

        /* Make the hamburger clearly visible */
        div[data-testid="column"]:last-child
        div[data-testid="stButton"] > button {
            min-height: 42px !important;
            height: 42px !important;
            width: 46px !important;
            padding: 0 !important;
            border-radius: 9px !important;
            background: #08084a !important;
            color: #ffffff !important;
            border: 1px solid rgba(120,190,255,.55) !important;
            font-size: 22px !important;
            line-height: 1 !important;
        }

        div[data-testid="column"]:last-child
        div[data-testid="stButton"] > button:hover {
            border-color: #72c8ff !important;
            color: #72c8ff !important;
        }

        .admin-access-label {
            text-align: right;
            color: #D7E4F7 !important;
            font-size: 11px;
            margin-top: 3px;
        }

        /* High-contrast text across login and OTP screens. */
        .stMarkdown, .stMarkdown p, .stMarkdown li,
        [data-testid="stCaptionContainer"], label,
        .stCaption, .stAlert {
            color: #F3F7FF !important;
        }

        h1, h2, h3, h4, h5, h6 {
            color: #FFFFFF !important;
        }

        .vs-muted {
            color: #D7E4F7 !important;
        }

        .stTextInput label, .stSelectbox label {
            color: #FFFFFF !important;
        }

        .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
            color: #FFFFFF !important;
            background: #0B0B5F !important;
            border-color: rgba(180,215,255,.42) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns(
        [12, 1],
        vertical_alignment="center",
    )

    with left:
        st.markdown(
            """
            <div class="user-topbar">
                <div class="user-brand">
                    🛡️ VERISYNC
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        if st.button(
            "☰",
            key="user_admin_hamburger",
            help="Admin Login",
        ):
            st.session_state.show_admin_menu = not st.session_state.get(
                "show_admin_menu",
                False,
            )
            st.rerun()

    # Admin dropdown/menu
    if st.session_state.get(
        "show_admin_menu",
        False,
    ):
        menu_left, menu_right = st.columns([9, 3])

        with menu_right:
            st.markdown(
                """
                <div style="
                    background:#08084a;
                    border:1px solid rgba(114,200,255,.45);
                    border-radius:10px;
                    padding:10px;
                    margin-top:-8px;
                    margin-bottom:10px;
                ">
                    <div style="
                        color:#72c8ff;
                        font-weight:700;
                        margin-bottom:6px;
                    ">
                        ADMIN ACCESS
                    </div>
                    <div style="
                        color:#b8cbe8;
                        font-size:12px;
                        margin-bottom:8px;
                    ">
                        Authorized personnel only
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(
                "ADMIN LOGIN",
                key="user_admin_login_button",
                use_container_width=True,
            ):
                st.session_state.show_admin_menu = False
                st.session_state.page = "admin_login"
                st.rerun()


def show_user_login():
    # IMPORTANT:
    # This was missing previously, which is why the hamburger
    # was not visible on the customer page.
    show_user_topbar()

    st.title("Customer Identity Verification")
    st.subheader("Enter your details to continue to E-KYC")
    st.caption("All fields are mandatory.")

    st.markdown(
        """
        <div class="vs-card">
            <b>Step 1 of 3 — Identity Details</b><br>
            <span class="vs-muted">
            Enter the details registered for your E-KYC verification.
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    full_name = st.text_input(
        "Full Name *",
        placeholder="Enter your full name",
    )

    country = st.selectbox(
        "Country Code *",
        list(COUNTRY_CODES.keys()),
    )

    phone = st.text_input(
        "Mobile Number *",
        placeholder="Enter registered mobile number",
    )

    aadhaar = st.text_input(
        "Aadhaar Number *",
        type="password",
        max_chars=12,
        placeholder="Enter 12-digit Aadhaar number",
    )

    if "captcha" not in st.session_state:
        st.session_state.captcha = generate_captcha()

    st.markdown("### Numeric CAPTCHA *")

    cap_left, cap_right = st.columns([1, 3])

    with cap_left:
        st.code(st.session_state.captcha)

    with cap_right:
        captcha_input = st.text_input(
            "Enter CAPTCHA",
            max_chars=4,
            placeholder="Enter the numbers shown",
            label_visibility="collapsed",
        )

    if st.button(
        "↻ Refresh CAPTCHA",
        key="refresh_captcha",
    ):
        st.session_state.captcha = generate_captcha()
        st.rerun()

    st.divider()

    if st.button(
        "VERIFY DETAILS & SEND OTP",
        type="primary",
        use_container_width=True,
        key="verify_details",
    ):
        errors = []

        if not full_name.strip():
            errors.append("Full Name is required.")

        if not validate_phone(phone):
            errors.append("Please enter a valid mobile number.")

        if not validate_aadhaar(aadhaar):
            errors.append(
                "Aadhaar number must contain exactly 12 digits."
            )

        if captcha_input.strip() != st.session_state.captcha:
            errors.append("Incorrect CAPTCHA.")

        if errors:
            for error in errors:
                st.error(error)

            st.session_state.captcha = generate_captcha()
            return

        st.session_state.user_full_name = full_name.strip()
        st.session_state.user_phone = phone.strip()
        st.session_state.user_country_code = COUNTRY_CODES[country]
        st.session_state.user_aadhaar = mask_aadhaar(aadhaar)

        st.session_state.demo_otp = generate_demo_otp()
        st.session_state.otp_sent = True
        st.session_state.otp_verified = False
        st.session_state.page = "otp"

        st.rerun()


def show_otp_page():
    # Keep Admin access available from OTP page as well.
    show_user_topbar()

    st.title("Mobile OTP Verification")
    st.subheader("Step 2 of 3 — Verify Registered Mobile")

    st.info(
        f"OTP verification for "
        f"{st.session_state.user_country_code} "
        f"{st.session_state.user_phone}"
    )

    st.markdown(
        """
        <div class="vs-card">
            <b>Why this step?</b><br>
            <span class="vs-muted">
            The mobile number must be verified before the live E-KYC
            verification can begin.
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    otp_input = st.text_input(
        "Enter 6-digit OTP *",
        max_chars=6,
        placeholder="Enter OTP",
    )

    st.warning(
        "DEMO MODE: The OTP is displayed below for prototype testing."
    )

    st.code(
        st.session_state.get(
            "demo_otp",
            "",
        )
    )

    if st.button(
        "VERIFY OTP & CONTINUE",
        type="primary",
        use_container_width=True,
        key="verify_otp",
    ):
        if verify_otp(
            otp_input,
            st.session_state.demo_otp,
        ):
            st.session_state.otp_verified = True
            st.session_state.page = "user_verification"
            st.rerun()
        else:
            st.error(
                "Incorrect OTP. Please re-enter the OTP."
            )

    if st.button(
        "← BACK TO DETAILS",
        key="back_to_details",
    ):
        st.session_state.page = "user_login"
        st.rerun()