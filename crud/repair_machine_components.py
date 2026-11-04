"""Read-only V8 machine component projection for the Repair system.

售后人员在 mobile 端按机型拍照清单逐项拍照/OCR，确认后由 V8 生成
``machine_component_bindings``（机台-位置-零部件编号绑定）。本模块把这些
「拍照任务实际收集到的机台零部件信息」整理成只读投影，供维修系统按机台
流水号查询，不写任何数据。
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text

from database import get_engine
from crud.repair_identity import compose_material_code


def _text(value: Any) -> str:
    return str(value or "").strip()


def _format_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return _text(value)


def _format_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _text(value)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    try:
        return bool(int(value or 0))
    except (TypeError, ValueError):
        return _text(value).lower() in {"1", "true", "yes", "on"}


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_repair_machine_components(
    rows: list[dict[str, Any]], *, include_inactive: bool = False
) -> dict[str, Any] | None:
    """把 ``machine_component_bindings`` 行投影成维修系统只读契约。

    - 机台头信息取第一行（绑定行自带机台字段）；
    - components 默认只返回当前有效（active=1）的零部件，传 include_inactive 时含历史行；
    - materialCode 统一为「位置前缀-零部件编号」，与 /api/v1/repair-identity 口径一致。
    """
    if not rows:
        return None
    current = [dict(row) for row in rows]
    machine = current[0]
    selected = [row for row in current if include_inactive or _as_bool(row.get("active"))]
    updated_times = [
        row.get("updated_at") for row in (selected or current) if isinstance(row.get("updated_at"), datetime)
    ]
    source_version = (
        f"V8_COMPONENTS:{max(updated_times).isoformat()}" if updated_times else "V8_COMPONENTS"
    )
    components = []
    for row in selected:
        position_code = _text(row.get("position_code"))
        component_serial_no = _text(row.get("component_serial_no"))
        components.append(
            {
                "positionCode": position_code,
                "positionName": _text(row.get("position_name")),
                "componentSerialNo": component_serial_no,
                "materialCode": compose_material_code(position_code, component_serial_no),
                "materialName": _text(row.get("material_name")),
                "materialType": _text(row.get("material_type")),
                "materialSpec": _text(row.get("material_spec")),
                "active": _as_bool(row.get("active")),
                "boundAt": _format_date(row.get("bound_at")),
                "deliveryDate": _format_date(row.get("delivery_date")),
                "outboundAt": _format_time(row.get("outbound_at")),
                "source": _text(row.get("source")),
                "photoTaskId": _as_int(row.get("source_task_id")),
                "photoTaskStatus": _text(row.get("photo_task_status")),
                "submitBatch": _text(row.get("photo_submit_batch")),
                "photoFileName": _text(row.get("file_name")),
                "recognizedValue": _text(row.get("recognized_value")),
                "manualValue": _text(row.get("manual_value")),
                "confidence": _as_float(row.get("confidence")),
                "checkStatus": _text(row.get("check_status")),
                "reviewedBy": _text(row.get("reviewed_by")),
                "reviewedAt": _format_time(row.get("reviewed_at")),
                "updatedAt": _format_time(row.get("updated_at")),
            }
        )
    return {
        "machineNo": _text(machine.get("machine_no")),
        "modelName": _text(machine.get("model_name")),
        "machineBatchNo": _text(machine.get("machine_batch_no")),
        "machineStatus": _text(machine.get("machine_status")),
        "customerName": _text(machine.get("customer")),
        "agent": _text(machine.get("agent")),
        "locationCode": _text(machine.get("location_code")),
        "deliveryDate": _format_date(machine.get("delivery_date")),
        "outboundAt": _format_time(machine.get("outbound_at")),
        "componentCount": len(components),
        "components": components,
        "sourceVersion": source_version,
    }


def find_repair_machine_components(
    machine_no: str, *, include_inactive: bool = False
) -> dict[str, Any] | None:
    """按机台流水号读取当前 / 历史零部件绑定；机台无任何绑定时返回 None。"""
    normalized = _text(machine_no)
    if not normalized:
        return None
    statement = text(
        """
        SELECT b.machine_no, b.machine_batch_no, b.model_name, b.customer, b.agent,
               b.machine_status, b.location_code, b.delivery_date, b.outbound_at,
               b.position_code, b.position_name, b.material_code, b.material_name,
               b.material_type, b.material_spec, b.component_serial_no, b.bound_at,
               b.active, b.source, b.source_task_id, b.source_file_id, b.file_name,
               b.recognized_value, b.manual_value, b.confidence, b.check_status,
               b.reviewed_by, b.reviewed_at, b.updated_at,
               t.status AS photo_task_status,
               t.submit_batch AS photo_submit_batch
        FROM machine_component_bindings b
        LEFT JOIN machine_photo_tasks t ON t.id = b.source_task_id
        WHERE b.machine_no = :machine_no
        ORDER BY b.active DESC, b.position_code ASC, b.id ASC
        """
    )
    with get_engine().connect() as connection:
        rows = [dict(row) for row in connection.execute(statement, {"machine_no": normalized}).mappings().all()]
    return to_repair_machine_components(rows, include_inactive=include_inactive)
