from datetime import datetime

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from database import get_engine


def normalize_username(username: str) -> str:
    return str(username).strip().lower()


def init_users_csv():
    """兼容入口：MySQL 版本中由 init_mysql_tables() 统一处理，此函数保留以避免调用报错"""
    pass


def get_all_users():
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql("SELECT username, password, role, name, status, register_time, audit_time, auditor FROM users", conn)
        if df.empty:
            return df
        # 读取时先做一次规范化去重，避免管理页重复显示
        df = df.fillna("")
        df["username"] = df["username"].astype(str).apply(normalize_username)
        priority = {"active": 3, "pending": 2, "rejected": 1}
        df["__p"] = df["status"].astype(str).str.strip().str.lower().map(priority).fillna(0)
        df["__t"] = pd.to_datetime(df["audit_time"], errors="coerce")
        df = df.sort_values(["username", "__p", "__t"], ascending=[True, False, False])
        df = df.drop_duplicates(subset=["username"], keep="first")
        return df.drop(columns=["__p", "__t"], errors="ignore")
    except (OperationalError, Exception) as e:
        print(f"get_all_users error: {e}")
        return pd.DataFrame(columns=["username", "password", "role", "name", "status", "register_time", "audit_time", "auditor"])


def save_all_users(df):
    try:
        df = df.copy()
        if "username" in df.columns:
            df["username"] = df["username"].astype(str).apply(normalize_username)
            df = df[df["username"] != ""]
            # 防止同一用户（大小写/空格差异）重复写入
            if "status" in df.columns:
                priority = {"active": 3, "pending": 2, "rejected": 1}
                df["__p"] = df["status"].astype(str).str.strip().str.lower().map(priority).fillna(0)
                if "audit_time" in df.columns:
                    df["__t"] = pd.to_datetime(df["audit_time"], errors="coerce")
                elif "register_time" in df.columns:
                    df["__t"] = pd.to_datetime(df["register_time"], errors="coerce")
                else:
                    df["__t"] = pd.NaT
                df = df.sort_values(["username", "__p", "__t"], ascending=[True, False, False])
                df = df.drop_duplicates(subset=["username"], keep="first")
                df = df.drop(columns=[c for c in ["__p", "__t"] if c in df.columns])
            else:
                df = df.drop_duplicates(subset=["username"], keep="first")
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users"))
            if not df.empty:
                df.fillna("").to_sql('users', conn, if_exists='append', index=False, method='multi')
        return True
    except (OperationalError, Exception) as e:
        print(f"save_all_users error: {e}")
        return False


def create_pending_user(username, password, role, name):
    username = normalize_username(username)
    password = str(password).strip()
    role = str(role).strip()
    name = str(name).strip()
    if not username or not password or not role or not name:
        raise ValueError("用户名、密码、角色、姓名不能为空")
    new_row = {
        "username": username,
        "password": password,
        "role": role,
        "name": name,
        "status": "pending",
        "register_time": datetime.now(),
        "audit_time": None,
        "auditor": "",
    }
    try:
        pd.DataFrame([new_row]).to_sql('users', get_engine(), if_exists='append', index=False, method='multi')
        return new_row
    except IntegrityError as e:
        raise ValueError("用户已存在") from e
    except (OperationalError, Exception) as e:
        raise RuntimeError(f"创建用户失败: {e}") from e


def user_exists(username):
    with get_engine().connect() as conn:
        username_norm = normalize_username(username)
        result = conn.execute(
            text("SELECT username FROM users WHERE LOWER(TRIM(username))=:u LIMIT 1"),
            {"u": username_norm},
        )
        return result.fetchone() is not None


def get_user_for_login(username):
    username_norm = normalize_username(username)
    if not username_norm:
        return None
    with get_engine().connect() as conn:
        result = conn.execute(
            text(
                "SELECT username, password, role, name, status, register_time, audit_time, auditor "
                "FROM users WHERE LOWER(TRIM(username))=:u LIMIT 1"
            ),
            {"u": username_norm},
        )
        row = result.mappings().first()
        return dict(row) if row else None
