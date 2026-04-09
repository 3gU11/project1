import streamlit as st
import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from config import DEFAULT_ROLE_PERMISSIONS
from database import get_engine
from core.navigation import go_home


def get_role_permissions(role):
    if role == "Admin":
        return [
            "PLANNING", "CONTRACT", "QUERY", "ARCHIVE",
            "SALES_CREATE", "INBOUND", "SALES_ALLOC",
            "SHIP_CONFIRM", "MACHINE_EDIT", "MACHINE_EDIT_MODEL",
            "WAREHOUSE_MAP",
        ]
    perms = []
    try:
        with get_engine().connect() as conn:
            df_perm = pd.read_sql(
                text("SELECT func_code FROM role_permissions WHERE role_id=:role"),
                conn, params={"role": role}
            )
        perms = df_perm['func_code'].tolist()
    except (OperationalError, Exception) as e:
        print(f"Error loading permissions: {e}")
    if (not perms) and (role in DEFAULT_ROLE_PERMISSIONS):
        return DEFAULT_ROLE_PERMISSIONS[role]
    return perms


def check_access(required_permission):
    if st.session_state.role == "Admin":
        return

    user_perms = st.session_state.get('permissions', [])
    if required_permission not in user_perms:
        st.error(f"🚫 权限不足！需要权限: {required_permission}")
        st.button("⬅️ 返回首页", on_click=go_home)
        st.stop()
