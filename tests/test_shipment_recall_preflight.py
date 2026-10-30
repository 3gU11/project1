from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text

from crud import workflows


@pytest.mark.parametrize('status', ['待发货', '待入库', '库存中'])
def test_unshipped_recall_rejected_before_creating_instance(monkeypatch, status):
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE workflow_instances (idempotency_key TEXT)'))
        conn.execute(text('CREATE TABLE finished_goods_data (`流水号` TEXT, `状态` TEXT, Location_Code TEXT)'))
        conn.execute(text("INSERT INTO finished_goods_data VALUES ('SN-1',:status,'MAIN')"), {'status': status})

    class Connection:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, query, params):
            return self.conn.execute(text(str(query).replace(' FOR UPDATE', '')), params)

    class Engine:
        @contextmanager
        def begin(self):
            with engine.begin() as conn:
                yield Connection(conn)

    monkeypatch.setattr(workflows, 'ensure_workflow_tables', lambda: None)
    monkeypatch.setattr(workflows, 'get_engine', lambda: Engine())
    with pytest.raises(ValueError, match='请先确认发货'):
        workflows.create_reverse_instance('shipment-recall', '机台', 'SN-1', 'admin', 'test')
    with engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM workflow_instances')).scalar() == 0
