-- MySQL 8; exported from repair_order_inventory_sync.py.
-- Select the intended database in your client before running.
-- Stop application writes and take a full database backup before APPLY.
-- Default: preview only. Run the whole file in ONE connection.
-- To apply: set @apply=1 and replace both expected counts with preview counts.
-- This does NOT clean all historical bindings (including all 09-08 cards).
-- Excess-contract cleanup is NOT included.
-- Backup tables are intentionally retained. Use a fresh suffix for each run.
SET NAMES utf8mb4;
SET @apply = 0;
SET @expected_unlogged = -1;
SET @expected_mirror = -1;
SET @run_id = DATE_FORMAT(NOW(), '%Y%m%d_%H%i%s');
DROP TEMPORARY TABLE IF EXISTS repair_unlogged;
DROP TEMPORARY TABLE IF EXISTS repair_mirror;
CREATE TEMPORARY TABLE repair_unlogged AS
SELECT
  u.unit_id,
  COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) AS serial_no,
  COALESCE(u.sales_id, '') AS order_no,
  COALESCE(u.contract_no, '') AS contract_no,
  COALESCE(fg.`状态`, '') AS inventory_status,
  COALESCE(fg.`Location_Code`, '') AS location_code
FROM finished_goods_data fg
JOIN units u
  ON TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no)) = TRIM(fg.`流水号`)
WHERE TRIM(COALESCE(fg.`状态`, '')) = '待发货'
  AND TRIM(COALESCE(fg.`占用订单号`, '')) = ''
  AND TRIM(COALESCE(u.sales_id, '')) <> ''
  AND NOT EXISTS (
    SELECT 1 FROM transaction_log tl
    WHERE TRIM(tl.`流水号`) = TRIM(fg.`流水号`)
      AND tl.`操作类型` IN (
        CONCAT('配货锁定-', TRIM(u.sales_id)),
        CONCAT('配货锁定-', TRIM(u.sales_id), '-库存现货'),
        CONCAT('配货锁定-', TRIM(u.sales_id), '-在产预占')
      )
  )
  AND NOT EXISTS (
    SELECT 1 FROM sys_operation_log sol
    WHERE TRIM(COALESCE(sol.serial_no, '')) = TRIM(fg.`流水号`)
      AND TRIM(COALESCE(sol.order_no, '')) = TRIM(u.sales_id)
      AND sol.module = '订单配货'
      AND sol.action_type = '配货'
  )
ORDER BY serial_no;
CREATE TEMPORARY TABLE repair_mirror AS
SELECT
  u.unit_id,
  COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) AS serial_no,
  COALESCE(u.contract_no, '') AS contract_no,
  COALESCE(u.customer, '') AS customer,
  COALESCE(u.dealer_name, '') AS dealer,
  COALESCE(u.order_remark, '') AS remark,
  COALESCE(u.sales_id, '') AS order_no
FROM units u
JOIN batches b ON b.batch_id = u.batch_id
JOIN finished_goods_data fg
  ON TRIM(fg.`流水号`) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
WHERE b.status IN ('Confirmed', 'In_Production')
  AND TRIM(COALESCE(u.contract_no, '')) <> ''
  AND (
    TRIM(COALESCE(u.contract_no, '')) <> TRIM(COALESCE(fg.`合同号`, ''))
    OR TRIM(COALESCE(u.sales_id, '')) <> TRIM(COALESCE(fg.`占用订单号`, ''))
  )
  AND TRIM(COALESCE(fg.`状态`, '')) NOT LIKE '库存中%'
  AND TRIM(COALESCE(fg.`状态`, '')) NOT IN ('待发货', '已出库', '已发货', '报废')
ORDER BY serial_no;

