-- Patch: add the highlighted machines to batch 06-18 only.
-- Database: rjfinshed
--
-- This version intentionally does NOT shift downstream pending batches.
-- After running it, re-audit pending batches so units.forecast_serial_no and
-- plan_import.流水号 can be recalculated by the normal planning flow.

USE rjfinshed;
SET NAMES utf8mb4 COLLATE utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS patch_backup_0618_only_finished_goods_data_20260703 LIKE finished_goods_data;
CREATE TABLE IF NOT EXISTS patch_backup_0618_only_units_20260703 LIKE units;
CREATE TABLE IF NOT EXISTS patch_backup_0618_only_plan_import_20260703 LIKE plan_import;
CREATE TABLE IF NOT EXISTS patch_backup_0618_only_wechat_batch_summary_20260703 LIKE wechat_batch_summary;
CREATE TABLE IF NOT EXISTS patch_backup_0618_only_batches_20260703 LIKE batches;

DROP PROCEDURE IF EXISTS patch_06_18_only_add_highlighted_machines;

DELIMITER $$

CREATE PROCEDURE patch_06_18_only_add_highlighted_machines()
BEGIN
    DECLARE v_batch_count INT DEFAULT 0;
    DECLARE v_batch_id VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
    DECLARE v_capacity INT DEFAULT 0;
    DECLARE v_line_id VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
    DECLARE v_status VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
    DECLARE v_conflicts INT DEFAULT 0;
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
     WHERE batch_code COLLATE utf8mb4_general_ci = '06-18';

    IF v_batch_count <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Abort: batch_code 06-18 must match exactly one row in batches.';
    END IF;

    SELECT batch_id COLLATE utf8mb4_general_ci, capacity, production_line_id COLLATE utf8mb4_general_ci, status COLLATE utf8mb4_general_ci
      INTO v_batch_id, v_capacity, v_line_id, v_status
      FROM batches
     WHERE batch_code COLLATE utf8mb4_general_ci = '06-18';

    SELECT COUNT(*)
      INTO v_conflicts
      FROM finished_goods_data fg
      JOIN tmp_0618_target t
        ON fg.`流水号` COLLATE utf8mb4_general_ci = t.serial_no
     WHERE TRIM(COALESCE(fg.`批次号`, '')) COLLATE utf8mb4_general_ci = '06-18';

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
     WHERE TRIM(COALESCE(`批次号`, '')) COLLATE utf8mb4_general_ci = '06-18'
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
      FROM finished_goods_data fg
      JOIN tmp_0618_target t
        ON fg.`流水号` COLLATE utf8mb4_general_ci = t.serial_no
     WHERE TRIM(COALESCE(fg.`批次号`, '')) COLLATE utf8mb4_general_ci <> '06-18';

    IF v_conflicts > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Abort: target serial already exists in another finished_goods_data batch.';
    END IF;

    INSERT IGNORE INTO patch_backup_0618_only_batches_20260703
    SELECT *
      FROM batches
     WHERE batch_code COLLATE utf8mb4_general_ci IN ('06-18', '06-19', '06-20');

    INSERT IGNORE INTO patch_backup_0618_only_finished_goods_data_20260703
    SELECT *
      FROM finished_goods_data
     WHERE TRIM(COALESCE(`批次号`, '')) COLLATE utf8mb4_general_ci = '06-18';

    INSERT IGNORE INTO patch_backup_0618_only_units_20260703
    SELECT *
      FROM units
     WHERE batch_id COLLATE utf8mb4_general_ci = v_batch_id;

    INSERT IGNORE INTO patch_backup_0618_only_plan_import_20260703
    SELECT pi.*
      FROM plan_import pi
      JOIN tmp_0618_target t
        ON pi.`流水号` COLLATE utf8mb4_general_ci = t.serial_no;

    INSERT IGNORE INTO patch_backup_0618_only_wechat_batch_summary_20260703
    SELECT *
      FROM wechat_batch_summary
     WHERE batch_no COLLATE utf8mb4_general_ci = '06-18'
        OR original_batch_no COLLATE utf8mb4_general_ci = '06-18'
        OR `批次号` COLLATE utf8mb4_general_ci = '06-18';

    START TRANSACTION;

    SELECT batch_id COLLATE utf8mb4_general_ci, capacity, production_line_id COLLATE utf8mb4_general_ci, status COLLATE utf8mb4_general_ci
      INTO v_batch_id, v_capacity, v_line_id, v_status
      FROM batches
     WHERE batch_code COLLATE utf8mb4_general_ci = '06-18'
     FOR UPDATE;

    DELETE FROM finished_goods_data
     WHERE TRIM(COALESCE(`批次号`, '')) COLLATE utf8mb4_general_ci = '06-18';

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
     WHERE batch_no COLLATE utf8mb4_general_ci = '06-18'
        OR original_batch_no COLLATE utf8mb4_general_ci = '06-18'
        OR `批次号` COLLATE utf8mb4_general_ci = '06-18';

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
             WHERE TRIM(COALESCE(`批次号`, '')) COLLATE utf8mb4_general_ci = '06-18'
               AND NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
               AND TRIM(COALESCE(`状态`, '')) COLLATE utf8mb4_general_ci = '待入库'
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
        CONCAT('manual-0618-only-pending-reaudit-', REPLACE(UUID(), '-', '')),
        'wechat_batch_summary_sync',
        'wechat_batch_summary',
        JSON_OBJECT('reason', 'manual_06_18_only_pending_reaudit', 'batch_code', '06-18'),
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
     WHERE TRIM(COALESCE(`批次号`, '')) COLLATE utf8mb4_general_ci = '06-18';

    SELECT
        `流水号`,
        `机型`,
        `状态`,
        `预计入库时间`
      FROM finished_goods_data
     WHERE TRIM(COALESCE(`批次号`, '')) COLLATE utf8mb4_general_ci = '06-18'
     ORDER BY CAST(SUBSTRING(`流水号`, 7) AS UNSIGNED);

    SELECT
        'units_06_18' AS check_name,
        COUNT(*) AS row_count,
        MIN(forecast_serial_no) AS min_serial,
        MAX(forecast_serial_no) AS max_serial
      FROM units
     WHERE batch_id COLLATE utf8mb4_general_ci = v_batch_id;

    SELECT
        'pending_units_need_reaudit' AS check_name,
        b.batch_code,
        u.slot_index,
        u.model_type,
        u.forecast_serial_no
      FROM units u
      JOIN batches b
        ON u.batch_id COLLATE utf8mb4_general_ci = b.batch_id COLLATE utf8mb4_general_ci
      JOIN tmp_0618_target t
        ON u.forecast_serial_no COLLATE utf8mb4_general_ci = t.serial_no
     WHERE u.batch_id COLLATE utf8mb4_general_ci <> v_batch_id
     ORDER BY b.batch_code, u.slot_index;

    SELECT
        'pending_plan_import_need_reaudit' AS check_name,
        pi.`批次号`,
        pi.`流水号`,
        pi.`机型`
      FROM plan_import pi
      JOIN tmp_0618_target t
        ON pi.`流水号` COLLATE utf8mb4_general_ci = t.serial_no
     WHERE TRIM(COALESCE(pi.`批次号`, '')) COLLATE utf8mb4_general_ci <> '06-18'
     ORDER BY pi.`批次号`, CAST(SUBSTRING(pi.`流水号`, 7) AS UNSIGNED);
END$$

DELIMITER ;

CALL patch_06_18_only_add_highlighted_machines();

DROP PROCEDURE IF EXISTS patch_06_18_only_add_highlighted_machines;
