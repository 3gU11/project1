"""One-time explicit upgrade; never run automatically on application startup."""
import json
from copy import deepcopy

from sqlalchemy import text
from database import get_engine
from crud.workflows import FORWARD_ENTRY_ACTIONS, publish_workflow_model, validate_workflow_snapshot


def upgraded_snapshot(snapshot, action):
    graph = deepcopy(snapshot)
    if not graph.get('nodes'):
        graph = {'nodes': [{'id': 'start', 'type': 'start', 'label': '发起', 'x': 60, 'y': 120},
                           {'id': 'end', 'type': 'end', 'label': '结束', 'x': 640, 'y': 120}],
                 'edges': [{'source': 'start', 'target': 'end'}]}
    if any(n.get('type') == 'execute' for n in graph['nodes']):
        return graph
    ends = {n['id'] for n in graph['nodes'] if n.get('type') == 'end'}
    ids = {n['id'] for n in graph['nodes']}
    for index, edge in enumerate(list(graph['edges'])):
        if edge.get('target') not in ends:
            continue
        node_id = f'business-action-{index}'
        while node_id in ids:
            node_id += '-new'
        ids.add(node_id)
        end = edge['target']
        edge['target'] = node_id
        graph['nodes'].append({'id': node_id, 'type': 'execute', 'action': action,
                               'label': '自动执行业务', 'x': 330, 'y': 120 + index * 80})
        graph['edges'].append({'source': node_id, 'target': end})
    return graph


def main():
    upgrades = []
    with get_engine().connect() as conn:
        for key, action in FORWARD_ENTRY_ACTIONS.items():
            rows = conn.execute(text("SELECT v.status,v.node_snapshot FROM workflow_model_versions v JOIN workflow_models m ON m.id=v.model_id WHERE m.workflow_key=:key AND v.status IN ('已发布','草稿')"), {'key': key}).mappings().all()
            if any(row['status'] == '草稿' for row in rows):
                raise ValueError(f'{key} 存在草稿，请先处理草稿后升级')
            published = [row for row in rows if row['status'] == '已发布']
            if len(published) != 1:
                raise ValueError(f'{key} 已发布版本不唯一')
            snapshot = published[0]['node_snapshot']
            snapshot = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
            upgraded = upgraded_snapshot(snapshot, action)
            validate_workflow_snapshot(upgraded, key)
            if upgraded != snapshot:
                upgrades.append((key, upgraded))
    for key, snapshot in upgrades:
        print(publish_workflow_model(key, snapshot, 'system-forward-entry-upgrade'))


if __name__ == '__main__':
    main()