SELECT DATABASE() AS target_database, @run_id AS run_id;
SELECT COUNT(*) AS unlogged_binding_count FROM repair_unlogged;
SELECT COUNT(*) AS mirror_mismatch_count FROM repair_mirror;
SELECT * FROM repair_unlogged;
SELECT * FROM repair_mirror;
-- A procedure provides explicit errors and rollback on verification failure.
-- Use a client supporting DELIMITER (mysql CLI / Workbench script runner).
DELIMITER $$
CREATE PROCEDURE v8_exported_repair_apply()
main: BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
  IF COALESCE(@apply,0) <> 1 THEN LEAVE main; END IF;
  IF @expected_unlogged <> (SELECT COUNT(*) FROM repair_unlogged)
     OR @expected_mirror <> (SELECT COUNT(*) FROM repair_mirror)
     OR @expected_unlogged IS NULL OR @expected_mirror IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Candidate counts not confirmed';
  END IF;
  SET @stmt = CONCAT('CREATE TABLE repair_sql_', @run_id, '_units AS SELECT u.* FROM units u JOIN repair_unlogged c ON c.unit_id=u.unit_id');
  PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;
  SET @stmt = CONCAT('CREATE TABLE repair_sql_', @run_id, '_fg AS SELECT f.* FROM finished_goods_data f WHERE EXISTS (SELECT 1 FROM repair_unlogged c WHERE c.serial_no=f.`流水号`)');
  PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;
  SET @stmt = CONCAT('CREATE TABLE repair_sql_', @run_id, '_mirror AS SELECT f.* FROM finished_goods_data f WHERE EXISTS (SELECT 1 FROM repair_mirror c WHERE c.serial_no=f.`流水号`)');
  PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;

  START TRANSACTION;
  UPDATE units u JOIN repair_unlogged c ON c.unit_id=u.unit_id
  SET u.contract_no=NULL,u.customer=NULL,u.dealer_id=NULL,u.dealer_name=NULL,
      u.due_date=NULL,u.sales_id=NULL,u.order_remark=NULL,u.is_contract_pinned=0,
      u.is_locked=0,u.locked_by=NULL,u.locked_at=NULL,u.updated_at=NOW();
  UPDATE finished_goods_data f JOIN repair_unlogged c ON c.serial_no=f.`流水号`
  SET f.`状态`=CASE WHEN TRIM(COALESCE(f.Location_Code,''))<>''
      THEN CONCAT('库存中（',TRIM(f.Location_Code),'）') ELSE '待入库' END,
      f.`占用订单号`=NULL,f.`客户`='',f.`代理商`='',f.`合同号`='',
      f.`合同备注`='',f.`更新时间`=NOW();
  UPDATE finished_goods_data f JOIN repair_mirror c ON c.serial_no=f.`流水号`
  SET f.`合同号`=c.contract_no,f.`客户`=c.customer,f.`代理商`=c.dealer,
      f.`合同备注`=c.remark,f.`占用订单号`=c.order_no,f.`更新时间`=NOW();
  INSERT INTO sys_operation_log
    (user_id,username,operate_time,module,action_type,biz_type,content,serial_no,order_no,contract_no)
  SELECT 'SystemRepair','SystemRepair',NOW(),'订单配货','数据纠错','机台',
    CONCAT('SQL清理历史自动误绑；备份运行编号：',@run_id),serial_no,order_no,contract_no FROM repair_unlogged;
  INSERT INTO sys_operation_log
    (user_id,username,operate_time,module,action_type,biz_type,content,serial_no,order_no,contract_no)
  SELECT 'SystemRepair','SystemRepair',NOW(),'库存同步','数据纠错','机台',
    CONCAT('SQL补齐库存镜像；备份运行编号：',@run_id),serial_no,order_no,contract_no FROM repair_mirror;
  IF EXISTS (SELECT 1 FROM (
SELECT
  u.unit_id,
  COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) AS serial_no,
  COALESCE(u.sales_id, '') AS order_no,
  COALESCE(u.contract_no, '') AS contract_no,
  COALESCE(fg.`状态`, '') AS inventory_status,
  COALESCE(fg.`Location_Code`, '') AS location_code
FROM finished_goods_data fg
JOIN units u
  ON TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no)) = TRIM(fg.`流水号`)
