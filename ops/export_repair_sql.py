"""Export the existing repair predicates as a reviewable MySQL 8 script."""
from pathlib import Path
import repair_order_inventory_sync as source

header = """-- MySQL 8; exported from repair_order_inventory_sync.py.
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
"""
sql = header
for name, query in [('repair_unlogged', source.UNLOGGED_BINDINGS_SQL), ('repair_mirror', source.MIRROR_MISMATCH_SQL)]:
    sql += f'CREATE TEMPORARY TABLE {name} AS\n{query.strip()};\n'
sql += """
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
"""
for suffix, query in [
    ('units', 'SELECT u.* FROM units u JOIN repair_unlogged c ON c.unit_id=u.unit_id'),
    ('fg', 'SELECT f.* FROM finished_goods_data f WHERE EXISTS (SELECT 1 FROM repair_unlogged c WHERE c.serial_no=f.`流水号`)'),
    ('mirror', 'SELECT f.* FROM finished_goods_data f WHERE EXISTS (SELECT 1 FROM repair_mirror c WHERE c.serial_no=f.`流水号`)'),
]:
    sql += f"  SET @stmt = CONCAT('CREATE TABLE repair_sql_', @run_id, '_{suffix} AS {query}');\n  PREPARE s FROM @stmt; EXECUTE s; DEALLOCATE PREPARE s;\n"
sql += """
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
"""
for query in [source.UNLOGGED_BINDINGS_SQL, source.MIRROR_MISMATCH_SQL]:
    sql += '  IF EXISTS (SELECT 1 FROM (\n' + query.strip() + "\n) remaining) THEN\n    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Post-repair verification failed';\n  END IF;\n"
sql += """  COMMIT;
  SELECT @run_id AS applied_run_id;
END$$
DELIMITER ;
CALL v8_exported_repair_apply();
DROP PROCEDURE v8_exported_repair_apply;
-- Informational only: historical inbound records vs current completion.
""" + source.COMPLETION_RISK_SQL.strip() + ';\n'
Path(__file__).with_name('repair_order_inventory_sync.sql').write_text(sql, encoding='utf-8')
