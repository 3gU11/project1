"""Release unused anonymous sandbox reservations after an order is shipped."""
import re
from collections import Counter

from sqlalchemy import bindparam, text


def _model(value):
    return str(value or '').replace('(加高)', '').replace('（加高）', '').strip()


def _demand(row):
    counts = Counter()
    raw = str(row.get('需求机型') or '')
    for token in re.split(r'[;；/,，]', raw):
        match = re.fullmatch(r'\s*(.+?)[x×:：]\s*(\d+)\s*', token, flags=re.I)
        if match:
            counts[_model(match[1])] += int(match[2])
    if not counts and _model(raw):
        try:
            counts[_model(raw)] = int(float(row.get('需求数量') or 0))
        except (ValueError, TypeError):
            pass
    return {model: qty for model, qty in counts.items() if model and qty > 0}


def release_completed_order_reservations(conn, order_ids):
    """Use the caller's transaction. Keep physical/locked/in-production cards.

    Return pre-update rows so callers can retain an audit/repair snapshot.
    Completion status alone is insufficient: current shipped serials must cover
    every model in the order, without double counting duplicate inventory rows.
    """
    released = []
    for oid in sorted({str(oid or '').strip() for oid in order_ids} - {''}):
        order = conn.execute(text('''
            SELECT `订单号`, `需求机型`, `需求数量`, status FROM sales_orders
            WHERE `订单号`=:oid FOR UPDATE
        '''), {'oid':oid}).mappings().first()
        if not order or order['status'] != 'done':
            continue
        demand = _demand(order)
        if not demand:
            continue
        shipped = conn.execute(text('''
            SELECT `流水号`, `机型` FROM finished_goods_data
            WHERE TRIM(COALESCE(`占用订单号`, ''))=:oid
              AND TRIM(COALESCE(`状态`, ''))='已出库' FOR UPDATE
        '''), {'oid':oid}).mappings().all()
        serial_models = {str(r['流水号']).strip(): _model(r['机型'])
                         for r in shipped if str(r['流水号'] or '').strip()}
        counts = Counter(serial_models.values())
        if any(counts[model] < qty for model, qty in demand.items()):
            continue
        rows = conn.execute(text('''
            SELECT u.* FROM units u JOIN batches b ON b.batch_id=u.batch_id
            WHERE TRIM(COALESCE(u.sales_id, ''))=:oid
              AND TRIM(COALESCE(u.contract_no, '')) <> ''
              AND u.status='Pending' AND b.status IN ('Predicted','Confirmed')
              AND TRIM(COALESCE(u.serial_no, ''))=''
              AND TRIM(COALESCE(u.forecast_serial_no, ''))=''
              AND TRIM(COALESCE(u.production_line_id, ''))=''
              AND COALESCE(u.is_locked,0)=0 AND COALESCE(u.is_contract_pinned,0)=0
            FOR UPDATE
        '''), {'oid':oid}).mappings().all()
        if not rows:
            continue
        conn.execute(text('''
            UPDATE units SET contract_no=NULL, sales_id=NULL, customer=NULL,
                dealer_id=NULL, dealer_name=NULL, due_date=NULL, order_remark=NULL,
                updated_at=NOW()
            WHERE unit_id IN :ids
        ''').bindparams(bindparam('ids', expanding=True)),
            {'ids':[r['unit_id'] for r in rows]})
        released.extend(dict(r) for r in rows)
    return released
