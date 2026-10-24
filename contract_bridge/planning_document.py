from .renderer import render


def render_planning_contract(contract_id, rows):
    """Use the canonical template; leave unavailable commercial terms blank."""
    if not rows or len(rows) > 4:
        raise ValueError('合同须包含 1 至 4 行产品，不能截断产品明细')
    first = rows[0]
    fields = dict(supplier_name='', contract_no=str(contract_id),
                  buyer_name=str(first.get('客户名') or ''), signing_place='',
                  signed_date='', delivery_date=str(first.get('要求交期') or ''),
                  settlement_terms='', total_upper='')
    for index, row in enumerate(rows, 1):
        fields[f'item{index}_spec'] = str(row.get('机型') or '')
        fields[f'item{index}_qty'] = str(row.get('排产数量') or '')
    return render(fields)[0]
