-- ============================================================
-- 脚本：将 finished_goods_data 中的特定批次机台分配到沙盘指定的产线
-- 逻辑：
--   1. 定义【批次号 -> 产线名】的映射关系
--   2. 清理旧的（由本脚本）生成的测试 batches 和 units
--   3. 在 batches 表中为这些批次创建 In_Production 的批次记录，绑定产线
--   4. 将 finished_goods_data 的机台插入 units 表，绑定到对应的 batch
-- ============================================================

-- ── 1. 创建映射表 ──────────────────────────────────────────────
CREATE TEMPORARY TABLE IF NOT EXISTS batch_line_mapping (
    batch_code VARCHAR(32),
    line_name VARCHAR(64),
    line_id VARCHAR(64)
);
TRUNCATE TABLE batch_line_mapping;

INSERT INTO batch_line_mapping (batch_code, line_name) VALUES
('05-08', '9号通用线'),
('05-07', '8号通用线'),
('05-06', '2号通用线'),
('05-05附加', '18号通用线'),
('05-02', '4号通用线'),
('05-05', '12号通用线'),
('05-04', '3号通用线'),
('04-06附加', '19号通用线'),
('03-03附加', '19号通用线'),
('05-03', '13号通用线'),
('05-01', '10号通用线'),
('04-22', '14号通用线'),
('04-21', '15号通用线'),
('04-20', '6号通用线'),
('04-19附加', '19号通用线'),
('04-19', '5号通用线'),
('04-18', '7号通用线'),
('04-16', '11号通用线'),
('04-14', '1号通用线'),
('04-10', '17号通用线'),
('04-09', '16号通用线'),
('03-16附加', '18号通用线'),
('02-08附加', '18号通用线'),
('11-14', '18号通用线');

-- 更新实际的 line_id (将 '9号通用线' 映射到 '产线 9' 的 line_id)
UPDATE batch_line_mapping m
JOIN production_lines pl 
  ON CONVERT(pl.line_name USING utf8mb4) COLLATE utf8mb4_general_ci = 
     CONVERT(CONCAT('产线 ', REPLACE(m.line_name, '号通用线', '')) USING utf8mb4) COLLATE utf8mb4_general_ci
SET m.line_id = pl.line_id;


-- ── 2. 清理之前用脚本插入的冲突数据 ──────────────────────────────
-- 删除以 BATCH-SYNC- 开头的测试批次及其包含的机台
DELETE FROM units WHERE batch_id LIKE 'BATCH-SYNC-%';
DELETE FROM batches WHERE batch_id LIKE 'BATCH-SYNC-%';

-- 重置产线当前批次（避免外键约束或状态错误）
UPDATE production_lines SET current_batch_id = NULL WHERE current_batch_id LIKE 'BATCH-SYNC-%';


-- ── 3. 创建批次记录 (Batches) ──────────────────────────────────
-- 对于映射表中的每一个批次，从 fg 推导大类，并创建批次
INSERT INTO batches (
    batch_id,
    batch_no,
    batch_code,
    model_type,
    capacity,
    status,
    production_line_id,
    source,
    created_at,
    updated_at
)
SELECT 
    CONCAT('BATCH-SYNC-', m.batch_code),
    -- 生成一个假的 batch_no
    (SELECT COALESCE(MAX(batch_no), 0) FROM batches) + ROW_NUMBER() OVER(ORDER BY m.batch_code),
    m.batch_code,
    -- 从 fg 推断该批次的大类
    COALESCE(
        (SELECT CASE
            WHEN UPPER(fg.`机型`) LIKE '%AUTO%'    THEN 'AUTO'
            WHEN UPPER(fg.`机型`) LIKE '%SPECIAL%' THEN 'SPECIAL'
            WHEN UPPER(fg.`机型`) LIKE '%XS%'      THEN 'XS'
            ELSE 'G' END
         FROM finished_goods_data fg 
         WHERE fg.`批次号` = m.batch_code LIMIT 1),
        'G'
    ) AS family,
    30 AS capacity, -- 默认容量 30
    'In_Production' AS status,
    m.line_id,
    'Sandbox' AS source,
    NOW(),
    NOW()
