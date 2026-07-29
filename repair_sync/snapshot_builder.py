from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from sqlalchemy import text

from config import MYSQL_DB
from database import get_engine

from .config import RepairSyncConfig, get_config

SCHEMA_VERSION = "repair-v8-snapshot-1"
QUERY_VERSION = "repair-base-v1"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SnapshotValidationError(ValueError):
    """Raised when the local data cannot form a complete repair snapshot."""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _optional(value: Any) -> Any:
    if value is None or _clean(value) == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _as_bool(value: Any) -> bool:
    return bool(value) and str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _stable_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _row_value(row: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return default


def _rows(rows: Mapping[str, Iterable[Mapping[str, Any]]] | None, name: str) -> list[Mapping[str, Any]]:
    return [dict(row) for row in (rows or {}).get(name, [])]


def _map_machines(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        machine_no = _clean(_row_value(row, "machine_no", "serial_no", "流水号"))
        if not machine_no:
            continue
        result.append(
            {
                "machine_no": machine_no,
                "model": _clean(_row_value(row, "model", "model_name", "机型")),
                "customer": "",
                "agent": "",
                "factory_date": _optional(_row_value(row, "factory_date")),
                "warranty_start": _optional(_row_value(row, "warranty_start", "delivery_date")),
                "status": _clean(_row_value(row, "status", "machine_status", "状态")),
            }
        )
    return result


def _map_materials(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        code = _clean(_row_value(row, "material_code", "code"))
        if not code:
            continue
        result.append(
            {
                "material_code": code,
                "name": _clean(_row_value(row, "name", "material_name")),
                "type": _clean(_row_value(row, "type", "material_type")),
                "spec": _clean(_row_value(row, "spec", "material_spec")),
                "track_serial": True,
                "default_warranty_months": int(_row_value(row, "default_warranty_months", default=12) or 12),
                "source": "V8_SYNC",
            }
        )
    return result


def _map_instances(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        serial = _clean(_row_value(row, "serial_no", "component_serial_no"))
        if not serial:
            continue
        result.append(
            {
                "serial_no": serial,
                "material_code": _clean(_row_value(row, "material_code")),
                "batch_no": _clean(_row_value(row, "batch_no", "instance_batch_no")),
                "flow_no": _clean(_row_value(row, "flow_no", "instance_flow_no")),
                "produced_at": _optional(_row_value(row, "produced_at", "bound_at")),
                "status": _clean(_row_value(row, "status", default="active")) or "active",
                "source": "V8_SYNC",
            }
        )
    return result


def _map_bindings(rows: Iterable[Mapping[str, Any]], allowed: tuple[str, ...]) -> list[dict[str, Any]]:
    result = []
    invalid: list[str] = []
    for row in rows:
        active = _as_bool(_row_value(row, "active", default=1))
        check_status = _clean(_row_value(row, "check_status", "status"))
        if not active:
            continue
        machine_no = _clean(_row_value(row, "machine_no"))
        serial = _clean(_row_value(row, "component_serial_no", "serial_no"))
        position_code = _clean(_row_value(row, "position_code"))
        if not machine_no or not serial or not position_code:
            invalid.append("missing machine_no/component_serial_no/position_code")
            continue
        if check_status not in allowed:
            invalid.append(f"{machine_no}:{position_code} check_status={check_status or '<empty>'}")
            continue
        binding_key = _clean(_row_value(row, "binding_key", "id")) or f"{machine_no}:{position_code}"
        result.append(
            {
                "id": f"V8-{binding_key}"[:40],
                "machine_no": machine_no,
                "serial_no": serial,
                "material_code": _clean(_row_value(row, "material_code")),
                "position": _clean(_row_value(row, "position_name", "position", "position_code")),
                "position_code": position_code,
                "bound_at": _optional(_row_value(row, "bound_at")),
                "unbound_at": None,
                "active": True,
                "source": "V8_SYNC",
                "work_order_no": "",
            }
        )
    if invalid:
        raise SnapshotValidationError("active binding is not ready: " + ", ".join(invalid[:20]))
    return result


def _map_model_dictionary(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "model_name": _clean(_row_value(row, "model_name", "model")),
            "model_family": _optional(_row_value(row, "model_family")),
            "sort_order": int(_row_value(row, "sort_order", default=0) or 0),
            "enabled": _as_bool(_row_value(row, "enabled", default=1)),
        }
        for row in rows
        if _clean(_row_value(row, "model_name", "model"))
    ]


def _map_photo_items(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "position_code": _clean(_row_value(row, "position_code")),
            "item_name": _clean(_row_value(row, "item_name", "name")),
            "sort_order": int(_row_value(row, "sort_order", default=0) or 0),
            "enabled": _as_bool(_row_value(row, "enabled", default=1)),
        }
        for row in rows
        if _clean(_row_value(row, "position_code"))
    ]


def _map_photo_config(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "model_name": _clean(_row_value(row, "model_name", "model_code", "model")),
            "position_code": _clean(_row_value(row, "position_code")),
            "required": _as_bool(_row_value(row, "required", default=1)),
            "enabled": _as_bool(_row_value(row, "enabled", default=1)),
            "sort_order": int(_row_value(row, "sort_order", default=0) or 0),
        }
        for row in rows
        if _clean(_row_value(row, "model_name", "model_code", "model"))
        and _clean(_row_value(row, "position_code"))
    ]


def _sort_records(records: dict[str, list[dict[str, Any]]]) -> None:
    keys = {
        "machines": ("machine_no",),
        "materials": ("material_code",),
        "materialInstances": ("material_code", "serial_no"),
        "machineMaterialBindings": ("machine_no", "position_code", "material_code", "serial_no"),
        "modelDictionary": ("sort_order", "model_name"),
        "photoItemLibrary": ("sort_order", "position_code"),
        "modelPhotoConfig": ("model_name", "sort_order", "position_code"),
    }
    for name, rows in records.items():
        rows.sort(key=lambda row: tuple(str(row.get(key) or "") for key in keys[name]))


def _dedupe_denormalized_records(records: dict[str, list[dict[str, Any]]]) -> None:
    # machine_component_bindings is intentionally denormalized, so the same
    # machine/material/instance can occur on many binding rows. Identical
    # copies collapse; conflicting copies remain a hard validation error.
    specs = {
        "machines": ("machine_no", "machine"),
        "materials": ("material_code", "material"),
        "materialInstances": ("material_code|serial_no", "material instance"),
    }
    for name, (key, label) in specs.items():
        unique: dict[str, dict[str, Any]] = {}
        for row in records[name]:
            identity = (
                f"{row.get('material_code') or ''}|{row.get('serial_no') or ''}"
                if name == "materialInstances"
                else str(row.get(key) or "")
            )
            previous = unique.get(identity)
            if previous is None:
                unique[identity] = row
            elif previous != row:
                if name == "materialInstances" and previous.get("material_code") == row.get("material_code"):
                    unique[identity] = min((previous, row), key=_stable_json)
                    continue
                raise SnapshotValidationError(f"conflicting {label}: {identity}")
        records[name] = list(unique.values())


def validate_records(records: dict[str, list[dict[str, Any]]]) -> None:
    errors: list[str] = []
    machines = records["machines"]
    materials = records["materials"]
    instances = records["materialInstances"]
    bindings = records["machineMaterialBindings"]
    models = records["modelDictionary"]
    photo_items = records["photoItemLibrary"]
    configs = records["modelPhotoConfig"]

    def duplicates(rows: list[dict[str, Any]], key: Any, label: str) -> None:
        seen: set[Any] = set()
        for row in rows:
            value = key(row)
            if value in seen:
                errors.append(f"duplicate {label}: {value}")
            seen.add(value)

    duplicates(machines, lambda r: r["machine_no"], "machine_no")
    duplicates(materials, lambda r: r["material_code"], "material_code")
    duplicates(instances, lambda r: (r["material_code"], r["serial_no"]), "material_code/serial_no")
    duplicates(bindings, lambda r: (r["machine_no"], r["position_code"]), "machine/position")
    duplicates(bindings, lambda r: r["id"], "binding id")
    duplicates(photo_items, lambda r: r["position_code"], "position_code")

    machine_keys = {row["machine_no"] for row in machines}
    material_keys = {row["material_code"] for row in materials}
    instance_keys: set[tuple[str, str]] = set()
    for row in instances:
        code = row["material_code"]
        if code and material_keys and code not in material_keys:
            errors.append(f"instance references unknown material: {row['serial_no']}")
        instance_keys.add((code, row["serial_no"]))
    for row in bindings:
        if machine_keys and row["machine_no"] not in machine_keys:
            errors.append(f"binding references unknown machine: {row['machine_no']}")
        binding_key = (row.get("material_code", ""), row["serial_no"])
        if binding_key not in instance_keys:
            errors.append(
                "binding references unknown material instance: "
                f"{row.get('material_code', '')}/{row['serial_no']}"
            )
    model_keys = {row["model_name"] for row in models}
    photo_keys = {row["position_code"] for row in photo_items}
    for row in configs:
        if model_keys and row["model_name"] not in model_keys:
            errors.append(f"photo config references unknown model: {row['model_name']}")
        if photo_keys and row["position_code"] not in photo_keys:
            errors.append(f"photo config references unknown position: {row['position_code']}")
    if errors:
        raise SnapshotValidationError("; ".join(errors[:20]))


def build_snapshot_from_rows(
    business_date: date,
    rows: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    snapshot_id: str | None = None,
    generated_at: datetime | None = None,
    source_watermark: Mapping[str, Any] | None = None,
    allowed_check_status: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    binding_rows = _rows(rows, "machineMaterialBindings")
    machine_rows = _rows(rows, "machines") or binding_rows
    material_rows = _rows(rows, "materials") or binding_rows
    instance_rows = _rows(rows, "materialInstances") or binding_rows
    records = {
        "machines": _map_machines(machine_rows),
        "materials": _map_materials(material_rows),
        "materialInstances": _map_instances(instance_rows),
        "machineMaterialBindings": _map_bindings(
            binding_rows,
            allowed_check_status or get_config().allowed_check_status,
        ),
        "modelDictionary": _map_model_dictionary(_rows(rows, "modelDictionary")),
        "photoItemLibrary": _map_photo_items(_rows(rows, "photoItemLibrary")),
        "modelPhotoConfig": _map_photo_config(_rows(rows, "modelPhotoConfig")),
    }
    _dedupe_denormalized_records(records)
    _sort_records(records)
    validate_records(records)
    records_digest = hashlib.sha256(_stable_json(records)).hexdigest()
    generated = generated_at or datetime.now(timezone.utc)
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "snapshotId": snapshot_id or str(uuid.uuid4()),
        "businessDate": business_date.isoformat(),
        "generatedAt": generated.isoformat(),
        "source": {"system": "V8", "database": MYSQL_DB, "queryVersion": QUERY_VERSION},
        "counts": {
            "machines": len(records["machines"]),
            "materials": len(records["materials"]),
            "materialInstances": len(records["materialInstances"]),
            "bindings": len(records["machineMaterialBindings"]),
            "models": len(records["modelDictionary"]),
            "photoItems": len(records["photoItemLibrary"]),
            "modelPhotoConfigs": len(records["modelPhotoConfig"]),
        },
        "recordsSha256": records_digest,
        "tables": records,
    }
    payload["sourceWatermark"] = dict(source_watermark or {})
    return payload


def _safe_table(table_name: str) -> str:
    if not _IDENTIFIER.fullmatch(table_name or ""):
        raise ValueError(f"invalid repair sync source table name: {table_name!r}")
    return table_name


def _table_exists(conn: Any, table_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema=DATABASE() AND table_name=:table_name"
            ),
            {"table_name": table_name},
        ).scalar()
    )


