package repo

import (
	"strings"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"smart-scheduling/server/internal/model"
)

type BatchRepo struct{ db *gorm.DB }

func NewBatchRepo(db *gorm.DB) *BatchRepo { return &BatchRepo{db: db} }

func (r *BatchRepo) List(status string, modelType string) ([]model.Batch, error) {
	tx := r.db.
		Model(&model.Batch{}).
		Select("batches.*, fbs.slot_no AS forecast_slot_no").
		Joins("LEFT JOIN forecast_batch_slots fbs ON fbs.batch_id = batches.batch_id").
		Preload("Units").
		Order("COALESCE(fbs.slot_no, batches.batch_no) ASC")
	if status != "" {
		parts := strings.Split(status, ",")
		if len(parts) == 1 {
			tx = tx.Where("batches.status = ?", status)
		} else {
			tx = tx.Where("batches.status IN (?)", parts)
		}
	}
	if modelType != "" {
		tx = tx.Where("batches.model_type = ?", modelType)
	}
	var batches []model.Batch
	if err := tx.Find(&batches).Error; err != nil {
		return batches, err
	}
	for i := range batches {
		attachPromisedDueDate(&batches[i])
	}
	return batches, nil
}

func (r *BatchRepo) GetByID(batchID string) (*model.Batch, error) {
	var b model.Batch
	err := r.db.Preload("Units").First(&b, "batch_id = ?", batchID).Error
	if err != nil {
		return nil, err
	}
	attachPromisedDueDate(&b)
	return &b, nil
}

func attachPromisedDueDate(batch *model.Batch) {
	if batch == nil || batch.DueDateEnd == nil || len(batch.Units) == 0 {
		return
	}
	for i := range batch.Units {
		if batch.Units[i].ContractNo != nil && *batch.Units[i].ContractNo != "" {
			batch.Units[i].PromisedDueDate = batch.DueDateEnd
		}
	}
}

func (r *BatchRepo) CountByStatus(statuses ...string) (int64, error) {
	var count int64
	err := r.db.Model(&model.Batch{}).Where("status IN ?", statuses).Count(&count).Error
	return count, err
}

func (r *BatchRepo) CreateInTx(tx *gorm.DB, batch *model.Batch) error {
	return tx.Create(batch).Error
}

func (r *BatchRepo) UpdateStatus(tx *gorm.DB, batchID string, status string) error {
	return tx.Model(&model.Batch{}).Where("batch_id = ?", batchID).Update("status", status).Error
}

func (r *BatchRepo) AssignLine(tx *gorm.DB, batchID string, lineID string) error {
	return tx.Model(&model.Batch{}).Where("batch_id = ?", batchID).Updates(map[string]interface{}{
		"status":             model.StatusInProduction,
		"production_line_id": lineID,
	}).Error
}

func (r *BatchRepo) DeleteOldPredictedByModel(tx *gorm.DB, modelType string) error {
	targetBatches := tx.Model(&model.Batch{}).
		Select("batch_id").
		Where("model_type = ? AND status = ?", modelType, model.StatusPredicted)

	if err := tx.Where("batch_id IN (?)", targetBatches).Delete(&model.Unit{}).Error; err != nil {
		return err
	}

	return tx.Where("model_type = ? AND status = ?", modelType, model.StatusPredicted).
		Delete(&model.Batch{}).Error
}

func (r *BatchRepo) LockBatchForUpdate(tx *gorm.DB, batchID string) (*model.Batch, error) {
	var b model.Batch
	err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("batch_id = ?", batchID).First(&b).Error
	if err != nil {
		return nil, err
	}
	return &b, nil
}

func (r *BatchRepo) ListPredictedByModelForUpdate(tx *gorm.DB, modelType string) ([]model.Batch, error) {
	var batches []model.Batch
	err := tx.Model(&model.Batch{}).
		Select("batches.*, fbs.slot_no AS forecast_slot_no").
		Joins("LEFT JOIN forecast_batch_slots fbs ON fbs.batch_id = batches.batch_id").
		Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("batches.status = ? AND batches.model_type = ?", model.StatusPredicted, modelType).
		Order("COALESCE(fbs.slot_no, batches.batch_no) ASC").
		Find(&batches).Error
	return batches, err
}
