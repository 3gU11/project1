"""Atomic contract -> selected batch -> order reservation and human review.

No inventory mirror is created until review. Confirmed batches are stable queue
cards; predicted cards cannot be reserved because sandbox recompute replaces them.
"""
import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import text, inspect

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


def _sync_active_ledger(conn, uid):
    if not inspect(conn).has_table("production_history_ledger"):
        return
    u = _rows(conn, "SELECT * FROM units WHERE unit_id=:uid", {"uid": uid})[0]
    conn.execute(text("""UPDATE production_history_ledger SET contract_no=:cid,customer=:customer,
        dealer_name=:dealer,order_remark=:note WHERE unit_id=:uid AND status='In_Production'"""),
        {"uid": uid, "cid": u.get("contract_no"), "customer": u.get("customer"),
         "dealer": u.get("dealer_name"), "note": u.get("order_remark")})


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
        metadata["unit_before"] = {u["unit_id"]: {k: u.get(k) for k in
            ("customer", "dealer_name", "order_remark", "due_date")} for u in units}
        metadata["rush_before"] = _rows(conn, "SELECT * FROM rush_order_queue WHERE contract_no=:cid AND status='pending'", {"cid": cid}, True)
        source = json.dumps({code: len(units), "_batch_plan": metadata}, ensure_ascii=False, default=str)
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
            _sync_active_ledger(conn, unit["unit_id"])
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


def _reservation(conn, oid, lock=False):
    orders = _rows(conn, "SELECT * FROM sales_orders WHERE `订单号`=:oid", {"oid": oid}, lock)
    if not orders:
        raise BatchPlanningError("订单不存在")
    order = orders[0]
    meta = _source(order.get("指定批次/来源")).get("_batch_plan", {})
    if order["status"] != REVIEW_STATUS or not meta or meta.get("reviewed"):
        raise BatchPlanningError("仅未确认配货的批次预占订单可以改配或撤销")
    contract = _contract(conn, meta["contract_id"], lock)
    if not contract or any(r.get("订单号") != oid or r.get("状态") != "已转订单" for r in contract):
        raise BatchPlanningError("合同状态或关联订单已变化，请刷新核查")
    units = _rows(conn, """SELECT u.*,b.status AS batch_status,b.batch_code,b.expected_inbound_date,
        COALESCE(NULLIF(TRIM(u.serial_no),''),TRIM(u.forecast_serial_no)) AS serial
        FROM units u JOIN batches b ON b.batch_id=u.batch_id WHERE u.sales_id=:oid ORDER BY u.unit_id""", {"oid": oid}, lock)
    if not units or {u["unit_id"] for u in units} != set(meta.get("unit_ids", [])):
        raise BatchPlanningError("预占机台已变化，请核查后处理")
    if any(u.get("contract_no") != meta["contract_id"] for u in units):
        raise BatchPlanningError("机台合同已变化，请核查后处理")
    return order, meta, contract, units


def reservation_info(order_id):
    """Derive waiting state from live machines, including legacy pending_review orders."""
    with get_engine().connect() as conn:
        order, meta, contract, units = _reservation(conn, order_id)
        waiting, blocked, machine_states = 0, [], {}
        for u in units:
            stocks = _rows(conn, "SELECT * FROM finished_goods_data WHERE `流水号`=:sn", {"sn": u["serial"]})
            line = _rows(conn, "SELECT status FROM production_lines WHERE line_id=:lid", {"lid": u.get("production_line_id")})
            ready = bool(stocks) and all(str(f.get("状态") or "").startswith("库存中") for f in stocks)
            producing = u["batch_status"] == u["status"] == "In_Production" and bool(line) and line[0]["status"] == "Busy"
            if any(f.get("状态") in ("待发货", "已出库", "已发货", "报废") or
                   str(f.get("占用订单号") or "").strip() not in ("", order_id) or
                   str(f.get("合同号") or "").strip() not in ("", meta["contract_id"]) for f in stocks):
                blocked.append(u["serial"])
                machine_states[u["serial"]] = "预占异常，待核查"
            elif not (ready or producing):
                waiting += 1
                machine_states[u["serial"]] = "待投产（已预占）"
            else:
                machine_states[u["serial"]] = "待配货确认"
        now = datetime.now()
        started = datetime.fromisoformat(meta.get("reserved_at") or meta["created_at"])
        days = max(0, (now.date() - started.date()).days)
        due = sorted(str(r.get("要求交期") or "")[:10] for r in contract if r.get("要求交期"))
        eta = max((str(u.get("expected_inbound_date") or "")[:10] for u in units), default="")
        risk = ""
        if due and due[0] < now.date().isoformat():
            risk = "已超过合同交期"
        elif due and eta and eta > due[0]:
            risk = "批次预计入库晚于合同交期"
        elif due and waiting:
            risk = "机台尚未投产，请核实能否按合同交期完成"
        return {"phase": "blocked" if blocked else "waiting_production" if waiting else "awaiting_confirmation",
                "label": "预占异常，待核查" if blocked else "待投产（已预占）" if waiting else "待配货确认",
                "can_confirm": not waiting and not blocked, "waiting_count": waiting,
                "reserved_days": days, "contract_due_date": due[0] if due else None,
                "risk": risk, "batch_code": units[0].get("batch_code"), "blocked_serials": blocked,
                "machine_states": machine_states}


