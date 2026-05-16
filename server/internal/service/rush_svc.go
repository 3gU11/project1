package service

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"smart-scheduling/server/internal/engine"
	"smart-scheduling/server/internal/model"
	"smart-scheduling/server/internal/repo"
	"smart-scheduling/server/internal/ws"
)

type RushSvc struct {
	db        *gorm.DB
	unitRepo  *repo.UnitRepo
	batchRepo *repo.BatchRepo
	wsHub     *ws.Hub
}

func NewRushSvc(db *gorm.DB, ur *repo.UnitRepo, br *repo.BatchRepo, hub *ws.Hub) *RushSvc {
	return &RushSvc{db: db, unitRepo: ur, batchRepo: br, wsHub: hub}
}

type RushInsertReq struct {
	Mode           string `json:"mode"`
	TargetUnitID   string `json:"target_unit_id"`
	FallbackUnitID string `json:"fallback_unit_id"`
	RushOrder      struct {
		ContractNo string `json:"contract_no" binding:"required"`
		Customer   string `json:"customer"`
		ModelType  string `json:"model_type" binding:"required"`
		DealerName string `json:"dealer_name"`
		DueDate    string `json:"due_date"`
		Remark     string `json:"remark"`
	} `json:"rush_order" binding:"required"`
	Reason string `json:"reason"`
}

type SwapContentReq struct {
	SourceUnitID   string `json:"source_unit_id" binding:"required"`
	TargetUnitID   string `json:"target_unit_id" binding:"required"`
	FallbackUnitID string `json:"fallback_unit_id" binding:"required"`
}

func (s *RushSvc) RushInsert(req RushInsertReq, actor string) error {
	mode := strings.ToLower(strings.TrimSpace(req.Mode))
	if mode == "auto" {
		return s.rushInsertAuto(req, actor)
	}
	if strings.TrimSpace(req.TargetUnitID) == "" {
		return fmt.Errorf("target_unit_id is required for manual mode")
	}
	return s.rushInsertManual(req, actor)
}

type orderPayload struct {
	ContractNo  string
	Customer    string
	DealerName  string
	DueDate     *time.Time
	SalesID     *string
	OrderRemark *string
	ModelType   string
}

