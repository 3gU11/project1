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

CALL `add_wechat_batch_summary_column_if_missing`('heightened', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `heightened` TINYINT(1) NOT NULL DEFAULT 0 AFTER `quantity`');
CALL `add_wechat_batch_summary_column_if_missing`('original_batch_no', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `original_batch_no` VARCHAR(100) DEFAULT '''' AFTER `heightened`');
CALL `add_wechat_batch_summary_column_if_missing`('original_expected_inbound_time', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `original_expected_inbound_time` DATETIME NULL AFTER `original_batch_no`');
CALL `add_wechat_batch_summary_column_if_missing`('updated_at', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `original_expected_inbound_time`');

CALL `refresh_wechat_batch_summary_all`();

DROP PROCEDURE IF EXISTS `add_wechat_batch_summary_column_if_missing`;
