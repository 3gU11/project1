package service

import (
	"encoding/json"
	"fmt"
	"time"

	"gorm.io/gorm"

	"smart-scheduling/server/internal/model"
	"smart-scheduling/server/internal/repo"
	"smart-scheduling/server/internal/ws"
)

type BatchSvc struct {
	db        *gorm.DB
	batchRepo *repo.BatchRepo
	unitRepo  *repo.UnitRepo
	cfgRepo   *repo.ConfigRepo
	wsHub     *ws.Hub
}

func NewBatchSvc(db *gorm.DB, br *repo.BatchRepo, ur *repo.UnitRepo, cr *repo.ConfigRepo, hub *ws.Hub) *BatchSvc {
	return &BatchSvc{db: db, batchRepo: br, unitRepo: ur, cfgRepo: cr, wsHub: hub}
}

func (s *BatchSvc) Confirm(batchID string, actor string, batchCode *string, inboundDate *time.Time) error {
	tx := s.db.Begin()
	defer tx.Rollback()

	b, err := s.batchRepo.LockBatchForUpdate(tx, batchID)
	if err != nil {
		return fmt.Errorf("batch not found: %w", err)
	}
	if b.Status != model.StatusPredicted {
		return fmt.Errorf("batch status is %s, expected Predicted", b.Status)
	}

	updates := map[string]interface{}{
		"status": model.StatusConfirmed,
	}
	if batchCode != nil {
		var count int64
		if err := tx.Model(&model.Batch{}).
			Where("batch_id <> ?", batchID).
			Where("batch_code = ?", *batchCode).
			Count(&count).Error; err != nil {
			return err
		}
		if count > 0 {
			return fmt.Errorf("batch_code %s already exists", *batchCode)
		}
		updates["batch_code"] = *batchCode
	}
	if inboundDate != nil {
		updates["expected_inbound_date"] = *inboundDate
	}
	if err := tx.Model(&model.Batch{}).Where("batch_id = ?", batchID).Updates(updates).Error; err != nil {
		return err
	}

	if err := tx.Commit().Error; err != nil {
		return err
	}

	s.log(actor, "confirm", "batch", batchID, map[string]string{"model_type": b.ModelType})
	s.wsHub.Broadcast("batch:confirmed", map[string]string{"batch_id": batchID, "model_type": b.ModelType})
	return nil
}

func (s *BatchSvc) Revoke(batchID string, actor string) error {
	tx := s.db.Begin()
	defer tx.Rollback()

	b, err := s.batchRepo.LockBatchForUpdate(tx, batchID)
	if err != nil {
		return fmt.Errorf("batch not found: %w", err)
	}
	if b.Status != model.StatusConfirmed {
		return fmt.Errorf("batch status is %s, expected Confirmed", b.Status)
	}

	updates := map[string]interface{}{
		"status":     model.StatusPredicted,
		"batch_code": nil,
	}
	if err := tx.Model(&model.Batch{}).Where("batch_id = ?", batchID).Updates(updates).Error; err != nil {
		return err
	}

	if err := tx.Commit().Error; err != nil {
		return err
	}

	s.log(actor, "revoke", "batch", batchID, map[string]string{"model_type": b.ModelType})
	s.wsHub.Broadcast("batch:revoked", map[string]string{"batch_id": batchID, "model_type": b.ModelType})
	return nil
}

func (s *BatchSvc) BatchConfirm(batchIDs []string, actor string) error {
	for _, id := range batchIDs {
		if err := s.Confirm(id, actor, nil, nil); err != nil {
			return fmt.Errorf("batch %s: %w", id, err)
		}
	}
	return nil
}

func (s *BatchSvc) AssignToLine(batchID string, lineID string, actor string) error {
	tx := s.db.Begin()
	defer tx.Rollback()

	var line model.ProductionLine
	if err := tx.Where("line_id = ?", lineID).First(&line).Error; err != nil {
		return fmt.Errorf("production line not found: %w", err)
	}
	if line.Status != model.LineIdle {
		return fmt.Errorf("line %s is not idle", lineID)
	}

	b, err := s.batchRepo.LockBatchForUpdate(tx, batchID)
	if err != nil {
		return fmt.Errorf("batch not found: %w", err)
	}
	if b.Status != model.StatusConfirmed {
		return fmt.Errorf("batch %s status is %s, expected Confirmed", b.BatchID, b.Status)
	}

	if err := s.batchRepo.AssignLine(tx, batchID, lineID); err != nil {
		return err
	}
	if err := tx.Model(&line).Updates(map[string]interface{}{
		"status":           model.LineBusy,
		"current_batch_id": batchID,
	}).Error; err != nil {
		return err
	}

	// Sync all units in this batch to In_Production with the production line
	if err := tx.Model(&model.Unit{}).Where("batch_id = ?", batchID).Updates(map[string]interface{}{
		"status":             model.StatusInProduction,
		"production_line_id": lineID,
	}).Error; err != nil {
		return err
	}

	if err := tx.Commit().Error; err != nil {
		return err
	}

	s.log(actor, "assign_line", "production_line", lineID, map[string]string{"batch_id": batchID})
	s.wsHub.Broadcast("line:updated", map[string]string{"line_id": lineID, "batch_id": batchID, "status": model.LineBusy})
	return nil
}

func (s *BatchSvc) ManualComplete(lineID string, actor string) error {
	tx := s.db.Begin()
	defer tx.Rollback()

	var line model.ProductionLine
	if err := tx.Where("line_id = ?", lineID).First(&line).Error; err != nil {
		return fmt.Errorf("line not found: %w", err)
	}
	if line.CurrentBatchID == nil {
		return fmt.Errorf("line %s has no active batch", lineID)
	}

	batchID := *line.CurrentBatchID
	if err := s.batchRepo.UpdateStatus(tx, batchID, model.StatusCompleted); err != nil {
		return err
	}
	if err := tx.Model(&line).Updates(map[string]interface{}{
		"status":           model.LineIdle,
		"current_batch_id": nil,
	}).Error; err != nil {
		return err
	}

	// Sync all units in this batch to Completed, clear production_line_id
	if err := tx.Model(&model.Unit{}).Where("batch_id = ?", batchID).Updates(map[string]interface{}{
		"status":             model.StatusCompleted,
		"production_line_id": nil,
	}).Error; err != nil {
		return err
	}

	if err := tx.Commit().Error; err != nil {
		return err
	}

	s.log(actor, "manual_complete", "production_line", lineID, map[string]string{"batch_id": batchID})
	s.wsHub.Broadcast("line:completed", map[string]string{"line_id": lineID, "batch_id": batchID})
	return nil
}

func (s *BatchSvc) log(actor string, action string, targetType string, targetID string, detail map[string]string) {
	detailJSON, _ := json.Marshal(detail)
	entry := model.OperationLog{
		Actor:      actor,
		Action:     action,
		TargetType: targetType,
		TargetID:   targetID,
		Detail:     detailJSON,
		CreatedAt:  time.Now(),
	}
	s.db.Create(&entry)
}
