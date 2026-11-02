from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi import HTTPException

from api.routes import planning
from crud.orders import allocate_inventory


def test_live_order_reader_bypasses_an_already_populated_worker_cache():
    from crud import orders

    def frame(status):
        return pd.DataFrame([{"订单号": "SO-TEST", "status": status, "指定批次/来源": "{}"}])

    orders.get_orders.cache_clear()
    try:
        with patch.object(orders, "get_engine", return_value=MagicMock()), \
             patch.object(orders.pd, "read_sql", side_effect=[frame("active"), frame("ready")]) as read:
            assert orders.get_orders().iloc[0]["status"] == "active"
            assert orders.get_orders().iloc[0]["status"] == "active"
            assert orders.get_orders_fresh().iloc[0]["status"] == "ready"
            assert read.call_count == 2
    finally:
        orders.get_orders.cache_clear()


def test_quantity_is_rechecked_using_locked_connection_and_current_allocations():
    order = {"订单号": "SO-TEST", "status": "active", "客户名": "test"}
    candidate = {"流水号": "NEW", "机型": "FR-600G", "合同备注": "", "状态": "库存中", "占用订单号": ""}
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = order

    def allocate(*args, validate_selection, **kwargs):
        # Simulate another request having already filled the demand before we got the lock.
        try:
            validate_selection(conn, [{"serial_no": "NEW", "model_type": "FR-600G", "order_remark": ""}])
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        pytest.fail("over-allocation must not reach writes")

    with patch.object(planning, "_guard_pending_batch_review"), \
         patch.object(planning, "get_orders_fresh", return_value=pd.DataFrame([order])), \
         patch.object(planning, "_get_order_contract_machine_rows", return_value=pd.DataFrame([candidate])), \
         patch.object(planning, "_order_required_variant_counts", return_value={("FR-600G", False): 1}) as demand, \
         patch.object(planning, "_get_explicit_order_allocations", return_value=pd.DataFrame([
             {"流水号": "EXISTING", "机型": "FR-600G", "合同备注": ""}
         ])) as current, \
         patch.object(planning, "allocate_inventory", side_effect=allocate):
        with pytest.raises(HTTPException) as error:
            planning.allocate_order_inventory_api(
                "SO-TEST", planning.OrderAllocatePayload(selected_serial_nos=["NEW"]),
                current_operator="test", current_user={})
        assert error.value.status_code == 422
        assert "超配" in error.value.detail
        assert demand.call_args.kwargs["conn"] is conn
        current.assert_called_once_with("SO-TEST", conn=conn)


def test_rejected_validation_rolls_back_before_any_machine_write():
    engine, conn = MagicMock(), MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    conn.execute.return_value.scalars.return_value.all.return_value = []
    conn.execute.return_value.fetchall.return_value = []
    conn.execute.return_value.mappings.return_value.all.side_effect = [[], [{
        "serial_no": "NEW", "model_type": "FR-600G", "order_remark": "", "status": "库存中"
    }]]

    def reject(connection, rows):
        assert connection is conn
        assert rows[0]["serial_no"] == "NEW"
        assert guard.called
        raise ValueError("超配")

    with patch("crud.orders.get_engine", return_value=engine), \
         patch("crud.orders._build_model_note_map", return_value=[]), \
         patch("crud.inventory_guards.require_inventory_order") as guard, \
         patch("crud.batch_planning.pending_review_order", return_value=None):
        with pytest.raises(RuntimeError, match="超配"):
            allocate_inventory("SO-TEST", "test", "", ["NEW"], validate_selection=reject)
    statements = [str(call.args[0]).strip().upper() for call in conn.execute.call_args_list]
    assert all(sql.startswith("SELECT") for sql in statements)
    assert engine.begin.return_value.__exit__.call_args.args[0] is ValueError