def replacement_batches(order_id):
    with get_engine().connect() as conn:
        _, meta, contract, _ = _reservation(conn, order_id)
        demand = requirements(contract)
        groups = defaultdict(list)
        for u in _free_units(conn):
            if u["batch_id"] != meta["batch_id"]:
                groups[u["batch_id"]].append(u)
        return [{"batch_id": bid, "batch_code": rows[0].get("batch_code") or bid,
                 "status": rows[0]["batch_status"], "available": len(rows), "required": sum(demand.values())}
                for bid, rows in groups.items() if select_units(rows, demand)]


def _release_reservation(conn, oid, meta, units):
    for u in units:
        if u.get("is_locked") or u.get("is_contract_pinned"):
            raise BatchPlanningError("预占机台已锁定，请先核查并解除锁定后再改配或撤销")
        stocks = _rows(conn, "SELECT * FROM finished_goods_data WHERE `流水号`=:sn", {"sn": u["serial"]}, True)
        for f in stocks:
            if f.get("状态") in ("待发货", "已出库", "已发货", "报废"):
                raise BatchPlanningError("机台已进入配货、发货或报废流程，不能撤销预占")
            if str(f.get("占用订单号") or "").strip() not in ("", oid) or str(f.get("合同号") or "").strip() not in ("", meta["contract_id"]):
                raise BatchPlanningError("库存关联已变化，不能释放其他订单或合同")
        before = meta.get("unit_before", {}).get(u["unit_id"], {})
        conn.execute(text("""UPDATE units SET contract_no=NULL,sales_id=NULL,customer=:customer,
            dealer_name=:dealer,order_remark=:note,due_date=:due,updated_at=CURRENT_TIMESTAMP
            WHERE unit_id=:uid AND sales_id=:oid AND contract_no=:cid"""),
            {"uid": u["unit_id"], "oid": oid, "cid": meta["contract_id"], "customer": before.get("customer"),
             "dealer": before.get("dealer_name"), "note": before.get("order_remark"), "due": before.get("due_date")})
        conn.execute(text("""UPDATE finished_goods_data SET `合同号`='',`占用订单号`='',`客户`='',`代理商`='',`合同备注`='',`更新时间`=CURRENT_TIMESTAMP
            WHERE `流水号`=:sn AND (`占用订单号`=:oid OR `合同号`=:cid)"""), {"sn": u["serial"], "oid": oid, "cid": meta["contract_id"]})
        if inspect(conn).has_table("production_history_ledger"):
            conn.execute(text("""UPDATE production_history_ledger SET contract_no=NULL,customer=NULL,dealer_name=NULL,order_remark=NULL
                WHERE unit_id=:uid AND contract_no=:cid AND status='In_Production'"""), {"uid": u["unit_id"], "cid": meta["contract_id"]})


