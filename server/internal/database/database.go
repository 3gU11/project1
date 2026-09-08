package database

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/go-redis/redis/v8"
	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"

	"smart-scheduling/server/internal/config"
)

func OpenMySQL(cfg config.Config) (*gorm.DB, error) {
	db, err := gorm.Open(mysql.Open(cfg.DBDSN), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Warn),
	})
	if err != nil {
		return nil, err
	}
	if err := ensureSchema(db); err != nil {
		return nil, err
	}
	return db, nil
}

func ensureSchema(db *gorm.DB) error {
	if err := addColumnIfMissing(db, "batches", "batch_code", "ALTER TABLE batches ADD COLUMN batch_code VARCHAR(64) NULL AFTER batch_no"); err != nil {
		return err
	}
	if err := ensureBatchCodeLength(db); err != nil {
		return err
	}
	if err := addColumnIfMissing(db, "batches", "expected_inbound_date", "ALTER TABLE batches ADD COLUMN expected_inbound_date DATE NULL AFTER due_date_end"); err != nil {
		return err
	}
	if err := addColumnIfMissing(db, "units", "dealer_name", "ALTER TABLE units ADD COLUMN dealer_name VARCHAR(255) NULL AFTER dealer_id"); err != nil {
		return err
	}
	if err := addColumnIfMissing(db, "units", "due_date", "ALTER TABLE units ADD COLUMN due_date DATE NULL AFTER dealer_name"); err != nil {
		return err
	}
	if err := addColumnIfMissing(db, "units", "forecast_serial_no", "ALTER TABLE units ADD COLUMN forecast_serial_no VARCHAR(64) NULL AFTER serial_no"); err != nil {
		return err
	}
	if err := addColumnIfMissing(db, "model_dictionary", "model_family", "ALTER TABLE model_dictionary ADD COLUMN model_family VARCHAR(16) NULL AFTER model_name"); err != nil {
		return err
	}
	if err := addColumnIfMissing(db, "model_dictionary", "model_size", "ALTER TABLE model_dictionary ADD COLUMN model_size INT NULL AFTER model_family"); err != nil {
		return err
	}
	if err := migrateModelFamilies(db); err != nil {
		return err
	}
	if err := ensureFH300CModel(db); err != nil {
		return err
	}
	if err := ensureMachinePhotoSchema(db); err != nil {
		return err
	}
	if err := seedDefaultPhotoItems(db); err != nil {
		return err
	}
	if err := db.Exec(`
CREATE TABLE IF NOT EXISTS forecast_batch_slots (
  slot_no INT NOT NULL PRIMARY KEY,
  model_type VARCHAR(32) NOT NULL,
  capacity INT NOT NULL,
  batch_id VARCHAR(64) NULL,
  source VARCHAR(32) NOT NULL DEFAULT 'ratio',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_forecast_batch_slots_model (model_type),
  INDEX idx_forecast_batch_slots_batch (batch_id)
)`).Error; err != nil {
		return err
	}
	if err := alignForecastSlotCollation(db); err != nil {
		return err
	}
	if err := normalizeFactoryPlanStatus(db); err != nil {
		return err
	}
	return nil
}

