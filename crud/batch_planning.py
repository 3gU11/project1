"""Atomic contract -> selected batch -> order reservation and human review.

No inventory mirror is created until review. Confirmed batches are stable queue
cards; predicted cards cannot be reserved because sandbox recompute replaces them.
"""
import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import text

from database import get_engine


REVIEW_STATUS = "pending_review"


class BatchPlanningError(ValueError):
    pass


def _lock(conn):
    return " FOR UPDATE" if conn.dialect.name != "sqlite" else ""


def _rows(conn, sql, params=None, lock=False):
    return [dict(row) for row in conn.execute(
        text(sql + (_lock(conn) if lock else "")), params or {}
    ).mappings().all()]


def _source(value):
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except (ValueError, TypeError):
        return {}


def _variant(model, note=""):
    from api.routes.planning import _normalize_alloc_model, _is_high_model_hint
    return _normalize_alloc_model(model), _is_high_model_hint(model, note)


def requirements(rows):
    result = Counter()
    if not rows:
        raise BatchPlanningError("合同不存在")
    for row in rows:
        try:
            qty = int(str(row.get("排产数量") or ""))
        except ValueError:
            raise BatchPlanningError("合同需求数量无效，请先修改合同")
        key = _variant(row.get("机型"), row.get("备注"))
        if not key[0] or qty <= 0:
            raise BatchPlanningError("合同机型或需求数量无效")
        result[key] += qty
    return result


def select_units(rows, demand):
    """Choose each variant deterministically; never fill from another batch."""
    groups = defaultdict(list)
    seen = set()
    for row in rows:
        sn = str(row.get("serial") or "").strip()
        if not sn or sn in seen:
            continue
        seen.add(sn)
        groups[_variant(row.get("model_type"), row.get("order_remark"))].append(row)
    chosen = []
    for key, qty in demand.items():
        if len(groups[key]) < qty:
            return []
        chosen.extend(groups[key][:qty])
    return chosen


def _contract(conn, cid, lock=False):
    return _rows(conn, "SELECT * FROM factory_plan WHERE `合同号`=:cid ORDER BY id", {"cid": cid}, lock)


def _validate_contract(rows):
    if not rows:
        raise BatchPlanningError("合同不存在")
    if any(str(r.get("订单号") or "").strip() for r in rows):
        raise BatchPlanningError("合同已转订单，请勿重复规划")
    if any(r.get("状态") != "待规划" for r in rows):
        raise BatchPlanningError("仅待规划合同可以按批次快捷规划")


def _free_units(conn, batch_id=None, lock=False):
    return _rows(conn, """
        SELECT u.*, b.batch_code, b.status AS batch_status,
               COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no)) AS serial
        FROM units u JOIN batches b ON b.batch_id=u.batch_id
        WHERE b.status IN ('Confirmed','In_Production')
          AND ((b.status='Confirmed' AND u.status IN ('Pending','Confirmed'))
               OR (b.status='In_Production' AND u.status='In_Production'))
          AND TRIM(COALESCE(u.contract_no,''))=''
          AND TRIM(COALESCE(u.sales_id,''))=''
          AND COALESCE(u.is_locked,0)=0
          AND COALESCE(u.is_contract_pinned,0)=0
          AND NOT EXISTS (
              SELECT 1 FROM finished_goods_data fg
              WHERE TRIM(fg.`流水号`)=COALESCE(NULLIF(TRIM(u.serial_no),''),TRIM(u.forecast_serial_no))
                AND (TRIM(COALESCE(fg.`合同号`,''))<>'' OR TRIM(COALESCE(fg.`占用订单号`,''))<>''
                     OR COALESCE(fg.`状态`,'') LIKE '库存中%'
                     OR fg.`状态` IN ('待发货','已出库','已发货','报废'))
          )
    """ + (" AND u.batch_id=:bid" if batch_id else "") + " ORDER BY b.batch_id,u.slot_index,u.unit_id",
        {"bid": batch_id} if batch_id else {}, lock)


