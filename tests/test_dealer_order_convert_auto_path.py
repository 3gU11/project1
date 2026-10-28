"""经销商订单转合同：按批次/来源自动选路 + 机台单行备注。

覆盖：
1. 路径分组（纯函数）：库存中合并一张，每个具体批次号各一张合同，同批次合并。
2. 单行备注：原备注 → 附加备注 → 加高/改数，机台只落一行。
3. 转合同端点编排：合同一律置「已规划」、多批次拆合同、逐行回写合同号、失败回滚。
4. 订单级合同号与逐行合同号回写。
"""

from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

import crud.dealer_orders as crud_dealer
import crud.orders as crud_orders
import crud.planning as crud_planning
import api.routes.planning as planning
from api.routes import dealer_orders as routes
from utils.order_notes import machine_remark_text, single_line_order_remark


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


def _build_groups(contract_items: list[dict], order_items: list[dict] | None = None) -> list[dict]:
    return routes._build_convert_groups(
        contract_items,
        order_items or [],
        total_note="",
        delivery_date="2026-11-01",
        customer="客户A",
        agent="代理A",
    )


def test_line_path_uses_batch_and_inventory_type():
    assert routes._line_path("FINISHED-STOCK", "finished") == "spot"
    assert routes._line_path("库存中", "finished") == "spot"
    assert routes._line_path("", "unmarked") == "spot"
    assert routes._line_path("", "finished") == "spot"
    assert routes._line_path("现货", "") == "spot"
    assert routes._line_path("09-10", "wip") == "batch"
    assert routes._line_path("08-04", "heightened") == "batch"


def test_mixed_order_splits_spot_and_batch_contracts():
    contract_items = [
        _contract_item("FR-400G", 1, batch_no="FINISHED-STOCK", inventory_type="finished"),
        _contract_item("FR-400G", 2, batch_no="09-10", inventory_type="wip"),
        _contract_item("FH-300C", 1, batch_no="", inventory_type="unmarked"),
    ]

    groups = _build_groups(contract_items)

    assert [group["path"] for group in groups] == ["spot", "batch"]
    assert [group["batch_no"] for group in groups] == ["", "09-10"]
    assert [group["first_index"] for group in groups] == [0, 1]
    assert [row["机型"] for row in groups[0]["add_list"]] == ["FR-400G", "FH-300C"]
    assert [row["排产数量"] for row in groups[0]["add_list"]] == [1, 1]
    assert groups[0]["qty"] == 2
    # 现货行不携带批次来源，批次行保留指定批次
    assert groups[0]["add_list"][0]["指定批次/来源"] == {}
    assert groups[1]["add_list"][0]["指定批次/来源"] == {"09-10": 2}
    assert groups[1]["add_list"][0]["排产数量"] == 2


def test_each_batch_no_gets_its_own_contract():
    contract_items = [
        _contract_item("FR-400G", 1, batch_no="09-10", inventory_type="wip"),
        _contract_item("FH-300C", 2, batch_no="10-02", inventory_type="wip"),
        _contract_item("FR-400G", 1, batch_no="09-10", inventory_type="wip"),
    ]

    groups = _build_groups(contract_items)

    assert [group["batch_no"] for group in groups] == ["09-10", "10-02"]
    assert [group["qty"] for group in groups] == [2, 2]
    # 同一批次的同机型同规格合并
    assert len(groups[0]["add_list"]) == 1
    assert groups[0]["add_list"][0]["排产数量"] == 2
    assert groups[0]["add_list"][0]["指定批次/来源"] == {"09-10": 2}
    assert groups[1]["add_list"][0]["指定批次/来源"] == {"10-02": 2}


def test_same_batch_rows_merge_but_heightened_stays_separate():
    contract_items = [
        _contract_item("FR-400G", 1, batch_no="09-16", inventory_type="wip"),
        _contract_item("FR-400G", 2, batch_no="09-16", inventory_type="wip"),
        _contract_item("FR-400G", 1, high=True, batch_no="09-16", inventory_type="heightened"),
    ]

    groups = _build_groups(contract_items)

    assert len(groups) == 1
    rows = groups[0]["add_list"]
    assert len(rows) == 2
    assert rows[0]["机型"] == "FR-400G"
    assert rows[0]["排产数量"] == 3
    assert rows[1]["排产数量"] == 1
    assert "加高" in rows[1]["备注"]


def test_contract_no_bump_only_handles_trailing_sequence():
    assert routes._bump_contract_no("HT202610280001") == "HT202610280002"
    assert routes._bump_contract_no("HT202610289999") == ""
    assert routes._bump_contract_no("2026.7.2合同") == ""


# ---------------------------------------------------------------------------
# 二、机台单行备注
# ---------------------------------------------------------------------------


