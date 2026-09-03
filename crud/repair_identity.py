"""Read-only repair identity projection for external internal systems."""

from sqlalchemy import text

from database import get_engine


def to_repair_identity(row: dict) -> dict:
    """Maps an already-reviewed V8 component binding to the Caigou contract."""
    updated_at = row.get("updated_at")
    version = f"V8_BINDING:{updated_at.isoformat()}" if updated_at else "V8_BINDING"
    position_code = str(row.get("position_code") or "").strip()
    component_serial_no = str(row.get("component_serial_no") or "").strip()
    material_code = compose_material_code(position_code, component_serial_no)
    # binding_key names the machine-position relationship. It is reused when a
    # component is replaced, so it must never identify the physical component.
    # V8 data contains repeated OCR suffixes across different component
    # positions. The prefix+suffix code is the collision-safe item identity.
    unique_item_id = material_code
    return {
        "boardNo": component_serial_no,
        "uniqueItemId": unique_item_id,
        "componentSerialNo": component_serial_no,
        "machineNo": row.get("machine_no") or "",
        "positionCode": position_code,
        "serialPrefix": position_code,
        "positionName": row.get("position_name") or "",
        "materialSuffix": component_serial_no,
        "materialCode": material_code,
        "materialName": row.get("material_name") or "",
        "modelName": row.get("model_name") or "",
        "deliveryDate": row.get("delivery_date").isoformat() if row.get("delivery_date") else "",
        "warrantyEnd": "",
        "bindingStatus": "ACTIVE",
        "sourceVersion": version,
    }


def compose_material_code(position_code: str, component_serial_no: str) -> str:
    """Build the full material code from the V8 position prefix and physical serial."""
    prefix = str(position_code or "").strip()
    suffix = str(component_serial_no or "").strip()
    if not prefix or not suffix:
        return ""
    if suffix.casefold().startswith(f"{prefix}-".casefold()):
        return suffix
    return f"{prefix}-{suffix}"


def find_repair_identity(board_no: str) -> dict | None:
    normalized = str(board_no or "").strip()
    if not normalized:
        return None
    statement = text("""
        SELECT binding_key, machine_no, model_name, position_code, position_name,
               material_code, material_name, component_serial_no, delivery_date, updated_at
        FROM machine_component_bindings
        WHERE active = 1
          AND (component_serial_no = :board_no OR binding_key = :board_no)
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
    """)
    with get_engine().connect() as connection:
        row = connection.execute(statement, {"board_no": normalized}).mappings().first()
    return to_repair_identity(dict(row)) if row else None


def find_repair_machine_identity(machine_no: str) -> dict | None:
    normalized = str(machine_no or "").strip()
    if not normalized:
        return None
    statement = text("""
        SELECT machine_no, model_name, customer, agent, delivery_date, updated_at
        FROM machine_component_bindings
        WHERE active = 1 AND machine_no = :machine_no
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
    """)
    with get_engine().connect() as connection:
        row = connection.execute(statement, {"machine_no": normalized}).mappings().first()
    if not row:
        return None
    return {
        "machineNo": row.get("machine_no") or normalized,
        "modelName": row.get("model_name") or "",
        "customerName": row.get("customer") or "",
        "agent": row.get("agent") or "",
        "deliveryDate": row.get("delivery_date").isoformat() if row.get("delivery_date") else "",
        "sourceVersion": f"V8_MACHINE:{row.get('updated_at').isoformat()}" if row.get("updated_at") else "V8_MACHINE",
    }