def eligible_batches(cid):
    with get_engine().connect() as conn:
        contract = _contract(conn, cid)
        _validate_contract(contract)
        demand = requirements(contract)
        groups = defaultdict(list)
        for row in _free_units(conn):
            groups[row["batch_id"]].append(row)
        return [{"batch_id": bid, "batch_code": rows[0].get("batch_code") or bid,
                 "status": rows[0]["batch_status"], "available": len(rows),
                 "required": sum(demand.values())}
                for bid, rows in groups.items() if select_units(rows, demand)]


def _clear_caches():
    from crud.planning import get_factory_plan, get_factory_plan_v2
    from crud.orders import get_orders, get_orders_v2
    from crud.inventory import clear_inventory_data_caches
    for fn in (get_factory_plan, get_factory_plan_v2, get_orders, get_orders_v2):
        if hasattr(fn, "cache_clear"):
            fn.cache_clear()
    clear_inventory_data_caches()


def plan_contract(cid, bid, operator):
    with get_engine().begin() as conn:
        contract = _contract(conn, cid, True)
        # Contract row lock is also the idempotency boundary (including HTTP retry).
        orders = {str(r.get("订单号") or "").strip() for r in contract} - {""}
        if len(orders) == 1:
            order = _rows(conn, "SELECT * FROM sales_orders WHERE `订单号`=:oid", {"oid": next(iter(orders))})
            if order and _source(order[0].get("指定批次/来源")).get("_batch_plan", {}).get("batch_id") == bid:
                return {"order_id": next(iter(orders)), "status": order[0]["status"], "replayed": True}
        _validate_contract(contract)
        demand = requirements(contract)
        batch = _rows(conn, "SELECT * FROM batches WHERE batch_id=:bid", {"bid": bid}, True)
        if not batch or batch[0]["status"] not in ("Confirmed", "In_Production"):
            raise BatchPlanningError("该批次不可规划，请刷新可选批次")
        units = select_units(_free_units(conn, bid, True), demand)
        if not units:
            raise BatchPlanningError("该批次适配空卡不足或已被占用，请重新选择批次")
        existing = _rows(conn, """SELECT u.unit_id FROM units u JOIN batches b ON b.batch_id=u.batch_id
            WHERE u.contract_no=:cid AND b.status<>'Predicted'""", {"cid": cid}, True)
        if existing:
            raise BatchPlanningError("合同已绑定其他非预测卡片，不能重复分配")
        oid = "SO" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:8].upper()
        code = batch[0].get("batch_code") or bid
        metadata = {"batch_id": bid, "contract_id": cid, "unit_ids": [u["unit_id"] for u in units],
                    "operator": operator, "created_at": datetime.now().isoformat(), "reviewed": False}
        source = json.dumps({code: len(units), "_batch_plan": metadata}, ensure_ascii=False)
        first = contract[0]
        conn.execute(text("""INSERT INTO sales_orders
            (`订单号`,`客户名`,`代理商`,`需求机型`,`需求数量`,`下单时间`,`备注`,`包装选项`,`指定批次/来源`,status)
            VALUES (:oid,:customer,:dealer,:demand,:qty,CURRENT_TIMESTAMP,:note,'',:source,:status)"""),
            {"oid": oid, "customer": first.get("客户名") or "", "dealer": first.get("代理商") or "",
             "demand": ";".join(f"{m}{'（加高）' if h else ''}×{q}" for (m,h),q in demand.items()),
             "qty": len(units), "note": "；".join(dict.fromkeys(str(r.get("备注") or "") for r in contract)),
             "source": source, "status": REVIEW_STATUS})
        # Only clear this contract's predicted placeholders, never another contract.
        conn.execute(text("""UPDATE units SET contract_no=NULL,customer=NULL,dealer_name=NULL,
            sales_id=NULL,order_remark=NULL,due_date=NULL,updated_at=CURRENT_TIMESTAMP
            WHERE contract_no=:cid AND batch_id IN (SELECT batch_id FROM batches WHERE status='Predicted')"""), {"cid": cid})
        notes = defaultdict(list)
        for row in contract:
            notes[_variant(row.get("机型"),row.get("备注"))].extend([row] * int(row["排产数量"]))
        for unit in units:
            detail = notes[_variant(unit["model_type"],unit.get("order_remark"))].pop(0)
            from api.routes.planning import _to_contract_date_text
            conn.execute(text("""UPDATE units SET contract_no=:cid,sales_id=:oid,customer=:customer,
                dealer_name=:dealer,order_remark=:note,due_date=:due,updated_at=CURRENT_TIMESTAMP
                WHERE unit_id=:uid AND TRIM(COALESCE(contract_no,''))='' AND TRIM(COALESCE(sales_id,''))=''"""),
                {"cid": cid,"oid": oid,"customer": first.get("客户名") or "", "dealer": first.get("代理商") or "",
                 "note": detail.get("备注") or "", "due": _to_contract_date_text(detail.get("要求交期")) or None,"uid": unit["unit_id"]})
        conn.execute(text("""UPDATE factory_plan SET `状态`='已转订单',`订单号`=:oid,`指定批次/来源`=:source
            WHERE `合同号`=:cid"""), {"oid":oid,"cid":cid,"source":json.dumps({code:len(units)},ensure_ascii=False)})
        conn.execute(text("UPDATE production_queue SET quantity_remaining=0,status='Pulled' WHERE contract_no=:cid AND status='Waiting'"), {"cid":cid})
        conn.execute(text("UPDATE rush_order_queue SET status='deleted',updated_by=:operator WHERE contract_no=:cid AND status='pending'"), {"cid":cid,"operator":operator})
    _clear_caches()
    return {"order_id":oid,"status":REVIEW_STATUS,"count":len(units),"batch_code":code}