def change_reservation(order_id, operator, batch_id=None):
    """Replace or cancel an unreviewed reservation in one transaction."""
    with get_engine().begin() as conn:
        # Same order lock as confirmation: only one action can win.
        order, meta, contract, old_units = _reservation(conn, order_id, True)
        cid = meta["contract_id"]
        if batch_id == meta["batch_id"]:
            raise BatchPlanningError("请选择其他批次")
        if batch_id:
            batch = _rows(conn, "SELECT * FROM batches WHERE batch_id=:bid", {"bid": batch_id}, True)
            if not batch or batch[0]["status"] not in ("Confirmed", "In_Production"):
                raise BatchPlanningError("目标批次已不可用")
            units = select_units(_free_units(conn, batch_id, True), requirements(contract))
            if not units:
                raise BatchPlanningError("目标批次适配空卡不足或已被占用，原预占保持不变")
        _release_reservation(conn, order_id, meta, old_units)
        history = meta.setdefault("changes", [])
        history.append({"action": "replace" if batch_id else "cancel", "batch_id": meta["batch_id"],
                        "unit_ids": meta["unit_ids"], "operator": operator, "at": datetime.now().isoformat()})
        if batch_id:
            meta["unit_before"] = {u["unit_id"]: {k: u.get(k) for k in
                ("customer", "dealer_name", "order_remark", "due_date")} for u in units}
            notes = defaultdict(list)
            for r in contract:
                notes[_variant(r["机型"], r.get("备注"))].extend([r] * int(r["排产数量"]))
            from api.routes.planning import _to_contract_date_text
            for u in units:
                r = notes[_variant(u["model_type"], u.get("order_remark"))].pop(0)
                conn.execute(text("""UPDATE units SET contract_no=:cid,sales_id=:oid,customer=:customer,
                    dealer_name=:dealer,order_remark=:note,due_date=:due,updated_at=CURRENT_TIMESTAMP WHERE unit_id=:uid"""),
                    {"cid": cid, "oid": order_id, "uid": u["unit_id"], "customer": r.get("客户名") or "",
                     "dealer": r.get("代理商") or "", "note": r.get("备注") or "", "due": _to_contract_date_text(r.get("要求交期")) or None})
                _sync_active_ledger(conn, u["unit_id"])
            meta.update(batch_id=batch_id, unit_ids=[u["unit_id"] for u in units], reserved_at=datetime.now().isoformat())
            plan = {batch[0].get("batch_code") or batch_id: len(units)}
            conn.execute(text("UPDATE factory_plan SET `指定批次/来源`=:plan WHERE `合同号`=:cid"), {"plan": json.dumps(plan, ensure_ascii=False), "cid": cid})
            status = REVIEW_STATUS
        else:
            conn.execute(text("UPDATE factory_plan SET `状态`='待规划',`订单号`=NULL,`指定批次/来源`=NULL WHERE `合同号`=:cid"), {"cid": cid})
            # Restore demand, not predicted machine identities (recompute owns those).
            rush = meta.get("rush_before", [])
            if rush:
                for r in rush:
                    result = conn.execute(text("UPDATE rush_order_queue SET status='pending',updated_by=:actor WHERE id=:id AND contract_no=:cid AND status='deleted'"),
                        {"id": r["id"], "cid": cid, "actor": operator})
                    if result.rowcount != 1:
                        raise BatchPlanningError("原急单队列已变化，撤销已回滚，请核查")
            else:
                conn.execute(text("UPDATE production_queue SET quantity_remaining=0,status='Pulled' WHERE contract_no=:cid AND status='Waiting'"), {"cid": cid})
                column_info = inspect(conn).get_columns("production_queue")
                columns = {c["name"] for c in column_info}
                from api.routes.planning import _to_contract_date_text
                for r in contract:
                    due = _to_contract_date_text(r.get("要求交期")) or None
                    if due is None and any(c["name"] == "due_date" and not c["nullable"] for c in column_info):
                        raise BatchPlanningError("合同缺少交期，无法恢复排产需求；请先补充交期")
                    values = {"contract_no": cid, "model_type": r["机型"], "customer": r.get("客户名") or "",
                              "dealer": r.get("代理商") or "", "dealer_name": r.get("代理商") or "",
                              "due_date": due,
                              "quantity_remaining": int(r["排产数量"]), "status": "Waiting", "priority": 0,
                              "payload": json.dumps({"remark": r.get("备注") or "", "source": "reservation-cancel"}, ensure_ascii=False)}
                    values = {k: v for k, v in values.items() if k in columns}
                    conn.execute(text(f"INSERT INTO production_queue ({','.join(values)}) VALUES ({','.join(':'+k for k in values)})"), values)
            meta["cancelled"] = True
            plan, status = {}, "canceled"
        plan["_batch_plan"] = meta
        conn.execute(text("UPDATE sales_orders SET status=:status,`指定批次/来源`=:source WHERE `订单号`=:oid"),
            {"oid": order_id, "status": status, "source": json.dumps(plan, ensure_ascii=False, default=str)})
    _clear_caches()
    return {"order_id": order_id, "status": status, "message": "改配完成，原订单号保留" if batch_id else "已撤销规划，合同及排产需求已恢复"}


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
            if unit.get("contract_no") != meta["contract_id"]:
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
