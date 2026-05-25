import streamlit as st
from utils.styles import apply_global_styles
from utils.auth import handle_auth_callback, current_user, get_auth_url, logout

st.set_page_config(
    page_title="Budget Management",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_global_styles()

# Handle OAuth redirect (must run before any other output)
handle_auth_callback()

user = current_user()

if not user:
    # ── Login page ──────────────────────────────────────────────
    st.title("Budget Management")
    st.caption("Internal OPEX Budget System — Chememan Public Company Limited")
    st.divider()

    col_left, col_center, col_right = st.columns([1, 1, 1])
    with col_center:
        st.markdown("#### Sign in to continue")
        auth_url = get_auth_url()
        st.link_button("Sign in with Microsoft", auth_url, use_container_width=True)

else:
    # ── Home (post-login) ────────────────────────────────────────
    st.title("Budget Management")
    st.caption("Internal OPEX Budget System — Chememan Public Company Limited")
    st.divider()

    st.markdown(f"Welcome, **{user['name']}**")

    if user["division"]:
        st.markdown(f"Division: **{user['division']}** &nbsp;|&nbsp; Role: **{user['role']}**")
    else:
        st.warning(
            "Your account is not mapped to any division. "
            "Please contact the Budget department to set up your access."
        )

    st.divider()
    st.markdown("Use the sidebar to navigate.")

    if st.button("Sign out"):
        logout()
        st.rerun()
