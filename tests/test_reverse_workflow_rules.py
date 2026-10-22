import json

import pytest

from crud.workflows import _validate_machine_snapshots


def test_machine_snapshot_rejects_status_change():
    items = [{"object_id": "SN-1", "before_state": json.dumps({"状态": "待发货", "占用订单号": "SO-1"})}]
    current = {"SN-1": {"状态": "已发货", "占用订单号": "SO-1"}}

    with pytest.raises(ValueError, match="审批后状态已变化"):
        _validate_machine_snapshots(items, current)


def test_machine_snapshot_rejects_order_change():
    items = [{"object_id": "SN-1", "before_state": {"状态": "待发货", "占用订单号": "SO-1"}}]
    current = {"SN-1": {"状态": "待发货", "占用订单号": "SO-2"}}

    with pytest.raises(ValueError, match="审批后状态已变化"):
        _validate_machine_snapshots(items, current)


def test_machine_snapshot_accepts_unchanged_object():
    items = [{"object_id": "SN-1", "before_state": {"状态": "待发货", "占用订单号": "SO-1"}}]
    current = {"SN-1": {"状态": "待发货", "占用订单号": "SO-1"}}

    _validate_machine_snapshots(items, current)