def test_single_line_remark_priority():
    assert (
        single_line_order_remark("[总]整单备注 加高 [备注]配单滤水箱 [附加]急件 [改数]2")
        == "配单滤水箱"
    )
    assert single_line_order_remark("[总]整单备注 [附加]急件") == "急件"
    assert single_line_order_remark("[总]整单备注 加高") == "加高"
    assert single_line_order_remark("[总]整单备注 [改数]2") == "改数2"
    assert single_line_order_remark("[总]整单备注 加高 [改数]2") == "加高 改数2"
    # 整单备注不属于单行备注
    assert single_line_order_remark("[总]整单备注") == ""
    # 换行/连续空白压成一行
    assert single_line_order_remark("[备注]第一行\n第二行") == "第一行 第二行"
    # 无分段的历史/外部备注原样保留（仍压成一行）
    assert single_line_order_remark("400G加高100mm 配单滤水箱") == "400G加高100mm 配单滤水箱"


def test_machine_remark_keeps_segment_so_high_hint_is_not_misleading():
    # 原备注正文里的「加高」只是说明文字，落机台时必须保留 [备注] 分段，
    # 否则后续 hasHighHint(机型, 合同备注) 会把普通机台误判成加高。
    assert machine_remark_text("[备注]400G加高100mm 配单滤水箱") == "[备注]400G加高100mm 配单滤水箱"
    assert machine_remark_text("[附加]急件") == "[附加]急件"
    assert machine_remark_text("[总]整单备注 加高 [备注]配单滤水箱") == "[备注]配单滤水箱"
    assert machine_remark_text("[总]整单备注 加高") == "加高"
    assert machine_remark_text("[总]整单备注 [改数]2") == "改数2"
    assert machine_remark_text("[备注]第一行\n第二行") == "[备注]第一行 第二行"
    # 展示口径不带分段前缀
    assert single_line_order_remark("[备注]400G加高100mm 配单滤水箱") == "400G加高100mm 配单滤水箱"


def test_split_detail_rows_exposes_single_line_remark():
    linked_rows = [
        {
            "合同号": "HT-1",
            "机型": "FR-400G",
            "排产数量": "1",
            "备注": "[总]整单备注 [备注]配单滤水箱 [附加]急件",
        }
    ]

    details = planning._split_factory_plan_detail_rows(linked_rows, {"需求机型": "FR-400Gx1"})

    assert details[0]["备注"] == "[总]整单备注 [备注]配单滤水箱 [附加]急件"
    assert details[0]["单行备注"] == "配单滤水箱"


def test_build_model_note_map_writes_single_line_remark(monkeypatch):
    plan_df = pd.DataFrame(
        [
            {
                "订单号": "SO-1",
                "合同号": "HT-1",
                "机型": "FR-400G",
                "排产数量": "1",
                "备注": "[总]整单备注 加高 [备注]配单滤水箱 [附加]急件",
            }
        ]
    )
    monkeypatch.setattr(crud_planning, "get_factory_plan_v2", lambda: plan_df)
    monkeypatch.setattr(crud_orders, "get_orders", lambda: pd.DataFrame([{"订单号": "SO-1"}]))

    notes = crud_orders._build_model_note_map("SO-1")

    assert len(notes) == 1
    assert notes[0]["note"] == "[备注]配单滤水箱"
    # 加高按原始分段备注判断，不能因为单行备注里出现「加高」正文而误判
    assert notes[0]["high"] is True


# ---------------------------------------------------------------------------
# 三、转合同端点编排（mock 合同落库，验证分组/编号/回写/回滚）
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


def _patch_convert_endpoint(monkeypatch, *, calls: dict):
    monkeypatch.setattr(routes, "get_engine", lambda: _FakeEngine())
    monkeypatch.setattr(routes, "contract_no_exists", lambda conn, cid: False)
    contract_numbers = iter(
        ["HT202610280001", "HT202610280002", "HT202610280003", "HT202610280004"]
    )
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
        routes, "_rollback_created_contracts", lambda ids: calls["rollback_contracts"].append(list(ids))
    )

    def fake_process_contracts_batch(**kwargs):
        calls["contracts"].append(kwargs)
        add_list = kwargs["add_list"]
        return {
            "contract_ids": [add_list[0]["合同号"]],
            "rush_created": 0,
            "rush_auto_inserted": 0,
            "save_mode": kwargs["save_mode"],
        }

    monkeypatch.setattr(planning, "_process_contracts_batch", fake_process_contracts_batch)


def _payload(items: list[dict]) -> routes.ConvertToContractPayload:
    return routes.ConvertToContractPayload(
        contract_no="HT202610280001",
        customer_name="客户A",
        agent_name="代理A",
        delivery_date="2026-11-01",
        items=items,
    )


