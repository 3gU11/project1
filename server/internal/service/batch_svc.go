package service

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"smart-scheduling/server/internal/engine"
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

type FactoryPlanStatusUpdateStats struct {
	Pairs int `json:"pairs"`
	Rows  int `json:"rows"`
}

type AutoCompletedBatch struct {
	BatchID   string `json:"batch_id"`
	BatchCode string `json:"batch_code"`
	LineID    string `json:"line_id"`
	UnitCount int64  `json:"unit_count"`
}

type inboundBatchProgress struct {
	TotalUnits   int64 `gorm:"column:total_units"`
	InboundUnits int64 `gorm:"column:inbound_units"`
}

type StockModelTarget struct {
	ModelType string `json:"model_type"`
	Count     int    `json:"count"`
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

func (s *BatchSvc) SyncStockModels(batchID string, targets []StockModelTarget, actor string) error {
	tx := s.db.Begin()
	defer tx.Rollback()

	b, err := s.batchRepo.LockBatchForUpdate(tx, batchID)
	if err != nil {
		return fmt.Errorf("batch not found: %w", err)
	}
	if b.Status != model.StatusPredicted {
		return fmt.Errorf("batch status is %s, expected Predicted", b.Status)
	}
	if isSpecialBatchModel(b.ModelType) {
		return fmt.Errorf("special batch stock cannot be edited")
	}

	units, err := s.unitRepo.ListByBatchIDsForUpdate(tx, []string{batchID})
	if err != nil {
		return err
	}

	targetByModel := make(map[string]int)
	for _, item := range targets {
		modelType := strings.TrimSpace(item.ModelType)
		if modelType == "" {
			return fmt.Errorf("model_type is required")
		}
		if item.Count < 0 {
			return fmt.Errorf("stock count for %s must be non-negative", modelType)
		}
		targetByModel[modelType] += item.Count
	}

	orderedCount := 0
	currentStockByModel := make(map[string][]model.Unit)
	for _, u := range units {
		contractNo := ""
		if u.ContractNo != nil {
			contractNo = strings.TrimSpace(*u.ContractNo)
		}
		if contractNo != "" {
			orderedCount++
			continue
		}
		mt := strings.TrimSpace(u.ModelType)
		if mt == "" {
			continue
		}
		currentStockByModel[mt] = append(currentStockByModel[mt], u)
	}

	targetStockTotal := 0
	for _, count := range targetByModel {
		targetStockTotal += count
	}
	if orderedCount+targetStockTotal > b.Capacity {
		return fmt.Errorf("ordered %d + stock %d exceeds batch capacity %d", orderedCount, targetStockTotal, b.Capacity)
	}

	for modelType := range currentStockByModel {
		if _, ok := targetByModel[modelType]; !ok {
			targetByModel[modelType] = 0
		}
	}

	now := time.Now()
	maxSlot, err := s.unitRepo.GetMaxSlotInBatch(tx, batchID)
	if err != nil {
		return err
	}
	created := 0
	deleted := 0
	for modelType, targetCount := range targetByModel {
		current := currentStockByModel[modelType]
		if targetCount > len(current) {
			for i := len(current); i < targetCount; i++ {
				maxSlot++
				created++
				unit := model.Unit{
					UnitID:    fmt.Sprintf("%s-STK-%d-%03d", batchID, now.UnixNano(), created),
					BatchID:   batchID,
					SlotIndex: maxSlot,
					ModelType: modelType,
					Status:    "Pending",
					CreatedAt: now,
					UpdatedAt: now,
				}
				if err := tx.Create(&unit).Error; err != nil {
					return err
				}
			}
			continue
		}
		if targetCount < len(current) {
			toDelete := len(current) - targetCount
			for i := 0; i < len(current)-1; i++ {
				for j := i + 1; j < len(current); j++ {
					if current[i].SlotIndex < current[j].SlotIndex {
						current[i], current[j] = current[j], current[i]
					}
				}
			}
			for i := 0; i < toDelete; i++ {
				if err := tx.Delete(&model.Unit{}, "unit_id = ? AND batch_id = ? AND (contract_no IS NULL OR TRIM(contract_no) = '')", current[i].UnitID, batchID).Error; err != nil {
					return err
				}
				deleted++
			}
		}
	}

	if err := s.unitRepo.CompactSlots(tx, batchID); err != nil {
		return err
	}
	if err := tx.Commit().Error; err != nil {
		return err
	}

	s.log(actor, "sync_stock_models", "batch", batchID, map[string]string{
		"created": fmt.Sprintf("%d", created),
		"deleted": fmt.Sprintf("%d", deleted),
	})
	s.wsHub.Broadcast("batch:updated", map[string]interface{}{"batch_id": batchID})
	return nil
}

func (s *BatchSvc) AssignToLine(batchID string, lineID string, actor string) (*FactoryPlanStatusUpdateStats, error) {
	tx := s.db.Begin()
	defer tx.Rollback()

	var line model.ProductionLine
	if err := tx.Where("line_id = ?", lineID).First(&line).Error; err != nil {
		return nil, fmt.Errorf("production line not found: %w", err)
	}

	b, err := s.batchRepo.LockBatchForUpdate(tx, batchID)
	if err != nil {
		return nil, fmt.Errorf("batch not found: %w", err)
	}
	if b.Status != model.StatusConfirmed {
		return nil, fmt.Errorf("batch %s status is %s, expected Confirmed", b.BatchID, b.Status)
	}
	if b.ProductionLineID != nil && strings.TrimSpace(*b.ProductionLineID) != "" {
		return nil, fmt.Errorf("batch %s is already assigned to line %s", b.BatchID, *b.ProductionLineID)
	}
	expectedRegion := engine.ProductionRegionForBatch(b.ModelType, b.Capacity)
	lineRegion := productionLineRegion(line)
	if expectedRegion == "" || lineRegion == "" || expectedRegion != lineRegion {
		return nil, fmt.Errorf("production line region mismatch: batch requires %s, line is %s", expectedRegion, lineRegion)
	}

	isSpecial := isSpecialBatchModel(b.ModelType)
	if line.Status != model.LineIdle {
		if !isSpecial {
			return nil, fmt.Errorf("line %s is not idle", lineID)
		}
		ok, err := s.lineHasOnlySpecialBatches(tx, lineID)
		if err != nil {
			return nil, err
		}
		if !ok {
			return nil, fmt.Errorf("line %s is busy with non-special batches", lineID)
		}
	}

	if err := s.batchRepo.AssignLine(tx, batchID, lineID); err != nil {
		return nil, err
	}
	lineUpdates := map[string]interface{}{
		"status": model.LineBusy,
	}
	if line.CurrentBatchID == nil || strings.TrimSpace(*line.CurrentBatchID) == "" {
		lineUpdates["current_batch_id"] = batchID
	}
	if err := tx.Model(&line).Updates(lineUpdates).Error; err != nil {
		return nil, err
	}

	// Sync all units in this batch to In_Production with the production line
	if err := tx.Model(&model.Unit{}).Where("batch_id = ?", batchID).Updates(map[string]interface{}{
		"status":             model.StatusInProduction,
		"production_line_id": lineID,
	}).Error; err != nil {
		return nil, err
	}

	// Cancel any existing active In_Production history for these units first (to avoid duplicates)
	if err := tx.Exec(`
UPDATE production_history_ledger 
SET status = 'Cancelled', completed_at = NOW()
WHERE status = 'In_Production' AND unit_id IN (SELECT unit_id FROM units WHERE batch_id = ?)
`, batchID).Error; err != nil {
		return nil, err
	}

	// Insert into production_history_ledger
	insertLedgerSQL := `
INSERT INTO production_history_ledger (
    unit_id,
    production_line_id,
    production_line_name,
    batch_code,
    model_type,
    contract_no,
    customer,
    dealer_name,
    order_remark,
    status,
    scheduled_at
)
SELECT 
    u.unit_id,
    u.production_line_id,
    pl.line_name,
    COALESCE(b.batch_code, CONCAT('第 ', b.batch_no, ' 批')),
    u.model_type,
    u.contract_no,
    u.customer,
    u.dealer_name,
    u.order_remark,
    'In_Production',
    NOW()
FROM units u
LEFT JOIN production_lines pl ON pl.line_id = u.production_line_id
LEFT JOIN batches b ON b.batch_id = u.batch_id
WHERE u.batch_id = ?
`
	if err := tx.Exec(insertLedgerSQL, batchID).Error; err != nil {
		return nil, fmt.Errorf("write production history ledger: %w", err)
	}

	// Sync factory_plan status by contract_no + model_type: 待规划 -> 已规划.
	type contractModelPair struct {
		ContractNo string `gorm:"column:contract_no"`
		ModelType  string `gorm:"column:model_type"`
	}
	var pairs []contractModelPair
	if err := tx.Raw(`
SELECT DISTINCT contract_no, model_type
FROM units
WHERE batch_id = ?
  AND contract_no IS NOT NULL
  AND TRIM(contract_no) <> ''
  AND model_type IS NOT NULL
  AND TRIM(model_type) <> ''`, batchID).Scan(&pairs).Error; err != nil {
		return nil, err
	}

	stats := &FactoryPlanStatusUpdateStats{Pairs: 0, Rows: 0}
	for _, pair := range pairs {
		cn := pair.ContractNo
		mt := pair.ModelType
		if cn == "" || mt == "" {
			continue
		}
		stats.Pairs++
		ret := tx.Exec("UPDATE factory_plan SET `状态` = '已规划' "+
			"WHERE `合同号` = ? AND `机型` COLLATE utf8mb4_general_ci = ? COLLATE utf8mb4_general_ci AND `状态` = '待规划'",
			cn, mt)
		if ret.Error != nil {
			return nil, ret.Error
		}
		stats.Rows += int(ret.RowsAffected)
	}

	if err := tx.Commit().Error; err != nil {
		return nil, err
	}

	s.log(actor, "assign_line", "production_line", lineID, map[string]string{
		"batch_id": batchID,
		"pairs":    fmt.Sprintf("%d", stats.Pairs),
		"rows":     fmt.Sprintf("%d", stats.Rows),
	})
	s.wsHub.Broadcast("line:updated", map[string]string{"line_id": lineID, "batch_id": batchID, "status": model.LineBusy})
	return stats, nil
}

func productionLineRegion(line model.ProductionLine) string {
	if line.Region != nil {
		if region := strings.ToUpper(strings.TrimSpace(*line.Region)); region == "SMALL" || region == "LARGE" || region == "SPECIAL" {
			return region
		}
	}
	text := strings.ToUpper(strings.TrimSpace(line.LineName))
	if line.ModelType != nil {
		text += " " + strings.ToUpper(strings.TrimSpace(*line.ModelType))
	}
	switch {
	case strings.Contains(text, "SPECIAL") || strings.Contains(text, "特殊"):
		return "SPECIAL"
	case strings.Contains(text, "LARGE") || strings.Contains(text, "中大型"):
		return "LARGE"
	case strings.Contains(text, "SMALL") || strings.Contains(text, "中小型"):
		return "SMALL"
	default:
		return ""
	}
}

func (s *BatchSvc) lineHasOnlySpecialBatches(tx *gorm.DB, lineID string) (bool, error) {
	var batches []model.Batch
	if err := tx.Where("production_line_id = ? AND status = ?", lineID, model.StatusInProduction).Find(&batches).Error; err != nil {
		return false, err
	}
	if len(batches) == 0 {
		return false, nil
	}
	for _, batch := range batches {
		if !isSpecialBatchModel(batch.ModelType) {
			return false, nil
		}
	}
	return true, nil
}

func isSpecialBatchModel(modelType string) bool {
	return strings.EqualFold(strings.TrimSpace(modelType), "SPECIAL")
}

func (s *BatchSvc) ManualComplete(lineID string, actor string) error {
	tx := s.db.Begin()
	defer tx.Rollback()

	var line model.ProductionLine
	if err := tx.Where("line_id = ?", lineID).First(&line).Error; err != nil {
		return fmt.Errorf("line not found: %w", err)
	}
	var batchIDs []string
	if err := tx.Model(&model.Batch{}).
		Where("production_line_id = ? AND status = ?", lineID, model.StatusInProduction).
		Pluck("batch_id", &batchIDs).Error; err != nil {
		return err
	}
	if len(batchIDs) == 0 && line.CurrentBatchID != nil && strings.TrimSpace(*line.CurrentBatchID) != "" {
		batchIDs = append(batchIDs, *line.CurrentBatchID)
	}
	if len(batchIDs) == 0 {
		return fmt.Errorf("line %s has no active batch", lineID)
	}

	if err := tx.Model(&model.Batch{}).Where("batch_id IN ?", batchIDs).Updates(map[string]interface{}{
		"status": model.StatusCompleted,
	}).Error; err != nil {
		return err
	}
	if err := tx.Model(&line).Updates(map[string]interface{}{
		"status":           model.LineIdle,
		"current_batch_id": nil,
	}).Error; err != nil {
		return err
	}

	// Sync all units in active batches to Completed, clear production_line_id.
	var unitIDs []string
	if err := tx.Model(&model.Unit{}).Where("batch_id IN ?", batchIDs).Pluck("unit_id", &unitIDs).Error; err != nil {
		return err
	}
	if err := tx.Model(&model.Unit{}).Where("unit_id IN ?", unitIDs).Updates(map[string]interface{}{
		"status":             model.StatusCompleted,
		"production_line_id": nil,
	}).Error; err != nil {
		return err
	}

	// Update history ledger status to Completed
	if err := tx.Exec(`
UPDATE production_history_ledger
SET status = 'Completed', completed_at = NOW()
WHERE status = 'In_Production' AND unit_id IN ?
`, unitIDs).Error; err != nil {
		return fmt.Errorf("update production history ledger to completed: %w", err)
	}

	if err := tx.Commit().Error; err != nil {
		return err
	}

	joinedBatchIDs := strings.Join(batchIDs, ",")
	s.log(actor, "manual_complete", "production_line", lineID, map[string]string{"batch_ids": joinedBatchIDs})
	s.wsHub.Broadcast("line:completed", map[string]string{"line_id": lineID, "batch_ids": joinedBatchIDs})
	return nil
}

func inboundBatchReady(progress inboundBatchProgress) bool {
	return progress.TotalUnits > 0 && progress.TotalUnits == progress.InboundUnits
}

func lineStateAfterBatchCompletion(currentBatchID *string, completedBatchID string, remainingBatchIDs []string) (string, *string) {
	if len(remainingBatchIDs) == 0 {
		return model.LineIdle, nil
	}
	if currentBatchID != nil {
		current := strings.TrimSpace(*currentBatchID)
		if current != "" && current != completedBatchID {
			for _, batchID := range remainingBatchIDs {
				if batchID == current {
					value := current
					return model.LineBusy, &value
				}
			}
		}
	}
	next := remainingBatchIDs[0]
	return model.LineBusy, &next
}

// ReconcileInboundBatches completes active batches once every unit has at least
// one immutable inbound_history event. Passing no serials scans all active batches.
func (s *BatchSvc) ReconcileInboundBatches(serialNos []string, actor string) ([]AutoCompletedBatch, error) {
	if !s.db.Migrator().HasTable("inbound_history") {
		return []AutoCompletedBatch{}, nil
	}

	serials := make([]string, 0, len(serialNos))
	seen := make(map[string]bool, len(serialNos))
	for _, raw := range serialNos {
		serial := strings.TrimSpace(raw)
		if serial == "" || seen[serial] {
			continue
		}
		seen[serial] = true
		serials = append(serials, serial)
	}

	query := s.db.Table("batches b").
		Select("DISTINCT b.batch_id").
		Joins("JOIN units u ON u.batch_id = b.batch_id").
		Where("b.status = ?", model.StatusInProduction)
	if len(serialNos) > 0 {
		if len(serials) == 0 {
			return []AutoCompletedBatch{}, nil
		}
		query = query.Where(`
COALESCE(NULLIF(TRIM(u.serial_no), ''), NULLIF(TRIM(u.forecast_serial_no), '')) IN ?
`, serials)
	}

	var batchIDs []string
	if err := query.Order("b.batch_id ASC").Pluck("b.batch_id", &batchIDs).Error; err != nil {
		return nil, err
	}

	completed := make([]AutoCompletedBatch, 0)
	for _, batchID := range batchIDs {
		result, err := s.autoCompleteInboundBatch(batchID, actor)
		if err != nil {
			return completed, err
		}
		if result != nil {
			completed = append(completed, *result)
		}
	}
	return completed, nil
}

func (s *BatchSvc) autoCompleteInboundBatch(batchID string, actor string) (*AutoCompletedBatch, error) {
	tx := s.db.Begin()
	defer tx.Rollback()

	var batch model.Batch
	if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Where("batch_id = ?", batchID).First(&batch).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			return nil, nil
		}
		return nil, err
	}
	if batch.Status != model.StatusInProduction || batch.ProductionLineID == nil || strings.TrimSpace(*batch.ProductionLineID) == "" {
		return nil, nil
	}
	lineID := strings.TrimSpace(*batch.ProductionLineID)

	var line model.ProductionLine
	if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Where("line_id = ?", lineID).First(&line).Error; err != nil {
		return nil, err
	}

	var progress inboundBatchProgress
	if err := tx.Raw(`
SELECT
    SUM(
        CASE
            WHEN COALESCE(NULLIF(TRIM(u.serial_no), ''), NULLIF(TRIM(u.forecast_serial_no), '')) IS NOT NULL
            THEN 1 ELSE 0
        END
    ) AS total_units,
    SUM(
        CASE
            WHEN COALESCE(NULLIF(TRIM(u.serial_no), ''), NULLIF(TRIM(u.forecast_serial_no), '')) IS NOT NULL
             AND EXISTS (
                SELECT 1
                FROM inbound_history ih
                WHERE TRIM(ih.serial_no) COLLATE utf8mb4_general_ci =
                      COALESCE(NULLIF(TRIM(u.serial_no), ''), NULLIF(TRIM(u.forecast_serial_no), '')) COLLATE utf8mb4_general_ci
             )
            THEN 1 ELSE 0
        END
    ) AS inbound_units
FROM units u
WHERE u.batch_id = ? AND u.status = ?
`, batchID, model.StatusInProduction).Scan(&progress).Error; err != nil {
		return nil, err
	}
	if !inboundBatchReady(progress) {
		return nil, nil
	}

	var unitIDs []string
	if err := tx.Model(&model.Unit{}).Where("batch_id = ? AND status = ?", batchID, model.StatusInProduction).Pluck("unit_id", &unitIDs).Error; err != nil {
		return nil, err
	}
	if err := tx.Model(&model.Batch{}).Where("batch_id = ? AND status = ?", batchID, model.StatusInProduction).Updates(map[string]interface{}{
		"status":     model.StatusCompleted,
		"updated_at": time.Now(),
	}).Error; err != nil {
		return nil, err
	}
	if err := tx.Model(&model.Unit{}).Where("unit_id IN ?", unitIDs).Updates(map[string]interface{}{
		"status":             model.StatusCompleted,
		"production_line_id": nil,
		"updated_at":         time.Now(),
	}).Error; err != nil {
		return nil, err
	}
	if err := tx.Exec(`
UPDATE production_history_ledger
SET status = 'Completed', completed_at = NOW(), updated_at = NOW()
WHERE status = 'In_Production' AND unit_id IN ?
`, unitIDs).Error; err != nil {
		return nil, fmt.Errorf("update production history ledger to completed: %w", err)
	}

	var remainingBatchIDs []string
	if err := tx.Model(&model.Batch{}).
		Where("production_line_id = ? AND status = ?", lineID, model.StatusInProduction).
		Order("batch_no ASC, batch_id ASC").
		Pluck("batch_id", &remainingBatchIDs).Error; err != nil {
		return nil, err
	}
	lineStatus, currentBatchID := lineStateAfterBatchCompletion(line.CurrentBatchID, batchID, remainingBatchIDs)
	if err := tx.Model(&line).Updates(map[string]interface{}{
		"status":           lineStatus,
		"current_batch_id": currentBatchID,
		"updated_at":       time.Now(),
	}).Error; err != nil {
		return nil, err
	}

	if strings.TrimSpace(actor) == "" {
		actor = "system"
	}
	batchCode := batchID
	if batch.BatchCode != nil && strings.TrimSpace(*batch.BatchCode) != "" {
		batchCode = strings.TrimSpace(*batch.BatchCode)
	}
	detailJSON, _ := json.Marshal(map[string]interface{}{
		"batch_code": batchCode,
		"line_id":    lineID,
		"unit_count": progress.TotalUnits,
		"reason":     "all_units_have_inbound_history",
	})
	if err := tx.Create(&model.OperationLog{
		Actor:      actor,
		Action:     "auto_complete_after_inbound",
		TargetType: "batch",
		TargetID:   batchID,
		Detail:     detailJSON,
		CreatedAt:  time.Now(),
	}).Error; err != nil {
		return nil, err
	}

	if err := tx.Commit().Error; err != nil {
		return nil, err
	}

	result := &AutoCompletedBatch{BatchID: batchID, BatchCode: batchCode, LineID: lineID, UnitCount: progress.TotalUnits}
	s.wsHub.Broadcast("batch:updated", result)
	s.wsHub.Broadcast("line:completed", map[string]interface{}{
		"line_id":   lineID,
		"batch_id":  batchID,
		"automatic": true,
	})
	return result, nil
}