func (s *RushSvc) rushInsertAuto(req RushInsertReq, actor string) error {
	targetModel := strings.TrimSpace(req.RushOrder.ModelType)
	if targetModel == "" {
		return fmt.Errorf("invalid rush model type")
	}

	tx := s.db.Begin()
	defer tx.Rollback()
	family, err := s.resolveBatchFamily(tx, targetModel)
	if err != nil {
		return fmt.Errorf("resolve rush model family: %w", err)
	}
	if family == "" {
		return fmt.Errorf("invalid rush model type")
	}
	affectedUnitIDs := map[string]struct{}{}

	isHigh := strings.Contains(req.RushOrder.Remark, "加高")

	var chain []model.Unit
	if !isHigh {
		// 1) Build production chain by exact model, ordered by earliest batch line then next lines.
		chain, err = s.loadProductionModelChain(tx, family, targetModel)
		if err != nil {
			return fmt.Errorf("load production model chain: %w", err)
		}
	}

	var dueDate *time.Time
	if strings.TrimSpace(req.RushOrder.DueDate) != "" {
		if d, e := time.Parse("2006-01-02", req.RushOrder.DueDate); e == nil {
			dueDate = &d
		}
	}
	carry := orderPayload{
		ContractNo: strings.TrimSpace(req.RushOrder.ContractNo),
		Customer:   strings.TrimSpace(req.RushOrder.Customer),
		DealerName: strings.TrimSpace(req.RushOrder.DealerName),
		DueDate:    dueDate,
		ModelType:  targetModel,
	}
	if remark := strings.TrimSpace(req.RushOrder.Remark); remark != "" {
		carry.OrderRemark = &remark
	}
	if carry.ContractNo == "" {
		return fmt.Errorf("rush contract_no is required")
	}

	overflow := (*orderPayload)(nil)
	if len(chain) > 0 {
		for i := range chain {
			u := chain[i]
			if u.IsLocked {
				return fmt.Errorf("unit is locked: %s", u.UnitID)
			}
			next := orderPayload{}
			if u.ContractNo != nil && strings.TrimSpace(*u.ContractNo) != "" {
				next.ContractNo = strings.TrimSpace(*u.ContractNo)
				next.Customer = strings.TrimSpace(strPtrVal(u.Customer))
				next.DealerName = strings.TrimSpace(strPtrVal(u.DealerName))
				next.DueDate = u.DueDate
				next.SalesID = u.SalesID
				next.OrderRemark = u.OrderRemark
				next.ModelType = strings.TrimSpace(u.ModelType)
			}

			updates := map[string]interface{}{
				"contract_no":  carry.ContractNo,
				"customer":     carry.Customer,
				"dealer_name":  carry.DealerName,
				"due_date":     carry.DueDate,
				"sales_id":     carry.SalesID,
				"order_remark": carry.OrderRemark,
				"model_type":   carry.ModelType,
				"is_locked":    false,
				"locked_by":    nil,
				"locked_at":    nil,
			}
			if err := s.unitRepo.UpdateOrderFields(tx, u.UnitID, updates); err != nil {
				return fmt.Errorf("write rush chain: %w", err)
			}
			affectedUnitIDs[u.UnitID] = struct{}{}

			if next.ContractNo == "" {
				overflow = nil
				break
			}
			carry = next
			if i == len(chain)-1 {
				tmp := carry
				overflow = &tmp
			}
		}
	} else {
		tmp := carry
		overflow = &tmp
	}

	// 2) If overflow exists, insert into sandbox first predicted batch of same family.
	if overflow != nil && overflow.ContractNo != "" {
		chain2, err := s.loadSandboxModelChain(tx, family, targetModel)
		if err != nil {
			return fmt.Errorf("load sandbox chain: %w", err)
		}
		if len(chain2) == 0 {
			if err := s.enqueueOverflow(tx, family, overflow); err != nil {
				return fmt.Errorf("enqueue overflow: %w", err)
			}
		} else {
			c2 := *overflow
			for i := range chain2 {
				u := chain2[i]
				if u.IsLocked {
					return fmt.Errorf("sandbox unit locked: %s", u.UnitID)
				}
				next := orderPayload{}
				if u.ContractNo != nil && strings.TrimSpace(*u.ContractNo) != "" {
					next.ContractNo = strings.TrimSpace(*u.ContractNo)
					next.Customer = strings.TrimSpace(strPtrVal(u.Customer))
					next.DealerName = strings.TrimSpace(strPtrVal(u.DealerName))
					next.DueDate = u.DueDate
					next.SalesID = u.SalesID
					next.OrderRemark = u.OrderRemark
					next.ModelType = strings.TrimSpace(u.ModelType)
				}
				updates := map[string]interface{}{
					"contract_no":  c2.ContractNo,
					"customer":     c2.Customer,
					"dealer_name":  c2.DealerName,
					"due_date":     c2.DueDate,
					"sales_id":     c2.SalesID,
					"order_remark": c2.OrderRemark,
					"model_type":   c2.ModelType,
					"is_locked":    false,
					"locked_by":    nil,
					"locked_at":    nil,
				}
				if err := s.unitRepo.UpdateOrderFields(tx, u.UnitID, updates); err != nil {
					return fmt.Errorf("write sandbox chain: %w", err)
				}
				affectedUnitIDs[u.UnitID] = struct{}{}
				if next.ContractNo == "" {
					c2.ContractNo = ""
					break
				}
				c2 = next
				if i == len(chain2)-1 {
					if err := s.enqueueOverflow(tx, family, &c2); err != nil {
						return fmt.Errorf("enqueue tail overflow: %w", err)
					}
				}
			}
		}
	}

	// Only lock the rush landing card, do not lock the whole shifted chain.
	if !isHigh && len(chain) > 0 {
		for i := 1; i < len(chain); i++ {
			if err := s.unitRepo.UnlockUnitDB(tx, chain[i].UnitID); err != nil {
				return fmt.Errorf("unlock shifted unit: %w", err)
			}
		}
		if err := s.unitRepo.LockUnit(tx, chain[0].UnitID, actor); err != nil {
			return fmt.Errorf("lock rush landing unit: %w", err)
		}
	}

	// For high rush orders, chain is empty, they go to sandbox directly. We should log chain2 instead if applicable.
	targetUnitIDForLog := ""
	if !isHigh && len(chain) > 0 {
		targetUnitIDForLog = chain[0].UnitID
	} else {
		// Attempt to get sandbox landing unit id
		chain2, err := s.loadSandboxModelChain(tx, family, targetModel)
		if err == nil && len(chain2) > 0 {
			targetUnitIDForLog = chain2[0].UnitID
			// Also lock the first card in sandbox
			if err := s.unitRepo.LockUnit(tx, targetUnitIDForLog, actor); err != nil {
				return fmt.Errorf("lock rush landing unit in sandbox: %w", err)
			}
		}
	}

	detail, _ := json.Marshal(map[string]interface{}{
		"mode":          "auto",
		"rush_contract": req.RushOrder.ContractNo,
		"family":        family,
	})
	tx.Create(&model.OperationLog{
		Actor: actor, Action: "rush_insert_auto", TargetType: "unit",
		TargetID: targetUnitIDForLog, Detail: detail, CreatedAt: time.Now(),
	})
	if err := s.markRushContractPlanned(tx, req.RushOrder.ContractNo, req.RushOrder.ModelType); err != nil {
		return fmt.Errorf("mark rush contract planned: %w", err)
	}
	if err := SyncFinishedGoodsByUnitIDs(tx, mapKeys(affectedUnitIDs)); err != nil {
		return fmt.Errorf("sync finished_goods_data: %w", err)
	}

	if err := tx.Commit().Error; err != nil {
		return fmt.Errorf("commit: %w", err)
	}
	s.wsHub.Broadcast("unit:updated", map[string]interface{}{"mode": "auto"})
	return nil
}

