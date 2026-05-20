SET NAMES utf8mb4 COLLATE utf8mb4_general_ci;

ALTER TABLE `wechat_batch_summary`
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

DELIMITER $$

DROP PROCEDURE IF EXISTS `add_wechat_batch_summary_column_if_missing`$$
CREATE PROCEDURE `add_wechat_batch_summary_column_if_missing`(
  IN p_column_name VARCHAR(100),
  IN p_alter_sql TEXT
)
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'wechat_batch_summary'
      AND COLUMN_NAME = p_column_name
  ) THEN
    SET @sql = p_alter_sql;
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
  END IF;
END$$

DELIMITER ;

CALL `add_wechat_batch_summary_column_if_missing`('批次号', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `批次号` VARCHAR(100) NOT NULL DEFAULT '''' AFTER `updated_at`');
CALL `add_wechat_batch_summary_column_if_missing`('预计入库时间', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `预计入库时间` DATETIME NULL AFTER `批次号`');
CALL `add_wechat_batch_summary_column_if_missing`('机型', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `机型` VARCHAR(100) NOT NULL DEFAULT '''' AFTER `预计入库时间`');
CALL `add_wechat_batch_summary_column_if_missing`('数量', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `数量` INT NOT NULL DEFAULT 0 AFTER `机型`');
CALL `add_wechat_batch_summary_column_if_missing`('更新时间', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `更新时间` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `数量`');

CALL `refresh_wechat_batch_summary_all`();

DROP PROCEDURE IF EXISTS `add_wechat_batch_summary_column_if_missing`;