func (s *BatchSvc) LockLineUnits(lineID string, unitIDs []string, orderRemark string, actor string) (int, error) {
	uniqueIDs := make([]string, 0, len(unitIDs))
	seen := make(map[string]bool, len(unitIDs))
	for _, id := range unitIDs {
		id = strings.TrimSpace(id)
		if id == "" || seen[id] {
			continue
		}
		seen[id] = true
		uniqueIDs = append(uniqueIDs, id)
	}
	if len(uniqueIDs) == 0 {
		return 0, fmt.Errorf("unit_ids is required")
	}

	tx := s.db.Begin()
	defer tx.Rollback()

	var line model.ProductionLine
	if err := tx.Where("line_id = ?", lineID).First(&line).Error; err != nil {
		return 0, fmt.Errorf("line not found: %w", err)
	}

	units, err := s.unitRepo.LockByIDs(tx, uniqueIDs)
	if err != nil {
		return 0, err
	}
	if len(units) != len(uniqueIDs) {
		return 0, fmt.Errorf("some units were not found")
	}
	for _, unit := range units {
		if unit.ProductionLineID == nil || *unit.ProductionLineID != lineID {
			return 0, fmt.Errorf("unit %s does not belong to line %s", unit.UnitID, lineID)
		}
		if unit.Status != model.StatusInProduction {
			return 0, fmt.Errorf("unit %s is not in production", unit.UnitID)
		}
	}

	if err := tx.Model(&model.Unit{}).Where("unit_id IN ?", uniqueIDs).Updates(map[string]interface{}{
		"order_remark": orderRemark,
		"is_locked":    true,
		"locked_by":    actor,
		"locked_at":    gorm.Expr("NOW()"),
		"updated_at":   gorm.Expr("NOW()"),
	}).Error; err != nil {
		return 0, err
	}

	// Sync remark update to production_history_ledger
	if err := tx.Exec(`
UPDATE production_history_ledger
SET order_remark = ?
WHERE status = 'In_Production' AND unit_id IN ?
`, orderRemark, uniqueIDs).Error; err != nil {
		return 0, fmt.Errorf("sync remark to production history ledger: %w", err)
	}

	if err := SyncFinishedGoodsByUnitIDs(tx, uniqueIDs); err != nil {
		return 0, fmt.Errorf("sync finished_goods: %w", err)
	}

	if err := tx.Commit().Error; err != nil {
		return 0, err
	}

	s.log(actor, "lock_line_units", "production_line", lineID, map[string]string{
		"unit_ids": strings.Join(uniqueIDs, ","),
		"count":    fmt.Sprintf("%d", len(uniqueIDs)),
	})
	s.wsHub.Broadcast("line:updated", map[string]interface{}{"line_id": lineID, "count": len(uniqueIDs)})
	return len(uniqueIDs), nil
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
