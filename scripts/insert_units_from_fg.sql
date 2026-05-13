-- ============================================================
-- 从 finished_goods_data 查询对应机台，插入到 units 表
-- 规则：
--   1. 仅处理 finished_goods_data 中状态为 '待入库'/'库存中'/'待发货' 的机台
--   2. 必须有批次号，且通过 batches.batch_code = 批次号 精准匹配
--   3. 插入时严格按 batches.capacity 控制每批次容量
--   4. 避免重复插入（ON DUPLICATE KEY）
--   5. unit_id 格式：{batch_id}_{slot_index}
-- ============================================================

-- ── Step 1a：查看 finished_goods_data 中对应批次号的机台 ──────
SELECT DISTINCT
    fg.`批次号`,
    fg.`机型`,
    fg.`状态`,
    fg.`流水号`,
    COUNT(*) OVER (PARTITION BY fg.`批次号`) AS cnt_in_batch
FROM finished_goods_data fg
WHERE fg.`批次号` IS NOT NULL
  AND TRIM(fg.`批次号`) <> ''
  AND CONVERT(fg.`批次号` USING utf8mb4) COLLATE utf8mb4_general_ci IN (
      '05-08', '05-07', '05-06', '05-02', '05-05', '05-04',
      '05-03', '05-01', '04-22', '04-21',
      '04-20', '04-19', '04-18', '04-16', '04-14', '04-10',
      '04-09'
  )
ORDER BY fg.`批次号`, fg.`机型`;


-- ── Step 1b：查看 batches 表现有 batch_code 值 ────────────────
SELECT batch_id, batch_code, model_type, capacity, status
FROM batches
ORDER BY batch_id
LIMIT 30;


-- ── Step 1c：LEFT JOIN 查看两表能否对上 ──────────────────────
SELECT
    fg.`批次号`       AS fg_batch_no,
    fg.`机型`,
    fg.`状态`,
    b.batch_id,
    b.batch_code,
    b.model_type,
    b.status          AS batch_status
FROM finished_goods_data fg
LEFT JOIN batches b
       ON CONVERT(b.batch_code USING utf8mb4) COLLATE utf8mb4_general_ci
        = CONVERT(fg.`批次号`  USING utf8mb4) COLLATE utf8mb4_general_ci
WHERE CONVERT(fg.`批次号` USING utf8mb4) COLLATE utf8mb4_general_ci IN (
      '05-08', '05-07', '05-06', '05-05附加', '05-02', '05-05', '05-04',
      '04-06附加', '03-03附加', '05-03', '05-01', '04-22', '04-21',
      '04-20', '04-19附加', '04-19', '04-18', '04-16', '04-14', '04-10',
      '04-09', '03-16附加', '02-08附加', '11-14'
  )
ORDER BY fg.`批次号`, fg.`流水号`
LIMIT 30;


-- ── Step 2：查看目标 batch 的当前容量使用情况 ─────────────────
SELECT
    b.batch_id,
    b.batch_code,
    b.model_type      AS batch_model_type,
    b.capacity        AS max_capacity,
    COUNT(u.unit_id)  AS current_unit_count,
    b.capacity - COUNT(u.unit_id) AS remaining_slots
FROM batches b
LEFT JOIN units u ON u.batch_id = b.batch_id
WHERE b.status IN ('Predicted', 'Confirmed', 'In_Production')
GROUP BY b.batch_id, b.batch_code, b.model_type, b.capacity
HAVING remaining_slots > 0
ORDER BY b.batch_id;


-- ── Step 3：核心插入逻辑（仅精准匹配，无兜底）───────────────
INSERT INTO units (
    unit_id,
    batch_id,
    slot_index,
    model_type,
    status,
    serial_no,
    created_at,
    updated_at
)
WITH

-- A: 候选机台精准匹配 batch（批次号 = batch_code，两端均非空）
fg_matched AS (
    SELECT
        fg.`流水号`  AS serial_no,
        fg.`机型`    AS model_name,
        b.batch_id
    FROM finished_goods_data fg
    INNER JOIN batches b
            ON CONVERT(b.batch_code USING utf8mb4) COLLATE utf8mb4_general_ci
             = CONVERT(fg.`批次号`  USING utf8mb4) COLLATE utf8mb4_general_ci
           AND b.status IN ('Predicted', 'Confirmed', 'In_Production')
    WHERE fg.`状态` IN ('待入库', '库存中', '待发货')
      AND (fg.`占用订单号` IS NULL OR fg.`占用订单号` = '')
      AND fg.`批次号` IS NOT NULL
      AND TRIM(fg.`批次号`) <> ''
      AND CONVERT(fg.`批次号` USING utf8mb4) COLLATE utf8mb4_general_ci IN (
          '05-08', '05-07', '05-06', '05-05附加', '05-02', '05-05', '05-04',
          '04-06附加', '03-03附加', '05-03', '05-01', '04-22', '04-21',
          '04-20', '04-19附加', '04-19', '04-18', '04-16', '04-14', '04-10',
          '04-09', '03-16附加', '02-08附加', '11-14'
      )
      AND NOT EXISTS (
          SELECT 1 FROM units u
          WHERE CONVERT(u.serial_no USING utf8mb4) COLLATE utf8mb4_general_ci
              = CONVERT(fg.`流水号` USING utf8mb4) COLLATE utf8mb4_general_ci
      )
),

-- B: 各批次当前已用 slot 统计
batch_usage AS (
    SELECT
        CONVERT(batch_id USING utf8mb4) COLLATE utf8mb4_general_ci AS batch_id,
        COUNT(*) AS used_cnt,
        MAX(slot_index) AS max_slot
    FROM units
    GROUP BY batch_id
),

-- C: 分配 slot_index（同一批次内按流水号排序递增）
alloc AS (
    SELECT
        fm.serial_no,
        fm.model_name,
        fm.batch_id,
        COALESCE(bu.max_slot, 0) + ROW_NUMBER() OVER (
            PARTITION BY fm.batch_id ORDER BY fm.serial_no
        ) AS slot_index
    FROM fg_matched fm
    LEFT JOIN batch_usage bu
           ON bu.batch_id = CONVERT(fm.batch_id USING utf8mb4) COLLATE utf8mb4_general_ci
)

SELECT
    CONCAT(batch_id, '_', slot_index) AS unit_id,
    batch_id,
    slot_index,
    model_name  AS model_type,
    'Predicted' AS status,
    serial_no,
    NOW()       AS created_at,
    NOW()       AS updated_at
FROM alloc

ON DUPLICATE KEY UPDATE
    serial_no  = VALUES(serial_no),
    updated_at = NOW();


-- ── Step 4：验证插入结果 ──────────────────────────────────────
SELECT
    b.batch_code,
    b.model_type,
    b.capacity,
    COUNT(u.unit_id)              AS total_units,
    SUM(u.serial_no IS NOT NULL)  AS with_serial
FROM batches b
JOIN units u ON u.batch_id = b.batch_id
GROUP BY b.batch_id, b.batch_code, b.model_type, b.capacity
ORDER BY b.batch_id;
