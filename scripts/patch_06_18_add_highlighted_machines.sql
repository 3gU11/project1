-- Patch: add the highlighted machines to batch 06-18 and cascade the serial number shift.
-- Database: rjfinshed
--
-- What this script does:
-- 1. Backs up the touched rows into patch_backup_0618_* tables.
-- 2. Moves downstream 96-06 serials from 96-06-508 onward forward by 6 in both
--    units.forecast_serial_no and plan_import.流水号.
-- 3. Rebuilds finished_goods_data for batch 06-18 as serials 96-06-498 through 96-06-513.
-- 4. Upserts the matching units rows for batch 06-18 slots 1 through 16.
-- 5. Rebuilds the local wechat_batch_summary rows affected by 06-18.
-- 6. Enqueues one cloud_sync_outbox event so the summary can be synced by the existing worker.
--
-- Expected current batch:
--   batch_code = 06-18
--   batch_id   = BATCH-202607-XS-MANUAL-024-403219

SET NAMES utf8mb4 COLLATE utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS patch_backup_0618_finished_goods_data_20260703 LIKE finished_goods_data;
CREATE TABLE IF NOT EXISTS patch_backup_0618_units_20260703 LIKE units;
CREATE TABLE IF NOT EXISTS patch_backup_0618_plan_import_20260703 LIKE plan_import;
CREATE TABLE IF NOT EXISTS patch_backup_0618_wechat_batch_summary_20260703 LIKE wechat_batch_summary;
CREATE TABLE IF NOT EXISTS patch_backup_0618_batches_20260703 LIKE batches;

DROP PROCEDURE IF EXISTS patch_06_18_add_highlighted_machines;

DELIMITER $$