func ensureMachinePhotoSchema(db *gorm.DB) error {
	statements := []string{
		`
CREATE TABLE IF NOT EXISTS photo_item_library (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  position_code VARCHAR(64) NOT NULL,
  item_name VARCHAR(128) NOT NULL,
  item_category VARCHAR(64) NULL,
  shooting_requirement TEXT NULL,
  default_required TINYINT(1) NOT NULL DEFAULT 1,
  default_ocr_enabled TINYINT(1) NOT NULL DEFAULT 1,
  default_ocr_profile VARCHAR(64) NULL,
  sort_order INT NOT NULL DEFAULT 0,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_photo_item_position_code (position_code),
  KEY idx_photo_item_enabled_sort (enabled, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci`,
		`
CREATE TABLE IF NOT EXISTS model_photo_config (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  model_id BIGINT NOT NULL,
  position_code VARCHAR(64) NOT NULL,
  required TINYINT(1) NOT NULL DEFAULT 1,
  ocr_enabled TINYINT(1) NOT NULL DEFAULT 1,
  ocr_profile VARCHAR(64) NULL,
  sort_order INT NOT NULL DEFAULT 0,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  remark VARCHAR(255) NULL,
  updated_by VARCHAR(64) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_model_photo_config (model_id, position_code),
  KEY idx_model_photo_config_model_sort (model_id, enabled, sort_order),
  KEY idx_model_photo_config_position (position_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci`,
		`
CREATE TABLE IF NOT EXISTS ocr_field_rules (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  ocr_profile VARCHAR(64) NOT NULL,
  position_code VARCHAR(64) NOT NULL,
  field_code VARCHAR(64) NOT NULL,
  field_name VARCHAR(128) NOT NULL,
  required TINYINT(1) NOT NULL DEFAULT 1,
  pattern VARCHAR(255) NULL,
  confidence_threshold DECIMAL(5,4) NOT NULL DEFAULT 0.8000,
  compare_target VARCHAR(128) NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_ocr_field_rule (ocr_profile, position_code, field_code),
  KEY idx_ocr_field_rule_profile_position (ocr_profile, position_code, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci`,
		`
CREATE TABLE IF NOT EXISTS machine_photo_tasks (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  serial_no VARCHAR(100) NOT NULL,
  model_name VARCHAR(100) NOT NULL,
  position_code VARCHAR(64) NOT NULL,
  item_name VARCHAR(128) NOT NULL,
  required TINYINT(1) NOT NULL DEFAULT 1,
  ocr_enabled TINYINT(1) NOT NULL DEFAULT 1,
  ocr_profile VARCHAR(64) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  sort_order INT NOT NULL DEFAULT 0,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  skip_reason VARCHAR(255) NULL,
  submit_batch VARCHAR(64) NULL,
  created_by VARCHAR(64) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_machine_photo_task (serial_no, position_code),
  KEY idx_machine_photo_task_serial_sort (serial_no, enabled, sort_order),
  KEY idx_machine_photo_task_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci`,
		`
CREATE TABLE IF NOT EXISTS machine_photo_files (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  task_id BIGINT NOT NULL,
  serial_no VARCHAR(100) NOT NULL,
  position_code VARCHAR(64) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  file_path VARCHAR(500) NOT NULL,
  thumb_path VARCHAR(500) NULL,
  mime_type VARCHAR(100) NULL,
  file_size BIGINT NULL,
  uploaded_by VARCHAR(64) NULL,
  uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_machine_photo_files_task (task_id),
  KEY idx_machine_photo_files_serial_position (serial_no, position_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci`,
		`
CREATE TABLE IF NOT EXISTS machine_photo_ocr_results (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  task_id BIGINT NOT NULL,
  file_id BIGINT NOT NULL,
  field_code VARCHAR(64) NOT NULL,
  field_name VARCHAR(128) NOT NULL,
  recognized_value TEXT NULL,
  confidence DECIMAL(6,5) NULL,
  manual_value TEXT NULL,
  check_status VARCHAR(32) NOT NULL DEFAULT 'empty',
  reviewed_by VARCHAR(64) NULL,
  reviewed_at DATETIME NULL,
  raw_result_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_machine_photo_ocr_task (task_id),
  KEY idx_machine_photo_ocr_file (file_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci`,
		`
CREATE TABLE IF NOT EXISTS machine_photo_submissions (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  serial_no VARCHAR(100) NOT NULL,
  model_name VARCHAR(100) NOT NULL,
  submit_batch VARCHAR(64) NOT NULL,
  submitted_by VARCHAR(64) NULL,
  submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  summary_json JSON NULL,
  UNIQUE KEY uq_machine_photo_submission_batch (submit_batch),
  KEY idx_machine_photo_submission_serial (serial_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci`,
		`
CREATE TABLE IF NOT EXISTS machine_component_bindings (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  binding_key VARCHAR(180) NOT NULL,
  machine_no VARCHAR(100) NOT NULL,
  machine_batch_no VARCHAR(100) NOT NULL DEFAULT '',
  model_name VARCHAR(100) NOT NULL,
  customer VARCHAR(255) NOT NULL DEFAULT '',
  agent VARCHAR(255) NOT NULL DEFAULT '',
  machine_status VARCHAR(100) NOT NULL DEFAULT '',
  location_code VARCHAR(100) NOT NULL DEFAULT '',
  delivery_date DATE NULL,
  outbound_at DATETIME NULL,
  material_code VARCHAR(80) NOT NULL,
  material_name VARCHAR(120) NOT NULL,
  material_type VARCHAR(40) NOT NULL DEFAULT '编号',
  material_spec VARCHAR(120) NOT NULL DEFAULT '',
  component_serial_no VARCHAR(100) NOT NULL,
  instance_batch_no VARCHAR(80) NOT NULL DEFAULT '',
  instance_flow_no VARCHAR(80) NOT NULL DEFAULT '',
  position_code VARCHAR(64) NOT NULL,
  position_name VARCHAR(120) NOT NULL,
  bound_at DATE NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  source VARCHAR(40) NOT NULL DEFAULT 'V8_OCR',
  source_task_id BIGINT NOT NULL,
  source_file_id BIGINT NULL,
  source_ocr_result_id BIGINT NULL,
  file_name VARCHAR(255) NOT NULL DEFAULT '',
  recognized_value TEXT NULL,
  manual_value TEXT NULL,
  confidence DECIMAL(6,5) NULL,
  check_status VARCHAR(32) NOT NULL DEFAULT '',
  reviewed_by VARCHAR(64) NOT NULL DEFAULT '',
  reviewed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_machine_component_binding_key (binding_key),
  UNIQUE KEY uq_machine_component_machine_position (machine_no, position_code),
  KEY idx_machine_component_machine (machine_no, active),
  KEY idx_machine_component_serial (component_serial_no),
  KEY idx_machine_component_material (material_code),
  KEY idx_machine_component_task (source_task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci`,
	}
	for _, statement := range statements {
		if err := db.Exec(statement).Error; err != nil {
			return err
		}
	}
	if err := addColumnIfMissing(db, "machine_photo_tasks", "enabled", "ALTER TABLE machine_photo_tasks ADD COLUMN enabled TINYINT(1) NOT NULL DEFAULT 1 AFTER sort_order"); err != nil {
		return err
	}
	if err := addColumnIfMissing(db, "machine_component_bindings", "delivery_date", "ALTER TABLE machine_component_bindings ADD COLUMN delivery_date DATE NULL AFTER location_code"); err != nil {
		return err
	}
	if err := addColumnIfMissing(db, "machine_component_bindings", "outbound_at", "ALTER TABLE machine_component_bindings ADD COLUMN outbound_at DATETIME NULL AFTER delivery_date"); err != nil {
		return err
	}
	if err := backfillMachineComponentBindings(db); err != nil {
		return err
	}
	return nil
}