def review_rows(order_id):
    with get_engine().connect() as conn:
        order = _rows(conn,"SELECT status FROM sales_orders WHERE `订单号`=:oid",{"oid":order_id})
        if not order or order[0]["status"] != REVIEW_STATUS:
            return None
        return _rows(conn,"""SELECT COALESCE(NULLIF(u.serial_no,''),u.forecast_serial_no) AS `流水号`,
            u.model_type AS `机型`,u.sales_id AS `占用订单号`,u.contract_no AS `合同号`,
            '待二次确认' AS `状态`,b.batch_code AS `批次号`,u.order_remark AS `合同备注`,
            CASE WHEN b.status='Confirmed' THEN '待投产机台' ELSE '在产机器' END AS `货源`
            FROM units u JOIN batches b ON b.batch_id=u.batch_id WHERE u.sales_id=:oid
            ORDER BY u.slot_index,u.unit_id""",{"oid":order_id})


def pending_review_order(conn, serial, order_id=""):
    """Resolve the reservation even if the inventory mirror predates planning."""
    rows = _rows(conn, """SELECT so.`订单号` AS oid FROM sales_orders so
        WHERE so.status=:status AND (so.`订单号`=:oid OR EXISTS (
            SELECT 1 FROM units u WHERE u.sales_id=so.`订单号`
            AND COALESCE(NULLIF(TRIM(u.serial_no),''),TRIM(u.forecast_serial_no))=:sn))""",
        {"status": REVIEW_STATUS, "oid": order_id, "sn": serial})
    return rows[0]["oid"] if rows else ""


