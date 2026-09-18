import sqlite3

from crud.inventory_scope import pending_inbound_scope_sql, inventory_relationship_join_sql, joined_pending_scope_sql


def test_pending_requires_active_line_batch_and_inventory_status():
    db = sqlite3.connect(':memory:')
    db.create_collation('utf8mb4_general_ci', lambda a, b: (a > b) - (a < b))
    db.executescript('''
        CREATE TABLE finished_goods_data (流水号 TEXT, 状态 TEXT);
        CREATE TABLE units (serial_no TEXT, forecast_serial_no TEXT, batch_id TEXT,
                            status TEXT, production_line_id TEXT, sales_id TEXT, contract_no TEXT);
        CREATE TABLE batches (batch_id TEXT, status TEXT);
        CREATE TABLE production_lines (line_id TEXT, status TEXT);
        INSERT INTO production_lines VALUES ('line', 'Busy'), ('idle', 'Idle');
        INSERT INTO batches VALUES ('active','In_Production'), ('queue','Confirmed'), ('done','Completed');
    ''')
    cases = [
        ('active', '待入库', 'In_Production', 'active', 'line', 'production'),
        ('stock', '库存中（D09）', 'In_Production', 'active', 'line', ''),
        ('shipping', '待发货', 'In_Production', 'active', 'line', ''),
        ('queue', '待入库', 'Pending', 'queue', None, 'queued'),
        ('done', '待入库', 'Completed', 'done', None, 'review'),
        ('stale-batch', '待入库', 'In_Production', 'done', 'line', 'review'),
        ('idle', '待入库', 'In_Production', 'active', 'idle', 'review'),
    ]
    for sn, inventory, state, batch, line, expected in cases:
        db.execute('INSERT INTO finished_goods_data VALUES (?,?)', (sn, inventory))
        db.execute('INSERT INTO units VALUES (?,?,?,?,?,?,?)', ('', sn, batch, state, line, 'SO-1', None))
    db.execute("INSERT INTO finished_goods_data VALUES ('orphan','待入库')")
    db.execute("INSERT INTO units SELECT * FROM units WHERE forecast_serial_no='active'")
    result = dict(db.execute(f'SELECT fg.流水号, {pending_inbound_scope_sql()} FROM finished_goods_data fg'))
    assert result == {**{row[0]: row[-1] for row in cases}, 'orphan': 'review'}
    assert len(result) == 8
    joined = list(db.execute(f'SELECT fg.流水号, {joined_pending_scope_sql()}, COALESCE(rel.bound,0) FROM finished_goods_data fg {inventory_relationship_join_sql()}'))
    assert len(joined) == 8
    assert {sn: scope for sn, scope, _ in joined} == result
    assert {sn for sn, _, bound in joined if bound} == {'active', 'stock', 'shipping'}