func backfillMachineComponentBindings(db *gorm.DB) error {
	if err := db.Exec(`
INSERT INTO machine_component_bindings
  (binding_key, machine_no, machine_batch_no, model_name, customer, agent, machine_status, location_code,
   delivery_date, outbound_at, material_code, material_name, material_type, material_spec, component_serial_no, instance_batch_no,
   instance_flow_no, position_code, position_name, bound_at, active, source, source_task_id, source_file_id,
   source_ocr_result_id, file_name, recognized_value, manual_value, confidence, check_status, reviewed_by, reviewed_at)
SELECT
  CONCAT('V8-', t.serial_no, '-', t.position_code) AS binding_key,
  t.serial_no AS machine_no,
  COALESCE(fg.` + "`批次号`" + `, '') AS machine_batch_no,
  t.model_name,
  COALESCE(fg.` + "`客户`" + `, '') AS customer,
  COALESCE(fg.` + "`代理商`" + `, '') AS agent,
  COALESCE(fg.` + "`状态`" + `, '') AS machine_status,
  COALESCE(fg.` + "`Location_Code`" + `, '') AS location_code,
  CASE
    WHEN sh.outbound_at IS NOT NULL THEN DATE(sh.outbound_at)
    WHEN TRIM(COALESCE(fg.` + "`状态`" + `, '')) LIKE '已出库%' THEN DATE(fg.` + "`更新时间`" + `)
    ELSE NULL
  END AS delivery_date,
  CASE
    WHEN sh.outbound_at IS NOT NULL THEN sh.outbound_at
    WHEN TRIM(COALESCE(fg.` + "`状态`" + `, '')) LIKE '已出库%' THEN fg.` + "`更新时间`" + `
    ELSE NULL
  END AS outbound_at,
  CONCAT('V8-', t.position_code) AS material_code,
  t.item_name AS material_name,
  COALESCE(NULLIF(pil.item_category, ''), '编号') AS material_type,
  t.position_code AS material_spec,
  LEFT(TRIM(COALESCE(NULLIF(r.manual_value, ''), r.recognized_value, '')), 100) AS component_serial_no,
  '' AS instance_batch_no,
  '' AS instance_flow_no,
  t.position_code,
  t.item_name AS position_name,
  DATE(COALESCE(r.reviewed_at, f.uploaded_at, t.updated_at, NOW())) AS bound_at,
  1 AS active,
  'V8_OCR' AS source,
  t.id AS source_task_id,
  r.file_id AS source_file_id,
  r.id AS source_ocr_result_id,
  COALESCE(f.file_name, '') AS file_name,
  r.recognized_value,
  r.manual_value,
  r.confidence,
  r.check_status,
  COALESCE(r.reviewed_by, '') AS reviewed_by,
  r.reviewed_at
FROM machine_photo_tasks t
JOIN (
  SELECT task_id, MAX(id) AS result_id
  FROM machine_photo_ocr_results
  WHERE check_status = 'manual_passed'
    AND TRIM(COALESCE(NULLIF(manual_value, ''), recognized_value, '')) <> ''
  GROUP BY task_id
) latest ON latest.task_id = t.id
JOIN machine_photo_ocr_results r ON r.id = latest.result_id
LEFT JOIN machine_photo_files f ON f.id = r.file_id
LEFT JOIN photo_item_library pil ON pil.position_code = t.position_code
LEFT JOIN finished_goods_data fg ON TRIM(fg.` + "`流水号`" + `) = t.serial_no
LEFT JOIN (
  SELECT TRIM(` + "`流水号`" + `) AS serial_no, MAX(` + "`更新时间`" + `) AS outbound_at
  FROM shipping_history
  WHERE TRIM(COALESCE(` + "`状态`" + `, '')) LIKE '已出库%'
  GROUP BY TRIM(` + "`流水号`" + `)
) sh ON sh.serial_no = t.serial_no
WHERE t.enabled = 1
  AND t.status IN ('manual_passed', 'completed')
ON DUPLICATE KEY UPDATE
  machine_batch_no = VALUES(machine_batch_no),
  model_name = VALUES(model_name),
  customer = VALUES(customer),
  agent = VALUES(agent),
  machine_status = VALUES(machine_status),
  location_code = VALUES(location_code),
  delivery_date = VALUES(delivery_date),
  outbound_at = VALUES(outbound_at),
  material_code = VALUES(material_code),
  material_name = VALUES(material_name),
  material_type = VALUES(material_type),
  material_spec = VALUES(material_spec),
  component_serial_no = VALUES(component_serial_no),
  instance_batch_no = VALUES(instance_batch_no),
  instance_flow_no = VALUES(instance_flow_no),
  position_name = VALUES(position_name),
  bound_at = VALUES(bound_at),
  active = VALUES(active),
  source = VALUES(source),
  source_task_id = VALUES(source_task_id),
  source_file_id = VALUES(source_file_id),
  source_ocr_result_id = VALUES(source_ocr_result_id),
  file_name = VALUES(file_name),
  recognized_value = VALUES(recognized_value),
  manual_value = VALUES(manual_value),
  confidence = VALUES(confidence),
  check_status = VALUES(check_status),
  reviewed_by = VALUES(reviewed_by),
  reviewed_at = VALUES(reviewed_at),
  updated_at = CURRENT_TIMESTAMP`).Error; err != nil {
		return err
	}
	return db.Exec(`
UPDATE machine_component_bindings b
LEFT JOIN (
  SELECT t.id AS task_id
  FROM machine_photo_tasks t
  JOIN machine_photo_ocr_results r ON r.task_id = t.id
  WHERE t.enabled = 1
    AND t.status IN ('manual_passed', 'completed')
    AND r.check_status = 'manual_passed'
    AND TRIM(COALESCE(NULLIF(r.manual_value, ''), r.recognized_value, '')) <> ''
  GROUP BY t.id
) confirmed ON confirmed.task_id = b.source_task_id
SET b.active = 0,
    b.updated_at = CURRENT_TIMESTAMP
WHERE b.source = 'V8_OCR'
  AND confirmed.task_id IS NULL`).Error
}