def _mixed_order_items() -> list[dict]:
    return [
        {"model": "FR-400G", "quantity": 1, "batch_no": "FINISHED-STOCK", "inventory_type": "finished"},
        {"model": "FH-300C", "quantity": 2, "batch_no": "10-02", "inventory_type": "wip"},
    ]


def _mixed_payload_items() -> list[dict]:
    return [
        {"model": "FR-400G", "qty": 1, "high": False, "batch_no": "FINISHED-STOCK", "inventory_type": "finished"},
        {"model": "FH-300C", "qty": 2, "high": False, "batch_no": "10-02", "inventory_type": "wip"},
    ]


def test_convert_endpoint_creates_planned_contracts_per_group(monkeypatch):
    calls = {"contracts": [], "marked": [], "audit": [], "assigned": [], "rollback_contracts": []}
    _patch_convert_endpoint(monkeypatch, calls=calls)
    monkeypatch.setattr(routes, "validate_dealer_order_convertible", lambda order_no: _mixed_order_items())

    result = routes.convert_to_contract(
        "DO-TEST-1",
        _payload(_mixed_payload_items()),
        request=None,
        background_tasks=_FakeBackgroundTasks(),
        ctx={"name": "tester", "username": "tester"},
    )

    # 库存中一张 + 每个批次号一张，全部按「已规划」创建（save_mode=spot）
    assert [call["save_mode"] for call in calls["contracts"]] == ["spot", "spot"]
    assert [call["is_rush"] for call in calls["contracts"]] == [False, False]
    groups = [group["add_list"] for group in calls["contracts"]]
    assert groups[0][0]["合同号"] == "HT202610280001"
    assert groups[1][0]["合同号"] == "HT202610280002"
    assert groups[0][0]["指定批次/来源"] == {}
    assert groups[1][0]["指定批次/来源"] == {"10-02": 2}

    # 回写经销商订单并逐行写各自合同
    assert calls["marked"][0][0] == ("DO-TEST-1",)
    assert calls["marked"][0][1]["contract_no"] == "HT202610280001、HT202610280002"
    assert calls["assigned"] == [
        ("DO-TEST-1", {"spot": "HT202610280001", "batch:10-02": "HT202610280002"})
    ]

    assert result["contract_no"] == "HT202610280001、HT202610280002"
    assert [item["path"] for item in result["contracts"]] == ["spot", "batch"]
    assert [item["batch_no"] for item in result["contracts"]] == ["", "10-02"]
    assert "auto_allocation" not in result
    assert "已规划" in result["message"] and "人工配货" in result["message"]
    assert "指定批次：10-02" in result["message"]
    assert calls["rollback_contracts"] == []


def test_convert_endpoint_splits_contract_per_batch_no(monkeypatch):
    calls = {"contracts": [], "marked": [], "audit": [], "assigned": [], "rollback_contracts": []}
    _patch_convert_endpoint(monkeypatch, calls=calls)
    monkeypatch.setattr(
        routes,
        "validate_dealer_order_convertible",
        lambda order_no: [
            {"model": "FR-400G", "quantity": 1, "batch_no": "09-16", "inventory_type": "heightened"},
            {"model": "FH-300C", "quantity": 1, "batch_no": "10-02", "inventory_type": "wip"},
        ],
    )

    result = routes.convert_to_contract(
        "DO-TEST-2",
        _payload(
            [
                {"model": "FR-400G", "qty": 1, "high": True, "batch_no": "09-16", "inventory_type": "heightened"},
                {"model": "FH-300C", "qty": 1, "high": False, "batch_no": "10-02", "inventory_type": "wip"},
            ]
        ),
        request=None,
        background_tasks=_FakeBackgroundTasks(),
        ctx={"name": "tester", "username": "tester"},
    )

    assert [call["save_mode"] for call in calls["contracts"]] == ["spot", "spot"]
    assert result["contract_no"] == "HT202610280001、HT202610280002"
    assert [item["batch_no"] for item in result["contracts"]] == ["09-16", "10-02"]
    assert calls["assigned"] == [
        (
            "DO-TEST-2",
            {"batch:09-16": "HT202610280001", "batch:10-02": "HT202610280002"},
        )
    ]
    assert calls["rollback_contracts"] == []