FROM batch_line_mapping m
WHERE m.line_id IS NOT NULL;


-- ── 4. 将 fg 的机台插入 Units 表 ───────────────────────────────
INSERT INTO units (
    unit_id,
    batch_id,
    slot_index,
    model_type,
    status,
    serial_no,
    production_line_id,
    contract_no,
    customer,
    dealer_name,
    order_remark,
    created_at,
    updated_at
)
WITH 
fg_candidates AS (
    SELECT 
        fg.`流水号` AS serial_no,
        fg.`机型`   AS model_name,
        fg.`批次号` AS fg_batch_code,
        fg.`合同号` AS contract_no,
        fg.`客户`   AS customer,
        fg.`代理商` AS dealer_name,
        CONCAT_WS(' | ', 
            NULLIF(TRIM(fg.`订单备注`), ''), 
            NULLIF(TRIM(fg.`机台备注/配置`), '')
        ) AS order_remark,
        b.batch_id,
        b.production_line_id,
        ROW_NUMBER() OVER (PARTITION BY b.batch_id ORDER BY fg.`流水号`) AS slot_index
    FROM finished_goods_data fg
    INNER JOIN batches b 
       ON CONVERT(b.batch_code USING utf8mb4) COLLATE utf8mb4_general_ci = 
          CONVERT(fg.`批次号` USING utf8mb4) COLLATE utf8mb4_general_ci
      AND b.batch_id LIKE 'BATCH-SYNC-%'
    WHERE fg.`状态` IN ('待入库', '库存中', '待发货')
      AND (fg.`占用订单号` IS NULL OR fg.`占用订单号` = '')
      AND fg.`批次号` IS NOT NULL 
      AND TRIM(fg.`批次号`) <> ''
)
SELECT 
    CONCAT(batch_id, '_', slot_index) AS unit_id,
    batch_id,
    slot_index,
    model_name AS model_type,
    'In_Production' AS status,
    serial_no,
    production_line_id,
    contract_no,
    customer,
    dealer_name,
    order_remark,
    NOW(),
    NOW()
FROM fg_candidates

ON DUPLICATE KEY UPDATE
    serial_no = VALUES(serial_no),
    status = VALUES(status),
    production_line_id = VALUES(production_line_id),
    contract_no = VALUES(contract_no),
    customer = VALUES(customer),
    dealer_name = VALUES(dealer_name),
    order_remark = VALUES(order_remark),
    updated_at = NOW();


-- ── 5. 设置产线的 current_batch_id ─────────────────────────────
-- (对于有多个批次的产线，随便选一个最新的作为 current_batch_id)
UPDATE production_lines pl
JOIN (
    SELECT production_line_id, MAX(batch_id) AS latest_batch_id
    FROM batches 
    WHERE batch_id LIKE 'BATCH-SYNC-%'
    GROUP BY production_line_id
) b ON pl.line_id = b.production_line_id
SET pl.current_batch_id = b.latest_batch_id,
    pl.status = 'Busy'
WHERE pl.current_batch_id IS NULL OR pl.status != 'Busy';


-- ── 6. 验证结果 ────────────────────────────────────────────────
SELECT 
    b.batch_code AS '批次号',
    pl.line_name AS '产线名称',
    b.model_type AS '大类',
    b.status AS '批次状态',
    COUNT(u.unit_id) AS '分配机台数'
FROM batches b
LEFT JOIN production_lines pl ON pl.line_id = b.production_line_id
LEFT JOIN units u ON u.batch_id = b.batch_id
WHERE b.batch_id LIKE 'BATCH-SYNC-%'
GROUP BY b.batch_id, b.batch_code, pl.line_name, b.model_type, b.status
ORDER BY pl.line_name, b.batch_code;
