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
	if err := addColumnIfMissing(db, "batches", "batch_code", "ALTER TABLE batches ADD COLUMN batch_code VARCHAR(16) NULL AFTER batch_no"); err != nil {
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