func (s *RushSvc) rushInsertManual(req RushInsertReq, actor string) error {
	targetModel := strings.TrimSpace(req.RushOrder.ModelType)
	if targetModel == "" {
		return fmt.Errorf("invalid rush model type")
	}

	tx := s.db.Begin()
	defer tx.Rollback()
	family, err := s.resolveBatchFamily(tx, targetModel)
	if err != nil {
		return fmt.Errorf("resolve rush model family: %w", err)
	}
	if family == "" {
		return fmt.Errorf("invalid rush model type")
	}
	affectedUnitIDs := map[string]struct{}{}

	isHigh := strings.Contains(req.RushOrder.Remark, "加高")

	target, err := s.unitRepo.LockForUpdate(tx, req.TargetUnitID)
	if err != nil {
		return fmt.Errorf("target unit not found")
	}
	if target.IsLocked {
		return fmt.Errorf("target unit is locked")
	}
	targetFamily, err := s.resolveBatchFamily(tx, target.ModelType)
	if err != nil {
		return fmt.Errorf("resolve target model family: %w", err)
	}
	if targetFamily != family {
		return fmt.Errorf("model type mismatch")
	}

	var chain []model.Unit
	start := -1
	if !isHigh {
		// Build the chain using the TARGET unit's own model_type so we can locate it.
		// (The rush order's model_type may differ within the same family, e.g. FR-400XS vs FR-500XS.)
		// The carry's ModelType (rush order model) will still be written into the target slot.
		chainModel := strings.TrimSpace(target.ModelType)
		if chainModel == "" {
			chainModel = targetModel
		}
		chain, err = s.loadProductionModelChain(tx, family, chainModel)
		if err != nil && err.Error() != "target model is empty" {
			// ignore non-fatal errors
		}
		for i := range chain {
			if chain[i].UnitID == req.TargetUnitID {
				start = i
				break
			}
		}
	}

	var chain2 []model.Unit
	start2 := -1
	if start < 0 {
		chain2, err = s.loadSandboxModelChain(tx, family, targetModel)
		if err != nil {
			return fmt.Errorf("load sandbox chain: %w", err)
		}
		for i := range chain2 {
			if chain2[i].UnitID == req.TargetUnitID {
				start2 = i
				break
			}
		}
		if start2 < 0 {
			if isHigh {
				return fmt.Errorf("加高急单不能插入到生产看板（生产中）的定死机台中，请插入沙盘批次")
			}
			return fmt.Errorf("target unit not found in any valid chain")
		}
	}

	var dueDate *time.Time
	if strings.TrimSpace(req.RushOrder.DueDate) != "" {
		if d, e := time.Parse("2006-01-02", req.RushOrder.DueDate); e == nil {
			dueDate = &d
		}
	}
	carry := orderPayload{
		ContractNo: strings.TrimSpace(req.RushOrder.ContractNo),
		Customer:   strings.TrimSpace(req.RushOrder.Customer),
		DealerName: strings.TrimSpace(req.RushOrder.DealerName),
		DueDate:    dueDate,
		ModelType:  targetModel,
	}
	if remark := strings.TrimSpace(req.RushOrder.Remark); remark != "" {
		carry.OrderRemark = &remark
	}
	if carry.ContractNo == "" {
		return fmt.Errorf("rush contract_no is required")
	}

	overflow := (*orderPayload)(nil)
	if start >= 0 {
		for i := start; i < len(chain); i++ {
			u := chain[i]
			if u.IsLocked {
				return fmt.Errorf("unit is locked: %s", u.UnitID)
			}
			next := orderPayload{}
			if u.ContractNo != nil && strings.TrimSpace(*u.ContractNo) != "" {
				next.ContractNo = strings.TrimSpace(*u.ContractNo)
				next.Customer = strings.TrimSpace(strPtrVal(u.Customer))
				next.DealerName = strings.TrimSpace(strPtrVal(u.DealerName))
				next.DueDate = u.DueDate
				next.SalesID = u.SalesID
				next.OrderRemark = u.OrderRemark
				next.ModelType = strings.TrimSpace(u.ModelType)
			}
			updates := map[string]interface{}{
				"contract_no":  carry.ContractNo,
				"customer":     carry.Customer,
				"dealer_name":  carry.DealerName,
				"due_date":     carry.DueDate,
				"sales_id":     carry.SalesID,
				"order_remark": carry.OrderRemark,
				"model_type":   carry.ModelType,
				"is_locked":    false,
				"locked_by":    nil,
				"locked_at":    nil,
			}
			if err := s.unitRepo.UpdateOrderFields(tx, u.UnitID, updates); err != nil {
				return fmt.Errorf("write manual rush chain: %w", err)
			}
			affectedUnitIDs[u.UnitID] = struct{}{}
			if next.ContractNo == "" {
				overflow = nil
				break
			}
			carry = next
			if i == len(chain)-1 {
				tmp := carry
				overflow = &tmp
			}
		}
	} else {
		tmp := carry
		overflow = &tmp
	}

	if overflow != nil && overflow.ContractNo != "" {
		if len(chain2) == 0 {
			chain2, err = s.loadSandboxModelChain(tx, family, targetModel)
			if err != nil {
				return fmt.Errorf("load sandbox chain: %w", err)
			}
		}
		if len(chain2) == 0 {
			if err := s.enqueueOverflow(tx, family, overflow); err != nil {
				return fmt.Errorf("enqueue overflow: %w", err)
			}
		} else {
			c2 := *overflow
			startIndex := 0
			if start2 >= 0 {
				startIndex = start2
			}
			for i := startIndex; i < len(chain2); i++ {
				u := chain2[i]
				if u.IsLocked {
					return fmt.Errorf("sandbox unit locked: %s", u.UnitID)
				}
				next := orderPayload{}
				if u.ContractNo != nil && strings.TrimSpace(*u.ContractNo) != "" {
					next.ContractNo = strings.TrimSpace(*u.ContractNo)
					next.Customer = strings.TrimSpace(strPtrVal(u.Customer))
					next.DealerName = strings.TrimSpace(strPtrVal(u.DealerName))
					next.DueDate = u.DueDate
					next.SalesID = u.SalesID
					next.OrderRemark = u.OrderRemark
					next.ModelType = strings.TrimSpace(u.ModelType)
				}
				updates := map[string]interface{}{
					"contract_no":  c2.ContractNo,
					"customer":     c2.Customer,
					"dealer_name":  c2.DealerName,
					"due_date":     c2.DueDate,
					"sales_id":     c2.SalesID,
					"order_remark": c2.OrderRemark,
					"model_type":   c2.ModelType,
					"is_locked":    false,
					"locked_by":    nil,
					"locked_at":    nil,
				}
				if err := s.unitRepo.UpdateOrderFields(tx, u.UnitID, updates); err != nil {
					return fmt.Errorf("write sandbox chain: %w", err)
				}
				affectedUnitIDs[u.UnitID] = struct{}{}
				if next.ContractNo == "" {
					c2.ContractNo = ""
					break
				}
				c2 = next
				if i == len(chain2)-1 {
					if err := s.enqueueOverflow(tx, family, &c2); err != nil {
						return fmt.Errorf("enqueue tail overflow: %w", err)
					}
				}
			}
		}
	}

	// Only lock the rush landing card, do not lock the whole shifted chain.
	if start >= 0 && start < len(chain) {
		for i := start + 1; i < len(chain); i++ {
			if err := s.unitRepo.UnlockUnitDB(tx, chain[i].UnitID); err != nil {
				return fmt.Errorf("unlock shifted unit: %w", err)
			}
		}
		if err := s.unitRepo.LockUnit(tx, chain[start].UnitID, actor); err != nil {
			return fmt.Errorf("lock rush landing unit: %w", err)
		}
	} else if start2 >= 0 && start2 < len(chain2) {
		for i := start2 + 1; i < len(chain2); i++ {
			if err := s.unitRepo.UnlockUnitDB(tx, chain2[i].UnitID); err != nil {
				return fmt.Errorf("unlock shifted unit: %w", err)
			}
		}
		if err := s.unitRepo.LockUnit(tx, chain2[start2].UnitID, actor); err != nil {
			return fmt.Errorf("lock rush landing unit: %w", err)
		}
	}

	detail, _ := json.Marshal(map[string]interface{}{
		"mode":          "manual",
		"target":        req.TargetUnitID,
		"rush_contract": req.RushOrder.ContractNo,
		"family":        family,
	})
	tx.Create(&model.OperationLog{
		Actor: actor, Action: "rush_insert_manual_shift", TargetType: "unit",
		TargetID: req.TargetUnitID, Detail: detail, CreatedAt: time.Now(),
	})
	if err := s.markRushContractPlanned(tx, req.RushOrder.ContractNo, req.RushOrder.ModelType); err != nil {
		return fmt.Errorf("mark rush contract planned: %w", err)
	}
	if err := SyncFinishedGoodsByUnitIDs(tx, mapKeys(affectedUnitIDs)); err != nil {
		return fmt.Errorf("sync finished_goods_data: %w", err)
	}
	if err := tx.Commit().Error; err != nil {
		return fmt.Errorf("commit: %w", err)
	}
	s.wsHub.Broadcast("unit:updated", map[string]interface{}{"mode": "manual"})
	return nil
}

