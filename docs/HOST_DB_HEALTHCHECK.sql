-- V8 主机库体检（只读，全部是 SELECT，不会改数据）
-- 用法：mysql -u<user> -p <db> < docs/HOST_DB_HEALTHCHECK.sql
-- 背景：主机当前跑的是 GitHub 版本（3751f35b），缺少本地 36 个提交中的多项修复，
-- 下列问题在旧代码下会持续产生，先摸清存量再决定怎么处理。

SELECT '1. 未完成流程实例（卡住的单子）' AS section;
SELECT instance_no, workflow_key, business_id, status, initiator_id,
       LEFT(COALESCE(failure_reason, ''), 80) AS failure_reason, created_at
FROM workflow_instances
WHERE status IN ('待审批', '审批中', '已通过', '执行中', '执行异常', '重试中', '永久失败待处理')
ORDER BY id DESC;

SELECT '2. 被占用的业务对象锁（这些对象发不起新流程）' AS section;
SELECT l.object_type, l.object_id, l.instance_id, i.instance_no, i.status, l.created_at
FROM workflow_object_locks l
LEFT JOIN workflow_instances i ON i.id = l.instance_id
WHERE l.lock_status = '占用中'
ORDER BY l.id DESC;

SELECT '3. 终态实例仍带失败原因（重试成功但没清干净）' AS section;
SELECT instance_no, status, LEFT(failure_reason, 60) AS failure_reason, completed_at
FROM workflow_instances
WHERE status IN ('已完成', '已撤回', '已拒绝')
  AND COALESCE(failure_reason, '') <> '';

SELECT '4. 待派生处理与待办重入库任务' AS section;
SELECT (SELECT COUNT(*) FROM workflow_instances WHERE status = '待派生处理') AS pending_instances,
       (SELECT COUNT(*) FROM workflow_derived_tasks WHERE status = '待处理') AS pending_tasks;

SELECT '5. 东莞仓状态与库位错位（状态说是 DG，库位却是普通货位）' AS section;
SELECT `流水号`, `状态`, `Location_Code`, `占用订单号`, `更新时间`
FROM finished_goods_data
WHERE TRIM(`状态`) = '库存中（DG-WH）'
  AND TRIM(COALESCE(`Location_Code`, '')) NOT IN ('DG-WH', 'DONGGUAN', '东莞仓库')
ORDER BY `占用订单号`, `流水号`;

SELECT '6. 东莞口径差异（同一批数据两种算法）' AS section;
SELECT
  (SELECT COUNT(*) FROM finished_goods_data WHERE TRIM(`状态`) = '库存中（DG-WH）') AS by_status,
  (SELECT COUNT(*) FROM finished_goods_data
     WHERE TRIM(COALESCE(`Location_Code`, '')) IN ('DG-WH', 'DONGGUAN', '东莞仓库')) AS by_location;

SELECT '7. 流程 outbox 积压（无消费者，会一直涨）' AS section;
SELECT event_type, status, COUNT(*) AS n, MIN(created_at) AS first_at, MAX(created_at) AS last_at
FROM workflow_outbox_events
GROUP BY event_type, status
ORDER BY n DESC;

SELECT '8. 近 7 天执行异常统计' AS section;
SELECT DATE(created_at) AS day, status, COUNT(*) AS n
FROM workflow_instances
WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
  AND status IN ('执行异常', '永久失败待处理')
GROUP BY DATE(created_at), status
ORDER BY day DESC;

SELECT '9. 表排序规则（流程表与业务表不一致，跨表 JOIN 要手写 COLLATE）' AS section;
SELECT TABLE_NAME, TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('finished_goods_data', 'sales_orders', 'users',
                     'workflow_instances', 'workflow_tasks', 'workflow_derived_tasks',
                     'workflow_object_locks', 'workflow_outbox_events')
ORDER BY TABLE_NAME;

SELECT '10. 关键表数据量（升级前记录基线）' AS section;
SELECT 'finished_goods_data' AS tbl, COUNT(*) AS rows_count FROM finished_goods_data
UNION ALL SELECT 'sales_orders', COUNT(*) FROM sales_orders
UNION ALL SELECT 'workflow_instances', COUNT(*) FROM workflow_instances
UNION ALL SELECT 'workflow_derived_tasks', COUNT(*) FROM workflow_derived_tasks
UNION ALL SELECT 'workflow_outbox_events', COUNT(*) FROM workflow_outbox_events
UNION ALL SELECT 'dealer_orders', COUNT(*) FROM dealer_orders;