def _fetch_if_exists(conn: Any, table_name: str) -> tuple[list[dict[str, Any]], Any]:
    table_name = _safe_table(table_name)
    if not _table_exists(conn, table_name):
        return [], None
    rows = [dict(row) for row in conn.execute(text(f"SELECT * FROM `{table_name}`")).mappings().all()]
    watermark = conn.execute(
        text(
            f"SELECT MAX(updated_at) FROM `{table_name}` "
            "WHERE 1=1"
        )
    ).scalar() if any("updated_at" in row for row in rows) else None
    return rows, watermark


def read_source_rows(config: RepairSyncConfig | None = None) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    config = config or get_config()
    rows: dict[str, list[dict[str, Any]]] = {}
    watermark: dict[str, Any] = {}
    with get_engine().connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        trans = conn.begin()
        try:
            source_specs = {
                "machineMaterialBindings": config.source_bindings_table,
                "materials": config.source_materials_table,
                "materialInstances": config.source_instances_table,
                "photoItemLibrary": config.source_photo_items_table,
                "modelPhotoConfig": config.source_photo_config_table,
            }
            for output_name, table_name in source_specs.items():
                if output_name == "modelPhotoConfig" and _table_exists(conn, _safe_table(table_name)) and _table_exists(conn, "model_dictionary"):
                    table_rows = [
                        dict(row)
                        for row in conn.execute(
                            text(
                                f"SELECT mpc.*, md.model_name "
                                f"FROM `{_safe_table(table_name)}` mpc "
                                "JOIN model_dictionary md ON md.id=mpc.model_id"
                            )
                        ).mappings().all()
                    ]
                    stamp = conn.execute(
                        text(f"SELECT MAX(updated_at) FROM `{_safe_table(table_name)}`")
                    ).scalar()
                else:
                    table_rows, stamp = _fetch_if_exists(conn, table_name)
                rows[output_name] = table_rows
                if stamp is not None:
                    watermark[table_name] = stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp)
            machine_rows, stamp = _fetch_if_exists(conn, "finished_goods_data")
            binding_rows = rows.get("machineMaterialBindings") or []
            # The Go photo service stores the current machine profile on every
            # binding row. Use it for overlapping machines, while retaining
            # finished-goods machines that have not received a binding yet.
            binding_machine_nos = {
                _clean(row.get("machine_no")) for row in binding_rows if _clean(row.get("machine_no"))
            }
            rows["machines"] = list(binding_rows) + [
                row
                for row in machine_rows
                if _clean(_row_value(row, "machine_no", "serial_no", "流水号")) not in binding_machine_nos
            ]
            if stamp is not None:
                watermark["finished_goods_data"] = stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp)
            if binding_rows:
                if not rows.get("materials"):
                    rows["materials"] = binding_rows
                if not rows.get("materialInstances"):
                    rows["materialInstances"] = binding_rows
            model_rows, stamp = _fetch_if_exists(conn, "model_dictionary")
            rows["modelDictionary"] = model_rows
            if stamp is not None:
                watermark["model_dictionary"] = stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp)
            trans.commit()
        except Exception:
            trans.rollback()
            raise
    return rows, watermark


def build_snapshot(
    business_date: date,
    *,
    snapshot_id: str | None = None,
    config: RepairSyncConfig | None = None,
) -> dict[str, Any]:
    rows, watermark = read_source_rows(config)
    active_config = config or get_config()
    try:
        generated_at = datetime.now(ZoneInfo(active_config.timezone))
    except Exception:
        generated_at = datetime.now(timezone.utc)
    return build_snapshot_from_rows(
        business_date,
        rows,
        snapshot_id=snapshot_id,
        generated_at=generated_at,
        source_watermark=watermark,
        allowed_check_status=active_config.allowed_check_status,
    )