WHERE TRIM(COALESCE(fg.`状态`, '')) = '待发货'
  AND TRIM(COALESCE(fg.`占用订单号`, '')) = ''
  AND TRIM(COALESCE(u.sales_id, '')) <> ''
  AND NOT EXISTS (
    SELECT 1 FROM transaction_log tl
    WHERE TRIM(tl.`流水号`) = TRIM(fg.`流水号`)
      AND tl.`操作类型` IN (
        CONCAT('配货锁定-', TRIM(u.sales_id)),
        CONCAT('配货锁定-', TRIM(u.sales_id), '-库存现货'),
        CONCAT('配货锁定-', TRIM(u.sales_id), '-在产预占')
      )
  )
  AND NOT EXISTS (
    SELECT 1 FROM sys_operation_log sol
    WHERE TRIM(COALESCE(sol.serial_no, '')) = TRIM(fg.`流水号`)
      AND TRIM(COALESCE(sol.order_no, '')) = TRIM(u.sales_id)
      AND sol.module = '订单配货'
      AND sol.action_type = '配货'
  )
ORDER BY serial_no
) remaining) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Post-repair verification failed';
  END IF;
  IF EXISTS (SELECT 1 FROM (
SELECT
  u.unit_id,
  COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no) AS serial_no,
  COALESCE(u.contract_no, '') AS contract_no,
  COALESCE(u.customer, '') AS customer,
  COALESCE(u.dealer_name, '') AS dealer,
  COALESCE(u.order_remark, '') AS remark,
  COALESCE(u.sales_id, '') AS order_no
FROM units u
JOIN batches b ON b.batch_id = u.batch_id
JOIN finished_goods_data fg
  ON TRIM(fg.`流水号`) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
WHERE b.status IN ('Confirmed', 'In_Production')
  AND TRIM(COALESCE(u.contract_no, '')) <> ''
  AND (
    TRIM(COALESCE(u.contract_no, '')) <> TRIM(COALESCE(fg.`合同号`, ''))
    OR TRIM(COALESCE(u.sales_id, '')) <> TRIM(COALESCE(fg.`占用订单号`, ''))
  )
  AND TRIM(COALESCE(fg.`状态`, '')) NOT LIKE '库存中%'
  AND TRIM(COALESCE(fg.`状态`, '')) NOT IN ('待发货', '已出库', '已发货', '报废')
ORDER BY serial_no
) remaining) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Post-repair verification failed';
  END IF;
  COMMIT;
  SELECT @run_id AS applied_run_id;
END$$
DELIMITER ;
CALL v8_exported_repair_apply();
DROP PROCEDURE v8_exported_repair_apply;
-- Informational only: historical inbound records vs current completion.
SELECT
  b.batch_code,
  b.status,
  COUNT(*) AS total_units,
  SUM(EXISTS(
    SELECT 1 FROM inbound_history ih
    WHERE TRIM(ih.serial_no) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
  )) AS historical_inbound_units,
  SUM(
    EXISTS(
      SELECT 1 FROM inbound_history ih
      WHERE TRIM(ih.serial_no) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
    )
    AND TRIM(COALESCE(fg.`状态`, '')) NOT IN ('', '待入库', '已绑定')
  ) AS currently_completed_units
FROM units u
JOIN batches b ON b.batch_id = u.batch_id
LEFT JOIN finished_goods_data fg
  ON TRIM(fg.`流水号`) = TRIM(COALESCE(NULLIF(u.serial_no, ''), u.forecast_serial_no))
WHERE b.status = 'In_Production'
GROUP BY b.batch_id, b.batch_code, b.status
HAVING historical_inbound_units > currently_completed_units
ORDER BY b.batch_code;