func seedDefaultPhotoItems(db *gorm.DB) error {
	items := []struct {
		Code        string
		Name        string
		Category    string
		Requirement string
		Required    bool
		OCR         bool
		Profile     string
		Order       int
	}{
		{"TY-01", "整机正面", "通用", "设备全貌清晰，能看清安装位置和主体状态。", true, false, "", 1},
		{"TY-02", "设备铭牌", "通用", "厂家、型号、出厂编号、功率等信息清晰。", true, true, "铭牌OCR", 2},
		{"TY-03", "设备编号标签", "通用", "公司内部设备编号或流水号清晰。", true, true, "设备编号OCR", 3},
		{"SN-XJ", "手脉信捷编号", "编号", "编号贴纸或铭牌完整清晰。", true, true, "编号标签OCR", 11},
		{"SN-LASER", "手脉激光编号", "编号", "编号贴纸或铭牌完整清晰。", true, true, "编号标签OCR", 12},
		{"SN-PLC", "信捷PLC编号", "编号", "PLC本体编号清晰。", true, true, "编号标签OCR", 13},
		{"SN-COMMON", "信捷公共机编号", "编号", "公共机编号清晰。", true, true, "编号标签OCR", 14},
		{"SN-DOG", "信捷公共机加密狗编号", "编号", "加密狗编号清晰。", false, true, "编号标签OCR", 15},
		{"SN-CPU", "CPU板编号", "编号", "CPU板标签或丝印清晰。", true, true, "编号标签OCR", 16},
		{"SN-HF", "高频板编号", "编号", "高频板标签或丝印清晰。", true, true, "编号标签OCR", 17},
		{"SN-DISPLAY", "显示器产品序号", "编号", "显示器背部或侧边序号清晰。", false, true, "编号标签OCR", 18},
		{"SN-MOTOR", "三相异步电机产品序号", "编号", "电机铭牌或产品序号清晰。", false, true, "编号标签OCR", 19},
		{"SN-VFD", "信捷变频器编号", "编号", "变频器侧面或铭牌编号清晰。", true, true, "编号标签OCR", 20},
	}
	for _, item := range items {
		if err := db.Exec(`
INSERT INTO photo_item_library
  (position_code, item_name, item_category, shooting_requirement, default_required, default_ocr_enabled, default_ocr_profile, sort_order, enabled)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
ON DUPLICATE KEY UPDATE
  item_name = VALUES(item_name),
  item_category = VALUES(item_category),
  shooting_requirement = VALUES(shooting_requirement),
  default_required = VALUES(default_required),
  default_ocr_enabled = VALUES(default_ocr_enabled),
  default_ocr_profile = VALUES(default_ocr_profile),
  sort_order = VALUES(sort_order),
  updated_at = CURRENT_TIMESTAMP`,
			item.Code,
			item.Name,
			item.Category,
			item.Requirement,
			boolToInt(item.Required),
			boolToInt(item.OCR),
			item.Profile,
			item.Order,
		).Error; err != nil {
			return err
		}
	}
	return nil
}

func boolToInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

func normalizeFactoryPlanStatus(db *gorm.DB) error {
	if err := db.Exec("UPDATE factory_plan SET `状态`='待规划' WHERE TRIM(COALESCE(`状态`, ''))='未下单'").Error; err != nil {
		return err
	}
	if err := db.Exec("UPDATE factory_plan SET `状态`='待规划' WHERE TRIM(COALESCE(`状态`, ''))=''").Error; err != nil {
		return err
	}
	return nil
}

func alignForecastSlotCollation(db *gorm.DB) error {
	getCollation := func(table string, column string) (string, error) {
		var collation string
		err := db.Raw(`
SELECT COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = ?
  AND COLUMN_NAME = ?
LIMIT 1`, table, column).Scan(&collation).Error
		if err != nil {
			return "", err
		}
		return strings.TrimSpace(collation), nil
	}

	desiredBatchIDCollation, err := getCollation("batches", "batch_id")
	if err != nil {
		return err
	}
	currentBatchIDCollation, err := getCollation("forecast_batch_slots", "batch_id")
	if err != nil {
		return err
	}
	if desiredBatchIDCollation != "" && currentBatchIDCollation != "" && desiredBatchIDCollation != currentBatchIDCollation {
		sql := fmt.Sprintf("ALTER TABLE forecast_batch_slots MODIFY COLUMN batch_id VARCHAR(64) NULL COLLATE %s", desiredBatchIDCollation)
		if err := db.Exec(sql).Error; err != nil {
			return err
		}
	}

	desiredModelTypeCollation, err := getCollation("batches", "model_type")
	if err != nil {
		return err
	}
	currentModelTypeCollation, err := getCollation("forecast_batch_slots", "model_type")
	if err != nil {
		return err
	}
	if desiredModelTypeCollation != "" && currentModelTypeCollation != "" && desiredModelTypeCollation != currentModelTypeCollation {
		sql := fmt.Sprintf("ALTER TABLE forecast_batch_slots MODIFY COLUMN model_type VARCHAR(32) NOT NULL COLLATE %s", desiredModelTypeCollation)
		if err := db.Exec(sql).Error; err != nil {
			return err
		}
	}

	return nil
}

