package repo

import (
	"fmt"
	"strings"

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
	err := r.db.Table("units").
		Select(`
			units.*, 
			md.model_family AS model_family, 
			fg.状态 AS fg_status,
			fg.合同备注 AS fg_remark,
			fg.机型 AS fg_model,
			fg.合同号 AS fg_contract_no,
			fg.客户 AS fg_customer,
			fg.代理商 AS fg_dealer,
			fg.占用订单号 AS fg_sales_id
		`).
		Joins("LEFT JOIN model_dictionary md ON md.model_name = units.model_type COLLATE utf8mb4_general_ci").
		Joins("LEFT JOIN finished_goods_data fg ON fg.流水号 = COALESCE(units.serial_no, units.forecast_serial_no) COLLATE utf8mb4_general_ci").
		Where("units.batch_id = ?", batchID).
		Order("units.slot_index ASC").
		Find(&units).Error
	if err == nil {
		for i := range units {
			r.mergeFgInfo(&units[i])
		}
	}
	return units, err
}

func (r *UnitRepo) GetByID(unitID string) (*model.Unit, error) {
	var u model.Unit
	err := r.db.Table("units").
		Select(`
			units.*,
			fg.状态 AS fg_status,
			fg.合同备注 AS fg_remark,
			fg.机型 AS fg_model,
			fg.合同号 AS fg_contract_no,
			fg.客户 AS fg_customer,
			fg.代理商 AS fg_dealer,
			fg.占用订单号 AS fg_sales_id
		`).
		Joins("LEFT JOIN finished_goods_data fg ON fg.流水号 = COALESCE(units.serial_no, units.forecast_serial_no) COLLATE utf8mb4_general_ci").
		Where("units.unit_id = ?", unitID).
		First(&u).Error
	if err != nil {
		return nil, err
	}
	r.mergeFgInfo(&u)
	return &u, nil
}

func (r *UnitRepo) mergeFgInfo(u *model.Unit) {
	// Support both bound serial_no and predicted forecast_serial_no
	hasSN := u.SerialNo != nil && *u.SerialNo != ""
	hasForecast := u.ForecastSerialNo != nil && *u.ForecastSerialNo != ""
	
	if !hasSN && !hasForecast {
		return
	}
	// IF it's linked to an SN/ForecastSN, the Main System (FG) is the source of truth.
	// We override even if FG info is empty, because the user expects the Kanban to match the Main System.
	if u.FgRemark != nil {
		u.OrderRemark = u.FgRemark
	}
	if u.FgModel != nil && strings.TrimSpace(*u.FgModel) != "" {
		u.ModelType = *u.FgModel
	}
	if u.FgContractNo != nil {
		u.ContractNo = u.FgContractNo
	}
	if u.FgCustomer != nil {
		u.Customer = u.FgCustomer
	}
	if u.FgDealer != nil {
		u.DealerName = u.FgDealer
	}
	if u.FgSalesID != nil {
		u.SalesID = u.FgSalesID
	}
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