def confirm_review(order_id, operator):
    with get_engine().begin() as conn:
        orders = _rows(conn,"SELECT * FROM sales_orders WHERE `订单号`=:oid",{"oid":order_id},True)
        if not orders:
            raise BatchPlanningError("订单不存在")
        order=orders[0]
        source=_source(order.get("指定批次/来源"))
        meta=source.get("_batch_plan",{})
        if meta.get("reviewed"):
            return {"status":order["status"],"replayed":True}
        if order["status"] != REVIEW_STATUS or not meta:
            raise BatchPlanningError("订单不是待二次确认状态")
        units=_rows(conn,"""SELECT u.*,b.status AS batch_status,b.batch_code,b.expected_inbound_date,
            COALESCE(NULLIF(u.serial_no,''),u.forecast_serial_no) AS serial
            FROM units u JOIN batches b ON b.batch_id=u.batch_id WHERE u.sales_id=:oid
            ORDER BY u.unit_id""",{"oid":order_id},True)
        if {u["unit_id"] for u in units} != set(meta["unit_ids"]):
            raise BatchPlanningError("预占机台已变化，请核查订单，不能直接确认")
        contract=_contract(conn,meta["contract_id"],True)
        demand=requirements(contract)
        if Counter(_variant(u["model_type"],u.get("order_remark")) for u in units) != demand:
            raise BatchPlanningError("预占机台与合同需求不一致")
        for unit in units:
            if unit.get("contract_no") != meta["contract_id"] or unit["batch_id"] != meta["batch_id"]:
                raise BatchPlanningError("机台合同或批次已变化，请重新核查")
            stock=_rows(conn,"SELECT * FROM finished_goods_data WHERE `流水号`=:sn",{"sn":unit["serial"]},True)
            fg=stock[0] if stock else {}
            if str(fg.get("占用订单号") or "").strip() not in ("",order_id):
                raise BatchPlanningError("机台已被其他订单占用")
            if str(fg.get("合同号") or "").strip() not in ("",meta["contract_id"]):
                raise BatchPlanningError("机台已绑定其他合同")
            status=str(fg.get("状态") or "")
            stock_ready=status.startswith("库存中")
            line=_rows(conn,"SELECT status FROM production_lines WHERE line_id=:lid",{"lid":unit.get("production_line_id")})
            in_production=unit["batch_status"] == unit["status"] == "In_Production" and bool(line) and line[0]["status"] == "Busy"
            if status in ("已出库","已发货","报废","待发货") or not (stock_ready or in_production):
                raise BatchPlanningError(f"机台 {unit['serial']} 尚未投产或不可配货，请待符合配货条件后确认")
            values={"sn":unit["serial"],"oid":order_id,"cid":meta["contract_id"],"customer":order["客户名"],
                    "dealer":order["代理商"],"note":unit.get("order_remark") or "","batch":unit.get("batch_code"),
                    "model":unit["model_type"],"eta":unit.get("expected_inbound_date")}
            if stock:
                conn.execute(text("""UPDATE finished_goods_data SET `状态`='待发货',`占用订单号`=:oid,
                    `合同号`=:cid,`客户`=:customer,`代理商`=:dealer,`合同备注`=:note,`更新时间`=CURRENT_TIMESTAMP
                    WHERE `流水号`=:sn"""),values)
            else:
                conn.execute(text("""INSERT INTO finished_goods_data
                    (`流水号`,`机型`,`批次号`,`状态`,`占用订单号`,`合同号`,`客户`,`代理商`,`合同备注`,`预计入库时间`,`更新时间`)
                    VALUES (:sn,:model,:batch,'待发货',:oid,:cid,:customer,:dealer,:note,:eta,CURRENT_TIMESTAMP)"""),values)
        meta.update(reviewed=True,reviewed_by=operator,reviewed_at=datetime.now().isoformat())
        conn.execute(text("UPDATE sales_orders SET status='ready',`指定批次/来源`=:source WHERE `订单号`=:oid"),
                     {"oid":order_id,"source":json.dumps(source,ensure_ascii=False)})
    _clear_caches()
    return {"status":"ready","count":len(units),"message":"二次确认完成，订单进入待发货"}
