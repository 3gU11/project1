"""Read-only order progress shared by order and customer inventory pages."""
from collections import Counter, defaultdict
from sqlalchemy import text, bindparam
from database import get_engine
from utils.parsers import parse_alloc_dict


def contract_is_planned(row):
    status = str(row.get("状态") or "").strip()
    if status == "已规划":
        return True
    if status != "已转订单":
        return False
    try:
        need = int(float(row.get("排产数量") or 0))
    except (ValueError, TypeError):
        return False
    return need > 0 and sum(parse_alloc_dict(row.get("指定批次/来源")).values()) >= need


def calculate_progress(status, required, shipped, allocated, contracts, variant_key, include_machines=False):
    special = {"deleted": "已删除", "canceled": "已取消", "pending_review": "待二次确认"}
    shipped = {str(r["流水号"]): r for r in shipped if r.get("流水号")}
    allocated = {str(r["流水号"]): r for r in allocated if r.get("流水号") and str(r["流水号"]) not in shipped}
    def covers(rows):
        counts = Counter(variant_key(r) for r in rows)
        return bool(required) and all(counts[k] >= n for k, n in required.items())
    result = {"shipped_count": len(shipped), "allocated_count": len(allocated), "required_count": sum(required.values())}
    if include_machines:
        result["machines"] = [
            {"serial_no": sn, "model": row.get("机型") or "", "stage": stage,
             "location": row.get("Location_Code") or "", "contract_no": row.get("合同号") or ""}
            for stage, machines in [("有效已发", shipped), ("已配未发", allocated)]
            for sn, row in sorted(machines.items())
        ]
    if status in special:
        label = special[status]
    elif covers(shipped.values()):
        label = "已完成"
    elif status in {"ready", "allocated", "packed"} and covers([*shipped.values(), *allocated.values()]):
        label = "待发货"
    elif shipped or allocated or status in {"ready", "allocated", "packed", "shipped", "done"}:
        label = "待配齐"
    elif not contracts:
        # 订单没有关联任何合同：与"合同未规划"是两回事，不能都叫待规划。
        label = "未关联合同"
    elif all(contract_is_planned(r) for r in contracts):
        label = "已规划"
    else:
        label = "待规划"
    return {**result, "order_status_label": label}


def load_order_progress(order_ids, demand_for_order, variant_key, include_machines=False):
    ids = sorted({str(x).strip() for x in order_ids if str(x or "").strip()})
    if not ids:
        return {}
    def fetch(conn, sql):
        return [dict(r) for r in conn.execute(text(sql).bindparams(bindparam("ids", expanding=True)), {"ids": ids}).mappings()]
    with get_engine().connect() as conn:
        orders = fetch(conn, "SELECT * FROM sales_orders WHERE `订单号` IN :ids")
        contracts = fetch(conn, "SELECT * FROM factory_plan WHERE `订单号` IN :ids")
        stock = fetch(conn, "SELECT * FROM finished_goods_data WHERE `占用订单号` IN :ids")
        history = fetch(conn, "SELECT * FROM shipping_history WHERE `占用订单号` IN :ids")
        production = fetch(conn, """SELECT COALESCE(NULLIF(u.serial_no,''),u.forecast_serial_no) AS `流水号`,
            u.model_type AS `机型`, u.order_remark AS `合同备注`, u.sales_id AS `占用订单号`
            FROM units u JOIN batches b ON b.batch_id=u.batch_id
            WHERE u.sales_id IN :ids AND b.status IN ('Confirmed','In_Production')""")
        returns = []
        if conn.execute(text("SHOW TABLES LIKE 'shipping_return_history'")).first():
            returns = fetch(conn, "SELECT `流水号`,`原订单号`,`操作时间` FROM shipping_return_history WHERE `原订单号` IN :ids")
    def group(rows, field):
        result = defaultdict(list)
        for row in rows:
            result[str(row.get(field) or "").strip()].append(row)
        return result
    contracts_by_order = group(contracts, "订单号")
    stock_by_order = group(stock, "占用订单号")
    production_by_order = group(production, "占用订单号")
    last_return = {}
    for row in returns:
        key = (str(row["原订单号"]).strip(), str(row["流水号"]).strip())
        last_return[key] = max(last_return.get(key, ""), str(row["操作时间"] or ""))
    valid_history = []
    for row in history:
        key = (str(row.get("占用订单号") or "").strip(), str(row.get("流水号") or "").strip())
        if key not in last_return or str(row.get("更新时间") or "") > last_return[key]:
            valid_history.append(row)
    history_by_order = group(valid_history, "占用订单号")
    result = {}
    for order in orders:
        oid = str(order["订单号"]).strip()
        current = stock_by_order[oid]
        # Keep legacy shipments without archive rows; DG stock needs an actual shipping record.
        legacy_shipped = [r for r in current if str(r.get("状态") or "").strip() in {"已出库", "已发货"}
                          and ((oid, str(r.get("流水号") or "").strip()) not in last_return
                               or str(r.get("更新时间") or "") > last_return[(oid, str(r.get("流水号") or "").strip())])]
        allocated = [r for r in current if str(r.get("状态") or "").strip() == "待发货"]
        result[oid] = calculate_progress(str(order.get("status") or "active"), demand_for_order(order),
            [*history_by_order[oid], *legacy_shipped], [*production_by_order[oid], *allocated],
            contracts_by_order[oid], variant_key, include_machines=include_machines)
    return result