func (s *RushSvc) loadProductionModelChain(tx *gorm.DB, family, targetModel string) ([]model.Unit, error) {
	normalizedModel := strings.TrimSpace(targetModel)
	if normalizedModel == "" {
		return nil, fmt.Errorf("target model is empty")
	}

	// Production chain: exact model only, earliest in-production batches first.
	var units []model.Unit
	err := tx.Model(&model.Unit{}).
		Select("units.*").
		Clauses(clause.Locking{Strength: "UPDATE"}).
		Joins("JOIN batches b ON b.batch_id = units.batch_id").
		Joins("LEFT JOIN production_lines pl ON pl.line_id = b.production_line_id").
		Where("b.model_type = ?", family).
		Where("b.status = ?", model.StatusInProduction).
		Where("units.is_locked = ?", false).
		Where("TRIM(units.model_type) = ?", normalizedModel).
		Order("COALESCE(pl.display_order, 999999) ASC").
		Order("b.batch_no ASC").
		Order("units.slot_index ASC").
		Find(&units).Error
	if err != nil {
		return nil, err
	}
	return units, nil
}

func (s *RushSvc) resolveBatchFamily(tx *gorm.DB, modelType string) (string, error) {
	modelName := strings.TrimSpace(modelType)
	if modelName == "" {
		return "", nil
	}

	var row struct {
		ModelFamily string `gorm:"column:model_family"`
	}
	if err := tx.Table("model_dictionary").
		Select("model_family").
		Where("enabled = 1").
		Where("UPPER(TRIM(model_name)) = UPPER(?)", modelName).
		Limit(1).
		Scan(&row).Error; err != nil {
		return "", err
	}

	familyRaw := strings.TrimSpace(row.ModelFamily)
	family := strings.ToUpper(familyRaw)
	if family == "SPECIAL" || familyRaw == "特殊" {
		return "SPECIAL", nil
	}
	if strings.Contains(familyRaw, "G") {
		return "G", nil
	}
	if strings.Contains(familyRaw, "XS") {
		return "XS", nil
	}
	if strings.Contains(familyRaw, "AUTO") {
		return "AUTO", nil
	}
	if family == "G" || family == "XS" || family == "AUTO" {
		return family, nil
	}
	return engine.NormalizeModelType(modelName), nil
}