CREATE PROCEDURE patch_06_18_add_highlighted_machines()
BEGIN
    DECLARE v_batch_count INT DEFAULT 0;
    DECLARE v_batch_id VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
    DECLARE v_capacity INT DEFAULT 0;
    DECLARE v_line_id VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
    DECLARE v_status VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
    DECLARE v_conflicts INT DEFAULT 0;
    DECLARE v_serial_prefix VARCHAR(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT '96-06-';
    DECLARE v_shift_start INT DEFAULT 508;
    DECLARE v_shift_size INT DEFAULT 6;
    DECLARE v_expected_inbound DATETIME DEFAULT '2026-08-31 00:00:00';

    CREATE TEMPORARY TABLE tmp_0618_target (
        slot_index INT NOT NULL PRIMARY KEY,
        serial_no VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL UNIQUE,
        model_type VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL
    ) ENGINE=MEMORY DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

    INSERT INTO tmp_0618_target (slot_index, serial_no, model_type) VALUES
        (1,  '96-06-498', 'FR-7055XS电压220V(PRO) 泰国'),
        (2,  '96-06-499', 'FR-7055XS加高100mm(PRO) 总线'),
        (3,  '96-06-500', 'FR-7055XS加高100mm(PRO) 总线'),
        (4,  '96-06-501', 'FR-7055XS加高200mm，后导电(PRO)'),
        (5,  '96-06-502', 'FR-8055XS(PRO)总线'),
        (6,  '96-06-503', 'FR-8055XS(PRO)总线'),
        (7,  '96-06-504', 'FR-8055XS加高100mm(PRO)总线'),
        (8,  '96-06-505', 'FR-8055AUTO'),
        (9,  '96-06-506', 'FR-8055AUTO'),
        (10, '96-06-507', 'FR-8055AUTO'),
        (11, '96-06-508', 'FR-8055AUTO'),
        (12, '96-06-509', 'FR-8055AUTO'),
        (13, '96-06-510', 'FR-8055AUTO'),
        (14, '96-06-511', 'FR-8055AUTO'),
        (15, '96-06-512', 'FR-8060XS（PRO）总线'),
        (16, '96-06-513', 'FR-8060AUTO');

    SELECT COUNT(*)
      INTO v_batch_count
      FROM batches
     WHERE batch_code = '06-18';

    IF v_batch_count <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Abort: batch_code 06-18 must match exactly one row in batches.';
    END IF;

    SELECT batch_id, capacity, production_line_id, status
      INTO v_batch_id, v_capacity, v_line_id, v_status
      FROM batches
     WHERE batch_code = '06-18';

    SELECT COUNT(*)
      INTO v_conflicts
      FROM finished_goods_data
     WHERE TRIM(COALESCE(`批次号`, '')) = '06-18'
       AND `流水号` IN (SELECT serial_no FROM tmp_0618_target);

    IF v_conflicts > 10 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Abort: patch appears already applied or partially applied; review before rerun.';
    END IF;

    IF v_batch_id <> 'BATCH-202607-XS-MANUAL-024-403219' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Abort: batch_id for 06-18 is not the expected batch.';
    END IF;

    IF v_capacity < 16 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Abort: batch 06-18 capacity is below 16.';
    END IF;

    IF v_status <> 'In_Production' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Abort: batch 06-18 is not In_Production.';
    END IF;

    SELECT COUNT(*)
      INTO v_conflicts
      FROM finished_goods_data
     WHERE TRIM(COALESCE(`批次号`, '')) = '06-18'
       AND (
            NULLIF(TRIM(COALESCE(`占用订单号`, '')), '') IS NOT NULL
         OR NULLIF(TRIM(COALESCE(`合同号`, '')), '') IS NOT NULL
         OR NULLIF(TRIM(COALESCE(`客户`, '')), '') IS NOT NULL
         OR NULLIF(TRIM(COALESCE(`代理商`, '')), '') IS NOT NULL
       );

    IF v_conflicts > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Abort: batch 06-18 has occupied/contracted finished_goods_data rows.';
    END IF;

    SELECT COUNT(*)
      INTO v_conflicts
      FROM units
     WHERE batch_id COLLATE utf8mb4_general_ci = v_batch_id
       AND (
            COALESCE(is_locked, 0) <> 0
         OR NULLIF(TRIM(COALESCE(contract_no, '')), '') IS NOT NULL
         OR NULLIF(TRIM(COALESCE(serial_no, '')), '') IS NOT NULL
       );

    IF v_conflicts > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Abort: batch 06-18 has locked/contracted units.';
    END IF;

    SELECT COUNT(*)
      INTO v_conflicts
      FROM units
     WHERE forecast_serial_no REGEXP '^96-06-[0-9]+$'
       AND CAST(SUBSTRING(forecast_serial_no, 7) AS UNSIGNED) >= v_shift_start
       AND batch_id COLLATE utf8mb4_general_ci <> v_batch_id
       AND (
            COALESCE(is_locked, 0) <> 0
         OR NULLIF(TRIM(COALESCE(contract_no, '')), '') IS NOT NULL
         OR NULLIF(TRIM(COALESCE(serial_no, '')), '') IS NOT NULL
       );

    IF v_conflicts > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Abort: downstream units already have locked/contracted serials.';
    END IF;

    SELECT COUNT(*)
      INTO v_conflicts
      FROM finished_goods_data
     WHERE `流水号` REGEXP '^96-06-[0-9]+$'
       AND CAST(SUBSTRING(`流水号`, 7) AS UNSIGNED) >= v_shift_start
       AND TRIM(COALESCE(`批次号`, '')) <> '06-18'
       AND (
            TRIM(COALESCE(`状态`, '')) <> '待入库'
         OR NULLIF(TRIM(COALESCE(`占用订单号`, '')), '') IS NOT NULL
         OR NULLIF(TRIM(COALESCE(`合同号`, '')), '') IS NOT NULL
         OR NULLIF(TRIM(COALESCE(`客户`, '')), '') IS NOT NULL
         OR NULLIF(TRIM(COALESCE(`代理商`, '')), '') IS NOT NULL
       );

    IF v_conflicts > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Abort: downstream finished_goods_data serials are not safe to shift.';
    END IF;

    INSERT IGNORE INTO patch_backup_0618_batches_20260703
    SELECT *
      FROM batches
     WHERE batch_code IN ('06-18', '06-19', '06-20');

    INSERT IGNORE INTO patch_backup_0618_finished_goods_data_20260703
    SELECT *
      FROM finished_goods_data
     WHERE TRIM(COALESCE(`批次号`, '')) = '06-18'
        OR `流水号` IN (SELECT serial_no FROM tmp_0618_target)
        OR (
             `流水号` REGEXP '^96-06-[0-9]+$'
         AND CAST(SUBSTRING(`流水号`, 7) AS UNSIGNED) >= v_shift_start
        );

    INSERT IGNORE INTO patch_backup_0618_units_20260703
    SELECT *
      FROM units
     WHERE batch_id COLLATE utf8mb4_general_ci = v_batch_id
        OR (
             forecast_serial_no REGEXP '^96-06-[0-9]+$'
         AND CAST(SUBSTRING(forecast_serial_no, 7) AS UNSIGNED) >= v_shift_start
        );

    INSERT IGNORE INTO patch_backup_0618_plan_import_20260703
    SELECT *
      FROM plan_import
     WHERE TRIM(COALESCE(`批次号`, '')) = '06-18'
        OR `流水号` IN (SELECT serial_no FROM tmp_0618_target)
        OR (
             `流水号` REGEXP '^96-06-[0-9]+$'
         AND CAST(SUBSTRING(`流水号`, 7) AS UNSIGNED) >= v_shift_start
        );

    INSERT IGNORE INTO patch_backup_0618_wechat_batch_summary_20260703
    SELECT *
      FROM wechat_batch_summary
     WHERE batch_no = '06-18'
        OR original_batch_no = '06-18'
        OR `批次号` = '06-18';

    START TRANSACTION;

    SELECT batch_id, capacity, production_line_id, status
      INTO v_batch_id, v_capacity, v_line_id, v_status
      FROM batches
     WHERE batch_code = '06-18'
     FOR UPDATE;

    UPDATE finished_goods_data
       SET `流水号` = CONCAT(v_serial_prefix, CAST(SUBSTRING(`流水号`, 7) AS UNSIGNED) + v_shift_size),
           `更新时间` = NOW()
     WHERE `流水号` REGEXP '^96-06-[0-9]+$'
       AND CAST(SUBSTRING(`流水号`, 7) AS UNSIGNED) >= v_shift_start
       AND TRIM(COALESCE(`批次号`, '')) <> '06-18';

    UPDATE plan_import
       SET `流水号` = CONCAT(v_serial_prefix, CAST(SUBSTRING(`流水号`, 7) AS UNSIGNED) + v_shift_size)
     WHERE `流水号` REGEXP '^96-06-[0-9]+$'
       AND CAST(SUBSTRING(`流水号`, 7) AS UNSIGNED) >= v_shift_start
       AND TRIM(COALESCE(`批次号`, '')) <> '06-18';

    UPDATE units
       SET forecast_serial_no = CONCAT(v_serial_prefix, CAST(SUBSTRING(forecast_serial_no, 7) AS UNSIGNED) + v_shift_size),
           updated_at = NOW()
     WHERE forecast_serial_no REGEXP '^96-06-[0-9]+$'
       AND CAST(SUBSTRING(forecast_serial_no, 7) AS UNSIGNED) >= v_shift_start
       AND batch_id COLLATE utf8mb4_general_ci <> v_batch_id;

    DELETE FROM finished_goods_data
     WHERE TRIM(COALESCE(`批次号`, '')) = '06-18'
        OR `流水号` IN (SELECT serial_no FROM tmp_0618_target);

    INSERT INTO finished_goods_data (
        `批次号`,
        `机型`,
        `流水号`,
        `状态`,
        `预计入库时间`,
        `更新时间`,
        `占用订单号`,
        `客户`,
        `代理商`,
        `合同备注`,
        `合同号`,
        `Location_Code`
    )
    SELECT
        '06-18',
        model_type,
        serial_no,
        '待入库',
        v_expected_inbound,
        NOW(),
        NULL,
        '',
        '',
        '',
        '',
        ''
      FROM tmp_0618_target
     ORDER BY slot_index;

    INSERT INTO units (
        unit_id,
        batch_id,
        slot_index,
        model_type,
        production_line_id,
        status,
        forecast_serial_no,
        serial_no,
        contract_no,
        customer,
        dealer_name,
        sales_id,
        order_remark,
        is_locked,
        is_contract_pinned
    )
    SELECT
        CONCAT(v_batch_id, '-U', LPAD(slot_index, 2, '0')),
        v_batch_id,
        slot_index,
        model_type,
        v_line_id,
        'In_Production',
        serial_no,
        NULL,
        NULL,
        '',
        '',
        NULL,
        '',
        0,
        0
      FROM tmp_0618_target
     ORDER BY slot_index
    ON DUPLICATE KEY UPDATE
        model_type = VALUES(model_type),
        production_line_id = VALUES(production_line_id),
        status = VALUES(status),
        forecast_serial_no = VALUES(forecast_serial_no),
        serial_no = NULL,
        contract_no = NULL,
        customer = '',
        dealer_name = '',
        sales_id = NULL,
        order_remark = '',
        is_locked = 0,
        is_contract_pinned = 0,
        updated_at = NOW();

    UPDATE batches
       SET capacity = 16,
           production_line_id = v_line_id,
           expected_inbound_date = DATE(v_expected_inbound),
           status = 'In_Production',
           updated_at = NOW()
     WHERE batch_id COLLATE utf8mb4_general_ci = v_batch_id;

    DELETE FROM wechat_batch_summary
     WHERE batch_no = '06-18'
        OR original_batch_no = '06-18'
        OR `批次号` = '06-18';

    INSERT INTO wechat_batch_summary (
        summary_id,
        batch_no,
        expected_inbound_time,
        model,
        quantity,
        heightened,
        original_batch_no,
        original_expected_inbound_time,
        `批次号`,
        `预计入库时间`,
        `机型`,
        `数量`
    )
    SELECT
        MD5(CONCAT(
            summary_rows.batch_no,
            '|',
            COALESCE(DATE_FORMAT(summary_rows.expected_inbound_time, '%Y-%m-%d %H:%i:%s'), ''),
            '|',
            summary_rows.model,
            '|',
            summary_rows.heightened,
            '|',
            COALESCE(summary_rows.original_batch_no, '')
        )),
        summary_rows.batch_no,
        summary_rows.expected_inbound_time,
        summary_rows.model,
        summary_rows.quantity,
        summary_rows.heightened,
        summary_rows.original_batch_no,
        summary_rows.original_expected_inbound_time,
        summary_rows.batch_no,
        summary_rows.expected_inbound_time,
        summary_rows.model,
        summary_rows.quantity
      FROM (
        SELECT
            CASE WHEN raw_rows.is_heightened = 1 THEN '加高' ELSE raw_rows.source_batch_no END AS batch_no,
            raw_rows.source_expected_inbound_time AS expected_inbound_time,
            raw_rows.base_model AS model,
            COUNT(*) AS quantity,
            raw_rows.is_heightened AS heightened,
            CASE WHEN raw_rows.is_heightened = 1 THEN raw_rows.source_batch_no ELSE '' END AS original_batch_no,
            CASE WHEN raw_rows.is_heightened = 1 THEN raw_rows.source_expected_inbound_time ELSE NULL END AS original_expected_inbound_time
          FROM (
            SELECT
                TRIM(`批次号`) AS source_batch_no,
                `预计入库时间` AS source_expected_inbound_time,
                TRIM(REPLACE(REPLACE(TRIM(`机型`), '(加高)', ''), '加高', '')) AS base_model,
                CASE
                    WHEN TRIM(COALESCE(`机型`, '')) LIKE '%加高%'
                      OR TRIM(COALESCE(`批次号`, '')) LIKE '%加高%'
                      OR TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'
                    THEN 1
                    ELSE 0
                END AS is_heightened
              FROM finished_goods_data
             WHERE TRIM(COALESCE(`批次号`, '')) = '06-18'
               AND NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
               AND TRIM(COALESCE(`状态`, '')) = '待入库'
          ) raw_rows
         WHERE NULLIF(raw_rows.base_model, '') IS NOT NULL
         GROUP BY
            raw_rows.source_batch_no,
            raw_rows.source_expected_inbound_time,
            raw_rows.base_model,
            raw_rows.is_heightened
      ) summary_rows
    ON DUPLICATE KEY UPDATE
        quantity = VALUES(quantity),
        heightened = VALUES(heightened),
        original_batch_no = VALUES(original_batch_no),
        original_expected_inbound_time = VALUES(original_expected_inbound_time),
        `批次号` = VALUES(`批次号`),
        `预计入库时间` = VALUES(`预计入库时间`),
        `机型` = VALUES(`机型`),
        `数量` = VALUES(`数量`),
        updated_at = NOW();

    INSERT INTO cloud_sync_outbox (
        event_id,
        event_type,
        biz_key,
        payload_json,
        status,
        retry_count,
        next_retry_at
    )
    VALUES (
        CONCAT('manual-0618-serial-cascade-', REPLACE(UUID(), '-', '')),
        'wechat_batch_summary_sync',
        'wechat_batch_summary',
        JSON_OBJECT('reason', 'manual_06_18_serial_cascade', 'batch_code', '06-18'),
        'pending',
        0,
        NULL
    );

    COMMIT;

    SELECT
        'finished_goods_data_06_18' AS check_name,
        COUNT(*) AS row_count,
        MIN(`流水号`) AS min_serial,
        MAX(`流水号`) AS max_serial
      FROM finished_goods_data
     WHERE TRIM(COALESCE(`批次号`, '')) = '06-18';

    SELECT
        `流水号`,
        `机型`,
        `状态`,
        `预计入库时间`
      FROM finished_goods_data
     WHERE TRIM(COALESCE(`批次号`, '')) = '06-18'
     ORDER BY `流水号`;

    SELECT
        'units_06_18' AS check_name,
        COUNT(*) AS row_count,
        MIN(forecast_serial_no) AS min_serial,
        MAX(forecast_serial_no) AS max_serial
      FROM units
     WHERE batch_id COLLATE utf8mb4_general_ci = v_batch_id;

    SELECT
        b.batch_code,
        COUNT(u.unit_id) AS unit_count,
        MIN(u.forecast_serial_no) AS min_forecast_serial,
        MAX(u.forecast_serial_no) AS max_forecast_serial
      FROM batches b
      JOIN units u ON u.batch_id = b.batch_id
     WHERE b.batch_code IN ('06-18', '06-19', '06-20')
     GROUP BY b.batch_code
     ORDER BY b.batch_code;

    SELECT
        'units_plan_import_serial_alignment' AS check_name,
        unit_rows.batch_code,
        unit_rows.unit_count,
        unit_rows.min_forecast_serial,
        unit_rows.max_forecast_serial,
        COALESCE(plan_rows.plan_import_count, 0) AS plan_import_count,
        plan_rows.min_plan_import_serial,
        plan_rows.max_plan_import_serial
      FROM (
        SELECT
            b.batch_code,
            COUNT(u.unit_id) AS unit_count,
            MIN(u.forecast_serial_no) AS min_forecast_serial,
            MAX(u.forecast_serial_no) AS max_forecast_serial
          FROM batches b
          JOIN units u ON u.batch_id = b.batch_id
         WHERE b.batch_code IN ('06-19', '06-20')
         GROUP BY b.batch_code
      ) unit_rows
      LEFT JOIN (
        SELECT
            TRIM(`批次号`) AS batch_code,
            COUNT(*) AS plan_import_count,
            MIN(`流水号`) AS min_plan_import_serial,
            MAX(`流水号`) AS max_plan_import_serial
          FROM plan_import
         WHERE TRIM(COALESCE(`批次号`, '')) IN ('06-19', '06-20')
           AND `流水号` REGEXP '^96-06-[0-9]+$'
         GROUP BY TRIM(`批次号`)
      ) plan_rows ON plan_rows.batch_code = unit_rows.batch_code
     ORDER BY unit_rows.batch_code;

    SELECT
        `批次号`,
        `流水号`,
        `机型`
      FROM plan_import
     WHERE TRIM(COALESCE(`批次号`, '')) IN ('06-19', '06-20')
       AND `流水号` REGEXP '^96-06-[0-9]+$'
     ORDER BY CAST(SUBSTRING(`流水号`, 7) AS UNSIGNED)
     LIMIT 12;

    SELECT
        batch_no,
        model,
        quantity,
        heightened,
        original_batch_no
      FROM wechat_batch_summary
     WHERE batch_no = '06-18'
        OR original_batch_no = '06-18'
        OR `批次号` = '06-18'
     ORDER BY batch_no, model;
END$$

DELIMITER ;

CALL patch_06_18_add_highlighted_machines();

DROP PROCEDURE IF EXISTS patch_06_18_add_highlighted_machines;
