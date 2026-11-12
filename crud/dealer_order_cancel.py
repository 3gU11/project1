"""经销商订单「一键取消」级联内核。

小程序经销商订单在「审核通过 → 转合同（factory_plan）→ 导入销售订单（sales_orders）
→ 配货（finished_goods_data 状态='待发货'，在产机台同时写 units.sales_id）」之后，
客户要取消时需要跨多个页面手工逆向。本模块提供三件事：

1) ``preview_dealer_order_cancel(order_no)``
   只读预检：告诉前端能不能取消、卡在哪些机台/合同上，以及会释放多少机台；
2) ``execute_dealer_order_cancel(conn, order_no, operator, reason="")``
   在调用方事务连接上做级联释放（写 finished_goods_data / units / factory_plan /
   sales_orders / dealer_orders / cloud_sync_outbox），不 begin、不 commit；
3) ``cancel_dealer_order(order_no, operator, reason="", initiator_role="")``
   审批编排层：先 preview，再懒 import crud.workflows 发起逆向审批实例并自动执行。

设计约束（与任务冻结接口保持一致）：
- ``execute_dealer_order_cancel`` 只接受调用方已经开启的事务连接；
- SQL 同时兼容 MySQL 与 sqlite 单测：不使用 ``ON DUPLICATE KEY`` / ``DATE_FORMAT`` /
  ``CONCAT`` 等 MySQL 专有语法；时间列统一用 ``CURRENT_TIMESTAMP``，只有
  ``dealer_orders.reviewed_at`` 沿用 ``NOW()``（sqlite 单测会注册该函数）；
- ``production_queue`` / ``rush_order_queue`` / ``production_history_ledger`` 等历史表
  可能不存在，先做表/列探测（SQLAlchemy Inspector，两种数据库都可用）再执行，缺失时跳过；
- ``crud.workflows`` 只在编排函数内部懒 import，避免与工作流执行器循环导入。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import bindparam, inspect, text

from database import get_engine
from crud.dealer_orders import (
    CONTRACT_NO_SEPARATOR,
    _aggregate_status,
    _enqueue_cloud_sync,
    _get_order_lines_for_update,
    _row_to_dict,
    split_contract_nos,
)
from crud.inventory import shipped_machine_sql

logger = logging.getLogger(__name__)

# 可取消的经销商订单聚合状态（pending 走「驳回」，已取消/已完成不再重复取消）。
CANCELLABLE_STATUSES = frozenset({"approved", "contracted", "partial_allocated", "allocated"})
TERMINAL_STATUSES = frozenset({"completed", "complete"})
CANCELLED_STATUS = "cancelled"

# 配货阶段占用机台在 finished_goods_data 里的状态（与配货写入口径一致）。
ALLOCATED_MACHINE_STATUSES = ("待发货", "机台")
# 已出库/已发货机台只能走发货复核，不允许在这里直接取消。
SHIPPED_BLOCKER_HINT = "请走「发货复核→退换货处理」"


def _normalize_operator(operator: str) -> str:
    return str(operator or "").strip() or "system"


def _split_order_nos(value: Any) -> list[str]:
    """把销售订单号（列表或 、/，/, 分隔文本）拆成去重列表。"""
    raw_values = [value] if isinstance(value, str) else list(value or [])
    order_nos: list[str] = []
    for raw in raw_values:
        for part in CONTRACT_NO_SEPARATOR.split(str(raw or "")):
            order_no = part.strip()
            if order_no and order_no not in order_nos:
                order_nos.append(order_no)
    return order_nos


def _collect_contracts(items: list[dict]) -> list[str]:
    return split_contract_nos([item.get("contract_no") for item in items])


def _collect_sales_orders(conn, contracts: list[str], items: list[dict]) -> list[str]:
    """销售订单 = factory_plan 按合同号取 DISTINCT 订单号 + dealer_orders.v7_order_no。"""
    sales_orders: list[str] = []
    if contracts:
        rows = conn.execute(
            text(
                "SELECT DISTINCT TRIM(COALESCE(`订单号`, '')) FROM factory_plan "
                "WHERE TRIM(COALESCE(`合同号`, '')) IN :contracts "
                "AND COALESCE(TRIM(`订单号`), '') <> ''"
            ).bindparams(bindparam("contracts", expanding=True)),
            {"contracts": list(contracts)},
        ).fetchall()
        for row in rows:
            order_no = str(row[0] or "").strip()
            if order_no and order_no not in sales_orders:
                sales_orders.append(order_no)
    for item in items:
        for order_no in _split_order_nos(item.get("v7_order_no")):
            if order_no not in sales_orders:
                sales_orders.append(order_no)
    return sales_orders


def _query_fg_by_chain(
    conn,
    contracts: list[str],
    sales_orders: list[str],
    *,
    statuses: tuple[str, ...] | None = None,
    shipped_only: bool = False,
) -> list[dict]:
    """按「占用订单号 IN 销售订单 OR 合同号 IN 合同」查 finished_goods_data 机台。

    拆成两条单参数查询（而不是拼复杂 OR），既避免空列表展开报错，也方便加
    shipped_machine_sql()/状态过滤；结果按流水号去重。
    这里是普通读（不加锁）：写路径随后用 ``_lock_machines`` 按流水号精确锁行，
    避免在 TRIM(COALESCE(...)) 表达式上做全表加锁扫描。
    """
    rows: list[dict] = []
    seen: set[str] = set()
    for column, values in (("`占用订单号`", sales_orders), ("`合同号`", contracts)):
        if not values:
            continue
        where_parts = [f"TRIM(COALESCE({column}, '')) IN :values"]
        bindings = [bindparam("values", expanding=True)]
        params: dict[str, Any] = {"values": list(values)}
        if statuses:
            where_parts.append("TRIM(COALESCE(`状态`, '')) IN :statuses")
            bindings.append(bindparam("statuses", expanding=True))
            params["statuses"] = list(statuses)
        if shipped_only:
            where_parts.append(shipped_machine_sql())
        sql = (
            "SELECT `流水号` AS serial_no, "
            "TRIM(COALESCE(`Location_Code`, '')) AS location_code, "
            "TRIM(COALESCE(`状态`, '')) AS status "
            "FROM finished_goods_data WHERE " + " AND ".join(where_parts)
        )
        statement = text(sql).bindparams(*bindings)
        for row in conn.execute(statement, params).mappings().all():
            data = dict(row)
            serial = str(data.get("serial_no") or "").strip()
            if not serial or serial in seen:
                continue
            seen.add(serial)
            data["serial_no"] = serial
            rows.append(data)
    return rows


def _production_serials(conn, serials: list[str]) -> set[str]:
    """在产机台：units JOIN batches（b.status IN Confirmed/In_Production）命中流水号。"""
    if not serials:
        return set()
    rows = conn.execute(
        text(
            """
            SELECT COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) AS serial_no
            FROM units u
            JOIN batches b ON b.batch_id = u.batch_id
            WHERE b.status IN ('Confirmed', 'In_Production')
              AND COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) IN :serials
            """
        ).bindparams(bindparam("serials", expanding=True)),
        {"serials": list(serials)},
    ).fetchall()
    return {str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()}


def _lock_machines(conn, serials: list[str]) -> dict[str, dict]:
    """按流水号精确加锁（走流水号索引），返回锁到的最新机台状态。

    写路径先普通读找出候选机台，再按流水号 ``FOR UPDATE`` 锁定：既避免在
    ``TRIM(COALESCE(...))`` 表达式上做全表加锁扫描，也能发现「候选读出后已被并发
    发货/改配」的机台（锁定读返回最新已提交状态）。
    """
    serial_list = [str(serial).strip() for serial in (serials or []) if str(serial).strip()]
    serial_list = list(dict.fromkeys(serial_list))
    if not serial_list:
        return {}
    rows = conn.execute(
        text(
            "SELECT `流水号` AS serial_no, "
            "TRIM(COALESCE(`Location_Code`, '')) AS location_code, "
            "TRIM(COALESCE(`状态`, '')) AS status, "
            "TRIM(COALESCE(`占用订单号`, '')) AS occupied_order_no, "
            "TRIM(COALESCE(`合同号`, '')) AS contract_no "
            "FROM finished_goods_data WHERE `流水号` IN :serials FOR UPDATE"
        ).bindparams(bindparam("serials", expanding=True)),
        {"serials": serial_list},
    ).mappings().all()
    return {str(row["serial_no"]).strip(): dict(row) for row in rows}


def _machines_snapshot(conn, contracts: list[str], sales_orders: list[str]) -> dict:
    rows = _query_fg_by_chain(
        conn, contracts, sales_orders, statuses=ALLOCATED_MACHINE_STATUSES
    )
    serials = sorted(str(row["serial_no"]) for row in rows)
    production = _production_serials(conn, serials)
    production_count = sum(1 for serial in serials if serial in production)
    return {
        "total": len(serials),
        "stock": len(serials) - production_count,
        "production": production_count,
        "serials": serials,
    }


def _table_columns(conn, table_name: str) -> set[str]:
    """探测表结构；表不存在时返回空集合（MySQL 与 sqlite 都可用）。"""
    try:
        return {str(column["name"]) for column in inspect(conn).get_columns(table_name)}
    except Exception:
        return set()


def preview_dealer_order_cancel(order_no: str) -> dict:
    """只读预检经销商订单取消；返回前端展示所需的完整快照。

    可取消状态：approved / contracted / partial_allocated / allocated；
    pending 提示先驳回、cancelled 幂等提示、completed 阻止；
    factory_pending=1 与存在已出库/已发货机台都会阻止。
    """
    order_no = str(order_no or "").strip()
    if not order_no:
        raise ValueError("经销商订单号不能为空")

    with get_engine().begin() as conn:
        rows = conn.execute(
            text("SELECT * FROM dealer_orders WHERE order_no=:order_no ORDER BY line_no, id"),
            {"order_no": order_no},
        ).fetchall()
        if not rows:
            raise ValueError("订单不存在")
        items = [_row_to_dict(row) for row in rows]
        status = str(_aggregate_status(items) or "").strip()
        contracts = _collect_contracts(items)
        sales_orders = _collect_sales_orders(conn, contracts, items)
        machines = _machines_snapshot(conn, contracts, sales_orders)
        shipped = _query_fg_by_chain(conn, contracts, sales_orders, shipped_only=True)

    blockers: list[str] = []
    warnings: list[str] = []
    shipped_machines = [str(row["serial_no"]) for row in shipped]

    if shipped_machines:
        detail = "、".join(
            f"{row['serial_no']}（{row.get('status') or '已出库'}）" for row in shipped[:10]
        )
        suffix = "等" if len(shipped_machines) > 10 else ""
        blockers.append(
            f"存在已出库/已发货机台：{detail}{suffix}，不能直接取消，{SHIPPED_BLOCKER_HINT}"
        )

    if any(int(item.get("factory_pending") or 0) for item in items):
        blockers.append("订单有新备注待工厂复审（factory_pending=1），复审通过后才可以取消")

    if status in TERMINAL_STATUSES:
        blockers.append("订单已完成，不能取消")
    elif status == CANCELLED_STATUS:
        warnings.append("订单已取消，无需重复操作")
    elif status == "pending":
        blockers.append("订单还在待审核，如需取消请直接驳回订单")
    elif status == "rejected":
        blockers.append("订单已驳回，无需取消")
    elif status not in CANCELLABLE_STATUSES:
        blockers.append(f"当前订单状态「{status or '未知'}」不支持一键取消")

    if status in CANCELLABLE_STATUSES:
        if not contracts:
            warnings.append("订单尚未转合同，取消只作废经销商订单与已配货机台")
        elif not sales_orders:
            warnings.append("未找到关联销售订单，取消将按合同与经销商订单收尾")
        if not machines["total"]:
            warnings.append("当前没有已配货机台，取消不会释放库存")

    return {
        "order_no": order_no,
        "status": status,
        # 已取消订单不需要再执行（幂等提示放在 warnings），但也不需要任何写操作。
        "cancellable": not blockers and status != CANCELLED_STATUS,
        "blockers": blockers,
        "warnings": warnings,
        "contracts": contracts,
        "sales_orders": sales_orders,
        "machines": machines,
        "shipped_machines": shipped_machines,
        "lines": len(items),
    }


def _release_allocated_machines(conn, release_rows: list[dict]) -> tuple[list[str], set[str]]:
    """释放未出库配货机台，返回 (release 流水号列表, 在产流水号集合)。"""
    released_serials = [str(row["serial_no"]) for row in release_rows]
    production_serials = _production_serials(conn, released_serials)
    status_groups: dict[str, list[str]] = {}
    for row in release_rows:
        serial = str(row["serial_no"])
        if serial in production_serials:
            next_status = "待入库"
        elif row.get("location_code"):
            next_status = f"库存中（{row['location_code']}）"
        else:
            next_status = "待入库"
        status_groups.setdefault(next_status, []).append(serial)
    for next_status, serials in status_groups.items():
        conn.execute(
            text(
                """
                UPDATE finished_goods_data
                SET `状态`=:status,
                    `占用订单号`='',
                    `客户`='',
                    `代理商`='',
                    `合同号`='',
                    `更新时间`=CURRENT_TIMESTAMP,
                    `row_version`=COALESCE(`row_version`, 1) + 1
                WHERE `流水号` IN :serials
                  AND TRIM(COALESCE(`状态`, '')) IN ('待发货', '机台')
                """
            ).bindparams(bindparam("serials", expanding=True)),
            {"status": next_status, "serials": serials},
        )
    return sorted(released_serials), production_serials


def _release_units(
    conn,
    released_serials: list[str],
    contracts: list[str],
    sales_orders: list[str],
) -> None:
    """清空 units 上的合同/客户/配货占用；按流水号加按合同/订单兜底各清一次。"""
    set_clause = (
        "contract_no = NULL, customer = NULL, dealer_name = NULL, sales_id = NULL, "
        "due_date = NULL, order_remark = NULL, is_locked = 0, locked_by = NULL, "
        "locked_at = NULL, updated_at = CURRENT_TIMESTAMP"
    )
    if released_serials:
        conn.execute(
            text(
                f"UPDATE units SET {set_clause} "
                "WHERE serial_no IN :serials OR forecast_serial_no IN :serials"
            ).bindparams(bindparam("serials", expanding=True)),
            {"serials": list(released_serials)},
        )
    clauses: list[str] = []
    bindings = []
    params: dict[str, Any] = {}
    if contracts:
        clauses.append("TRIM(COALESCE(contract_no, '')) IN :contracts")
        bindings.append(bindparam("contracts", expanding=True))
        params["contracts"] = list(contracts)
    if sales_orders:
        clauses.append("TRIM(COALESCE(sales_id, '')) IN :sales_orders")
        bindings.append(bindparam("sales_orders", expanding=True))
        params["sales_orders"] = list(sales_orders)
    if clauses:
        conn.execute(
            text(f"UPDATE units SET {set_clause} WHERE {' OR '.join(clauses)}").bindparams(
                *bindings
            ),
            params,
        )


def _cancel_factory_plan(conn, contracts: list[str]) -> None:
    if not contracts:
        return
    conn.execute(
        text(
            "UPDATE factory_plan SET `状态`='已取消', `订单号`=NULL "
            "WHERE TRIM(COALESCE(`合同号`, '')) IN :contracts"
        ).bindparams(bindparam("contracts", expanding=True)),
        {"contracts": list(contracts)},
    )


def _cancel_optional_queues(conn, contracts: list[str], operator: str) -> None:
    """清理历史排产/插单/生产台账；表或列不存在时静默跳过。"""
    if not contracts:
        return

    production_queue_columns = _table_columns(conn, "production_queue")
    if {"contract_no", "status"} <= production_queue_columns:
        conn.execute(
            text(
                "DELETE FROM production_queue "
                "WHERE TRIM(COALESCE(contract_no, '')) IN :contracts AND status='Waiting'"
            ).bindparams(bindparam("contracts", expanding=True)),
            {"contracts": list(contracts)},
        )

    rush_columns = _table_columns(conn, "rush_order_queue")
    if {"contract_no", "status"} <= rush_columns:
        set_parts = ["status='deleted'"]
        params: dict[str, Any] = {"contracts": list(contracts)}
        if "updated_by" in rush_columns:
            set_parts.append("updated_by=:operator")
            params["operator"] = operator
        conn.execute(
            text(
                f"UPDATE rush_order_queue SET {', '.join(set_parts)} "
                "WHERE TRIM(COALESCE(contract_no, '')) IN :contracts AND status='pending'"
            ).bindparams(bindparam("contracts", expanding=True)),
            params,
        )

    ledger_columns = _table_columns(conn, "production_history_ledger")
    if {"contract_no", "status"} <= ledger_columns:
        set_parts = ["status='Cancelled'"]
        if "completed_at" in ledger_columns:
            set_parts.append("completed_at=CURRENT_TIMESTAMP")
        conn.execute(
            text(
                f"UPDATE production_history_ledger SET {', '.join(set_parts)} "
                "WHERE status='In_Production' "
                "AND TRIM(COALESCE(contract_no, '')) IN :contracts"
            ).bindparams(bindparam("contracts", expanding=True)),
            {"contracts": list(contracts)},
        )


def _soft_delete_sales_orders(conn, order_no: str, note: str, sales_orders: list[str]) -> None:
    if not sales_orders:
        return
    delete_reason = f"经销商订单 {order_no} 取消：{note}"
    row_version_sql = ""
    if "row_version" in _table_columns(conn, "sales_orders"):
        row_version_sql = ", row_version=COALESCE(row_version, 1) + 1"
    conn.execute(
        text(
            "UPDATE sales_orders SET status='deleted', delete_reason=:reason"
            + row_version_sql
            + " WHERE TRIM(COALESCE(`订单号`, '')) IN :order_ids"
        ).bindparams(bindparam("order_ids", expanding=True)),
        {"reason": delete_reason, "order_ids": list(sales_orders)},
    )


def _enqueue_cancel_event(conn, order_no: str, contracts: list[str], operator: str, note: str) -> dict:
    """先作废同订单旧 pending 回传，再入队整单取消事件（不带 line_nos）。"""
    supersede = None
    try:
        from crud.cloud_sync_outbox import supersede_pending_order_sync_events

        supersede = supersede_pending_order_sync_events
    except (ImportError, AttributeError):  # 同步层尚未提供该函数时降级为直接入队
        logger.warning("supersede_pending_order_sync_events unavailable; enqueue cancel event directly")
    superseded = 0
    if supersede is not None:
        superseded = int(supersede(conn, order_no, reason=note) or 0)

    payload = {
        "order_no": order_no,
        "contract_no": "、".join(sorted(contracts)),
        "operator": operator,
        "note": note,
    }
    _enqueue_cloud_sync(conn, "dealer_order_cancelled", order_no, payload)
    logger.info(
        "dealer order %s cancelled: cloud event dealer_order_cancelled enqueued (superseded=%s)",
        order_no,
        superseded,
    )
    return {
        "event_type": "dealer_order_cancelled",
        "order_no": order_no,
        "payload": payload,
        "superseded": superseded,
    }


def execute_dealer_order_cancel(conn, order_no: str, operator: str, reason: str = "") -> dict:
    """在调用方事务连接上执行经销商订单取消级联（不开事务、不 commit）。

    幂等：订单已全部 cancelled 时不写库直接返回；无可释放机台时照常收尾订单/合同/
    销售订单并回传云端，只是 released_serials 为空。
    """
    order_no = str(order_no or "").strip()
    if not order_no:
        raise ValueError("经销商订单号不能为空")
    operator = _normalize_operator(operator)
    note = str(reason or "").strip() or "经销商订单取消"

    items = _get_order_lines_for_update(conn, order_no)
    status = str(_aggregate_status(items) or "").strip()
    contracts = _collect_contracts(items)
    sales_orders = _collect_sales_orders(conn, contracts, items)

    if status == CANCELLED_STATUS:
        return {
            "status": CANCELLED_STATUS,
            "released_serials": [],
            "stock": 0,
            "production": 0,
            "contracts": contracts,
            "sales_orders": sales_orders,
            "dealer_lines": 0,
            "cloud_event": None,
            "warnings": ["订单已取消，无需重复取消"],
        }
    if status in TERMINAL_STATUSES:
        raise ValueError("订单已完成，不能取消")
    # 执行时二次校验状态：预览后订单可能被驳回/审批流介入，不能借已建好的实例绕过门禁。
    if status not in CANCELLABLE_STATUSES:
        raise ValueError(f"当前订单状态「{status or '未知'}」不支持取消")
    if any(int(item.get("factory_pending") or 0) for item in items):
        raise ValueError("订单有新备注待工厂复审，复审通过后才可以取消")

    # 先按流水号锁定候选机台，再复核状态：与并发发货/改配串行化，避免把刚发出的
    # 机台退回库存；候选读出后被改配的机台会导致整单取消失败（由调用方决定重试）。
    release_candidates = _query_fg_by_chain(
        conn, contracts, sales_orders, statuses=ALLOCATED_MACHINE_STATUSES
    )
    locked_machines = _lock_machines(
        conn, [row["serial_no"] for row in release_candidates]
    )

    def _still_belongs_to_chain(row: dict) -> bool:
        """锁定后复核占用归属：只认仍挂在本单销售订单或本合同下的机台。

        候选机台是锁定前按「占用订单号 OR 合同号」查出来的；如果这段时间里机台被
        改配给别的订单/合同，状态可能仍是「待发货」，不能再按本单释放。
        """
        occupied = str(row.get("occupied_order_no") or "").strip()
        contract = str(row.get("contract_no") or "").strip()
        if occupied and occupied in sales_orders:
            return True
        return bool(contract) and contract in contracts

    stale_serials = [
        serial
        for serial, row in locked_machines.items()
        if str(row.get("status") or "") not in ALLOCATED_MACHINE_STATUSES
        or not _still_belongs_to_chain(row)
    ]
    if stale_serials:
        raise ValueError(
            f"机台状态已变化，不能取消：{('、'.join(sorted(stale_serials)[:10]))}"
        )
    release_rows = [
        locked_machines[str(row["serial_no"])]
        for row in release_candidates
        if str(row["serial_no"]) in locked_machines
    ]

    shipped = _query_fg_by_chain(conn, contracts, sales_orders, shipped_only=True)
    if shipped:
        detail = "、".join(
            f"{row['serial_no']}（{row.get('status') or '已出库'}）" for row in shipped[:10]
        )
        suffix = "等" if len(shipped) > 10 else ""
        raise ValueError(f"存在已出库/已发货机台：{detail}{suffix}，不能取消，{SHIPPED_BLOCKER_HINT}")

    warnings: list[str] = []
    released_serials, production_serials = _release_allocated_machines(conn, release_rows)
    if released_serials:
        logger.info(
            "dealer order %s released machines: stock=%s production=%s",
            order_no,
            len([serial for serial in released_serials if serial not in production_serials]),
            len([serial for serial in released_serials if serial in production_serials]),
        )
    else:
        warnings.append("没有需要释放的配货机台")

    _release_units(conn, released_serials, contracts, sales_orders)
    _cancel_factory_plan(conn, contracts)
    _cancel_optional_queues(conn, contracts, operator)
    _soft_delete_sales_orders(conn, order_no, note, sales_orders)

    conn.execute(
        text(
            "UPDATE dealer_orders SET status='cancelled', factory_pending=0, allocated_qty=0, "
            "reviewed_at=NOW(), reviewed_by=:operator, review_note=:note "
            "WHERE order_no=:order_no"
        ),
        {"operator": operator, "note": note, "order_no": order_no},
    )

    cloud_event = _enqueue_cancel_event(conn, order_no, contracts, operator, note)

    if not contracts:
        warnings.append("订单尚未转合同，仅取消经销商订单本身")
    if not sales_orders:
        warnings.append("未找到关联销售订单")

    production_count = sum(1 for serial in released_serials if serial in production_serials)
    return {
        "status": CANCELLED_STATUS,
        "released_serials": released_serials,
        "stock": len(released_serials) - production_count,
        "production": production_count,
        "contracts": contracts,
        "sales_orders": sales_orders,
        "dealer_lines": len(items),
        "cloud_event": cloud_event,
        "warnings": warnings,
    }


def _post_cancel_side_effects(order_no: str, operator: str, reason: str) -> None:
    """执行成功后的非关键副作用：失败只记日志，不影响取消结果。"""
    try:
        from crud.cloud_sync_outbox import enqueue_wechat_batch_summary_sync

        enqueue_wechat_batch_summary_sync("dealer_order_cancel")
    except Exception:
        logger.exception(
            "dealer order %s cancelled but wechat batch summary sync enqueue failed", order_no
        )
    try:
        from crud.local_contract_drafts import reject_for_order

        reject_for_order(order_no, operator, reason)
    except Exception:
        logger.exception(
            "dealer order %s cancelled but contract drafts reject failed", order_no
        )


def cancel_dealer_order(
    order_no: str, operator: str, reason: str = "", initiator_role: str = ""
) -> dict:
    """编排层：预检 → 发起取消审批实例 → 已通过则自动执行级联。

    返回 ``{message, status, approval_pending, instance_no, preview, result}``；
    不可取消时抛 ValueError（blockers 合并文案），已取消时直接返回幂等结果。
    """
    order_no = str(order_no or "").strip()
    if not order_no:
        raise ValueError("经销商订单号不能为空")
    operator = _normalize_operator(operator)
    note = str(reason or "").strip()

    preview = preview_dealer_order_cancel(order_no)
    if str(preview.get("status") or "") == CANCELLED_STATUS:
        return {
            "message": "订单已取消，无需重复操作",
            "status": CANCELLED_STATUS,
            "approval_pending": False,
            "instance_no": "",
            "preview": preview,
            "result": None,
        }
    if not preview.get("cancellable"):
        blockers = [str(blocker) for blocker in preview.get("blockers") or [] if str(blocker).strip()]
        raise ValueError("；".join(blockers) or "当前订单不可取消")

    # 懒 import：crud.workflows 的执行器也只在函数内 import 本模块，避免循环导入。
    from crud.workflows import (
        acquire_execution_lease,
        create_reverse_instance,
        dispatch_pending_model_notifications,
        ensure_dealer_order_cancel_model,
    )

    ensure_dealer_order_cancel_model()
    items = [
        {"object_type": "机台", "object_id": serial}
        for serial in (preview.get("machines") or {}).get("serials") or []
        if str(serial).strip()
    ]
    items.append({"object_type": "经销商订单", "object_id": order_no})
    created = create_reverse_instance(
        workflow_key="dealer-order-cancel",
        business_type="经销商订单",
        business_id=order_no,
        operator_id=operator,
        idempotency_key=f"dealer-order-cancel:{order_no}",
        reason=note,
        initiator_role=initiator_role,
        items=items,
    )
    instance = created[0] if isinstance(created, tuple) else created
    instance = dict(instance or {})
    instance_no = str(instance.get("instance_no") or "").strip()
    instance_status = str(instance.get("status") or "").strip()

    result: dict[str, Any] = {
        "message": "",
        "status": instance_status,
        "approval_pending": instance_status in {"待审批", "审批中"},
        "instance_no": instance_no,
        "preview": preview,
        "result": None,
    }
    if instance_status in {"待审批", "审批中"}:
        result["message"] = "取消申请已提交，审批通过后自动执行库存释放"
        return result
    if instance_status != "已通过":
        result["message"] = f"取消申请当前状态：{instance_status}，未自动执行"
        return result

    acquire_execution_lease(instance_no, operator)
    from crud.workflows import execute_dealer_order_cancel as run_dealer_order_cancel

    try:
        execution = run_dealer_order_cancel(instance_no, operator) or {}
    except Exception as exc:
        # 业务级联已随事务回滚；实例不能留在「执行中」等租约过期（对象锁会一直占着），
        # 立即标记执行异常并释放锁，管理员可在审批中心重试/作废，业务可稍后重新发起。
        try:
            from crud.workflows import mark_execution_failure

            mark_execution_failure(instance_no, operator, str(exc))
        except Exception:
            logger.exception(
                "dealer order %s cancel execution failed and failure marking failed", order_no
            )
        raise ValueError(f"取消执行失败：{exc}") from exc
    try:
        dispatch_pending_model_notifications(instance_no)
    except Exception:
        logger.exception(
            "dealer order %s cancel workflow notifications failed", order_no
        )
        result["notification_delivery_pending"] = True

    released = [str(serial) for serial in execution.get("released_serials") or []]
    result["result"] = execution
    result["status"] = CANCELLED_STATUS
    result["approval_pending"] = False
    result["message"] = (
        f"订单取消完成，已释放 {len(released)} 台机台并提交云端回传"
        if released
        else "订单取消完成，未发现需要释放的配货机台"
    )
    _post_cancel_side_effects(order_no, operator, note)
    return result
