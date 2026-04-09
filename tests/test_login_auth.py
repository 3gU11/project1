from sqlalchemy import create_engine, text

from core.auth import verify_login
from crud import users as users_crud


def test_verify_login_success_with_case_and_space_username(monkeypatch):
    row = {
        "username": "boss",
        "password": "888",
        "role": "Boss",
        "name": "老板",
        "status": "active",
    }
    monkeypatch.setattr("core.auth.get_user_for_login", lambda username: row)
    ok, msg, user = verify_login("  BOSS  ", "888")
    assert ok is True
    assert msg == "登录成功"
    assert user["username"] == "boss"


def test_verify_login_user_not_found(monkeypatch):
    monkeypatch.setattr("core.auth.get_user_for_login", lambda username: None)
    ok, msg, user = verify_login("ghost", "123")
    assert ok is False
    assert msg == "用户不存在"
    assert user is None


def test_verify_login_password_mismatch(monkeypatch):
    row = {
        "username": "boss",
        "password": "888",
        "role": "Boss",
        "name": "老板",
        "status": "active",
    }
    monkeypatch.setattr("core.auth.get_user_for_login", lambda username: row)
    ok, msg, user = verify_login("boss", "999")
    assert ok is False
    assert msg == "密码错误"
    assert user is None


def test_verify_login_pending_status(monkeypatch):
    row = {
        "username": "boss",
        "password": "888",
        "role": "Boss",
        "name": "老板",
        "status": "PENDING",
    }
    monkeypatch.setattr("core.auth.get_user_for_login", lambda username: row)
    ok, msg, user = verify_login("boss", "888")
    assert ok is False
    assert msg == "账户待审核，请联系管理员"
    assert user is None


def test_user_lookup_trim_and_case_insensitive(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users ("
                "username TEXT PRIMARY KEY, password TEXT, role TEXT, name TEXT, "
                "status TEXT, register_time TEXT, audit_time TEXT, auditor TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (username, password, role, name, status, register_time, audit_time, auditor) "
                "VALUES (:username, :password, :role, :name, :status, NULL, NULL, '')"
            ),
            {"username": "Boss  ", "password": "888", "role": "Boss", "name": "老板", "status": "active"},
        )

    monkeypatch.setattr(users_crud, "get_engine", lambda: engine)

    assert users_crud.user_exists(" boss") is True
    row = users_crud.get_user_for_login("BOSS ")
    assert row is not None
    assert row["password"] == "888"
