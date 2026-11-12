"""把现有流程模型复制成一套“全自动通过/自动执行”的新模型。

规则：
  * 只新增模型，绝不修改原有模型（原模型及其版本快照保持不动）。
  * 新模型 Key 统一加 `-auto` 后缀，名称加“（全自动通过）”。
  * 新模型快照会删除 approval/approve 节点并把前后连线接上；
    发起、条件、执行、通知、结束节点全部保留。
  * 没有审批节点后，create_reverse_instance 会直接把实例置为“已通过”
    并推进到业务执行节点，即“自动通过 + 自动执行”。
  * 新模型以“已发布”状态写入，处理方式自动为“自动通过”。

用法：
    python tools/rebuild_workflow_models_auto.py            # 预演，只打印计划
    python tools/rebuild_workflow_models_auto.py --apply    # 实际写入数据库
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

import pymysql

sys.path.insert(0, '.')
from crud.workflows import (  # noqa: E402
    validate_workflow_snapshot,
    _snapshot_requires_approval,
)

DB = dict(host='localhost', port=3306, user='root', password='123321',
          database='rjfinshed_v8_import', charset='utf8mb4',
          cursorclass=pymysql.cursors.DictCursor)
OPERATOR = 'system-auto-pass'
SUFFIX = '-auto'
APPROVAL_TYPES = {'approval', 'approve'}


def load_models(conn):
    with conn.cursor() as cur:
        cur.execute("""SELECT m.id, m.workflow_key, m.name, m.category_key, m.direction,
                              m.processing_type, m.business_object, m.execution_scope,
                              m.status, m.is_required, m.current_version,
                              v.version_no, v.node_snapshot
                       FROM workflow_models m
                       LEFT JOIN workflow_model_versions v
                         ON v.model_id = m.id AND v.version_no = m.current_version
                       ORDER BY m.id""")
        return cur.fetchall()


def as_snapshot(raw):
    if isinstance(raw, str):
        return json.loads(raw)
    return raw or {}


def strip_approval_nodes(snapshot: dict) -> tuple[dict, list[str]]:
    """删除审批节点，把审批节点前驱直接连到后继；返回 (新快照, 被删节点ID)。"""
    nodes = [node for node in snapshot.get('nodes', []) if isinstance(node, dict)]
    edges = [edge for edge in snapshot.get('edges', []) if isinstance(edge, dict)]
    approval_ids = {str(node.get('id')) for node in nodes
                    if str(node.get('type', '')).lower() in APPROVAL_TYPES}
    if not approval_ids:
        return {'nodes': nodes, 'edges': edges}, []

    kept_nodes = [node for node in nodes if str(node.get('id')) not in approval_ids]
    new_edges = [edge for edge in edges
                 if str(edge.get('source')) not in approval_ids
                 and str(edge.get('target')) not in approval_ids]
    for approval_id in approval_ids:
        preds = [edge for edge in edges if str(edge.get('target')) == approval_id]
        succs = [edge for edge in edges if str(edge.get('source')) == approval_id]
        for pred in preds:
            for succ in succs:
                merged = dict(pred)
                merged['target'] = succ['target']
                # 审批节点自身的连线属性（如 branch）不应覆盖前驱条件分支的标记。
                for key, value in succ.items():
                    if key in ('source', 'target'):
                        continue
                    merged.setdefault(key, value)
                new_edges.append(merged)
    return {'nodes': kept_nodes, 'edges': new_edges}, sorted(approval_ids)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='实际写入数据库')
    args = parser.parse_args()

    conn = pymysql.connect(**DB)
    try:
        models = load_models(conn)
        if not models:
            print('没有找到流程模型')
            return 1
        with conn.cursor() as cur:
            cur.execute('SELECT workflow_key FROM workflow_models')
            existing_keys = {row['workflow_key'] for row in cur.fetchall()}

        plans, conflicts, errors = [], [], []
        for model in models:
            snapshot = as_snapshot(model['node_snapshot'])
            if not snapshot.get('nodes'):
                errors.append(f"{model['workflow_key']}: 当前版本没有节点快照")
                continue
            new_snapshot, removed = strip_approval_nodes(snapshot)
            new_key = f"{model['workflow_key']}{SUFFIX}"
            if new_key in existing_keys:
                conflicts.append(new_key)
            try:
                # 用原 Key 校验一次，保证去掉审批后仍满足逆向流程的动作约束。
                validate_workflow_snapshot(new_snapshot, model['workflow_key'])
                validate_workflow_snapshot(new_snapshot, new_key)
            except ValueError as exc:
                errors.append(f"{model['workflow_key']}: 校验失败 {exc}")
                continue
            if _snapshot_requires_approval(new_snapshot):
                errors.append(f"{model['workflow_key']}: 仍有审批节点")
                continue
            plans.append({'model': model, 'snapshot': new_snapshot, 'removed': removed,
                          'new_key': new_key,
                          'new_name': f"{model['name']}（全自动通过）"})

        print(f'待复制模型：{len(plans)} 个；已有同名 Key：{len(conflicts)} 个；异常：{len(errors)} 个')
        for plan in plans:
            removed = '、'.join(plan['removed']) or '无'
            print(f"  {plan['model']['workflow_key']:<28} -> {plan['new_key']:<32} "
                  f"删除审批节点: {removed}")
        for conflict in conflicts:
            print(f'  [已存在] {conflict}')
        for error in errors:
            print(f'  [错误] {error}')

        if conflicts or errors:
            print('存在冲突或校验问题，未写入任何数据。')
            return 2
        if not args.apply:
            print('预演完成；加 --apply 才会写入。')
            return 0

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with conn.cursor() as cur:
            for plan in plans:
                model = plan['model']
                cur.execute("""INSERT INTO workflow_models
                    (workflow_key,name,category_key,direction,processing_type,business_object,
                     execution_scope,status,is_required,current_version,created_by,updated_by,
                     created_at,updated_at)
                    VALUES (%s,%s,%s,%s,'自动通过',%s,%s,'已发布',%s,1,%s,%s,%s,%s)""", (
                    plan['new_key'], plan['new_name'], model['category_key'], model['direction'],
                    model['business_object'], model['execution_scope'], model['is_required'],
                    OPERATOR, OPERATOR, now, now))
                model_id = cur.lastrowid
                cur.execute("""INSERT INTO workflow_model_versions
                    (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,
                     published_at,created_at)
                    VALUES (%s,1,'已发布',%s,1,%s,%s,%s)""", (
                    model_id,
                    json.dumps(plan['snapshot'], ensure_ascii=False, separators=(',', ':')),
                    OPERATOR, now, now))
        conn.commit()
        print(f'已写入 {len(plans)} 个新模型（Key 后缀 {SUFFIX}）。')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
