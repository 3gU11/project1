import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

try:
    import extra_streamlit_components as stx
    COOKIE_COMPONENT_AVAILABLE = True
except ImportError:
    stx = None
    COOKIE_COMPONENT_AVAILABLE = False

from crud.users import create_pending_user, get_user_for_login, normalize_username, user_exists
from database import get_engine


logger = logging.getLogger(__name__)

REMEMBER_COOKIE_NAME = "remember_token"
REMEMBER_DAYS = 30


def init_session_state():
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None
        st.session_state.role = None
        st.session_state.operator_name = ''
        st.session_state.is_admin = False
        st.session_state.page = 'home'
        st.session_state.current_batch = ''
        st.session_state.permissions = []
        st.session_state.remember_token = None


def _get_cookie_manager():
    if not COOKIE_COMPONENT_AVAILABLE:
        return None
    if 'cookie_manager' not in st.session_state:
        st.session_state.cookie_manager = stx.CookieManager()
    return st.session_state.cookie_manager


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()


def _set_login_session(user_row: dict):
    st.session_state.current_user = user_row["username"]
    st.session_state.role = user_row["role"]
    st.session_state.operator_name = user_row["name"]
    st.session_state.is_admin = (user_row["role"] == "Admin")


def create_remember_session(username: str, days: int = REMEMBER_DAYS) -> str:
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now() + timedelta(days=days)

    with get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_sessions (username, token_hash, expires_at, revoked, created_at) "
                "VALUES (:username, :token_hash, :expires_at, 0, :created_at)"
            ),
            {
                "username": normalize_username(username),
                "token_hash": token_hash,
                "expires_at": expires_at,
                "created_at": datetime.now(),
            },
        )
    return raw_token


def set_remember_cookie(raw_token: str, days: int = REMEMBER_DAYS):
    cm = _get_cookie_manager()
    if not cm:
        return
    cm.set(
        REMEMBER_COOKIE_NAME,
        raw_token,
        expires_at=datetime.now() + timedelta(days=days),
    )
    st.session_state.remember_token = raw_token


def _get_cookie_token():
    cm = _get_cookie_manager()
    if not cm:
        return None
    cookies = cm.get_all() or {}
    return cookies.get(REMEMBER_COOKIE_NAME)


def revoke_remember_session(raw_token: Optional[str]):
    if not raw_token:
        return
    token_hash = _hash_token(raw_token)
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE user_sessions SET revoked=1, revoked_at=:revoked_at "
                "WHERE token_hash=:token_hash"
            ),
            {"revoked_at": datetime.now(), "token_hash": token_hash},
        )


def clear_remember_cookie():
    cm = _get_cookie_manager()
    if cm:
        cm.delete(REMEMBER_COOKIE_NAME)
    st.session_state.remember_token = None


def logout_user():
    revoke_remember_session(st.session_state.get("remember_token"))
    clear_remember_cookie()

    st.session_state.current_user = None
    st.session_state.role = None
    st.session_state.operator_name = ''
    st.session_state.is_admin = False
    st.session_state.permissions = []
    st.session_state.page = 'home'


def try_auto_login():
    if st.session_state.get("current_user"):
        return False

    raw_token = _get_cookie_token()
    if not raw_token:
        return False

    token_hash = _hash_token(raw_token)
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT username FROM user_sessions "
                "WHERE token_hash=:token_hash AND revoked=0 AND expires_at > :now "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"token_hash": token_hash, "now": datetime.now()},
        ).mappings().first()

    if not row:
        clear_remember_cookie()
        return False

    user_row = get_user_for_login(row["username"])
    if not user_row or str(user_row.get("status", "")).strip().lower() != "active":
        revoke_remember_session(raw_token)
        clear_remember_cookie()
        return False

    _set_login_session(user_row)
    st.session_state.remember_token = raw_token
    logger.info("auto_login_success username='%s'", row["username"])
    return True


def register_user(username, password, role, name):
    try:
        if user_exists(username):
            return False, "用户名已存在"
    except (OperationalError, Exception) as e:
        return False, f"系统错误: {e}"

    try:
        create_pending_user(username, password, role, name)
        return True, "注册成功，请等待管理员审核"
    except (IntegrityError, OperationalError, Exception) as e:
        return False, f"系统错误，保存失败: {e}"


def verify_login(username, password):
    raw_username = str(username)
    username_norm = normalize_username(raw_username)
    logger.info("login_verify_start username_raw='%s' username_norm='%s'", raw_username, username_norm)
    try:
        user_row = get_user_for_login(raw_username)
    except (OperationalError, Exception) as e:
        logger.exception("login_verify_db_error username_norm='%s'", username_norm)
        return False, f"系统错误: {e}", None

    if not user_row:
        logger.warning("login_verify_user_not_found username_norm='%s'", username_norm)
        return False, "用户不存在", None

    if str(user_row.get('password', '')) != str(password):
        logger.warning("login_verify_password_mismatch username_norm='%s'", username_norm)
        return False, "密码错误", None

    status = str(user_row.get('status', '')).strip().lower()
    if status == 'active':
        logger.info("login_verify_success username_norm='%s' role='%s'", username_norm, user_row.get("role", ""))
        return True, "登录成功", user_row
    if status == 'pending':
        return False, "账户待审核，请联系管理员", None
    if status == 'rejected':
        return False, "账户审核未通过", None
    return False, f"账户状态异常: {status}", None
