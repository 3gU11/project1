package repo

import (
	"fmt"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"smart-scheduling/server/internal/model"
)

type UnitRepo struct{ db *gorm.DB }

func NewUnitRepo(db *gorm.DB) *UnitRepo { return &UnitRepo{db: db} }

func (r *UnitRepo) CreateInTx(tx *gorm.DB, unit *model.Unit) error {
	return tx.Create(unit).Error
}

func (r *UnitRepo) CreateBatchInTx(tx *gorm.DB, units []model.Unit) error {
	if len(units) == 0 {
		return nil
	}
	return tx.Create(&units).Error
}

func (r *UnitRepo) GetByBatch(batchID string) ([]model.Unit, error) {
	var units []model.Unit
	return units, r.db.Where("batch_id = ?", batchID).Order("slot_index ASC").Find(&units).Error
}

func (r *UnitRepo) GetByID(unitID string) (*model.Unit, error) {
	var u model.Unit
	err := r.db.First(&u, "unit_id = ?", unitID).Error
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (r *UnitRepo) LockForUpdate(tx *gorm.DB, unitID string) (*model.Unit, error) {
	var u model.Unit
	err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("unit_id = ?", unitID).First(&u).Error
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (r *UnitRepo) LockByIDs(tx *gorm.DB, ids []string) ([]model.Unit, error) {
	var units []model.Unit
	err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("unit_id IN ?", ids).Find(&units).Error
	return units, err
}

func (r *UnitRepo) ListByBatchIDsForUpdate(tx *gorm.DB, batchIDs []string) ([]model.Unit, error) {
	if len(batchIDs) == 0 {
		return []model.Unit{}, nil
	}
	var units []model.Unit
	err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("batch_id IN ?", batchIDs).
		Order("batch_id ASC, slot_index ASC").
		Find(&units).Error
	return units, err
}

func (r *UnitRepo) UpdateOrderFields(tx *gorm.DB, unitID string, fields map[string]interface{}) error {
	return tx.Model(&model.Unit{}).Where("unit_id = ?", unitID).Updates(fields).Error
}

func (r *UnitRepo) ClearOrderFields(tx *gorm.DB, unitID string) error {
	return tx.Model(&model.Unit{}).Where("unit_id = ?", unitID).Updates(map[string]interface{}{
		"contract_no": nil, "customer": nil, "dealer_id": nil,
		"dealer_name": nil, "due_date": nil, "sales_id": nil, "order_remark": nil,
	}).Error
}

func (r *UnitRepo) MoveToBatch(tx *gorm.DB, unitID string, newBatchID string, newSlot int) error {
	return tx.Model(&model.Unit{}).Where("unit_id = ?", unitID).Updates(map[string]interface{}{
		"batch_id":   newBatchID,
		"slot_index": newSlot,
	}).Error
}

func (r *UnitRepo) LockUnit(tx *gorm.DB, unitID string, lockedBy string) error {
	return tx.Model(&model.Unit{}).Where("unit_id = ?", unitID).Updates(map[string]interface{}{
		"is_locked": true, "locked_by": lockedBy, "locked_at": gorm.Expr("NOW()"),
	}).Error
}

func (r *UnitRepo) UnlockUnitDB(tx *gorm.DB, unitID string) error {
	return tx.Model(&model.Unit{}).Where("unit_id = ?", unitID).Updates(map[string]interface{}{
		"is_locked": false, "locked_by": nil, "locked_at": nil,
	}).Error
}

func (r *UnitRepo) FindEmptyContainers(modelType string) ([]model.Unit, error) {
	var units []model.Unit
	err := r.db.Where("status = ?", "Pending").
		Where("contract_no IS NULL").
		Where("model_type = ?", modelType).
		Where("is_locked = ?", false).
		Order("slot_index ASC").Limit(50).Find(&units).Error
	return units, err
}

func (r *UnitRepo) DeleteByBatchIDs(tx *gorm.DB, batchIDs []string) error {
	if len(batchIDs) == 0 {
		return nil
	}
	return tx.Where("batch_id IN ?", batchIDs).Delete(&model.Unit{}).Error
}

func (r *UnitRepo) ReSlotBatch(tx *gorm.DB, batchID string) error {
	var units []model.Unit
	if err := tx.Where("batch_id = ?", batchID).Order("slot_index ASC").Find(&units).Error; err != nil {
		return err
	}
	for i := range units {
		newSlot := i + 1
		targetID := fmt.Sprintf("%s-S%02d", batchID, newSlot)
		if err := tx.Model(&units[i]).Updates(map[string]interface{}{
			"slot_index": newSlot,
			"unit_id":    targetID,
		}).Error; err != nil {
			return err
		}
	}
	return nil
}

func (r *UnitRepo) GetMaxSlotInBatch(tx *gorm.DB, batchID string) (int, error) {
	var maxSlot int
	err := tx.Model(&model.Unit{}).Where("batch_id = ?", batchID).
		Select("COALESCE(MAX(slot_index), 0)").Scan(&maxSlot).Error
	return maxSlot, err
}

func (r *UnitRepo) CountByBatch(tx *gorm.DB, batchID string) (int64, error) {
	var count int64
	err := tx.Model(&model.Unit{}).Where("batch_id = ?", batchID).Count(&count).Error
	return count, err
}

// ShiftSlots increments slot_index by delta for all units in batch with slot_index >= fromSlot.
func (r *UnitRepo) ShiftSlots(tx *gorm.DB, batchID string, fromSlot int, delta int) error {
	if delta == 0 {
		return nil
	}
	var units []model.Unit
	if err := tx.Where("batch_id = ? AND slot_index >= ?", batchID, fromSlot).
		Order("slot_index ASC").
		Find(&units).Error; err != nil {
		return err
	}
	if len(units) == 0 {
		return nil
	}
	for i := range units {
		if err := tx.Model(&model.Unit{}).
			Where("unit_id = ?", units[i].UnitID).
			Update("slot_index", 1000000+i).Error; err != nil {
			return err
		}
	}
	for i := range units {
		if err := tx.Model(&model.Unit{}).
			Where("unit_id = ?", units[i].UnitID).
			Update("slot_index", units[i].SlotIndex+delta).Error; err != nil {
			return err
		}
	}
	return nil
}

// CompactSlots renumbers slot_index sequentially (1,2,3...) within a batch without changing unit_ids.
func (r *UnitRepo) CompactSlots(tx *gorm.DB, batchID string) error {
	var units []model.Unit
	if err := tx.Where("batch_id = ?", batchID).Order("slot_index ASC").Find(&units).Error; err != nil {
		return err
	}
	for i := range units {
		newSlot := i + 1
		if units[i].SlotIndex != newSlot {
			if err := tx.Model(&units[i]).Update("slot_index", newSlot).Error; err != nil {
				return err
			}
		}
	}
	return nil
}

func (r *UnitRepo) ReorderBatchWithUnit(tx *gorm.DB, batchID string, unitID string, targetSlot int) error {
	var units []model.Unit
	if err := tx.Where("batch_id = ?", batchID).
		Where("unit_id <> ?", unitID).
		Order("slot_index ASC").
		Find(&units).Error; err != nil {
		return err
	}

	if targetSlot < 1 {
		targetSlot = len(units) + 1
	}
	if targetSlot > len(units)+1 {
		targetSlot = len(units) + 1
	}

	ordered := make([]string, 0, len(units)+1)
	insertIdx := targetSlot - 1
	for i, u := range units {
		if i == insertIdx {
			ordered = append(ordered, unitID)
		}
		ordered = append(ordered, u.UnitID)
	}
	if insertIdx >= len(units) {
		ordered = append(ordered, unitID)
	}

	// Move rows out of the unique slot range before assigning final contiguous slots.
	for i, id := range ordered {
		if err := tx.Model(&model.Unit{}).
			Where("unit_id = ?", id).
			Update("slot_index", 100000+i).Error; err != nil {
			return err
		}
	}
	for i, id := range ordered {
		if err := tx.Model(&model.Unit{}).
			Where("unit_id = ?", id).
			Update("slot_index", i+1).Error; err != nil {
			return err
		}
	}
	return nil
}

func (r *UnitRepo) RewriteBatchAssignments(tx *gorm.DB, assignments map[string][]string) error {
	unitIDs := make([]string, 0)
	seen := map[string]bool{}
	for _, ids := range assignments {
		for _, id := range ids {
			if seen[id] {
				continue
			}
			seen[id] = true
			unitIDs = append(unitIDs, id)
		}
	}

	for i, id := range unitIDs {
		if err := tx.Model(&model.Unit{}).
			Where("unit_id = ?", id).
			Update("slot_index", 100000+i).Error; err != nil {
			return err
		}
	}

	for batchID, ids := range assignments {
		for i, id := range ids {
			if err := tx.Model(&model.Unit{}).
				Where("unit_id = ?", id).
				Updates(map[string]interface{}{
					"batch_id":   batchID,
					"slot_index": i + 1,
				}).Error; err != nil {
				return err
			}
		}
	}
	return nil
}
