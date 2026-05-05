import os
import requests
import msal
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

_CLIENT_ID     = os.getenv("ENTRA_CLIENT_ID")
_TENANT_ID     = os.getenv("ENTRA_TENANT_ID")
_CLIENT_SECRET = os.getenv("ENTRA_CLIENT_SECRET")
_AUTHORITY     = f"https://login.microsoftonline.com/{_TENANT_ID}"
_SCOPES        = ["User.Read"]
_REDIRECT_URI  = os.getenv("REDIRECT_URI", "http://localhost:8501")


def _msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        _CLIENT_ID,
        authority=_AUTHORITY,
        client_credential=_CLIENT_SECRET,
    )


def get_auth_url() -> str:
    return _msal_app().get_authorization_request_url(
        scopes=_SCOPES,
        redirect_uri=_REDIRECT_URI,
    )


def _exchange_code(code: str) -> dict | None:
    result = _msal_app().acquire_token_by_authorization_code(
        code=code,
        scopes=_SCOPES,
        redirect_uri=_REDIRECT_URI,
    )
    return result if "access_token" in result else None


def _graph_me(access_token: str) -> dict | None:
    resp = requests.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    return resp.json() if resp.status_code == 200 else None


def _fetch_user_role(email: str) -> dict | None:
    """Pull division + role from user_division_map. Returns None if not found."""
    from db.connection import get_connection
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT division, role, approver_email
            FROM user_division_map
            WHERE LOWER(email) = LOWER(?)
            """,
            email,
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"division": row[0], "role": row[1], "approver_email": row[2]}
    except Exception as e:
        st.error(f"DB error fetching user role: {e}")
    return None


def handle_auth_callback() -> None:
    """Exchange OAuth code → token → user info. Call once at the top of app.py."""
    params = st.query_params
    if "code" not in params or "user" in st.session_state:
        return

    token = _exchange_code(params["code"])
    if not token:
        st.error("Authentication failed — could not exchange token.")
        return

    profile = _graph_me(token["access_token"])
    if not profile:
        st.error("Authentication failed — could not fetch user profile.")
        return

    email = profile.get("mail") or profile.get("userPrincipalName", "")
    role_info = _fetch_user_role(email)

    st.session_state["user"] = {
        "email": email,
        "name": profile.get("displayName", ""),
        "division": role_info["division"] if role_info else None,
        "role": role_info["role"] if role_info else None,
        "approver_email": role_info["approver_email"] if role_info else None,
        "access_token": token["access_token"],
    }
    st.query_params.clear()
    st.rerun()


def current_user() -> dict | None:
    return st.session_state.get("user")


def require_login() -> dict:
    """Return user dict or stop the page with a login prompt."""
    user = current_user()
    if not user:
        st.info("Please log in to continue.")
        st.stop()
    return user


def require_role(*roles: str) -> dict:
    """Return user dict if role matches, otherwise stop."""
    user = require_login()
    if user.get("role") not in roles:
        st.error("You do not have permission to view this page.")
        st.stop()
    return user


def logout() -> None:
    st.session_state.pop("user", None)
    st.query_params.clear()
