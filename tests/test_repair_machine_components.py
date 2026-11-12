"""维修系统机台零部件只读投影的单元测试。"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, text

import crud.repair_machine_components as projection


def _row(**overrides):
    row = {
        "machine_no": "96-06-234",
        "machine_batch_no": "06-09",
        "model_name": "FR-400XS(PRO)",
        "customer": "",
        "agent": "",
        "machine_status": "已出库",
        "location_code": "C05",
        "delivery_date": date(2026, 7, 13),
        "outbound_at": datetime(2026, 7, 13, 14, 52, 0),
        "position_code": "SN-CPU",
        "position_name": "CPU板编号",
        "material_code": "V8-SN-CPU",
        "material_name": "CPU板编号",
        "material_type": "编号",
        "material_spec": "SN-CPU",
        "component_serial_no": "JQ242025-834",
        "bound_at": date(2026, 7, 13),
        "active": 1,
        "source": "V8_OCR",
        "source_task_id": 12,
        "source_file_id": 34,
        "file_name": "96-06-234_SN-CPU_1.jpg",
        "recognized_value": "JQ242025-834",
        "manual_value": "",
        "confidence": Decimal("0.95000"),
        "check_status": "manual_passed",
        "reviewed_by": "tester",
        "reviewed_at": datetime(2026, 7, 13, 15, 0, 0),
        "updated_at": datetime(2026, 8, 1, 15, 41, 57),
        "photo_task_status": "completed",
        "photo_submit_batch": "PHOTO-96-06-234-1790000000",
    }
    row.update(overrides)
    return row


def test_active_components_are_projected_with_composed_material_code():
    data = projection.to_repair_machine_components([_row()])

    assert data["machineNo"] == "96-06-234"
    assert data["modelName"] == "FR-400XS(PRO)"
    assert data["machineBatchNo"] == "06-09"
    assert data["deliveryDate"] == "2026-07-13"
    assert data["outboundAt"] == "2026-07-13 14:52:00"
    assert data["sourceVersion"] == "V8_COMPONENTS:2026-08-01T15:41:57"
    assert data["componentCount"] == 1

    component = data["components"][0]
    assert component["positionCode"] == "SN-CPU"
    assert component["componentSerialNo"] == "JQ242025-834"
    assert component["materialCode"] == "SN-CPU-JQ242025-834"
    assert component["materialName"] == "CPU板编号"
    assert component["active"] is True
    assert component["boundAt"] == "2026-07-13"
    assert component["photoTaskId"] == 12
    assert component["photoTaskStatus"] == "completed"
    assert component["submitBatch"] == "PHOTO-96-06-234-1790000000"
    assert component["photoFileName"] == "96-06-234_SN-CPU_1.jpg"
    assert component["confidence"] == 0.95
    assert component["checkStatus"] == "manual_passed"
    assert component["reviewedAt"] == "2026-07-13 15:00:00"


def test_inactive_bindings_are_hidden_unless_requested():
    rows = [
        _row(),
        _row(position_code="SN-MOTOR", component_serial_no="MOTOR-1", active=0, updated_at=datetime(2026, 9, 1, 8, 0, 0)),
    ]

    current = projection.to_repair_machine_components(rows)
    assert current["componentCount"] == 1
    assert [item["positionCode"] for item in current["components"]] == ["SN-CPU"]

    history = projection.to_repair_machine_components(rows, include_inactive=True)
    assert history["componentCount"] == 2
    assert [item["positionCode"] for item in history["components"]] == ["SN-CPU", "SN-MOTOR"]
    assert history["components"][1]["active"] is False


def test_machine_without_bindings_is_not_found():
    assert projection.to_repair_machine_components([]) is None
    assert projection.find_repair_machine_components("") is None


def test_find_repair_machine_components_queries_bindings_and_photo_tasks(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE machine_component_bindings ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, machine_no TEXT, machine_batch_no TEXT, "
                "model_name TEXT, customer TEXT, agent TEXT, machine_status TEXT, location_code TEXT, "
                "delivery_date TEXT, outbound_at TEXT, position_code TEXT, position_name TEXT, "
                "material_code TEXT, material_name TEXT, material_type TEXT, material_spec TEXT, "
                "component_serial_no TEXT, bound_at TEXT, active INTEGER, source TEXT, "
                "source_task_id INTEGER, source_file_id INTEGER, file_name TEXT, "
                "recognized_value TEXT, manual_value TEXT, confidence TEXT, check_status TEXT, "
                "reviewed_by TEXT, reviewed_at TEXT, updated_at TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE machine_photo_tasks ("
                "id INTEGER PRIMARY KEY, status TEXT, submit_batch TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO machine_photo_tasks (id, status, submit_batch) "
                "VALUES (12, 'completed', 'PHOTO-96-06-234-1790000000')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO machine_component_bindings "
                "(machine_no, machine_batch_no, model_name, customer, agent, machine_status, "
                "location_code, delivery_date, outbound_at, position_code, position_name, "
                "material_code, material_name, material_type, material_spec, component_serial_no, "
                "bound_at, active, source, source_task_id, source_file_id, file_name, "
                "recognized_value, manual_value, confidence, check_status, reviewed_by, "
                "reviewed_at, updated_at) VALUES "
                "('96-06-234', '06-09', 'FR-400XS(PRO)', '', '', '已出库', 'C05', "
                "'2026-07-13', '2026-07-13 14:52:00', 'SN-CPU', 'CPU板编号', "
                "'V8-SN-CPU', 'CPU板编号', '编号', 'SN-CPU', 'JQ242025-834', "
                "'2026-07-13', 1, 'V8_OCR', 12, 34, '96-06-234_SN-CPU_1.jpg', "
                "'JQ242025-834', '', '0.95000', 'manual_passed', 'tester', "
                "'2026-07-13 15:00:00', '2026-08-01 15:41:57')"
            )
        )
    monkeypatch.setattr(projection, "get_engine", lambda: engine)

    data = projection.find_repair_machine_components("96-06-234")

    assert data["machineNo"] == "96-06-234"
    assert data["components"][0]["photoTaskStatus"] == "completed"
    assert data["components"][0]["submitBatch"] == "PHOTO-96-06-234-1790000000"
    assert projection.find_repair_machine_components("96-06-999") is None
