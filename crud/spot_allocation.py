"""库存中（现货）路径的自动建单与配货。

转合同时按经销商订单明细的「批次/来源」自动选路：

- 库存中行（``FINISHED-STOCK`` / ``库存中`` / 批次为空 / ``inventory_type=finished``）：
  合同行直接置为「已规划」，由本模块自动建立销售订单，并按「机型 + 加高」从
  ``finished_goods_data`` 里未占用的库存机台分配；配齐部分直接分配，缺口原样回传，
  由调用方提示人工补配。
- 具体批次行（如 ``09-10``）：仍走沙盘「待规划」，不在本模块处理。

所有写操作放在同一个数据库事务里；失败由调用方决定是否回滚整个转合同动作。
"""

from __future__ import annotations

import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Iterable, Mapping

from sqlalchemy import text

from database import get_engine
from utils.heightened import (
    is_high_text_hint,
    normalize_dictionary_model_name,
    split_heightened_model_name,
)


class SpotAllocationError(ValueError):
    """现货路径自动配货失败（合同状态、合同数据或订单号生成不允许继续）。"""


def _lock(conn) -> str:
    """sqlite（单元测试）不支持 SELECT ... FOR UPDATE，仅 MySQL 加锁。"""
    return " FOR UPDATE" if conn.dialect.name != "sqlite" else ""


def _to_int(value: Any) -> int:
    try:
        return int(float(str(value).strip() or 0))
    except (TypeError, ValueError):
        return 0


def _to_datetime(value: Any) -> datetime | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text_value[:19], fmt)
        except ValueError:
            continue
    return None


def _new_order_id(conn) -> str:
    for _ in range(20):
        order_id = f"SO-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:4].upper()}"
        exists = conn.execute(
            text("SELECT 1 FROM sales_orders WHERE `订单号` = :oid LIMIT 1"),
            {"oid": order_id},
        ).first()
        if not exists:
            return order_id
    raise SpotAllocationError("订单号生成冲突，请稍后重试")


def _contract_demand(rows: Iterable[Mapping[str, Any]]) -> tuple[dict[tuple[str, bool], int], dict[tuple[str, bool], dict]]:
    """合同行 → {(机型, 是否加高): 需求数量}，并保留每行原始数据用于写备注。"""
    demand: Counter = Counter()
    row_by_key: dict[tuple[str, bool], dict] = {}
    for row in rows:
        raw_model = str(row.get("机型") or "").strip()
        model, name_high = split_heightened_model_name(raw_model)
        if not model:
            raise SpotAllocationError("合同机型为空，无法自动配货")
        qty = _to_int(row.get("排产数量"))
        if qty <= 0:
            raise SpotAllocationError(f"{model} 的需求数量无效，无法自动配货")
        high = name_high or is_high_text_hint(raw_model, row.get("备注"))
        key = (model, high)
        demand[key] += qty
        row_by_key.setdefault(key, dict(row))
    return dict(demand), row_by_key


