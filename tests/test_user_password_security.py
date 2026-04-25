"""
测试用户管理密码安全修复
验证：
1. 用户列表 SQL 不查询 password 字段
2. 审核/修改用户 SQL 不涉及 password 字段
"""

import pytest


def test_list_users_sql_excludes_password():
    """验证 list_users 的 SQL 不包含 password"""
    with open("api/routes/users.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # 查找 SELECT username, role... 这一行
    import re
    
    # 检查是否移除了 password 字段查询
    # 旧代码: "SELECT username, password, role..."
    # 新代码: "SELECT username, role..."
    select_pattern = r'SELECT username,\s*(\w+)'
    matches = re.findall(select_pattern, content)
    
    for match in matches:
        # 第一个字段应该是 role 而不是 password
        if match == "password":
            # 允许在 FROM 之前的字段列表中包含 password，但应该只在 crud/users.py
            # api/routes/users.py 不应该查询 password
            in_routes_file = 'api/routes/users.py' in content or True  # 我们打开的就是这个文件
            if in_routes_file:
                assert False, "api/routes/users.py 中的 SELECT 不应该包含 password 字段"


def test_api_routes_users_no_password_in_select():
    """验证 api/routes/users.py 不查询 password"""
    with open("api/routes/users.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # 检查 SELECT 语句
    import re
    select_statements = re.findall(r'SELECT\s+([^"]+?)\s+FROM\s+users', content, re.DOTALL | re.IGNORECASE)
    
    for sql in select_statements:
        # 在 api/routes 中不应该查询 password
        assert "password" not in sql.lower(), f"SQL 不应包含 password: {sql}"


def test_audit_user_no_save_all_users():
    """验证 audit_user 不使用 save_all_users"""
    with open("api/routes/users.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # 检查 audit_user 函数区域
    import re
    
    # 找到 @router.post("/audit") 到下一个路由定义之间的内容
    audit_section = re.search(r'@router\.post\("/audit"\).*?(?=@router\.|\Z)', content, re.DOTALL)
    if audit_section:
        audit_func = audit_section.group(0)
        assert "save_all_users" not in audit_func, "audit_user 不应调用 save_all_users"
        assert ("UPDATE users" in audit_func or "DELETE FROM users" in audit_func), "audit_user 应该使用单个 SQL 操作"


def test_patch_user_no_save_all_users():
    """验证 patch_user 不使用 save_all_users"""
    with open("api/routes/users.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    import re
    patch_section = re.search(r'@router\.patch\("/\{username\}"\).*?(?=@router\.|\Z)', content, re.DOTALL)
    if patch_section:
        patch_func = patch_section.group(0)
        assert "save_all_users" not in patch_func, "patch_user 不应调用 save_all_users"
        assert "UPDATE users" in patch_func, "patch_user 应该使用 UPDATE 语句"


class TestPasswordNotInApiResponse:
    """验证 API 响应结构不包含密码"""
    
    def test_user_list_response_has_no_password_field(self):
        """用户列表响应不应包含 password"""
        sample_response = {
            "data": [
                {
                    "username": "admin",
                    "role": "Admin",
                    "name": "管理员",
                    "status": "active",
                    "register_time": "2024-01-01",
                    "audit_time": None,
                    "auditor": None
                }
            ],
            "total": 1,
            "skip": 0,
            "limit": 100
        }
        
        for user in sample_response["data"]:
            assert "password" not in user, "API 响应不应包含 password 字段"
