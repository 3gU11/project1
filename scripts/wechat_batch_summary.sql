-- WeChat mini-program read model for C:\RJ_Wechat_App.
-- This script adds an independent summary table that follows finished_goods_data
-- through MySQL triggers. It does not change any V7 application code.

SET NAMES utf8mb4 COLLATE utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS `wechat_batch_summary` (
  `summary_id` CHAR(32) NOT NULL,
  `batch_no` VARCHAR(100) NOT NULL,
  `expected_inbound_time` DATETIME NULL,
  `model` VARCHAR(100) NOT NULL,
  `quantity` INT NOT NULL DEFAULT 0,
  `批次号` VARCHAR(100) NOT NULL,
  `预计入库时间` DATETIME NULL,
  `机型` VARCHAR(100) NOT NULL,
  `数量` INT NOT NULL DEFAULT 0,
  `更新时间` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`summary_id`),
  INDEX `idx_wechat_batch_summary_batch` (`批次号`),
  INDEX `idx_wechat_batch_summary_inbound` (`预计入库时间`),
  INDEX `idx_wechat_batch_summary_model` (`机型`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DROP TRIGGER IF EXISTS `trg_fg_wechat_summary_ai`;
DROP TRIGGER IF EXISTS `trg_fg_wechat_summary_au`;
DROP TRIGGER IF EXISTS `trg_fg_wechat_summary_ad`;
DROP PROCEDURE IF EXISTS `refresh_wechat_batch_summary_group`;
DROP PROCEDURE IF EXISTS `refresh_wechat_batch_summary_all`;

DELIMITER $$

CREATE PROCEDURE `refresh_wechat_batch_summary_group`(
  IN p_batch_no VARCHAR(100),
  IN p_expected DATETIME,
  IN p_model VARCHAR(100)
)
BEGIN
  DECLARE v_batch_no VARCHAR(100);
  DECLARE v_model VARCHAR(100);
  DECLARE v_summary_id CHAR(32);
  DECLARE v_stock_summary_id CHAR(32);

  SET v_batch_no = NULLIF(TRIM(COALESCE(p_batch_no, '')), '');
  SET v_model = NULLIF(TRIM(COALESCE(p_model, '')), '');
  SET v_summary_id = MD5(CONCAT(
    COALESCE(v_batch_no, ''),
    '|',
    COALESCE(DATE_FORMAT(p_expected, '%Y-%m-%d %H:%i:%s'), ''),
    '|',
    COALESCE(v_model, '')
  ));
  SET v_stock_summary_id = MD5(CONCAT('库存中', '|', '', '|', COALESCE(v_model, '')));

  DELETE FROM `wechat_batch_summary`
  WHERE `summary_id` IN (v_summary_id, v_stock_summary_id);

  IF v_batch_no IS NOT NULL AND v_model IS NOT NULL THEN
    INSERT INTO `wechat_batch_summary` (
      `summary_id`,
      `batch_no`,
      `expected_inbound_time`,
      `model`,
      `quantity`,
      `批次号`,
      `预计入库时间`,
      `机型`,
      `数量`
    )
    SELECT
      v_summary_id,
      s.`batch_no`,
      s.`expected_inbound_time`,
      s.`model`,
      s.`quantity`,
      s.`batch_no` AS `批次号`,
      s.`expected_inbound_time` AS `预计入库时间`,
      s.`model` AS `机型`,
      s.`quantity` AS `数量`
    FROM (
      SELECT
        TRIM(`批次号`) AS `batch_no`,
        `预计入库时间` AS `expected_inbound_time`,
        TRIM(`机型`) AS `model`,
        COUNT(*) AS `quantity`
      FROM `finished_goods_data`
      WHERE NULLIF(TRIM(COALESCE(`批次号`, '')), '') = v_batch_no
        AND `预计入库时间` <=> p_expected
        AND NULLIF(TRIM(COALESCE(`机型`, '')), '') = v_model
        AND TRIM(COALESCE(`状态`, '')) = '待入库'
      GROUP BY TRIM(`批次号`), `预计入库时间`, TRIM(`机型`)
    ) s;
  END IF;

  IF v_model IS NOT NULL THEN
    INSERT INTO `wechat_batch_summary` (
      `summary_id`,
      `batch_no`,
      `expected_inbound_time`,
      `model`,
      `quantity`,
      `批次号`,
      `预计入库时间`,
      `机型`,
      `数量`
    )
    SELECT
      v_stock_summary_id,
      s.`batch_no`,
      s.`expected_inbound_time`,
      s.`model`,
      s.`quantity`,
      s.`batch_no` AS `批次号`,
      s.`expected_inbound_time` AS `预计入库时间`,
      s.`model` AS `机型`,
      s.`quantity` AS `数量`
    FROM (
      SELECT
        '库存中' AS `batch_no`,
        CAST(NULL AS DATETIME) AS `expected_inbound_time`,
        TRIM(`机型`) AS `model`,
        COUNT(*) AS `quantity`
      FROM `finished_goods_data`
      WHERE NULLIF(TRIM(COALESCE(`机型`, '')), '') = v_model
        AND TRIM(COALESCE(`状态`, '')) = '库存中'
      GROUP BY TRIM(`机型`)
    ) s;
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
    `批次号`,
    `预计入库时间`,
    `机型`,
    `数量`
  )
  SELECT
    MD5(CONCAT(
      s.`batch_no`,
      '|',
      COALESCE(DATE_FORMAT(s.`expected_inbound_time`, '%Y-%m-%d %H:%i:%s'), ''),
      '|',
      s.`model`
    )) AS `summary_id`,
    s.`batch_no`,
    s.`expected_inbound_time`,
    s.`model`,
    s.`quantity`,
    s.`batch_no` AS `批次号`,
    s.`expected_inbound_time` AS `预计入库时间`,
    s.`model` AS `机型`,
    s.`quantity` AS `数量`
  FROM (
    SELECT
      TRIM(`批次号`) AS `batch_no`,
      `预计入库时间` AS `expected_inbound_time`,
      TRIM(`机型`) AS `model`,
      COUNT(*) AS `quantity`
    FROM `finished_goods_data`
    WHERE NULLIF(TRIM(COALESCE(`批次号`, '')), '') IS NOT NULL
      AND NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
      AND TRIM(COALESCE(`状态`, '')) = '待入库'
    GROUP BY TRIM(`批次号`), `预计入库时间`, TRIM(`机型`)
    UNION ALL
    SELECT
      '库存中' AS `batch_no`,
      CAST(NULL AS DATETIME) AS `expected_inbound_time`,
      TRIM(`机型`) AS `model`,
      COUNT(*) AS `quantity`
    FROM `finished_goods_data`
    WHERE NULLIF(TRIM(COALESCE(`机型`, '')), '') IS NOT NULL
      AND TRIM(COALESCE(`状态`, '')) = '库存中'
    GROUP BY TRIM(`机型`)
  ) s;
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

CALL `refresh_wechat_batch_summary_all`();
