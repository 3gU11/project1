"""经销商订单转合同：一张合同 + 行级批次来源 + 机台单行备注。

覆盖：
1. 转合同：整单只生成一张已规划合同，行级保留批次/来源，同机型同规格合并。
2. 单行备注：原备注 → 附加备注 → 加高/改数，机台只落一行。
3. 转合同端点编排：单合同、回写经销商订单、失败回滚。
4. 指定批次软约束：候选机台「匹配 / 其他批次」标记。
5. 订单级合同号聚合。
"""

from __future__ import annotations

import pandas as pd
import pytest

import crud.dealer_orders as crud_dealer
import crud.orders as crud_orders
import crud.planning as crud_planning
import api.routes.planning as planning
from api.routes import dealer_orders as routes
from utils.order_notes import machine_remark_text, single_line_order_remark


# ---------------------------------------------------------------------------
# 一、转合同：整单一张合同
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


def _build_contract(contract_items: list[dict]) -> dict:
    return routes._build_convert_contract(
        contract_items,
        [],
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
    assert routes._line_path("08-04", "heightened") == "batch"
    assert routes._line_path("09-16", "wip") == "batch"


def test_mixed_sources_share_one_contract_with_row_level_batches():
    contract = _build_contract(
        [
            _contract_item("FH-300C", 3, batch_no="FINISHED-STOCK", inventory_type="finished"),
            _contract_item("FR-400G", 1, high=True, batch_no="08-04", inventory_type="heightened"),
            _contract_item("FR-400AUTO", 1, batch_no="FINISHED-STOCK", inventory_type="finished"),
        ]
    )

    assert contract["qty"] == 5
    assert contract["models"] == ["FH-300C", "FR-400G", "FR-400AUTO"]
    assert contract["batch_nos"] == ["08-04"]
    rows = contract["add_list"]
    assert [row["机型"] for row in rows] == ["FH-300C", "FR-400G", "FR-400AUTO"]
    # 现货行不写批次；批次行写指定批次
    assert rows[0]["指定批次/来源"] == {}
    assert rows[1]["指定批次/来源"] == {"08-04": 1}
    assert "加高" in rows[1]["备注"]
    assert rows[2]["指定批次/来源"] == {}


def test_same_variant_merges_and_accumulates_batch_sources():
    contract = _build_contract(
        [
            _contract_item("FR-400G", 1, batch_no="09-16", inventory_type="wip"),
            _contract_item("FR-400G", 2, batch_no="09-16", inventory_type="wip"),
            _contract_item("FR-400G", 1, high=True, batch_no="09-16", inventory_type="heightened"),
        ]
    )

    rows = contract["add_list"]
    assert len(rows) == 2
    assert rows[0]["排产数量"] == 3
    assert rows[0]["指定批次/来源"] == {"09-16": 3}
    assert rows[1]["排产数量"] == 1
    assert "加高" in rows[1]["备注"]
    assert contract["batch_nos"] == ["09-16"]


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
    assert single_line_order_remark("[总]整单备注") == ""
    assert single_line_order_remark("[备注]第一行\n第二行") == "第一行 第二行"
    assert single_line_order_remark("400G加高100mm 配单滤水箱") == "400G加高100mm 配单滤水箱"


def test_machine_remark_keeps_segment_so_high_hint_is_not_misleading():
    assert machine_remark_text("[备注]400G加高100mm 配单滤水箱") == "[备注]400G加高100mm 配单滤水箱"
    assert machine_remark_text("[附加]急件") == "[附加]急件"
    assert machine_remark_text("[总]整单备注 加高 [备注]配单滤水箱") == "[备注]配单滤水箱"
    assert machine_remark_text("[总]整单备注 加高") == "加高"
    assert machine_remark_text("[总]整单备注 [改数]2") == "改数2"
    assert machine_remark_text("[备注]第一行\n第二行") == "[备注]第一行 第二行"
    assert single_line_order_remark("[备注]400G加高100mm 配单滤水箱") == "400G加高100mm 配单滤水箱"


def test_split_detail_rows_exposes_single_line_remark_and_batch_source():
    linked_rows = [
        {
            "合同号": "HT-1",
            "机型": "FR-400G",
            "排产数量": "1",
            "备注": "[总]整单备注 [备注]配单滤水箱 [附加]急件",
            "指定批次/来源": '{"08-04": 1}',
        }
    ]

    details = planning._split_factory_plan_detail_rows(linked_rows, {"需求机型": "FR-400Gx1"})

    assert details[0]["备注"] == "[总]整单备注 [备注]配单滤水箱 [附加]急件"
    assert details[0]["单行备注"] == "配单滤水箱"
    assert details[0]["指定批次/来源"] == {"08-04": 1}


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
    assert notes[0]["high"] is True


# ---------------------------------------------------------------------------
# 三、转合同端点编排（mock 合同落库）
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
    monkeypatch.setattr(routes, "next_contract_no", lambda conn: "HT202610280009")
    monkeypatch.setattr(planning, "_assert_models_in_dictionary", lambda names: None)
    monkeypatch.setattr(routes, "append_audit_log", lambda **kwargs: calls["audit"].append(kwargs))
    monkeypatch.setattr(routes, "_attach_order_form_to_contracts", lambda *a, **k: [])
    monkeypatch.setattr(routes, "_sync_cloud_attachments_for_order", lambda *a, **k: {})
    monkeypatch.setattr(routes, "mark_dealer_order_contracted", lambda *a, **k: calls["marked"].append((a, k)))
    monkeypatch.setattr(
        routes, "_rollback_created_contracts", lambda ids: calls["rollback_contracts"].append(list(ids))
    )

    def fake_process_contracts_batch(**kwargs):
        calls["contracts"].append(kwargs)
        return {
            "contract_ids": [kwargs["add_list"][0]["合同号"]],
            "rush_created": 0,
            "rush_auto_inserted": 0,
            "save_mode": kwargs["save_mode"],
        }

    monkeypatch.setattr(planning, "_process_contracts_batch", fake_process_contracts_batch)


def _payload() -> routes.ConvertToContractPayload:
    return routes.ConvertToContractPayload(
        contract_no="HT202610280001",
        customer_name="客户A",
        agent_name="代理A",
        delivery_date="2026-11-01",
        items=[
            {"model": "FH-300C", "qty": 3, "high": False, "batch_no": "FINISHED-STOCK", "inventory_type": "finished"},
            {"model": "FR-400G", "qty": 1, "high": True, "batch_no": "08-04", "inventory_type": "heightened"},
        ],
    )


def _order_items() -> list[dict]:
    return [
        {"model": "FH-300C", "quantity": 3, "batch_no": "FINISHED-STOCK", "inventory_type": "finished"},
        {"model": "FR-400G", "quantity": 1, "batch_no": "08-04", "inventory_type": "heightened"},
    ]


def test_convert_endpoint_creates_one_planned_contract(monkeypatch):
    calls = {"contracts": [], "marked": [], "audit": [], "rollback_contracts": []}
    _patch_convert_endpoint(monkeypatch, calls=calls)
    monkeypatch.setattr(routes, "validate_dealer_order_convertible", lambda order_no: _order_items())

    result = routes.convert_to_contract(
        "DO-TEST-1",
        _payload(),
        request=None,
        background_tasks=_FakeBackgroundTasks(),
        ctx={"name": "tester", "username": "tester"},
    )

    assert len(calls["contracts"]) == 1
    call = calls["contracts"][0]
    assert call["save_mode"] == "spot"
    assert call["is_rush"] is False
    rows = call["add_list"]
    assert len(rows) == 2
    assert rows[0]["合同号"] == "HT202610280001"
    assert rows[1]["指定批次/来源"] == {"08-04": 1}
    assert rows[0]["指定批次/来源"] == {}

    assert calls["marked"][0][0] == ("DO-TEST-1",)
    assert calls["marked"][0][1]["contract_no"] == "HT202610280001"
    assert calls["rollback_contracts"] == []

    assert result["contract_no"] == "HT202610280001"
    assert result["contracts"] == [
        {
            "contract_no": "HT202610280001",
            "path": "auto",
            "status": "已规划",
            "batch_nos": ["08-04"],
            "path_label": "按明细来源自动选路（合同已规划）",
            "row_count": 2,
            "qty": 4,
            "models": ["FH-300C", "FR-400G"],
        }
    ]
    assert "指定批次：08-04" in result["message"]
    assert "已规划" in result["message"]


def test_convert_endpoint_generates_contract_no_when_missing(monkeypatch):
    calls = {"contracts": [], "marked": [], "audit": [], "rollback_contracts": []}
    _patch_convert_endpoint(monkeypatch, calls=calls)
    monkeypatch.setattr(routes, "validate_dealer_order_convertible", lambda order_no: _order_items())
    payload = _payload()
    payload.contract_no = ""

    result = routes.convert_to_contract(
        "DO-TEST-2",
        payload,
        request=None,
        background_tasks=_FakeBackgroundTasks(),
        ctx={"name": "tester", "username": "tester"},
    )

    assert result["contract_no"] == "HT202610280009"
    assert calls["marked"][0][1]["contract_no"] == "HT202610280009"


def test_convert_endpoint_rolls_back_contract_when_create_fails(monkeypatch):
    calls = {"contracts": [], "marked": [], "audit": [], "rollback_contracts": []}
    _patch_convert_endpoint(monkeypatch, calls=calls)
    monkeypatch.setattr(routes, "validate_dealer_order_convertible", lambda order_no: _order_items())

    def failing_process(**kwargs):
        calls["contracts"].append(kwargs)
        raise RuntimeError("合同落库失败")

    monkeypatch.setattr(planning, "_process_contracts_batch", failing_process)

    with pytest.raises(routes.HTTPException) as exc_info:
        routes.convert_to_contract(
            "DO-TEST-3",
            _payload(),
            request=None,
            background_tasks=_FakeBackgroundTasks(),
            ctx={"name": "tester", "username": "tester"},
        )

    assert exc_info.value.status_code == 500
    assert calls["rollback_contracts"] == [["HT202610280001"]]
    assert calls["marked"] == []


# ---------------------------------------------------------------------------
# 四、指定批次软约束
# ---------------------------------------------------------------------------


def test_required_batches_by_variant_ignores_stock_aliases():
    details = [
        {"机型": "FR-400G", "备注": "加高", "指定批次/来源": {"08-04": 1}},
        {"机型": "FH-300C", "备注": "", "指定批次/来源": {"FINISHED-STOCK": 3}},
        {"机型": "FR-400AUTO", "备注": "", "指定批次/来源": {"库存中": 1}},
        {"机型": "FR-500XS(PRO)", "备注": "", "指定批次/来源": {"现货(Spot)": 1}},
    ]

    required = planning._required_batches_by_variant(details)

    assert required == {("FR-400G", True): {"08-04"}}


def test_batch_match_label_marks_matching_and_other_batches():
    required = {("FR-400G", True): {"08-04"}}

    assert planning._batch_match_label(
        {"机型": "FR-400G", "批次号": "08-04", "合同备注": "加高"}, required
    ) == "匹配"
    assert planning._batch_match_label(
        {"机型": "FR-400G", "批次号": "09-08", "合同备注": "加高"}, required
    ) == "其他批次"
    # 未要求批次的变体不标记
    assert planning._batch_match_label(
        {"机型": "FH-300C", "批次号": "08-04", "合同备注": ""}, required
    ) == ""
    assert planning._batch_match_label({"机型": "FR-400G", "批次号": "08-04"}, {}) == ""


# ---------------------------------------------------------------------------
# 五、订单级合同号聚合
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


# ---------------------------------------------------------------------------
# 六、无货预订拆分为待规划合同（进入沙盘）
# ---------------------------------------------------------------------------


def _preorder_payload() -> routes.ConvertToContractPayload:
    return routes.ConvertToContractPayload(
        contract_no="HT202610280001",
        customer_name="客户A",
        agent_name="代理A",
        delivery_date="2026-11-01",
        items=[
            {"model": "FH-300C", "qty": 2, "high": False, "batch_no": "FINISHED-STOCK", "inventory_type": "finished"},
            {"model": "FR-400AUTO", "qty": 1, "high": False, "batch_no": "10-02", "inventory_type": "wip"},
            {"model": "FR-400G", "qty": 3, "high": False, "batch_no": "", "inventory_type": "unmarked"},
        ],
    )


def _preorder_order_items() -> list[dict]:
    return [
        {"model": "FH-300C", "quantity": 2, "batch_no": "FINISHED-STOCK", "inventory_type": "finished"},
        {"model": "FR-400AUTO", "quantity": 1, "batch_no": "10-02", "inventory_type": "wip"},
        {"model": "FR-400G", "quantity": 3, "batch_no": "", "inventory_type": "unmarked"},
    ]


def test_convert_endpoint_splits_preorder_into_pending_contract(monkeypatch):
    calls = {"contracts": [], "marked": [], "audit": [], "rollback_contracts": []}
    _patch_convert_endpoint(monkeypatch, calls=calls)
    monkeypatch.setattr(routes, "validate_dealer_order_convertible", lambda order_no: _preorder_order_items())

    result = routes.convert_to_contract(
        "DO-TEST-4",
        _preorder_payload(),
        request=None,
        background_tasks=_FakeBackgroundTasks(),
        ctx={"name": "tester", "username": "tester"},
    )

    assert len(calls["contracts"]) == 1
    call = calls["contracts"][0]
    assert call["save_mode"] == "spot"
    assert call["is_rush"] is False
    assert call["trigger_sandbox"] is True
    assert call["status_overrides"] == {"HT202610280009": "待规划"}

    rows = call["add_list"]
    assert len(rows) == 3
    assert [row["合同号"] for row in rows] == [
        "HT202610280001",
        "HT202610280001",
        "HT202610280009",
    ]
    # 无货预订行备注带标记，方便沙盘/合同管理识别
    assert "无货预订" in rows[2]["备注"]
    assert rows[0]["指定批次/来源"] == {}
    assert rows[1]["指定批次/来源"] == {"10-02": 1}

    assert len(result["contracts"]) == 2
    assert result["contract_ids"] == ["HT202610280001", "HT202610280009"]
    assert result["contracts"][0]["status"] == "已规划"
    assert result["contracts"][0]["path"] == "auto"
    assert result["contracts"][1]["status"] == "待规划"
    assert result["contracts"][1]["path"] == "preorder"
    assert "沙盘" in result["message"]
    assert "已规划" in result["message"]
    assert calls["marked"][0][1]["contract_no"] == "HT202610280001、HT202610280009"
    assert calls["rollback_contracts"] == []


def test_convert_preorder_only_order_uses_single_pending_contract(monkeypatch):
    calls = {"contracts": [], "marked": [], "audit": [], "rollback_contracts": []}
    _patch_convert_endpoint(monkeypatch, calls=calls)
    order_items = [
        {"model": "FR-400G", "quantity": 2, "batch_no": "", "inventory_type": "unmarked"},
    ]
    monkeypatch.setattr(routes, "validate_dealer_order_convertible", lambda order_no: order_items)
    payload = routes.ConvertToContractPayload(
        contract_no="HT202610280001",
        customer_name="客户A",
        agent_name="代理A",
        delivery_date="2026-11-01",
        items=[{"model": "FR-400G", "qty": 2, "high": False, "batch_no": "", "inventory_type": "unmarked"}],
    )

    result = routes.convert_to_contract(
        "DO-TEST-5",
        payload,
        request=None,
        background_tasks=_FakeBackgroundTasks(),
        ctx={"username": "tester"},
    )

    assert len(calls["contracts"]) == 1
    call = calls["contracts"][0]
    assert call["status_overrides"] == {"HT202610280001": "待规划"}
    assert call["trigger_sandbox"] is True
    assert result["contract_ids"] == ["HT202610280001"]
    assert result["contracts"][0]["status"] == "待规划"
    assert result["contracts"][0]["path"] == "preorder"
    assert "沙盘" in result["message"]
    assert calls["marked"][0][1]["contract_no"] == "HT202610280001"