func (s *RushSvc) loadSandboxModelChain(tx *gorm.DB, family, targetModel string) ([]model.Unit, error) {
	normalizedModel := strings.TrimSpace(targetModel)
	isHighModel := strings.Contains(normalizedModel, "加高")

	// Sandbox insertion starts from first confirmed or predicted batch in the same family.
	var units []model.Unit
	q := tx.Model(&model.Unit{}).
		Select("units.*").
		Clauses(clause.Locking{Strength: "UPDATE"}).
		Joins("JOIN batches b ON b.batch_id = units.batch_id").
		Where("b.model_type = ?", family).
		Where("b.status IN ?", []string{model.StatusConfirmed, model.StatusPredicted}).
		Where("units.is_locked = ?", false).
		Order("CASE WHEN b.status = 'Confirmed' THEN 0 ELSE 1 END ASC").
		Order("b.batch_no ASC").
		Order(clause.Expr{SQL: "CASE WHEN TRIM(units.model_type) = ? THEN 0 ELSE 1 END ASC", Vars: []interface{}{normalizedModel}}).
		Order("units.slot_index ASC")
	if normalizedModel != "" && !isHighModel {
		q = q.Where("(TRIM(units.model_type) = ? OR units.model_type = ?)", normalizedModel, family)
	} else if normalizedModel == "" {
		q = q.Where("units.model_type = ?", family)
	}
	err := q.Find(&units).Error
	if err != nil {
		return nil, err
	}
	return units, nil
}

