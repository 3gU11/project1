"""Idempotent V8 updates for component replacements completed by Caigou."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import text

from crud.repair_identity import compose_material_code
from database import get_engine


class ComponentReplacementConflict(ValueError):
    """The binding changed after Caigou inspected it, or the request was reused."""


def _value(values: dict[str, Any], key: str) -> str:
    return str(values.get(key) or "").strip()


def _canonical_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _version(row: dict[str, Any]) -> str:
    updated_at = row.get("updated_at")
    return f"V8_BINDING:{updated_at.isoformat()}" if updated_at else "V8_BINDING"


def _serial_for_position(position_code: str, identity: str) -> str:
    prefix = f"{position_code}-"
    return identity[len(prefix):] if identity.casefold().startswith(prefix.casefold()) else identity


def _ensure_event_table(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS repair_component_replacement_events (
          id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
          idempotency_key VARCHAR(180) NOT NULL,
          repair_outbound_no VARCHAR(100) NOT NULL,
          operator VARCHAR(100) NOT NULL,
          payload_hash CHAR(64) NOT NULL,
          previous_bindings_json JSON NOT NULL,
          result_json JSON NOT NULL,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE KEY uk_repair_component_replacement_idempotency (idempotency_key),
          KEY idx_repair_component_replacement_outbound (repair_outbound_no)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    columns = connection.execute(text("SHOW COLUMNS FROM repair_component_replacement_events LIKE 'previous_bindings_json'")).all()
    if not columns:
        connection.execute(text("ALTER TABLE repair_component_replacement_events ADD COLUMN previous_bindings_json JSON NULL AFTER payload_hash"))
        connection.execute(text("UPDATE repair_component_replacement_events SET previous_bindings_json = JSON_ARRAY() WHERE previous_bindings_json IS NULL"))
        connection.execute(text("ALTER TABLE repair_component_replacement_events MODIFY COLUMN previous_bindings_json JSON NOT NULL"))


def apply_component_replacements(payload: dict[str, Any]) -> dict[str, Any]:
    """Replace active machine-position bindings without deleting V8 history."""
    idempotency_key = _value(payload, "idempotencyKey")
    outbound_no = _value(payload, "repairOutboundNo")
    operator = _value(payload, "operator") or "caigou-repair"
    replacements = payload.get("replacements")
    if not idempotency_key or not outbound_no or not isinstance(replacements, list) or not replacements:
        raise ValueError("维修替换回写必须提供出库单号、幂等键和替换明细")
    payload_hash = hashlib.sha256(_canonical_payload(payload).encode("utf-8")).hexdigest()

    with get_engine().begin() as connection:
        _ensure_event_table(connection)
        existing = connection.execute(text("""
            SELECT payload_hash, result_json FROM repair_component_replacement_events
            WHERE idempotency_key = :idempotency_key FOR UPDATE
        """), {"idempotency_key": idempotency_key}).mappings().first()
        if existing:
            if existing["payload_hash"] != payload_hash:
                raise ComponentReplacementConflict("维修出库幂等键已用于不同的 V8 替换内容")
            return json.loads(existing["result_json"])

        results: list[dict[str, Any]] = []
        previous_bindings: list[dict[str, Any]] = []
        for index, raw in enumerate(replacements, start=1):
            if not isinstance(raw, dict):
                raise ValueError(f"第 {index} 条替换明细格式无效")
            machine_no = _value(raw, "machineNo")
            position_code = _value(raw, "positionCode")
            old_serial = _serial_for_position(position_code, _value(raw, "oldComponentSerialNo"))
            new_serial = _serial_for_position(position_code, _value(raw, "newComponentSerialNo"))
            if not machine_no or not position_code or not old_serial or not new_serial:
                raise ValueError(f"第 {index} 条替换明细缺少机床、位置、旧件或新件编号")
            if old_serial.casefold() == new_serial.casefold():
                raise ValueError(f"第 {index} 条替换明细的新旧件编号不能相同")
            binding = connection.execute(text("""
                SELECT * FROM machine_component_bindings
                WHERE machine_no = :machine_no AND position_code = :position_code AND active = 1
                FOR UPDATE
            """), {"machine_no": machine_no, "position_code": position_code}).mappings().first()
            if not binding:
                raise ComponentReplacementConflict(f"V8 未找到机床 {machine_no} 的位置 {position_code} 有效绑定")
            binding = dict(binding)
            if old_serial.casefold() != _value(binding, "component_serial_no").casefold():
                raise ComponentReplacementConflict(f"V8 中 {machine_no}/{position_code} 的旧件编号已变化")
            expected_version = _value(raw, "expectedBindingVersion")
            if expected_version and expected_version != _version(binding):
                raise ComponentReplacementConflict(f"V8 中 {machine_no}/{position_code} 的绑定版本已变化")
            new_material_code = compose_material_code(position_code, new_serial)
            new_material_name = _value(raw, "newMaterialName") or _value(binding, "material_name")
            old_snapshot = {
                "bindingId": binding["id"],
                "componentSerialNo": _value(binding, "component_serial_no"),
                "materialCode": _value(binding, "material_code"),
                "source": _value(binding, "source"),
                "sourceVersion": _version(binding),
                "sourceFileId": binding.get("source_file_id"),
                "sourceOcrResultId": binding.get("source_ocr_result_id"),
                "recognizedValue": binding.get("recognized_value"),
                "manualValue": binding.get("manual_value"),
                "confidence": str(binding.get("confidence") or ""),
                "reviewedBy": _value(binding, "reviewed_by"),
                "reviewedAt": binding.get("reviewed_at").isoformat() if binding.get("reviewed_at") else "",
            }
            connection.execute(text("""
                UPDATE machine_component_bindings
                SET component_serial_no = :new_serial,
                    material_code = :new_material_code,
                    material_name = :new_material_name,
                    source = 'CAIGOU_REPAIR',
                    source_file_id = NULL,
                    source_ocr_result_id = NULL,
                    file_name = '',
                    recognized_value = NULL,
                    manual_value = :new_serial,
                    confidence = NULL,
                    check_status = 'REPAIR_REPLACED_PENDING_EVIDENCE',
                    reviewed_by = :operator,
                    reviewed_at = :reviewed_at,
                    bound_at = CURRENT_DATE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :binding_id
            """), {
                "new_serial": new_serial, "new_material_code": new_material_code,
                "new_material_name": new_material_name, "operator": operator,
                "reviewed_at": datetime.now(), "binding_id": binding["id"],
            })
            results.append({
                "machineNo": machine_no, "positionCode": position_code,
                "oldComponentSerialNo": old_serial, "newComponentSerialNo": new_serial,
                "oldMaterialCode": old_snapshot["materialCode"], "newMaterialCode": new_material_code,
                "previousBindingVersion": old_snapshot["sourceVersion"],
                "evidenceStatus": "REPAIR_REPLACED_PENDING_EVIDENCE",
            })
            previous_bindings.append(old_snapshot)
        result = {"status": "synced", "syncReference": f"V8-{outbound_no}", "replacements": results}
        connection.execute(text("""
            INSERT INTO repair_component_replacement_events
              (idempotency_key, repair_outbound_no, operator, payload_hash, previous_bindings_json, result_json)
            VALUES (:idempotency_key, :repair_outbound_no, :operator, :payload_hash, :previous_bindings_json, :result_json)
        """), {
            "idempotency_key": idempotency_key, "repair_outbound_no": outbound_no,
            "operator": operator, "payload_hash": payload_hash,
            "previous_bindings_json": json.dumps(previous_bindings, ensure_ascii=False, default=str),
            "result_json": json.dumps(result, ensure_ascii=False),
        })
        return result
