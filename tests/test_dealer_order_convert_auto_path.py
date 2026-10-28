"""经销商订单转合同：按批次/来源自动选路 + 库存中合同自动配货。

覆盖两块：
1. 路径分组（纯函数）：库存中/空批次 → 现货组，具体批次 → 批次组，同路径合并。
2. 现货自动配货（SQLite）：自动建销售订单、按机型+加高占用库存机台、缺口回传、失败回滚。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

import crud.dealer_orders as crud_dealer
import crud.spot_allocation as spot
from api.routes import dealer_orders as routes


# ---------------------------------------------------------------------------
# 一、路径分组
# ---------------------------------------------------------------------------


def _contract_item(model: str, qty: int, *, high: bool = False, batch_no: str = "", inventory_type: str = "") -> dict:
    return {
        "model": model,
        "qty": qty,
        "high": high,
        "rowNote": "",
        "batch_no": batch_no,
        "inventory_type": inventory_type,
    }


def test_line_path_uses_batch_and_inventory_type():
    assert routes._line_path("FINISHED-STOCK", "finished") == "spot"
    assert routes._line_path("库存中", "finished") == "spot"
    assert routes._line_path("", "unmarked") == "spot"
    assert routes._line_path("", "finished") == "spot"
    assert routes._line_path("现货", "") == "spot"
    assert routes._line_path("09-10", "wip") == "batch"
    assert routes._line_path("08-04", "heightened") == "batch"


def test_mixed_order_splits_into_spot_and_batch_groups():
    order_items = [
        {"model": "FR-400G", "quantity": 1, "batch_no": "FINISHED-STOCK", "inventory_type": "finished"},
        {"model": "FR-400G", "quantity": 2, "batch_no": "09-10", "inventory_type": "wip"},
        {"model": "FH-300C", "quantity": 1, "batch_no": "", "inventory_type": "unmarked"},
    ]
    contract_items = [
        _contract_item("FR-400G", 1, batch_no="FINISHED-STOCK", inventory_type="finished"),
        _contract_item("FR-400G", 2, batch_no="09-10", inventory_type="wip"),
        _contract_item("FH-300C", 1, batch_no="", inventory_type="unmarked"),
    ]

    groups = routes._build_convert_groups(
        contract_items,
        order_items,
        total_note="",
        delivery_date="2026-11-01",
        customer="客户A",
        agent="代理A",
        is_rush=False,
    )

    assert set(groups) == {"spot", "batch"}
    assert groups["spot"]["first_index"] == 0
    assert groups["batch"]["first_index"] == 1
    assert [row["机型"] for row in groups["spot"]["add_list"]] == ["FR-400G", "FH-300C"]
    assert [row["排产数量"] for row in groups["spot"]["add_list"]] == [1, 1]
    assert groups["spot"]["qty"] == 2
    # 现货行不再携带批次来源，批次行保留指定批次
    assert groups["spot"]["add_list"][0]["指定批次/来源"] == {}
    assert groups["batch"]["add_list"][0]["指定批次/来源"] == {"09-10": 2}
    assert groups["batch"]["add_list"][0]["排产数量"] == 2


def test_same_path_rows_merge_but_heightened_stays_separate():
    contract_items = [
        _contract_item("FR-400G", 1, batch_no="09-10", inventory_type="wip"),
        _contract_item("FR-400G", 2, batch_no="09-10", inventory_type="wip"),
        _contract_item("FR-400G", 1, high=True, batch_no="09-10", inventory_type="wip"),
    ]

    groups = routes._build_convert_groups(
        contract_items,
        [],
        total_note="整单备注",
        delivery_date="2026-11-01",
        customer="客户A",
        agent="代理A",
        is_rush=True,
    )

    assert set(groups) == {"batch"}
    rows = groups["batch"]["add_list"]
    # 同机型同规格合并成一行，加高单独一行
    assert len(rows) == 2
    assert rows[0]["机型"] == "FR-400G"
    assert rows[0]["排产数量"] == 3
    assert rows[1]["排产数量"] == 1
    assert "加高" in rows[1]["备注"]
    assert groups["batch"]["rush_rows"][1]["qty"] == 1


def test_contract_no_bump_only_handles_trailing_sequence():
    assert routes._bump_contract_no("HT202610280001") == "HT202610280002"
    assert routes._bump_contract_no("HT202610289999") == ""
    assert routes._bump_contract_no("2026.7.2合同") == ""


# ---------------------------------------------------------------------------
# 二、现货合同自动配货（SQLite）
# ---------------------------------------------------------------------------


def _make_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE factory_plan ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, `合同号` TEXT, `机型` TEXT, "
                "`排产数量` TEXT, `要求交期` TEXT, `状态` TEXT, `备注` TEXT, `客户名` TEXT, "
                "`代理商` TEXT, `指定批次/来源` TEXT, `订单号` TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE sales_orders ("
                "`订单号` TEXT PRIMARY KEY, `客户名` TEXT, `代理商` TEXT, `需求机型` TEXT, "
                "`需求数量` INTEGER, `下单时间` TEXT, `备注` TEXT, `包装选项` TEXT, "
                "`发货时间` TEXT, `指定批次/来源` TEXT, `status` TEXT, `delete_reason` TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE finished_goods_data ("
                "`流水号` TEXT PRIMARY KEY, `机型` TEXT, `状态` TEXT, `占用订单号` TEXT, "
                "`合同号` TEXT, `合同备注` TEXT, `批次号` TEXT, `客户` TEXT, `代理商` TEXT, "
                "`更新时间` TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE contract_notifications ("
                "contract_id TEXT PRIMARY KEY, created_snapshot TEXT, created_by TEXT, "
                "created_at TEXT, converted_snapshot TEXT, converted_by TEXT, converted_at TEXT, "
                "order_id TEXT, latest_at TEXT, version INTEGER)"
            )
        )
    return engine


@pytest.fixture()
def engine(monkeypatch):
    engine = _make_engine()
    monkeypatch.setattr(spot, "get_engine", lambda: engine)
    return engine


def _insert_contract(conn, contract_id: str, rows: list[tuple[str, int, str]], status: str = "已规划") -> None:
    for model, qty, remark in rows:
        conn.execute(
            text(
                "INSERT INTO factory_plan (`合同号`, `机型`, `排产数量`, `要求交期`, `状态`, `备注`, "
                "`客户名`, `代理商`, `指定批次/来源`, `订单号`) "
                "VALUES (:cid, :model, :qty, '2026-11-01', :status, :remark, '客户A', '代理A', '{}', '')"
            ),
            {"cid": contract_id, "model": model, "qty": str(qty), "status": status, "remark": remark},
        )


def _insert_stock(conn, serial: str, model: str, status: str = "库存中（A02）", remark: str = "") -> None:
    conn.execute(
        text(
            "INSERT INTO finished_goods_data (`流水号`, `机型`, `状态`, `占用订单号`, `合同号`, "
            "`合同备注`, `批次号`, `客户`, `代理商`, `更新时间`) "
            "VALUES (:serial, :model, :status, '', '', :remark, '', '', '', NULL)"
        ),
        {"serial": serial, "model": model, "status": status, "remark": remark},
    )


def _contract_row(engine, contract_id: str) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT `状态`, `订单号` FROM factory_plan WHERE `合同号` = :cid ORDER BY id"),
            {"cid": contract_id},
        ).mappings().first()
    return dict(row)


def test_allocate_spot_contract_moves_stock_to_waiting_shipment(engine):
    with engine.begin() as conn:
        _insert_contract(conn, "HT202610280001", [("FR-400G", 2, "")])
        _insert_stock(conn, "SN-001", "FR-400G")
        _insert_stock(conn, "SN-002", "FR-400G")
        _insert_stock(conn, "SN-003", "FR-500G")

    result = spot.allocate_spot_contract(
        "HT202610280001", customer="客户A", agent="代理A", operator="tester"
    )

    assert result["required_qty"] == 2
    assert result["allocated_qty"] == 2
    assert result["order_status"] == "ready"
    assert result["shortages"] == []
    assert sorted(result["serials"]) == ["SN-001", "SN-002"]

    order_id = result["order_id"]
    with engine.connect() as conn:
        stock = {
            row["流水号"]: dict(row)
            for row in conn.execute(
                text("SELECT `流水号`, `状态`, `占用订单号`, `合同号` FROM finished_goods_data")
            ).mappings()
        }
        assert stock["SN-001"]["状态"] == "待发货"
        assert stock["SN-001"]["占用订单号"] == order_id
        assert stock["SN-001"]["合同号"] == "HT202610280001"
        assert stock["SN-003"]["状态"] == "库存中（A02）"
        assert stock["SN-003"]["占用订单号"] == ""

        order = conn.execute(
            text("SELECT `status`, `需求数量`, `需求机型` FROM sales_orders WHERE `订单号` = :oid"),
            {"oid": order_id},
        ).mappings().one()
        assert order["status"] == "ready"
        assert order["需求数量"] == 2
        assert order["需求机型"] == "FR-400Gx2"

        notification = conn.execute(
            text("SELECT order_id FROM contract_notifications WHERE contract_id = :cid"),
            {"cid": "HT202610280001"},
        ).mappings().first()
        assert notification and notification["order_id"] == order_id

    contract = _contract_row(engine, "HT202610280001")
    assert contract["状态"] == "已转订单"
    assert contract["订单号"] == order_id


def test_allocate_spot_contract_reports_shortage_and_keeps_order_active(engine):
    with engine.begin() as conn:
        _insert_contract(conn, "HT202610280002", [("FR-400G", 2, "")])
        _insert_stock(conn, "SN-010", "FR-400G")

    result = spot.allocate_spot_contract("HT202610280002", customer="客户A", agent="代理A")

    assert result["required_qty"] == 2
    assert result["allocated_qty"] == 1
    assert result["order_status"] == "active"
    assert result["shortages"] == [
        {"model": "FR-400G", "high": False, "need": 2, "allocated": 1, "shortage": 1}
    ]
    with engine.connect() as conn:
        status = conn.execute(
            text("SELECT `status` FROM sales_orders WHERE `订单号` = :oid"),
            {"oid": result["order_id"]},
        ).scalar()
    assert status == "active"


def test_heightened_demand_does_not_consume_normal_stock(engine):
    with engine.begin() as conn:
        _insert_contract(conn, "HT202610280003", [("FR-400G", 1, "加高")])
        _insert_stock(conn, "SN-020", "FR-400G")

    result = spot.allocate_spot_contract("HT202610280003")

    assert result["allocated_qty"] == 0
    assert result["shortages"][0]["high"] is True
    with engine.connect() as conn:
        stock = conn.execute(
            text("SELECT `状态`, `占用订单号` FROM finished_goods_data WHERE `流水号` = 'SN-020'")
        ).mappings().one()
    assert stock["状态"] == "库存中（A02）"
    assert stock["占用订单号"] == ""


def test_rollback_restores_stock_and_contract(engine):
    with engine.begin() as conn:
        _insert_contract(conn, "HT202610280004", [("FR-400G", 1, "")])
        _insert_stock(conn, "SN-030", "FR-400G", status="库存中（B01）", remark="展厅样机")

    result = spot.allocate_spot_contract("HT202610280004", customer="客户A", agent="代理A")
    assert result["allocated_qty"] == 1

    spot.rollback_spot_allocation(result)

    with engine.connect() as conn:
        stock = conn.execute(
            text(
                "SELECT `状态`, `占用订单号`, `合同号`, `合同备注` FROM finished_goods_data "
                "WHERE `流水号` = 'SN-030'"
            )
        ).mappings().one()
        assert stock["状态"] == "库存中（B01）"
        assert stock["占用订单号"] is None
        assert stock["合同号"] == ""
        assert stock["合同备注"] == "展厅样机"
        assert conn.execute(text("SELECT COUNT(*) FROM sales_orders")).scalar() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM contract_notifications")).scalar() == 0

    contract = _contract_row(engine, "HT202610280004")
    assert contract["状态"] == "已规划"
    assert contract["订单号"] is None


def test_allocate_rejects_contract_not_planned(engine):
    with engine.begin() as conn:
        _insert_contract(conn, "HT202610280005", [("FR-400G", 1, "")], status="待规划")

    with pytest.raises(spot.SpotAllocationError):
        spot.allocate_spot_contract("HT202610280005")


def test_allocate_rejects_contract_already_converted(engine):
    with engine.begin() as conn:
        _insert_contract(conn, "HT202610280006", [("FR-400G", 1, "")])
        conn.execute(
            text("UPDATE factory_plan SET `订单号` = 'SO-EXIST' WHERE `合同号` = 'HT202610280006'")
        )

    with pytest.raises(spot.SpotAllocationError):
        spot.allocate_spot_contract("HT202610280006")

# ---------------------------------------------------------------------------
# 三、转合同端点编排（mock 掉合同落库与配货写库，只验证分组/编号/调用顺序/响应）
# ---------------------------------------------------------------------------


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeEngine:
    def connect(self):
        return _FakeConn()


class _FakeBackgroundTasks:
    def add_task(self, *args, **kwargs):
        return None


def _mixed_order_items() -> list[dict]:
    return [
        {"model": "FR-400G", "quantity": 1, "batch_no": "FINISHED-STOCK", "inventory_type": "finished"},
        {"model": "FH-300C", "quantity": 2, "batch_no": "10-02", "inventory_type": "wip"},
    ]


def _patch_convert_endpoint(monkeypatch, *, calls: dict):
    import api.routes.planning as planning

    monkeypatch.setattr(routes, "get_engine", lambda: _FakeEngine())
    monkeypatch.setattr(routes, "contract_no_exists", lambda conn, cid: False)
    contract_numbers = iter(["HT202610280001", "HT202610280002", "HT202610280003"])
    monkeypatch.setattr(routes, "next_contract_no", lambda conn: next(contract_numbers))
    monkeypatch.setattr(planning, "_assert_models_in_dictionary", lambda names: None)
    monkeypatch.setattr(routes, "append_audit_log", lambda **kwargs: calls["audit"].append(kwargs))
    monkeypatch.setattr(routes, "_attach_order_form_to_contracts", lambda *a, **k: [])
    monkeypatch.setattr(routes, "_sync_cloud_attachments_for_order", lambda *a, **k: {})
    monkeypatch.setattr(routes, "mark_dealer_order_contracted", lambda *a, **k: calls["marked"].append((a, k)))
    calls.setdefault("assigned", [])
    monkeypatch.setattr(
        routes,
        "assign_dealer_order_line_contracts",
        lambda order_no, mapping: calls["assigned"].append((order_no, dict(mapping))),
    )
    monkeypatch.setattr(
        routes,
        "sync_dealer_order_statuses_by_sales_orders",
        lambda order_ids: calls["synced"].append(list(order_ids)),
    )

    def fake_process_contracts_batch(**kwargs):
        calls["contracts"].append(kwargs)
        save_mode = kwargs["save_mode"]
        add_list = kwargs["add_list"]
        return {
            "contract_ids": [add_list[0]["合同号"]],
            "rush_created": 0,
            "rush_auto_inserted": 0,
            "save_mode": save_mode,
        }

    monkeypatch.setattr(planning, "_process_contracts_batch", fake_process_contracts_batch)

    def fake_allocate(contract_id, **kwargs):
        calls["allocated"].append((contract_id, kwargs))
        return {
            "contract_no": contract_id,
            "order_id": "SO-20261028-ABCD",
            "order_status": "active",
            "required_qty": 1,
            "allocated_qty": 0,
            "shortages": [{"model": "FR-400G", "high": False, "need": 1, "allocated": 0, "shortage": 1}],
            "serials": [],
            "restore": [],
            "message": "已自动配货 0/1 台",
        }

    monkeypatch.setattr(routes, "allocate_spot_contract", fake_allocate)
    monkeypatch.setattr(routes, "rollback_spot_allocation", lambda result: calls["rollback_alloc"].append(result))
    monkeypatch.setattr(
        routes, "_rollback_created_contracts", lambda ids: calls["rollback_contracts"].append(list(ids))
    )
    return planning


def test_convert_endpoint_splits_mixed_order_and_auto_allocates(monkeypatch):
    calls = {"contracts": [], "allocated": [], "marked": [], "synced": [], "audit": [], "rollback_alloc": [], "rollback_contracts": []}
    _patch_convert_endpoint(monkeypatch, calls=calls)
    monkeypatch.setattr(routes, "validate_dealer_order_convertible", lambda order_no: _mixed_order_items())

    payload = routes.ConvertToContractPayload(
        contract_no="HT202610280001",
        customer_name="客户A",
        agent_name="代理A",
        delivery_date="2026-11-01",
        items=[
            {"model": "FR-400G", "qty": 1, "high": False, "batch_no": "FINISHED-STOCK", "inventory_type": "finished"},
            {"model": "FH-300C", "qty": 2, "high": False, "batch_no": "10-02", "inventory_type": "wip"},
        ],
    )

    result = routes.convert_to_contract(
        "DO-TEST-1",
        payload,
        request=None,
        background_tasks=_FakeBackgroundTasks(),
        ctx={"name": "tester", "username": "tester"},
    )

    # 同路径合并：现货一张、批次一张，主号给首行所在的现货组
    assert [call["save_mode"] for call in calls["contracts"]] == ["spot", "sandbox"]
    spot_rows = calls["contracts"][0]["add_list"]
    batch_rows = calls["contracts"][1]["add_list"]
    assert [row["机型"] for row in spot_rows] == ["FR-400G"]
    assert [row["机型"] for row in batch_rows] == ["FH-300C"]
    assert spot_rows[0]["合同号"] == "HT202610280001"
    assert batch_rows[0]["合同号"] == "HT202610280002"
    assert batch_rows[0]["指定批次/来源"] == {"10-02": 2}
    assert calls["contracts"][1]["rush_source_rows"][0]["source_alloc"] == {"10-02": 2}

    # 现货组建完立即自动配货，再回写经销商订单并同步配货状态
    assert calls["allocated"][0][0] == "HT202610280001"
    assert calls["marked"][0][0] == ("DO-TEST-1",)
    assert calls["marked"][0][1]["contract_no"] == "HT202610280001、HT202610280002"
    assert calls["assigned"] == [
        ("DO-TEST-1", {"spot": "HT202610280001", "batch": "HT202610280002"})
    ]
    assert calls["synced"] == [["SO-20261028-ABCD"]]

    assert result["contract_no"] == "HT202610280001、HT202610280002"
    assert [item["path"] for item in result["contracts"]] == ["spot", "batch"]
    assert result["auto_allocation"]["order_id"] == "SO-20261028-ABCD"
    assert result["auto_shortage_qty"] == 1
    assert "自动配货" in result["message"]
    assert calls["rollback_contracts"] == []
    assert calls["rollback_alloc"] == []


def test_convert_endpoint_batch_only_keeps_sandbox_path(monkeypatch):
    calls = {"contracts": [], "allocated": [], "marked": [], "synced": [], "audit": [], "rollback_alloc": [], "rollback_contracts": []}
    _patch_convert_endpoint(monkeypatch, calls=calls)
    monkeypatch.setattr(
        routes,
        "validate_dealer_order_convertible",
        lambda order_no: [{"model": "FH-300C", "quantity": 2, "batch_no": "10-02", "inventory_type": "wip"}],
    )

    payload = routes.ConvertToContractPayload(
        contract_no="HT202610280001",
        customer_name="客户A",
        agent_name="代理A",
        delivery_date="2026-11-01",
        is_rush=True,
        items=[{"model": "FH-300C", "qty": 2, "high": False, "batch_no": "10-02", "inventory_type": "wip"}],
    )

    result = routes.convert_to_contract(
        "DO-TEST-2",
        payload,
        request=None,
        background_tasks=_FakeBackgroundTasks(),
        ctx={"name": "tester", "username": "tester"},
    )

    assert [call["save_mode"] for call in calls["contracts"]] == ["sandbox"]
    assert calls["contracts"][0]["is_rush"] is True
    assert calls["allocated"] == []
    assert result["contracts"] == [
        {
            "contract_no": "HT202610280001",
            "path": "batch",
            "path_label": "批次 → 沙盘待规划",
            "row_count": 1,
            "qty": 2,
            "models": ["FH-300C"],
        }
    ]
    assert result["auto_allocation"] is None
    assert result["auto_allocated_qty"] == 0


def test_convert_endpoint_rolls_back_when_batch_contract_fails(monkeypatch):
    calls = {"contracts": [], "allocated": [], "marked": [], "synced": [], "audit": [], "rollback_alloc": [], "rollback_contracts": []}
    planning = _patch_convert_endpoint(monkeypatch, calls=calls)
    monkeypatch.setattr(routes, "validate_dealer_order_convertible", lambda order_no: _mixed_order_items())

    def failing_process(**kwargs):
        calls["contracts"].append(kwargs)
        if kwargs["save_mode"] == "sandbox":
            raise RuntimeError("合同落库失败")
        return {"contract_ids": [kwargs["add_list"][0]["合同号"]], "rush_created": 0, "rush_auto_inserted": 0}

    monkeypatch.setattr(planning, "_process_contracts_batch", failing_process)

    payload = routes.ConvertToContractPayload(
        contract_no="HT202610280001",
        customer_name="客户A",
        agent_name="代理A",
        delivery_date="2026-11-01",
        items=[
            {"model": "FR-400G", "qty": 1, "high": False, "batch_no": "FINISHED-STOCK", "inventory_type": "finished"},
            {"model": "FH-300C", "qty": 2, "high": False, "batch_no": "10-02", "inventory_type": "wip"},
        ],
    )

    with pytest.raises(routes.HTTPException) as exc_info:
        routes.convert_to_contract(
            "DO-TEST-3",
            payload,
            request=None,
            background_tasks=_FakeBackgroundTasks(),
            ctx={"name": "tester", "username": "tester"},
        )

    assert exc_info.value.status_code == 500
    # 报价组已建且已配货，必须回滚配货 + 已建合同，且不能回写经销商订单
    assert calls["allocated"][0][0] == "HT202610280001"
    assert len(calls["rollback_alloc"]) == 1
    assert calls["rollback_contracts"] == [["HT202610280001"]]
    assert calls["marked"] == []

# ---------------------------------------------------------------------------
# 四、混合订单的合同号回写
# ---------------------------------------------------------------------------


def test_group_orders_keeps_all_split_contract_numbers():
    rows = [
        {
            "order_no": "DO-1",
            "line_no": 1,
            "contract_no": "HT-A",
            "status": "contracted",
            "quantity": 1,
            "allocated_qty": 0,
        },
        {
            "order_no": "DO-1",
            "line_no": 2,
            "contract_no": "HT-B",
            "status": "contracted",
            "quantity": 2,
            "allocated_qty": 0,
        },
    ]

    order = crud_dealer._group_orders(rows)[0]

    assert order["contract_no"] == "HT-A、HT-B"
    assert order["quantity"] == 3


def test_assign_line_contracts_follows_batch_source(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE dealer_orders ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT, line_no INTEGER, "
                "batch_no TEXT, inventory_type TEXT, contract_no TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO dealer_orders (order_no, line_no, batch_no, inventory_type, contract_no) VALUES "
                "('DO-2', 1, 'FINISHED-STOCK', 'finished', 'HT-A、HT-B'),"
                "('DO-2', 2, '09-10', 'wip', 'HT-A、HT-B')"
            )
        )

    monkeypatch.setattr(crud_dealer, "get_engine", lambda: engine)
    monkeypatch.setattr(crud_dealer, "ensure_dealer_order_tables", lambda: None)

    updated = crud_dealer.assign_dealer_order_line_contracts(
        "DO-2", {"spot": "HT-A", "batch": "HT-B"}
    )

    assert updated == 2
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT line_no, contract_no FROM dealer_orders ORDER BY line_no")
        ).fetchall()
    assert [tuple(row) for row in rows] == [(1, "HT-A"), (2, "HT-B")]


def test_assign_line_contracts_skips_single_contract_order(monkeypatch):
    monkeypatch.setattr(crud_dealer, "ensure_dealer_order_tables", lambda: None)

    assert crud_dealer.assign_dealer_order_line_contracts("DO-3", {"spot": "HT-A"}) == 0
    assert crud_dealer.assign_dealer_order_line_contracts("DO-3", {}) == 0