func (s *RushSvc) SwapContent(req SwapContentReq, actor string) error {
	tx := s.db.Begin()
	defer tx.Rollback()

	var units []model.Unit
	err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("unit_id IN ?", []string{req.SourceUnitID, req.TargetUnitID, req.FallbackUnitID}).
		Find(&units).Error
	if err != nil {
		return fmt.Errorf("lock units: %w", err)
	}

	if len(units) < 3 {
		return fmt.Errorf("one or more units not found")
	}

	var source, target, fallback *model.Unit
	for i := range units {
		switch units[i].UnitID {
		case req.SourceUnitID:
			source = &units[i]
		case req.TargetUnitID:
			target = &units[i]
		case req.FallbackUnitID:
			fallback = &units[i]
		}
	}

	if target.IsLocked {
		return fmt.Errorf("target unit is locked")
	}
	if fallback.ContractNo != nil && *fallback.ContractNo != "" {
		return fmt.Errorf("fallback unit is not empty")
	}

	sourceMT := engine.NormalizeModelType(source.ModelType)
	targetMT := engine.NormalizeModelType(target.ModelType)
	fallbackMT := engine.NormalizeModelType(fallback.ModelType)
	if sourceMT != targetMT || targetMT != fallbackMT {
		return fmt.Errorf("model type mismatch")
	}

	// Move target order to fallback first
	if target.ContractNo != nil && *target.ContractNo != "" {
		if err := s.unitRepo.UpdateOrderFields(tx, req.FallbackUnitID, map[string]interface{}{
			"contract_no":  *target.ContractNo,
			"customer":     target.Customer,
			"dealer_id":    target.DealerID,
			"dealer_name":  target.DealerName,
			"due_date":     target.DueDate,
			"sales_id":     target.SalesID,
			"order_remark": target.OrderRemark,
		}); err != nil {
			return err
		}
	}

	// Move source order to target
	if err := s.unitRepo.UpdateOrderFields(tx, req.TargetUnitID, map[string]interface{}{
		"contract_no":  *source.ContractNo,
		"customer":     source.Customer,
		"dealer_id":    source.DealerID,
		"dealer_name":  source.DealerName,
		"due_date":     source.DueDate,
		"sales_id":     source.SalesID,
		"order_remark": source.OrderRemark,
	}); err != nil {
		return err
	}

	// Clear source
	if err := s.unitRepo.ClearOrderFields(tx, req.SourceUnitID); err != nil {
		return err
	}

	detail, _ := json.Marshal(map[string]string{
		"source": req.SourceUnitID, "target": req.TargetUnitID, "fallback": req.FallbackUnitID,
	})
	tx.Create(&model.OperationLog{
		Actor: actor, Action: "swap_content", TargetType: "unit",
		TargetID: req.TargetUnitID, Detail: detail, CreatedAt: time.Now(),
	})
	if err := SyncFinishedGoodsByUnitIDs(tx, []string{req.SourceUnitID, req.TargetUnitID, req.FallbackUnitID}); err != nil {
		return fmt.Errorf("sync finished_goods_data: %w", err)
	}

	if err := tx.Commit().Error; err != nil {
		return err
	}

	s.wsHub.Broadcast("unit:updated", map[string]interface{}{
		"units": []string{req.SourceUnitID, req.TargetUnitID, req.FallbackUnitID},
	})
	return nil
}


