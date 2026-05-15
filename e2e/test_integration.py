
import sys
import os
from fastapi.testclient import TestClient
from sqlalchemy import text

# 加入路径
sys.path.append(r"d:\CURSORpj\V7STD1.0")

from api.main import app
from database import get_engine
from config import GO_INTERNAL_TOKEN

client = TestClient(app)
engine = get_engine()

def test_reverse_sync_api():
    print("\n=== 集成测试: 看板 -> 主系统反向同步接口 ===")
    
    # 1. 准备测试数据
    with engine.connect() as conn:
        row = conn.execute(text("SELECT 合同号, 机型, 备注 FROM factory_plan WHERE 合同号 != '' LIMIT 1")).fetchone()
    
    if not row:
        print("跳过: factory_plan 无数据")
        return

    c_no, old_m, old_r = row
    new_r = f"INTEGRATION_TEST_{os.getpid()}"
    print(f"测试合同: {c_no}, 原备注: {old_r}, 目标新备注: {new_r}")

    # 2. 模拟 Go 端发起请求 (带 Token)
    headers = {"X-Internal-Token": GO_INTERNAL_TOKEN}
    payload = {
        "contract_no": c_no,
        "old_model": old_m,
        "new_model": old_m,
        "order_remark": new_r
    }
    
    print("发起 PATCH /internal/planning/unit-sync ...")
    response = client.patch("/internal/planning/unit-sync", json=payload, headers=headers)
    
    # 3. 验证接口响应
    if response.status_code == 200:
        print(f"[OK] 接口响应成功: {response.json()}")
    else:
        print(f"[FAIL] 接口响应失败: {response.status_code}, {response.text}")
        return

    # 4. 验证数据库是否真实更新
    with engine.connect() as conn:
        updated_r = conn.execute(text("SELECT 备注 FROM factory_plan WHERE 合同号 = :c AND 机型 = :m"), {"c": c_no, "m": old_m}).fetchone()[0]
    
    if updated_r == new_r:
        print(f"[SUCCESS] 数据库验证通过: 备注已更新为 {updated_r}")
    else:
        print(f"[FAILURE] 数据库验证失败: 预期 {new_r}, 实际 {updated_r}")

def test_auth_security():
    print("\n=== 安全性测试: 验证非法 Token 拦截 ===")
    config_token = (GO_INTERNAL_TOKEN or "").strip()
    
    if not config_token:
        print("[SKIP] 当前环境未配置 GO_INTERNAL_TOKEN，跳过权限拦截测试")
        return

    headers = {"X-Internal-Token": "WRONG_TOKEN_VALUE_123"}
    payload = {"contract_no": "test", "old_model": "test", "new_model": "test", "order_remark": "test"}
    
    response = client.patch("/internal/planning/unit-sync", json=payload, headers=headers)
    if response.status_code == 403:
        print("[SUCCESS] 非法 Token 已被正确拦截 (403 Forbidden)")
    else:
        print(f"[FAILURE] 安全隐患: 提供了错误 Token 但未被拦截 ({response.status_code})")

if __name__ == "__main__":
    try:
        test_reverse_sync_api()
        test_auth_security()
    except Exception as e:
        print(f"测试运行出错: {e}")
