import streamlit as st

from database import init_database
from auth import check_admin_login
from user_ui import show_user_login, show_otp_page
from admin_ui import show_admin_dashboard

st.set_page_config(
    page_title="VERISYNC E-KYC",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

init_database()

defaults = {
    "page": "home",
    "user_full_name": "",
    "user_phone": "",
    "user_country_code": "",
    "user_aadhaar": "",
    "otp": "",
    "otp_verified": False,
    "verification_id": None,
    "verification_started": False,
    "verification_finished": False,
    "database_saved": False,
    "final_decision": None,
    "final_reason": None,
    "admin_logged_in": False,
    "selected_verification": None,
    "auto_start_verification": False,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background: #000052 !important;
    }

    [data-testid="stHeader"] {
        background: #000052 !important;
    }

    [data-testid="stSidebar"],
    [data-testid="stSidebarNav"] {
        display: none !important;
    }

    [data-testid="collapsedControl"] {
        display: none !important;
    }

    .block-container {
        max-width: 1180px;
        padding-top: 4.5rem !important;
        padding-bottom: 2.5rem !important;
    }

    .vs-topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        min-height: 48px;
        margin-bottom: 1.2rem;
        position: relative;
        z-index: 10;
    }

    .vs-brand {
        font-size: 1.15rem;
        font-weight: 800;
        letter-spacing: .04em;
    }

    .vs-brand span {
        color: #7cc8ff;
    }

    .vs-menu-note {
        color: #d7e6ff;
        font-size: .82rem;
    }

    .stButton > button {
        min-height: 46px;
        border-radius: 10px;
        font-weight: 700;
        border: 1px solid rgba(255,255,255,.20);
    }

    /* Keep the compact Admin hamburger completely inside the viewport. */
    div[data-testid="stButton"] > button {
        box-sizing: border-box !important;
        line-height: 1 !important;
    }

    [data-testid="stHeader"] {
        z-index: 1000 !important;
    }

    .vs-hero {
        padding: 3.2rem 1rem 2.2rem;
        text-align: center;
    }

    .vs-hero h1 {
        font-size: clamp(2.2rem, 6vw, 4.2rem);
        margin-bottom: .35rem;
        letter-spacing: .03em;
    }

    .vs-hero h1 span {
        color: #75c9ff;
    }

    .vs-subtitle {
        font-size: clamp(1rem, 2vw, 1.25rem);
        color: #e8efff;
        margin-bottom: .65rem;
    }

    .vs-description {
        color: #E7F0FF !important;
        max-width: 760px;
        margin: 0 auto 2rem;
    }

    /* Global high-contrast text for readability on the navy theme. */
    .stMarkdown, .stMarkdown p, .stMarkdown li,
    [data-testid="stText"], [data-testid="stCaptionContainer"],
    label, .stCaption, .stAlert {
        color: #F3F7FF !important;
    }

    h1, h2, h3, h4, h5, h6 {
        color: #FFFFFF !important;
    }

    .stCaption, [data-testid="stCaptionContainer"] {
        color: #D7E4F7 !important;
    }

    .stTextInput label, .stSelectbox label, .stCheckbox label {
        color: #FFFFFF !important;
    }

    .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
        color: #FFFFFF !important;
        background: #0B0B5F !important;
        border-color: rgba(180,215,255,.42) !important;
    }

    .vs-card h3, .vs-card h4 {
        color: #FFFFFF !important;
    }

    .vs-card p {
        color: #E7F0FF !important;
    }

    .vs-muted {
        color: #D7E4F7 !important;
    }

    .vs-card {
        background: rgba(8, 8, 74, .72);
        border: 1px solid rgba(160,190,255,.18);
        border-radius: 16px;
        padding: 1.3rem;
        margin: .5rem 0 1rem;
    }

    .vs-admin-box {
        background: rgba(3, 3, 45, .96);
        border: 1px solid rgba(124,200,255,.35);
        border-radius: 14px;
        padding: 1rem;
    }

    @media (max-width: 700px) {
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
        .vs-hero {
            padding-top: 2rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def show_topbar(show_menu=True):
    left, right = st.columns([8, 1], vertical_alignment="center")
    with left:
        st.markdown(
            '<div class="vs-brand">🛡️ <span>VERISYNC</span></div>',
            unsafe_allow_html=True,
        )
    with right:
        if show_menu:
            if st.button("☰", key="global_admin_menu", help="Admin login"):
                st.session_state.page = "admin_login"
                st.rerun()


def show_home():
    show_topbar(show_menu=True)

    st.markdown(
        """
        <div class="vs-hero">
            <h1>🛡️ <span>VERISYNC</span></h1>
            <div class="vs-subtitle">
                AI-Powered Cross-Modal Identity Verification
            </div>
            <div class="vs-description">
                Secure E-KYC verification using synchronized camera,
                microphone and live facial-motion analysis.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="vs-card">
            <h3>🔐 Secure E-KYC Verification</h3>
            <p>
                Complete a short live challenge. VERISYNC evaluates face
                presence, lip movement, speech activity, pause timing and
                audio-video synchronization on one shared timeline.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "🛡️ START E-KYC VERIFICATION",
        type="primary",
        use_container_width=True,
        key="home_start_ekyc",
    ):
        st.session_state.page = "user_login"
        st.rerun()

    st.caption("Admin access is available through the ☰ menu in the top-right corner.")


def show_admin_login():
    show_topbar(show_menu=False)

    st.title("🧑‍💼 Admin Login")
    st.write("Authorized personnel only.")

    admin_id = st.text_input(
        "Admin ID",
        placeholder="Enter admin ID",
    )
    password = st.text_input(
        "Password",
        type="password",
        placeholder="Enter password",
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "🔐 LOGIN",
            type="primary",
            use_container_width=True,
        ):
            if check_admin_login(admin_id, password):
                st.session_state.admin_logged_in = True
                st.session_state.page = "admin"
                st.rerun()
            else:
                st.error("Invalid Admin ID or password.")

    with col2:
        if st.button("← BACK TO USER", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()


def show_user_verification():
    show_topbar(show_menu=True)

    st.title("🛡️ VERISYNC E-KYC")
    st.subheader("Ready for live verification")

    st.success("🟢 System Status: Operational")

    st.info(
        "Allow camera and microphone access when prompted. "
        "After you continue, the live verification starts automatically."
    )

    st.markdown(
        """
        <div class="vs-card">
            <h4>10-second verification challenge</h4>
            <p><b>1. GET READY:</b> Keep your face clearly visible.</p>
            <p><b>2. SPEAK:</b> Say code <b>4721</b>.</p>
            <p><b>3. SILENCE:</b> Remain silent when instructed.</p>
            <p><b>4. SPEAK:</b> Say <b>I AM VERIFYING MY IDENTITY</b>.</p>
            <p>
                The system checks facial movement, speech activity,
                pause/breath-proxy timing and audio-video consistency.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "🛡️ CONTINUE & START VERIFICATION",
        type="primary",
        use_container_width=True,
    ):
        st.session_state.auto_start_verification = True
        st.session_state.page = "user_verification"
        st.switch_page("pages/2_EKYC_Verification.py")


page = st.session_state.get("page", "home")

if page == "home":
    show_home()
elif page == "user_login":
    show_user_login()
elif page == "otp":
    show_otp_page()
elif page == "user_verification":
    show_user_verification()
elif page == "admin_login":
    show_admin_login()
elif page == "admin":
    if st.session_state.get("admin_logged_in", False):
        show_admin_dashboard()
    else:
        st.session_state.page = "admin_login"
        st.rerun()