func mapKeys(m map[string]struct{}) []string {
	if len(m) == 0 {
		return nil
	}
	keys := make([]string, 0, len(m))
	for k := range m {
		if strings.TrimSpace(k) == "" {
			continue
		}
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}


func (s *RushSvc) markRushContractPlanned(tx *gorm.DB, contractNo string, modelType string) error {
	cn := strings.TrimSpace(contractNo)
	mt := strings.TrimSpace(modelType)
	if cn == "" {
		return nil
	}
	// Rush orders are inserted as 未下单, while normal planning may already normalize them to 待规划.
	// Treat both as plannable here because the board insertion is the planning action for rush orders.
	ret := tx.Exec(
		"UPDATE factory_plan SET `状态` = '已规划' "+
			"WHERE TRIM(COALESCE(`合同号`, '')) = ? "+
			"AND TRIM(COALESCE(`机型`, '')) COLLATE utf8mb4_general_ci = ? COLLATE utf8mb4_general_ci "+
			"AND TRIM(COALESCE(`状态`, '')) IN ('待规划', '未下单', '')",
		cn, mt,
	)
	if ret.Error != nil {
		return ret.Error
	}
	if ret.RowsAffected > 0 || mt == "" {
		return nil
	}
	return tx.Exec(
		"UPDATE factory_plan SET `状态` = '已规划' "+
			"WHERE TRIM(COALESCE(`合同号`, '')) = ? "+
			"AND TRIM(COALESCE(`状态`, '')) IN ('待规划', '未下单', '')",
		cn,
	).Error
}

// enqueueOverflow 将溢出订单写入 production_queue。
// 兼容旧版 schema：若表中无 priority/payload 列，仅写入基础字段。
func (s *RushSvc) enqueueOverflow(tx *gorm.DB, family string, p *orderPayload) error {
	dueStr := time.Now().Format("2006-01-02")
	if p.DueDate != nil {
		dueStr = p.DueDate.Format("2006-01-02")
	}

	hasNewCols := queueTableHasColumns(tx, "payload", "priority")

	if hasNewCols {
		row := map[string]interface{}{
			"model_type":         family,
			"contract_no":        p.ContractNo,
			"status":             model.QueueWaiting,
			"priority":           0,
			"due_date":           dueStr,
			"quantity_remaining": 1,
		}
		payload, _ := json.Marshal(map[string]interface{}{
			"customer":    p.Customer,
			"dealer_name": p.DealerName,
			"due_date":    dueStr,
		})
		row["payload"] = payload
		return tx.Table("production_queue").Create(row).Error
	}

	// 旧版 schema：只写实际存在的列
	baseCols := queueExistingBaseCols(tx)
	row := map[string]interface{}{}
	for _, c := range baseCols {
		switch c {
		case "model_type":
			row[c] = family
		case "contract_no":
			row[c] = p.ContractNo
		case "customer":
			row[c] = p.Customer
		case "dealer", "dealer_name":
			row[c] = p.DealerName
		case "due_date":
			row[c] = dueStr
		case "status":
			row[c] = model.QueueWaiting
		case "quantity_remaining":
			row[c] = 1
		}
	}
	if len(row) == 0 {
		// 表结构完全未知，跳过入队不回误
		return nil
	}
	return tx.Table("production_queue").Create(row).Error
}

// queueTableHasColumns 检查 production_queue 表是否有指定列。
func queueTableHasColumns(db *gorm.DB, cols ...string) bool {
	var cols2 []struct{ Field string }
	if err := db.Raw("SHOW COLUMNS FROM production_queue").Scan(&cols2).Error; err != nil {
		return false
	}
	existing := make(map[string]bool, len(cols2))
	for _, c := range cols2 {
		existing[strings.ToLower(c.Field)] = true
	}
	for _, col := range cols {
		if !existing[strings.ToLower(col)] {
			return false
		}
	}
	return true
}

// queueExistingBaseCols 返回 production_queue 表中实际存在的列名集合。
func queueExistingBaseCols(db *gorm.DB) []string {
	var cols []struct{ Field string }
	if err := db.Raw("SHOW COLUMNS FROM production_queue").Scan(&cols).Error; err != nil {
		return nil
	}
	result := make([]string, 0, len(cols))
	for _, c := range cols {
		result = append(result, strings.ToLower(c.Field))
	}
	return result
}
