"""One-off repair. Default is read-only; --apply performs the authorized repair.

Explicit MySQL table locks provide a brief write maintenance window across all
related tables. No DDL or ordinary inbound/completion APIs are used.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "outputs" / "ghost_inventory_20260920"
TARGETS = {}
for numbers, model, slot in [
    (range(31, 37), "FR-400AUTO", "老厂一车间400"),
    (range(271, 279), "FR-400XS(PRO)", "老厂四车间二楼400"),
    (range(46, 51), "FR-600AUTO", "H08"),
    ([297, 298], "FR-600XS(PRO)", "H09"),
]:
    for n in numbers:
        TARGETS[f"96-08-{n}"] = (model, slot)
PROTECTED = ["units", "sales_orders", "inbound_history", "shipping_history",
             "warehouse_layout", "batches", "production_lines", "production_history_ledger",
             "factory_plan", "transaction_log", "contract_records"]


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def digest(rows):
    return hashlib.sha256("\n".join(sorted(encode(r) for r in rows)).encode("utf-8")).hexdigest()


def persist(path, value):
    # Flush the pre-image before any UPDATE is sent.
    with path.open("x", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False, default=str, indent=2))
        f.flush()
        os.fsync(f.fileno())


def snapshot(q):
    result = {}
    for table in ["finished_goods_data", *PROTECTED]:
        q.execute(f"SELECT * FROM `{table}`")
        result[table] = q.fetchall()
    return result


def validate(data):
    rows = [r for r in data["finished_goods_data"] if r["流水号"] in TARGETS]
    assert len(rows) == 21 and {r["流水号"] for r in rows} == set(TARGETS), "目标缺失或重复"
    completed = 0
    for r in rows:
        model, slot = TARGETS[r["流水号"]]
        assert r["机型"] == model, "机型变化"
        assert all(not str(r.get(k) or "").strip() for k in ["占用订单号", "客户", "代理商", "合同号", "合同备注"]), "已出现业务绑定"
        if r["状态"] == f"库存中（{slot}）" and r["Location_Code"] == slot:
            completed += 1
        else:
            assert r["状态"] == "待发货" and not r["Location_Code"], "状态或库位变化"
    assert completed in (0, 21), "部分修复状态，禁止继续覆盖"
    units = [r for r in data["units"] if r["serial_no"] in TARGETS or r["forecast_serial_no"] in TARGETS]
    assert len(units) == 21, "生产关联数量变化"
    assert {r["serial_no"] or r["forecast_serial_no"] for r in units} == set(TARGETS), "生产关联不唯一"
    for r in units:
        assert r["status"] == "Completed" and not r["sales_id"] and not r["contract_no"] and not r["is_locked"] and not r["production_line_id"], "生产卡片变化"
    assert not any(r["流水号"] in TARGETS for r in data["shipping_history"]), "出现发货历史"
    history = [r for r in data["inbound_history"] if r["serial_no"] in TARGETS]
    assert Counter(r["serial_no"] for r in history) == Counter({sn: 1 for sn in TARGETS}), "入库历史变化"
    layout = next(r for r in data["warehouse_layout"] if r["layout_id"] == "default")
    slots = {s["code"]: s for s in json.loads(layout["layout_json"])["slots"]}
    for slot in {v[1] for v in TARGETS.values()}:
        assert slot in slots and slots[slot].get("status") == "正常", "库位不可用"
        assert not slots[slot].get("allowed_models"), "库位限制变化"
    for slot, added in [("H08", 5), ("H09", 2)]:
        occupants = [r for r in data["finished_goods_data"] if r["Location_Code"] == slot and r["流水号"] not in TARGETS
                     and (str(r["状态"] or "").startswith("库存中") or r["状态"] == "待发货")]
        assert len(occupants) + added <= 5, "库位容量不足"
    return rows, bool(completed)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback-test", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    c = pymysql.connect(host=os.getenv("MYSQL_HOST", "localhost"), port=int(os.getenv("MYSQL_PORT", "3306")),
                        user=os.getenv("MYSQL_USER", "root"), password=os.environ["MYSQL_PASSWORD"],
                        database=os.getenv("MYSQL_DB", "rjfinshed"), charset="utf8mb4", autocommit=False,
                        cursorclass=pymysql.cursors.DictCursor, connect_timeout=10, read_timeout=30, write_timeout=30)
    OUT.mkdir(exist_ok=True)
    run_id = "ghost21_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    locked = False
    try:
        with c.cursor() as q:
            q.execute("SELECT DATABASE() db, @@hostname host, @@port port")
            identity = q.fetchone()
            assert identity == {"db": "rjfinshed", "host": "DESKTOP-APMFOHM", "port": 3306}, "数据库目标不同"
            q.execute("SHOW TRIGGERS")
            assert not q.fetchall(), "触发器发生变化，需重新评估"
            q.execute("SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")
            engines = {r["TABLE_NAME"]: r["ENGINE"] for r in q.fetchall()}
            assert all(engines.get(t) == "InnoDB" for t in ["finished_goods_data", "sys_operation_log", *PROTECTED])
            if args.apply or args.rollback_test:
                q.execute("SET SESSION lock_wait_timeout=10")
                q.execute("SET SESSION innodb_lock_wait_timeout=10")
                # LOCK TABLES commits any previous transaction. autocommit=0 is
                # already set; never issue START TRANSACTION after acquiring it.
                q.execute("LOCK TABLES finished_goods_data WRITE, sys_operation_log WRITE, " +
                          ", ".join(f"`{t}` READ" for t in PROTECTED))
                locked = True
            else:
                q.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
            before = snapshot(q)
            rows, already_done = validate(before)
            report = {"run_id": run_id, "database": identity, "already_done": already_done,
                      "target_count": len(rows), "mode": "apply" if args.apply else ("rollback_test" if args.rollback_test else "read_only"),
                      "targets": [{"serial": sn, "model": m, "slot": s, "status": f"库存中（{s}）"}
                                  for sn, (m, s) in sorted(TARGETS.items())]}
            if not (args.apply or args.rollback_test) or already_done:
                c.rollback()
                persist(OUT / f"{run_id}_preview.json", report)
                print(encode(report))
                return
            q.execute("SELECT * FROM sys_operation_log")
            audit_before = q.fetchall()
            backup = {"report": report, "data": before, "existing_audit_digest": digest(audit_before)}
            backup_path = OUT / f"{run_id}_before.json"
            persist(backup_path, backup)
            q.execute("SELECT NOW() AS repair_time")
            repair_time = q.fetchone()["repair_time"]
            audit_ids = []
            for r in sorted(rows, key=lambda r: r["流水号"]):
                sn = r["流水号"]
                model, slot = TARGETS[sn]
                status = f"库存中（{slot}）"
                where = " AND ".join(f"`{key}` <=> %s" for key in r)
                q.execute("UPDATE finished_goods_data SET `状态`=%s, `Location_Code`=%s, `更新时间`=%s WHERE " + where,
                          [status, slot, repair_time, *r.values()])
                assert q.rowcount == 1, "前像不匹配或更新行数异常"
                content = encode({"repair_id": run_id, "reason": "用户确认盘点：无订单待发货恢复库存并指定库位",
                                  "before": {k: r[k] for k in ["状态", "Location_Code", "更新时间"]},
                                  "after": {"状态": status, "Location_Code": slot, "更新时间": repair_time}})
                q.execute("INSERT INTO sys_operation_log (user_id,username,operate_time,module,action_type,biz_type,serial_no,content) "
                          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                          ["codex_authorized_repair", "Codex（用户授权）", repair_time, "库存管理", "库存状态纠错", "机台", sn, content])
                audit_ids.append(q.lastrowid)
            after = snapshot(q)
            _, done = validate(after)
            assert done
            unchanged = {}
            for table in PROTECTED:
                unchanged[table] = digest(before[table]) == digest(after[table])
                assert unchanged[table], f"非目标表变化: {table}"
            other_before = [r for r in before["finished_goods_data"] if r["流水号"] not in TARGETS]
            other_after = [r for r in after["finished_goods_data"] if r["流水号"] not in TARGETS]
            assert digest(other_before) == digest(other_after), "其他库存变化"
            old_by_sn = {r["流水号"]: r for r in rows}
            for r in after["finished_goods_data"]:
                if r["流水号"] in TARGETS:
                    old = old_by_sn[r["流水号"]]
                    assert all(r[k] == old[k] for k in old if k not in {"状态", "Location_Code", "更新时间"})
            q.execute("SELECT * FROM sys_operation_log")
            audits = q.fetchall()
            assert digest([r for r in audits if r["id"] not in audit_ids]) == digest(audit_before)
            valid_orders = {r["订单号"] for r in after["sales_orders"] if str(r["status"] or "").lower() not in {"deleted", "cancelled", "canceled"}}
            ghosts = [r["流水号"] for r in after["finished_goods_data"] if r["状态"] == "待发货" and r["占用订单号"] not in valid_orders]
            assert not ghosts, f"仍存在无有效订单待发货: {ghosts}"
            report.update({"repair_time": repair_time, "updated_rows": 21, "audit_ids": audit_ids,
                           "non_target_inventory_unchanged": True, "protected_tables_unchanged": unchanged,
                           "ghost_count": len(ghosts), "backup": str(backup_path),
                           "after": [r for r in after["finished_goods_data"] if r["流水号"] in TARGETS]})
            persist(OUT / f"{run_id}_verified_before_commit.json", report)
            if args.rollback_test:
                c.rollback()
                restored = snapshot(q)
                assert all(digest(before[t]) == digest(restored[t]) for t in before), "回滚未恢复前像"
                q.execute("SELECT * FROM sys_operation_log")
                assert digest(q.fetchall()) == digest(audit_before), "审计未随事务回滚"
                report["rollback_verified"] = True
                persist(OUT / f"{run_id}_rollback_test.json", report)
                print(encode({k: v for k, v in report.items() if k not in {"targets", "after"}}))
                return
            c.commit()
            report["committed"] = True
            persist(OUT / f"{run_id}_committed.json", report)
            print(encode(report))
    except BaseException:
        c.rollback()
        raise
    finally:
        if locked:
            with c.cursor() as q:
                q.execute("UNLOCK TABLES")
        c.close()


if __name__ == "__main__":
    main()