def _stock_candidates(conn) -> dict[tuple[str, bool], list[dict[str, Any]]]:
    """收集可分配的库存机台，按（机型, 加高）分池，保持流水号稳定顺序。"""
    rows = conn.execute(
        text(
            "SELECT `流水号` AS serial_no, `机型` AS model, COALESCE(`状态`, '') AS status, "
            "COALESCE(`批次号`, '') AS batch_no, COALESCE(`合同备注`, '') AS order_remark, "
            "COALESCE(`客户`, '') AS customer, COALESCE(`代理商`, '') AS agent "
            "FROM finished_goods_data "
            "WHERE TRIM(COALESCE(`状态`, '')) LIKE '库存中%' "
            "  AND TRIM(COALESCE(`占用订单号`, '')) = '' "
            "  AND TRIM(COALESCE(`合同号`, '')) = '' "
            "ORDER BY `流水号`" + _lock(conn)
        )
    ).mappings().all()
    pools: dict[tuple[str, bool], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        serial = str(row.get("serial_no") or "").strip()
        if not serial:
            continue
        raw_model = str(row.get("model") or "").strip()
        model, name_high = split_heightened_model_name(raw_model)
        if not model:
            continue
        high = name_high or is_high_text_hint(raw_model, row.get("batch_no"), row.get("order_remark"))
        pools[(model, high)].append(
            {
                "serial": serial,
                "status": str(row.get("status") or "").strip(),
                "customer": str(row.get("customer") or ""),
                "agent": str(row.get("agent") or ""),
                "order_remark": str(row.get("order_remark") or ""),
            }
        )
    return dict(pools)


def _cache_clear() -> None:
    from crud.inventory import clear_inventory_data_caches
    from crud.orders import get_orders, get_orders_v2
    from crud.planning import get_factory_plan, get_factory_plan_v2

    for fn in (get_factory_plan, get_factory_plan_v2, get_orders, get_orders_v2):
        if hasattr(fn, "cache_clear"):
            fn.cache_clear()
    clear_inventory_data_caches()


def allocate_spot_contract(
    contract_id: str,
    *,
    customer: str = "",
    agent: str = "",
    operator: str = "",
) -> dict:
    """把一张「已规划」合同自动转成销售订单，并分配库存中机台。

    返回字段：
    - ``contract_no`` / ``order_id`` / ``required_qty`` / ``allocated_qty``
    - ``status``：``ready``（配齐）或 ``active``（有缺口，等人工补配）
    - ``shortages``：每条未配齐的（机型, 加高）缺口
    - ``serials`` / ``restore``：本次占用的机台及回滚所需的原状态
    - ``message``：可直接展示的中文摘要
    """
    contract_id = str(contract_id or "").strip()
    if not contract_id:
        raise SpotAllocationError("合同号不能为空")

    with get_engine().begin() as conn:
        rows = conn.execute(
            text("SELECT * FROM factory_plan WHERE `合同号` = :cid ORDER BY id" + _lock(conn)),
            {"cid": contract_id},
        ).mappings().all()
        rows = [dict(row) for row in rows]
        if not rows:
            raise SpotAllocationError("合同不存在，无法自动配货")
        if any(str(row.get("订单号") or "").strip() for row in rows):
            raise SpotAllocationError("合同已转订单，不能重复自动配货")
        if any(str(row.get("状态") or "").strip() != "已规划" for row in rows):
            raise SpotAllocationError("仅已规划合同可以走库存自动配货")

        demand, row_by_key = _contract_demand(rows)
        pools = _stock_candidates(conn)

        chosen: dict[tuple[str, bool], list[dict[str, Any]]] = {}
        shortages: list[dict[str, Any]] = []
        for key, need in demand.items():
            picked = pools.get(key, [])[:need]
            chosen[key] = picked
            if len(picked) < need:
                shortages.append(
                    {
                        "model": key[0],
                        "high": bool(key[1]),
                        "need": need,
                        "allocated": len(picked),
                        "shortage": need - len(picked),
                    }
                )

        required_qty = sum(demand.values())
        allocated_qty = sum(len(items) for items in chosen.values())
        order_id = _new_order_id(conn)
        order_status = "ready" if allocated_qty >= required_qty else "active"
        now = datetime.now()

        customer_name = str(customer or "").strip() or str(rows[0].get("客户名") or "").strip()
        agent_name = str(agent or "").strip() or str(rows[0].get("代理商") or "").strip()
        due_date = next(
            (str(row.get("要求交期") or "").strip() for row in rows if str(row.get("要求交期") or "").strip()),
            "",
        )
        notes = [
            str(row.get("备注") or "").strip()
            for row in rows
            if str(row.get("备注") or "").strip()
        ]
        order_note = "；".join(dict.fromkeys(notes))
        demand_text = ";".join(
            f"{model}{'（加高）' if high else ''}x{qty}" for (model, high), qty in demand.items()
        )
        source_alloc = json.dumps({"库存中": allocated_qty}, ensure_ascii=False) if allocated_qty else "{}"

        conn.execute(
            text(
                "INSERT INTO sales_orders "
                "(`订单号`, `客户名`, `代理商`, `需求机型`, `需求数量`, `下单时间`, `备注`, "
                " `包装选项`, `发货时间`, `指定批次/来源`, `status`, `delete_reason`) "
                "VALUES (:oid, :customer, :agent, :demand, :qty, :now, :note, '', :due, :source, :status, '')"
            ),
            {
                "oid": order_id,
                "customer": customer_name,
                "agent": agent_name,
                "demand": demand_text,
                "qty": required_qty,
                "now": now,
                "note": order_note,
                "due": _to_datetime(due_date),
                "source": source_alloc,
                "status": order_status,
            },
        )
        conn.execute(
            text(
                "UPDATE factory_plan SET `状态` = '已转订单', `订单号` = :oid "
                "WHERE `合同号` = :cid"
            ),
            {"oid": order_id, "cid": contract_id},
        )

        restore: list[dict[str, Any]] = []
        serials: list[str] = []
        for key, machines in chosen.items():
            remark = str(row_by_key[key].get("备注") or "").strip()
            for machine in machines:
                serial = machine["serial"]
                conn.execute(
                    text(
                        "UPDATE finished_goods_data SET `状态` = '待发货', `占用订单号` = :oid, "
                        "`客户` = :customer, `代理商` = :agent, `合同号` = :cid, "
                        "`合同备注` = :note, `更新时间` = :now "
                        "WHERE `流水号` = :serial"
                    ),
                    {
                        "oid": order_id,
                        "customer": customer_name,
                        "agent": agent_name,
                        "cid": contract_id,
                        "note": remark,
                        "now": now,
                        "serial": serial,
                    },
                )
                serials.append(serial)
                restore.append(
                    {
                        "serial": serial,
                        "status": machine["status"],
                        "customer": machine["customer"],
                        "agent": machine["agent"],
                        "order_remark": machine["order_remark"],
                    }
                )

        from crud.contract_notifications import contract_rows, record_converted

        record_converted(conn, contract_rows(conn, [contract_id]), order_id, operator)

    _cache_clear()

    if shortages:
        missing_text = "、".join(
            f"{item['model']}{'（加高）' if item['high'] else ''}缺 {item['shortage']}"
            for item in shortages
        )
        message = (
            f"已自动配货 {allocated_qty}/{required_qty} 台，订单 {order_id}；未配齐：{missing_text}"
        )
    else:
        message = f"已自动配货 {allocated_qty}/{required_qty} 台，订单 {order_id} 已待发货"

    return {
        "contract_no": contract_id,
        "order_id": order_id,
        "order_status": order_status,
        "required_qty": required_qty,
        "allocated_qty": allocated_qty,
        "shortages": shortages,
        "serials": serials,
        "restore": restore,
        "message": message,
    }


def rollback_spot_allocation(result: Mapping[str, Any] | None) -> None:
    """回滚一次现货自动配货：释放机台、删除销售订单、把合同恢复为已规划。

    只用于转合同同一请求内的补偿；失败只记日志，不掩盖原始错误。
    """
    if not result:
        return
    import logging

    contract_id = str(result.get("contract_no") or "").strip()
    order_id = str(result.get("order_id") or "").strip()
    machines = list(result.get("restore") or [])
    now = datetime.now()
    try:
        with get_engine().begin() as conn:
            if order_id:
                for machine in machines:
                    conn.execute(
                        text(
                            "UPDATE finished_goods_data SET `状态` = :status, `占用订单号` = NULL, "
                            "`客户` = :customer, `代理商` = :agent, `合同号` = '', "
                            "`合同备注` = :note, `更新时间` = :now "
                            "WHERE `流水号` = :serial AND `占用订单号` = :oid"
                        ),
                        {
                            "status": machine.get("status") or "库存中",
                            "customer": machine.get("customer") or "",
                            "agent": machine.get("agent") or "",
                            "note": machine.get("order_remark") or "",
                            "now": now,
                            "serial": machine.get("serial"),
                            "oid": order_id,
                        },
                    )
                conn.execute(
                    text("DELETE FROM sales_orders WHERE `订单号` = :oid"),
                    {"oid": order_id},
                )
            if contract_id:
                conn.execute(
                    text(
                        "UPDATE factory_plan SET `订单号` = NULL, `状态` = '已规划' "
                        "WHERE `合同号` = :cid"
                    ),
                    {"cid": contract_id},
                )
                conn.execute(
                    text("DELETE FROM contract_notifications WHERE contract_id = :cid"),
                    {"cid": contract_id},
                )
    except Exception:
        logging.getLogger(__name__).exception(
            "spot allocation rollback failed contract=%s order=%s", contract_id, order_id
        )
    finally:
        try:
            _cache_clear()
        except Exception:
            logging.getLogger(__name__).exception("spot allocation cache clear failed")


def normalize_contract_model(value: Any) -> str:
    """对外暴露的机型归一化（去掉「(加高)」后缀），便于测试与调用方复用。"""
    return normalize_dictionary_model_name(value)