func addColumnIfMissing(db *gorm.DB, tableName string, columnName string, alterSQL string) error {
	var count int64
	if err := db.Raw(`
SELECT COUNT(*)
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = ?
  AND COLUMN_NAME = ?`, tableName, columnName).Scan(&count).Error; err != nil {
		return err
	}
	if count > 0 {
		return nil
	}
	return db.Exec(alterSQL).Error
}

func ensureBatchCodeLength(db *gorm.DB) error {
	var maxLength int64
	if err := db.Raw(`
SELECT COALESCE(CHARACTER_MAXIMUM_LENGTH, 0)
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'batches'
  AND COLUMN_NAME = 'batch_code'
LIMIT 1`).Scan(&maxLength).Error; err != nil {
		return err
	}
	if maxLength >= 64 {
		return nil
	}
	return db.Exec("ALTER TABLE batches MODIFY COLUMN batch_code VARCHAR(64) NULL").Error
}

func ensureFH300CModel(db *gorm.DB) error {
	if err := db.Exec(`
INSERT INTO model_dictionary (model_name, model_family, sort_order, enabled, remark)
SELECT 'FH-300C', '中小型G', next_order, 1, '老板计划中小型G机型'
FROM (SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM model_dictionary) AS order_seed
WHERE NOT EXISTS (
  SELECT 1 FROM (SELECT model_name FROM model_dictionary WHERE UPPER(TRIM(model_name)) = 'FH-300C' LIMIT 1) AS existing_model
)`).Error; err != nil {
		return err
	}
	return db.Exec(`
UPDATE model_dictionary
SET model_name = 'FH-300C', model_family = '中小型G', enabled = 1
WHERE UPPER(TRIM(model_name)) = 'FH-300C'`).Error
}

func migrateModelFamilies(db *gorm.DB) error {
	replacements := map[string]string{
		"小机G":     "中小型G",
		"小机XS":    "中小型XS",
		"小机/XS":   "中小型XS",
		"小机AUTO":  "中小型AUTO",
		"大机XS":    "中大型XS",
		"大机AUTO":  "中大型AUTO",
		"SPECIAL": "特殊",
	}
	for oldFamily, newFamily := range replacements {
		if err := db.Exec(
			"UPDATE model_dictionary SET model_family = ? WHERE TRIM(COALESCE(model_family, '')) = ?",
			newFamily,
			oldFamily,
		).Error; err != nil {
			return err
		}
	}
	return nil
}

func OpenRedis(cfg config.Config) *redis.Client {
	if !cfg.RedisEnabled {
		return nil
	}

	rdb := redis.NewClient(&redis.Options{
		Addr:        cfg.RedisAddr,
		Password:    cfg.RedisPass,
		DB:          cfg.RedisDB,
		DialTimeout: 800 * time.Millisecond,
	})
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		_ = rdb.Close()
		return nil
	}
	return rdb
}
