package repo

import (
	"encoding/json"
	"errors"

	"gorm.io/datatypes"
	"gorm.io/gorm"

	"smart-scheduling/server/internal/model"
)

type ConfigRepo struct {
	db *gorm.DB
}

func NewConfigRepo(db *gorm.DB) *ConfigRepo { return &ConfigRepo{db: db} }

func (r *ConfigRepo) GetJSON(key string, fallback any, out any) error {
	var cfg model.SystemConfig
	if err := r.db.First(&cfg, "config_key = ?", key).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) && fallback != nil {
			raw, _ := json.Marshal(fallback)
			return json.Unmarshal(raw, out)
		}
		return err
	}
	return json.Unmarshal(cfg.ConfigValue, out)
}

func (r *ConfigRepo) UpsertJSON(key string, value any, desc string, actor string) error {
	raw, err := json.Marshal(value)
	if err != nil {
		return err
	}
	cfg := model.SystemConfig{
		ConfigKey:   key,
		ConfigValue: datatypes.JSON(raw),
		Description: &desc,
		UpdatedBy:   actor,
	}
	return r.db.Save(&cfg).Error
}