def test_convert_endpoint_batch_only_creates_one_planned_contract(monkeypatch):
    calls = {"contracts": [], "marked": [], "audit": [], "assigned": [], "rollback_contracts": []}
    _patch_convert_endpoint(monkeypatch, calls=calls)
    monkeypatch.setattr(
        routes,
        "validate_dealer_order_convertible",
        lambda order_no: [{"model": "FH-300C", "quantity": 2, "batch_no": "10-02", "inventory_type": "wip"}],
    )

    result = routes.convert_to_contract(
        "DO-TEST-3",
        _payload(
            [{"model": "FH-300C", "qty": 2, "high": False, "batch_no": "10-02", "inventory_type": "wip"}]
        ),
        request=None,
        background_tasks=_FakeBackgroundTasks(),
        ctx={"name": "tester", "username": "tester"},
    )

    assert [call["save_mode"] for call in calls["contracts"]] == ["spot"]
    # 只有一张合同时不逐行改合同号
    assert calls["assigned"] == []
    assert result["contracts"] == [
        {
            "contract_no": "HT202610280001",
            "path": "batch",
            "batch_no": "10-02",
            "path_label": "批次 10-02 → 指定批次（合同已规划）",
            "row_count": 1,
            "qty": 2,
            "models": ["FH-300C"],
        }
    ]


def test_convert_endpoint_rolls_back_contracts_when_later_contract_fails(monkeypatch):
    calls = {"contracts": [], "marked": [], "audit": [], "assigned": [], "rollback_contracts": []}
    _patch_convert_endpoint(monkeypatch, calls=calls)
    monkeypatch.setattr(routes, "validate_dealer_order_convertible", lambda order_no: _mixed_order_items())

    def failing_process(**kwargs):
        calls["contracts"].append(kwargs)
        if len(calls["contracts"]) >= 2:
            raise RuntimeError("合同落库失败")
        return {"contract_ids": [kwargs["add_list"][0]["合同号"]], "rush_created": 0, "rush_auto_inserted": 0}

    monkeypatch.setattr(planning, "_process_contracts_batch", failing_process)

    with pytest.raises(routes.HTTPException) as exc_info:
        routes.convert_to_contract(
            "DO-TEST-4",
            _payload(_mixed_payload_items()),
            request=None,
            background_tasks=_FakeBackgroundTasks(),
            ctx={"name": "tester", "username": "tester"},
        )

    assert exc_info.value.status_code == 500
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


def _dealer_engine(*lines: tuple[str, str, str]) -> object:
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE dealer_orders ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT, line_no INTEGER, "
                "batch_no TEXT, inventory_type TEXT, contract_no TEXT)"
            )
        )
        for line_no, (batch_no, inventory_type, contract_no) in enumerate(lines, start=1):
            conn.execute(
                text(
                    "INSERT INTO dealer_orders (order_no, line_no, batch_no, inventory_type, contract_no) "
                    "VALUES (:order_no, :line_no, :batch_no, :inventory_type, :contract_no)"
                ),
                {
                    "order_no": "DO-2",
                    "line_no": line_no,
                    "batch_no": batch_no,
                    "inventory_type": inventory_type,
                    "contract_no": contract_no,
                },
            )
    return engine


def test_assign_line_contracts_follows_batch_source(monkeypatch):
    engine = _dealer_engine(
        ("FINISHED-STOCK", "finished", "HT-A、HT-B"),
        ("09-10", "wip", "HT-A、HT-B"),
    )
    monkeypatch.setattr(crud_dealer, "get_engine", lambda: engine)
    monkeypatch.setattr(crud_dealer, "ensure_dealer_order_tables", lambda: None)

    updated = crud_dealer.assign_dealer_order_line_contracts(
        "DO-2", {"spot": "HT-A", "batch:09-10": "HT-B"}
    )

    assert updated == 2
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT line_no, contract_no FROM dealer_orders ORDER BY line_no")
        ).fetchall()
    assert [tuple(row) for row in rows] == [(1, "HT-A"), (2, "HT-B")]


def test_assign_line_contracts_supports_multiple_batches(monkeypatch):
    engine = _dealer_engine(
        ("09-16", "heightened", "HT-A、HT-B、HT-C"),
        ("10-02", "wip", "HT-A、HT-B、HT-C"),
        ("FINISHED-STOCK", "finished", "HT-A、HT-B、HT-C"),
    )
    monkeypatch.setattr(crud_dealer, "get_engine", lambda: engine)
    monkeypatch.setattr(crud_dealer, "ensure_dealer_order_tables", lambda: None)

    updated = crud_dealer.assign_dealer_order_line_contracts(
        "DO-2",
        {"spot": "HT-A", "batch:09-16": "HT-B", "batch:10-02": "HT-C"},
    )

    assert updated == 3
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT line_no, contract_no FROM dealer_orders ORDER BY line_no")
        ).fetchall()
    assert [tuple(row) for row in rows] == [(1, "HT-B"), (2, "HT-C"), (3, "HT-A")]


def test_assign_line_contracts_skips_single_contract_order(monkeypatch):
    monkeypatch.setattr(crud_dealer, "ensure_dealer_order_tables", lambda: None)

    assert crud_dealer.assign_dealer_order_line_contracts("DO-3", {"spot": "HT-A"}) == 0
    assert crud_dealer.assign_dealer_order_line_contracts("DO-3", {}) == 0
