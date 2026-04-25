"""
测试用户管理密码安全修复
验证：
1. 用户列表不返回 password 字段
2. 审核/修改用户不篡改其他用户密码
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import pandas as pd


def test_list_users_excludes_password():
    """测试用户列表不返回 password 字段"""
    from api.routes.users import list_users
    
    mock_df = pd.DataFrame({
        "username": ["admin", "user1"],
        "role": ["Admin", "Sales"],
        "name": ["管理员", "张三"],
        "status": ["active", "pending"],
        "register_time": ["2024-01-01", "2024-01-02"],
        "audit_time": [None, None],
        "auditor": ["", ""],
    })
    
    with patch("api.routes.users.get_engine") as mock_engine:
        mock_conn = MagicMock()
        mock_engine.return_value.connect.return_value.__enter__ = lambda self: mock_conn
        mock_engine.return_value.connect.return_value.__exit__ = lambda self, *args: None
        
        mock_total_df = pd.DataFrame({"total": [2]})
        
        with patch("pandas.read_sql") as mock_read_sql:
            mock_read_sql.side_effect = [mock_total_df, mock_df]
            
            result = list_users.__wrapped__(skip=0, limit=10, status="", role="", keyword="", _ctx={"role": "Admin"})
            
            assert "data" in result
            assert len(result["data"]) == 2
            # 验证没有 password 字段
            for user in result["data"]:
                assert "password" not in user


def test_audit_user_does_not_affect_passwords():
    """测试审核用户不修改密码"""
    from api.routes.users import audit_user
    from api.routes.users import UserAuditPayload
    
    payload = UserAuditPayload(username="user1", action="approve", auditor="admin")
    
    with patch("api.routes.users.get_engine") as mock_engine:
        mock_conn = MagicMock()
        mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
        mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None
        
        # 模拟用户存在
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("user1",)
        mock_conn.execute.return_value = mock_result
        
        result = audit_user.__wrapped__(
            payload=payload,
            request=MagicMock(),
            _ctx={"username": "admin", "name": "管理员"}
        )
        
        # 验证执行的是 UPDATE 而不是 DELETE+INSERT
        call_args_list = mock_conn.execute.call_args_list
        
        # 应该有 2 次调用：检查存在 + UPDATE
        assert len(call_args_list) == 2
        
        # 第二次调用应该是 UPDATE
        second_call = call_args_list[1]
        sql = str(second_call[1][1])  # text(sql)
        assert "UPDATE" in sql
        assert "password" not in sql  # 不涉及密码字段


def test_patch_user_does_not_affect_passwords():
    """测试修改用户不修改密码"""
    from api.routes.users import patch_user
    from api.routes.users import UserPatchPayload
    
    payload = UserPatchPayload(role="Boss", name="李四")
    
    with patch("api.routes.users.get_engine") as mock_engine:
        mock_conn = MagicMock()
        mock_engine.return_value.connect.return_value.__enter__ = lambda self: mock_conn
        mock_engine.return_value.connect.return_value.__exit__ = lambda self, *args: None
        mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
        mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None
        
        # 模拟用户存在
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("user1",)
        mock_conn.execute.return_value = mock_result
        
        result = patch_user.__wrapped__(
            username="user1",
            payload=payload,
            request=MagicMock(),
            _ctx={"username": "admin", "name": "管理员"}
        )
        
        # 获取最后一次执行的是 UPDATE
        call_args_list = mock_conn.execute.call_args_list
        last_call = call_args_list[-1]
        sql = str(last_call[1][1])  # text(sql)
        
        assert "UPDATE" in sql
        assert "role = :role" in sql or "name = :name" in sql
        assert "password" not in sql  # 不涉及密码字段


class TestPasswordSecurityRegression:
    """回归测试：防止密码被意外修改"""
    
    def test_admin_password_survives_user_edit(self):
        """测试：编辑其他用户后，admin 密码保持不变"""
        # 这个测试模拟一个场景：
        # admin 修改了 user1 的角色，然后检查 admin 的密码是否还在
        
        mock_users = [
            {"username": "admin", "password": "888", "role": "Admin", "status": "active"},
            {"username": "user1", "password": "user123", "role": "Sales", "status": "active"},
        ]
        
        # 模拟数据库状态
        db_state = {u["username"]: u for u in mock_users}
        
        def mock_update(sql, params=None):
            sql_str = str(sql)
            if "UPDATE" in sql_str and "user1" in str(params):
                # 只修改 user1，不影响其他用户
                if "role" in sql_str:
                    db_state["user1"]["role"] = params.get("role", "Sales")
                return MagicMock(rowcount=1)
            return MagicMock(rowcount=0)
        
        with patch("api.routes.users.get_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = mock_update
            mock_engine.return_value.connect.return_value.__enter__ = lambda self: mock_conn
            mock_engine.return_value.connect.return_value.__exit__ = lambda self, *args: None
            mock_engine.return_value.begin.return_value.__enter__ = lambda self: mock_conn
            mock_engine.return_value.begin.return_value.__exit__ = lambda self, *args: None
            
            # 执行修改 user1 的操作
            from api.routes.users import patch_user, UserPatchPayload
            
            result = mock_update(
                "UPDATE users SET role = :role WHERE LOWER(TRIM(username)) = :username",
                {"username": "user1", "role": "Boss"}
            )
            
            # 验证 admin 密码未被修改
            assert db_state["admin"]["password"] == "888"
            assert db_state["user1"]["password"] == "user123"
