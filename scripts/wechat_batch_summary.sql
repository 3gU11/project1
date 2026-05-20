-- WeChat mini-program read model for C:\RJ_Wechat_App.
-- Pure-English target schema. Source data still comes from finished_goods_data
-- whose operational columns are Chinese.

SET NAMES utf8mb4 COLLATE utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `wechat_batch_summary` (
  `summary_id` CHAR(32) NOT NULL,
  `batch_no` VARCHAR(100) NOT NULL,
  `expected_inbound_time` DATETIME NULL,
  `model` VARCHAR(100) NOT NULL,
  `quantity` INT NOT NULL DEFAULT 0,
  `heightened` TINYINT(1) NOT NULL DEFAULT 0,
  `original_batch_no` VARCHAR(100) DEFAULT '',
  `original_expected_inbound_time` DATETIME NULL,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`summary_id`),
  INDEX `idx_wechat_batch_summary_batch` (`batch_no`),
  INDEX `idx_wechat_batch_summary_inbound` (`expected_inbound_time`),
  INDEX `idx_wechat_batch_summary_model` (`model`),
  INDEX `idx_wechat_batch_summary_heightened` (`heightened`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

ALTER TABLE `wechat_batch_summary`
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

DROP TRIGGER IF EXISTS `trg_fg_wechat_summary_ai`;
DROP TRIGGER IF EXISTS `trg_fg_wechat_summary_au`;
DROP TRIGGER IF EXISTS `trg_fg_wechat_summary_ad`;
DROP PROCEDURE IF EXISTS `refresh_wechat_batch_summary_group`;
DROP PROCEDURE IF EXISTS `refresh_wechat_batch_summary_all`;
DROP PROCEDURE IF EXISTS `add_wechat_batch_summary_column_if_missing`;

DELIMITER $$

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

CREATE PROCEDURE `refresh_wechat_batch_summary_group`(
  IN p_batch_no VARCHAR(100),
  IN p_expected DATETIME,
  IN p_model VARCHAR(100)
)
BEGIN
  DECLARE v_batch_no VARCHAR(100);
  DECLARE v_model VARCHAR(100);
  DECLARE v_model_base VARCHAR(100);

  SET v_batch_no = NULLIF(TRIM(COALESCE(p_batch_no, '')), '');
  SET v_model = NULLIF(TRIM(COALESCE(p_model, '')), '');
  SET v_model_base = NULLIF(TRIM(REPLACE(REPLACE(COALESCE(v_model, ''), '(加高)', ''), '加高', '')), '');

  DELETE FROM `wechat_batch_summary`
  WHERE (
      `original_batch_no` = COALESCE(v_batch_no, '')
      AND `original_expected_inbound_time` <=> p_expected
      AND `model` = v_model_base
    )
    OR (
      `batch_no` = COALESCE(v_batch_no, '')
      AND `expected_inbound_time` <=> p_expected
      AND `model` = v_model_base
      AND `heightened` = 0
    )
    OR (
      `batch_no` = '库存中'
      AND `expected_inbound_time` IS NULL
      AND `model` = v_model_base
      AND (
        `original_batch_no` = COALESCE(v_batch_no, '')
        OR COALESCE(`original_batch_no`, '') = ''
      )
    );

  IF v_batch_no IS NOT NULL AND v_model_base IS NOT NULL THEN
    INSERT INTO `wechat_batch_summary` (
      `summary_id`,
      `batch_no`,
      `expected_inbound_time`,
      `model`,
      `quantity`,
      `heightened`,
      `original_batch_no`,
      `original_expected_inbound_time`
    )
    SELECT
      MD5(CONCAT(
        s.`batch_no`,
        '|',
        COALESCE(DATE_FORMAT(s.`expected_inbound_time`, '%Y-%m-%d %H:%i:%s'), ''),
        '|',
        s.`model`,
        '|',
        s.`heightened`,
        '|',
        COALESCE(s.`original_batch_no`, '')
      )) AS `summary_id`,
      s.`batch_no`,
      s.`expected_inbound_time`,
      s.`model`,
      s.`quantity`,
      s.`heightened`,
      s.`original_batch_no`,
      s.`original_expected_inbound_time`
    FROM (
      SELECT
        IF(raw.`is_high`, '加高', raw.`source_batch_no`) AS `batch_no`,
        raw.`source_expected_inbound_time` AS `expected_inbound_time`,
        raw.`base_model` AS `model`,
        COUNT(*) AS `quantity`,
        IF(raw.`is_high`, 1, 0) AS `heightened`,
        IF(raw.`is_high`, raw.`source_batch_no`, '') AS `original_batch_no`,
        IF(raw.`is_high`, raw.`source_expected_inbound_time`, NULL) AS `original_expected_inbound_time`
      FROM (
        SELECT
          TRIM(`批次号`) AS `source_batch_no`,
          `预计入库时间` AS `source_expected_inbound_time`,
          TRIM(REPLACE(REPLACE(TRIM(`机型`), '(加高)', ''), '加高', '')) AS `base_model`,
          (
            TRIM(COALESCE(`机型`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`批次号`, '')) LIKE '%附加%'
            OR TRIM(COALESCE(`批次号`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`订单备注`, '')) LIKE '%加高%'
          ) AS `is_high`
        FROM `finished_goods_data`
        WHERE NULLIF(TRIM(COALESCE(`批次号`, '')), '') = v_batch_no
          AND `预计入库时间` <=> p_expected
          AND TRIM(REPLACE(REPLACE(TRIM(COALESCE(`机型`, '')), '(加高)', ''), '加高', '')) = v_model_base
          AND TRIM(COALESCE(`状态`, '')) = '待入库'
      ) raw
      WHERE NULLIF(raw.`base_model`, '') IS NOT NULL
      GROUP BY raw.`source_batch_no`, raw.`source_expected_inbound_time`, raw.`base_model`, raw.`is_high`
    ) s
    ON DUPLICATE KEY UPDATE
      `batch_no` = VALUES(`batch_no`),
      `expected_inbound_time` = VALUES(`expected_inbound_time`),
      `model` = VALUES(`model`),
      `quantity` = VALUES(`quantity`),
      `heightened` = VALUES(`heightened`),
      `original_batch_no` = VALUES(`original_batch_no`),
      `original_expected_inbound_time` = VALUES(`original_expected_inbound_time`);
  END IF;

  IF v_model_base IS NOT NULL THEN
    INSERT INTO `wechat_batch_summary` (
      `summary_id`,
      `batch_no`,
      `expected_inbound_time`,
      `model`,
      `quantity`,
      `heightened`,
      `original_batch_no`,
      `original_expected_inbound_time`
    )
    SELECT
      MD5(CONCAT(
        s.`batch_no`,
        '|',
        COALESCE(DATE_FORMAT(s.`expected_inbound_time`, '%Y-%m-%d %H:%i:%s'), ''),
        '|',
        s.`model`,
        '|',
        s.`heightened`,
        '|',
        COALESCE(s.`original_batch_no`, '')
      )) AS `summary_id`,
      s.`batch_no`,
      s.`expected_inbound_time`,
      s.`model`,
      s.`quantity`,
      s.`heightened`,
      s.`original_batch_no`,
      s.`original_expected_inbound_time`
    FROM (
      SELECT
        IF(raw.`is_high`, '加高', '库存中') AS `batch_no`,
        CAST(NULL AS DATETIME) AS `expected_inbound_time`,
        raw.`base_model` AS `model`,
        COUNT(*) AS `quantity`,
        IF(raw.`is_high`, 1, 0) AS `heightened`,
        IF(raw.`is_high`, COALESCE(NULLIF(raw.`source_batch_no`, ''), '库存中'), '') AS `original_batch_no`,
        CAST(NULL AS DATETIME) AS `original_expected_inbound_time`
      FROM (
        SELECT
          TRIM(COALESCE(`批次号`, '')) AS `source_batch_no`,
          TRIM(REPLACE(REPLACE(TRIM(`机型`), '(加高)', ''), '加高', '')) AS `base_model`,
          (
            TRIM(COALESCE(`机型`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`批次号`, '')) LIKE '%附加%'
            OR TRIM(COALESCE(`批次号`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'
            OR TRIM(COALESCE(`订单备注`, '')) LIKE '%加高%'
          ) AS `is_high`
        FROM `finished_goods_data`
        WHERE TRIM(REPLACE(REPLACE(TRIM(COALESCE(`机型`, '')), '(加高)', ''), '加高', '')) = v_model_base
          AND TRIM(COALESCE(`状态`, '')) = '库存中'
      ) raw
      WHERE NULLIF(raw.`base_model`, '') IS NOT NULL
      GROUP BY raw.`base_model`, raw.`is_high`, IF(raw.`is_high`, COALESCE(NULLIF(raw.`source_batch_no`, ''), '库存中'), '')
    ) s
    ON DUPLICATE KEY UPDATE
      `batch_no` = VALUES(`batch_no`),
      `expected_inbound_time` = VALUES(`expected_inbound_time`),
      `model` = VALUES(`model`),
      `quantity` = VALUES(`quantity`),
      `heightened` = VALUES(`heightened`),
      `original_batch_no` = VALUES(`original_batch_no`),
      `original_expected_inbound_time` = VALUES(`original_expected_inbound_time`);
  END IF;
END$$

CREATE PROCEDURE `refresh_wechat_batch_summary_all`()
BEGIN
  TRUNCATE TABLE `wechat_batch_summary`;

  INSERT INTO `wechat_batch_summary` (
    `summary_id`,
    `batch_no`,
    `expected_inbound_time`,
    `model`,
    `quantity`,
    `heightened`,
    `original_batch_no`,
    `original_expected_inbound_time`
  )
  SELECT
    MD5(CONCAT(
      s.`batch_no`,
      '|',
      COALESCE(DATE_FORMAT(s.`expected_inbound_time`, '%Y-%m-%d %H:%i:%s'), ''),
      '|',
      s.`model`,
      '|',
      s.`heightened`,
      '|',
      COALESCE(s.`original_batch_no`, '')
    )) AS `summary_id`,
    s.`batch_no`,
    s.`expected_inbound_time`,
    s.`model`,
    s.`quantity`,
    s.`heightened`,
    s.`original_batch_no`,
    s.`original_expected_inbound_time`
  FROM (
    SELECT
      IF(raw.`is_high`, '加高', raw.`source_batch_no`) AS `batch_no`,
      raw.`source_expected_inbound_time` AS `expected_inbound_time`,
      raw.`base_model` AS `model`,
      COUNT(*) AS `quantity`,
      IF(raw.`is_high`, 1, 0) AS `heightened`,
      IF(raw.`is_high`, raw.`source_batch_no`, '') AS `original_batch_no`,
      IF(raw.`is_high`, raw.`source_expected_inbound_time`, NULL) AS `original_expected_inbound_time`
    FROM (
      SELECT
        TRIM(`批次号`) AS `source_batch_no`,
        `预计入库时间` AS `source_expected_inbound_time`,
        TRIM(REPLACE(REPLACE(TRIM(`机型`), '(加高)', ''), '加高', '')) AS `base_model`,
        (
          TRIM(COALESCE(`机型`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`批次号`, '')) LIKE '%附加%'
          OR TRIM(COALESCE(`批次号`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`订单备注`, '')) LIKE '%加高%'
        ) AS `is_high`
      FROM `finished_goods_data`
      WHERE NULLIF(TRIM(COALESCE(`批次号`, '')), '') IS NOT NULL
        AND NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
        AND TRIM(COALESCE(`状态`, '')) = '待入库'
    ) raw
    WHERE NULLIF(raw.`base_model`, '') IS NOT NULL
    GROUP BY raw.`source_batch_no`, raw.`source_expected_inbound_time`, raw.`base_model`, raw.`is_high`
    UNION ALL
    SELECT
      IF(raw.`is_high`, '加高', '库存中') AS `batch_no`,
      CAST(NULL AS DATETIME) AS `expected_inbound_time`,
      raw.`base_model` AS `model`,
      COUNT(*) AS `quantity`,
      IF(raw.`is_high`, 1, 0) AS `heightened`,
      IF(raw.`is_high`, COALESCE(NULLIF(raw.`source_batch_no`, ''), '库存中'), '') AS `original_batch_no`,
      CAST(NULL AS DATETIME) AS `original_expected_inbound_time`
    FROM (
      SELECT
        TRIM(COALESCE(`批次号`, '')) AS `source_batch_no`,
        TRIM(REPLACE(REPLACE(TRIM(`机型`), '(加高)', ''), '加高', '')) AS `base_model`,
        (
          TRIM(COALESCE(`机型`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`批次号`, '')) LIKE '%附加%'
          OR TRIM(COALESCE(`批次号`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`合同备注`, '')) LIKE '%加高%'
          OR TRIM(COALESCE(`订单备注`, '')) LIKE '%加高%'
        ) AS `is_high`
      FROM `finished_goods_data`
      WHERE NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
        AND TRIM(COALESCE(`状态`, '')) = '库存中'
    ) raw
    WHERE NULLIF(raw.`base_model`, '') IS NOT NULL
    GROUP BY raw.`base_model`, raw.`is_high`, IF(raw.`is_high`, COALESCE(NULLIF(raw.`source_batch_no`, ''), '库存中'), '')
  ) s
  ON DUPLICATE KEY UPDATE
    `batch_no` = VALUES(`batch_no`),
    `expected_inbound_time` = VALUES(`expected_inbound_time`),
    `model` = VALUES(`model`),
    `quantity` = VALUES(`quantity`),
    `heightened` = VALUES(`heightened`),
    `original_batch_no` = VALUES(`original_batch_no`),
    `original_expected_inbound_time` = VALUES(`original_expected_inbound_time`);
END$$

CREATE TRIGGER `trg_fg_wechat_summary_ai`
AFTER INSERT ON `finished_goods_data`
FOR EACH ROW
BEGIN
  CALL `refresh_wechat_batch_summary_group`(NEW.`批次号`, NEW.`预计入库时间`, NEW.`机型`);
END$$

CREATE TRIGGER `trg_fg_wechat_summary_au`
AFTER UPDATE ON `finished_goods_data`
FOR EACH ROW
BEGIN
  CALL `refresh_wechat_batch_summary_group`(OLD.`批次号`, OLD.`预计入库时间`, OLD.`机型`);
  IF NOT (
    OLD.`批次号` <=> NEW.`批次号`
    AND OLD.`预计入库时间` <=> NEW.`预计入库时间`
    AND OLD.`机型` <=> NEW.`机型`
  ) THEN
    CALL `refresh_wechat_batch_summary_group`(NEW.`批次号`, NEW.`预计入库时间`, NEW.`机型`);
  END IF;
END$$

CREATE TRIGGER `trg_fg_wechat_summary_ad`
AFTER DELETE ON `finished_goods_data`
FOR EACH ROW
BEGIN
  CALL `refresh_wechat_batch_summary_group`(OLD.`批次号`, OLD.`预计入库时间`, OLD.`机型`);
END$$

DELIMITER ;

CALL `add_wechat_batch_summary_column_if_missing`('heightened', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `heightened` TINYINT(1) NOT NULL DEFAULT 0 AFTER `quantity`');
CALL `add_wechat_batch_summary_column_if_missing`('original_batch_no', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `original_batch_no` VARCHAR(100) DEFAULT '''' AFTER `heightened`');
CALL `add_wechat_batch_summary_column_if_missing`('original_expected_inbound_time', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `original_expected_inbound_time` DATETIME NULL AFTER `original_batch_no`');
CALL `add_wechat_batch_summary_column_if_missing`('updated_at', 'ALTER TABLE `wechat_batch_summary` ADD COLUMN `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `original_expected_inbound_time`');

DROP PROCEDURE IF EXISTS `add_wechat_batch_summary_column_if_missing`;

CALL `refresh_wechat_batch_summary_all`();
