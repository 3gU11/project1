package handler

import (
	"encoding/json"
	"fmt"
	"math"
	"math/rand"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/datatypes"
	"gorm.io/gorm"

	"smart-scheduling/server/internal/engine"
	"smart-scheduling/server/internal/model"
	"smart-scheduling/server/internal/repo"
	"smart-scheduling/server/internal/service"
	"smart-scheduling/server/internal/ws"
)

type UnitHandler struct {
	db            *gorm.DB
	repo          *repo.UnitRepo
	batchRepo     *repo.BatchRepo
	rushSvc       *service.RushSvc
	pythonURL     string
	internalToken string
	hub           *ws.Hub
}

type capacityRatioCfg struct {
	Level2Global map[string]int            `json:"level2_global"`
	Level2       map[string]map[string]int `json:"level2"`
	Level3       map[string]map[string]int `json:"level3"`
}

func NewUnitHandler(db *gorm.DB, r *repo.UnitRepo, br *repo.BatchRepo, rs *service.RushSvc, pythonURL, token string, hub *ws.Hub) *UnitHandler {
	return &UnitHandler{
		db:            db,
		repo:          r,
		batchRepo:     br,
		rushSvc:       rs,
		pythonURL:     pythonURL,
		internalToken: token,
		hub:           hub,
	}
}

func (h *UnitHandler) GetByID(c *gin.Context) {
	unit, err := h.repo.GetByID(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "unit not found"})
		return
	}
	sanitizeUnitRemarkForResponse(unit)
	c.JSON(http.StatusOK, gin.H{"unit": unit})
}

func (h *UnitHandler) Update(c *gin.Context) {
	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}

	var req map[string]interface{}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Capture old state for sync
	oldUnit, _ := h.repo.GetByID(c.Param("id"))
	boundContract := oldUnit != nil && oldUnit.ContractNo != nil && strings.TrimSpace(*oldUnit.ContractNo) != ""
	if oldUnit != nil && oldUnit.Status == model.StatusInProduction {
		if _, exists := req["model_type"]; exists {
			c.JSON(http.StatusBadRequest, gin.H{"error": "生产看板上线卡片不允许手动修改机型，请到机台编辑修改"})
			return
		}
	}

	// Remove protected fields
	delete(req, "unit_id")
	delete(req, "batch_id")
	delete(req, "is_locked")
	delete(req, "production_line_id")
	delete(req, "status")
	delete(req, "created_at")
	delete(req, "updated_at")
	if _, exists := req["contract_no"]; exists {
		c.JSON(http.StatusBadRequest, gin.H{"error": "contract_no is read-only"})
		return
	}
	allowedFields := map[string]struct{}{
		"customer":     {},
		"dealer_name":  {},
		"order_remark": {},
		"model_type":   {},
	}
	for key := range req {
		if _, ok := allowedFields[key]; !ok {
			delete(req, key)
		}
	}
	if boundContract {
		for _, key := range []string{"model_type", "customer", "dealer_name"} {
			if _, exists := req[key]; exists {
				c.JSON(http.StatusBadRequest, gin.H{"error": "绑定合同的卡片只能在合同管理修改机型、客户和代理商"})
				return
			}
		}
	}

	// Validate model_type update from "信息强改" with whitelist from model_dictionary.
	if rawMT, exists := req["model_type"]; exists {
		mt, ok := rawMT.(string)
		if !ok {
			c.JSON(http.StatusBadRequest, gin.H{"error": "model_type must be string"})
			return
		}
		mt = strings.TrimSpace(mt)
		if mt == "" {
			delete(req, "model_type")
		} else {
			upper := strings.ToUpper(mt)
			if upper == "G" || upper == "XS" || upper == "AUTO" {
				c.JSON(http.StatusBadRequest, gin.H{"error": "model_type must be specific model, not family"})
				return
			}
			ok, err := h.isEnabledModelType(mt)
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			if !ok {
				c.JSON(http.StatusBadRequest, gin.H{"error": "invalid model_type"})
				return
			}
			req["model_type"] = mt
		}
	}

	// Force lock when editing
	req["is_locked"] = true
	req["locked_by"] = actor
	req["locked_at"] = time.Now()

	tx := h.db.Begin()
	defer tx.Rollback()

	if err := h.repo.UpdateOrderFields(tx, c.Param("id"), req); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// 同步修改到历史排产台账中。绑定合同卡片这里只允许备注变化。
	if boundContract {
		if rVal, ok := req["order_remark"].(string); ok {
			if err := tx.Exec(`
UPDATE production_history_ledger
SET order_remark = ?
WHERE status = 'In_Production' AND unit_id = ?
`, rVal, c.Param("id")).Error; err != nil {
				fmt.Printf("Update: sync production_history_ledger remark failed: %v\n", err)
			}
		}
	} else {
		var newCustomer *string
		var newDealer *string
		var newRemark *string
		var newModel string

		if cVal, ok := req["customer"].(string); ok {
			newCustomer = &cVal
		} else if oldUnit != nil {
			newCustomer = oldUnit.Customer
		}

		if dVal, ok := req["dealer_name"].(string); ok {
			newDealer = &dVal
		} else if oldUnit != nil {
			newDealer = oldUnit.DealerName
		}

		if rVal, ok := req["order_remark"].(string); ok {
			newRemark = &rVal
		} else if oldUnit != nil {
			newRemark = oldUnit.OrderRemark
		}

		if mVal, ok := req["model_type"].(string); ok {
			newModel = mVal
		} else if oldUnit != nil {
			newModel = oldUnit.ModelType
		}

		if err := tx.Exec(`
UPDATE production_history_ledger
SET customer = ?, dealer_name = ?, order_remark = ?, model_type = ?
WHERE status = 'In_Production' AND unit_id = ?
`, newCustomer, newDealer, newRemark, newModel, c.Param("id")).Error; err != nil {
			fmt.Printf("Update: sync production_history_ledger failed: %v\n", err)
		}
	}

	if err := service.SyncFinishedGoodsByUnitIDs(tx, []string{c.Param("id")}); err != nil {
		// Log error but continue as primary update succeeded
		fmt.Printf("Update: sync finished_goods failed: %v\n", err)
	}

	if err := service.SyncPlanImportByUnitIDs(tx, []string{c.Param("id")}, req); err != nil {
		// Log error but continue as primary update succeeded
		fmt.Printf("Update: sync plan_import failed: %v\n", err)
	}

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	newUnit, _ := h.repo.GetByID(c.Param("id"))

	// 【缺口1补全】反向同步：如果修改了机型或备注，且属于某个合同，则写回 Python
	if oldUnit != nil && newUnit != nil && newUnit.ContractNo != nil && *newUnit.ContractNo != "" {
		newRemark := ""
		if newUnit.OrderRemark != nil {
			newRemark = *newUnit.OrderRemark
		}

		oldRemark := ""
		if oldUnit.OrderRemark != nil {
			oldRemark = *oldUnit.OrderRemark
		}

		if newRemark != oldRemark {
			go h.SyncRemarkToPython(*newUnit.ContractNo, newUnit.ModelType, newRemark)
		}
	}

	sanitizeUnitRemarkForResponse(newUnit)
	c.JSON(http.StatusOK, gin.H{"unit": newUnit})
}

func (h *UnitHandler) SyncRemarkToPython(contractNo, model, remark string) {
	url := fmt.Sprintf("%s/internal/planning/unit-sync", h.pythonURL)
	payload := map[string]string{
		"contract_no":  contractNo,
		"old_model":    model,
		"new_model":    model,
		"order_remark": remark,
	}
	body, _ := json.Marshal(payload)

	req, err := http.NewRequest("PATCH", url, strings.NewReader(string(body)))
	if err != nil {
		fmt.Printf("SyncToPython: failed to create request: %v\n", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	if h.internalToken != "" {
		req.Header.Set("X-Internal-Token", h.internalToken)
	}

	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Printf("SyncToPython: request failed: %v\n", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		fmt.Printf("SyncToPython: status non-200: %d\n", resp.StatusCode)
	}
}

func (h *UnitHandler) NotifyContractCancelToPython(contractNo, actor, source string) {
	contractNo = strings.TrimSpace(contractNo)
	if contractNo == "" || h.pythonURL == "" {
		return
	}
	if actor == "" {
		actor = "system"
	}
	if source == "" {
		source = "go"
	}
	url := fmt.Sprintf("%s/internal/planning/contract-cancel-sync", h.pythonURL)
	payload := map[string]string{
		"contract_no": contractNo,
		"operator":    actor,
		"source":      source,
	}
	body, _ := json.Marshal(payload)

	req, err := http.NewRequest("POST", url, strings.NewReader(string(body)))
	if err != nil {
		fmt.Printf("NotifyContractCancelToPython: failed to create request: %v\n", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	if h.internalToken != "" {
		req.Header.Set("X-Internal-Token", h.internalToken)
	}

	client := &http.Client{Timeout: 120 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Printf("NotifyContractCancelToPython: request failed: %v\n", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		fmt.Printf("NotifyContractCancelToPython: status non-2xx: %d\n", resp.StatusCode)
	}
}

func (h *UnitHandler) isEnabledModelType(modelType string) (bool, error) {
	var count int64
	err := h.db.Table("model_dictionary").
		Where("enabled = 1").
		Where("UPPER(TRIM(model_name)) = UPPER(?)", strings.TrimSpace(modelType)).
		Count(&count).Error
	return count > 0, err
}

func (h *UnitHandler) Unlock(c *gin.Context) {
	tx := h.db.Begin()
	defer tx.Rollback()

	if err := h.repo.UnlockUnitDB(tx, c.Param("id")); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *UnitHandler) MoveBatch(c *gin.Context) {
	var raw map[string]interface{}
	if err := c.ShouldBindJSON(&raw); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	forbiddenFields := []string{"contract_no", "customer", "dealer_id", "dealer_name", "sales_id", "order_remark", "model_type"}
	for _, key := range forbiddenFields {
		if _, exists := raw[key]; exists {
			c.JSON(http.StatusBadRequest, gin.H{"error": "move-batch cannot update contract ownership fields"})
			return
		}
	}
	targetBatchID := strings.TrimSpace(fmt.Sprintf("%v", raw["target_batch_id"]))
	if targetBatchID == "" || strings.EqualFold(targetBatchID, "<nil>") {
		c.JSON(http.StatusBadRequest, gin.H{"error": "target_batch_id is required"})
		return
	}
	var req struct {
		TargetBatchID         string
		InsertBeforeSlotIndex *int
		TargetSlot            *int
	}
	req.TargetBatchID = targetBatchID
	if v, ok := raw["insert_before_slot_index"]; ok && v != nil {
		i := toInt(v)
		req.InsertBeforeSlotIndex = &i
	}
	if v, ok := raw["target_slot"]; ok && v != nil {
		i := toInt(v)
		req.TargetSlot = &i
	}

	tx := h.db.Begin()
	defer tx.Rollback()

	unit, err := h.repo.LockForUpdate(tx, c.Param("id"))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "unit not found"})
		return
	}
	if unit.IsLocked {
		c.JSON(http.StatusBadRequest, gin.H{"error": "unit is locked"})
		return
	}

	sourceBatchID := unit.BatchID
	isSameBatch := sourceBatchID == req.TargetBatchID
	unitID := c.Param("id")
	isStockUnit := unit.ContractNo == nil || strings.TrimSpace(*unit.ContractNo) == ""

	if !isSameBatch && isStockUnit {
		c.JSON(http.StatusBadRequest, gin.H{"error": "插入失败，该机台为备货机台"})
		return
	}

	sourceBatch, err := h.batchRepo.LockBatchForUpdate(tx, sourceBatchID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "source batch not found"})
		return
	}

	targetBatch := sourceBatch
	if !isSameBatch {
		targetBatch, err = h.batchRepo.LockBatchForUpdate(tx, req.TargetBatchID)
	}
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "target batch not found"})
		return
	}

	requestedSlot := req.InsertBeforeSlotIndex
	if requestedSlot == nil {
		requestedSlot = req.TargetSlot
	}

	sourceIsSpecial := strings.EqualFold(strings.TrimSpace(sourceBatch.ModelType), "SPECIAL")
	targetIsSpecial := strings.EqualFold(strings.TrimSpace(targetBatch.ModelType), "SPECIAL")
	if sourceIsSpecial || targetIsSpecial {
		if sourceIsSpecial && targetIsSpecial {
			newSlot, err := h.moveSpecialUnit(tx, unit, sourceBatchID, req.TargetBatchID, requestedSlot)
			if err != nil {
				c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
				return
			}
			if err := tx.Commit().Error; err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			c.JSON(http.StatusOK, gin.H{"success": true, "new_slot": newSlot})
			return
		}
		if sourceIsSpecial && !targetIsSpecial {
			newSlot, err := h.moveSpecialUnitToRegularBatch(tx, unit, sourceBatch, targetBatch, requestedSlot)
			if err != nil {
				c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
				return
			}
			if err := tx.Commit().Error; err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			c.JSON(http.StatusOK, gin.H{"success": true, "new_slot": newSlot})
			return
		}
		newSlot, err := h.moveRegularUnitToSpecialBatch(tx, unit, sourceBatch, targetBatch, requestedSlot)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		if err := tx.Commit().Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{"success": true, "new_slot": newSlot})
		return
	}

	sourceMT := engine.NormalizeModelType(unit.ModelType)
	targetMT := engine.NormalizeModelType(targetBatch.ModelType)
	if !isSameBatch {
		sourceGroup := engine.ProductionGroupForBatch(sourceBatch.ModelType, sourceBatch.Capacity)
		targetGroup := engine.ProductionGroupForBatch(targetBatch.ModelType, targetBatch.Capacity)
		unitGroup := engine.ProductionGroupForModel(unit.ModelType)
		if !engine.ProductionGroupsCompatible(sourceGroup, targetGroup) || unitGroup != sourceGroup {
			c.JSON(http.StatusBadRequest, gin.H{"error": "production group mismatch: cannot move between incompatible batches"})
			return
		}
		if sourceMT != targetMT && sourceGroup != engine.ProductionGroupLarge {
			c.JSON(http.StatusBadRequest, gin.H{"error": "model type mismatch: cannot move between different model types"})
			return
		}
	}

	var newSlot int
	overflowTouchedBatchIDs := []string{}
	directEjectApplied := false

	if isSameBatch {
		if err := h.repo.MoveToBatch(tx, unitID, req.TargetBatchID, 0); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		newSlot = slotFromRequest(requestedSlot, 1)
		if err := h.repo.ReorderBatchWithUnit(tx, req.TargetBatchID, unitID, newSlot); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	} else {
		if sourceBatch.Status != model.StatusPredicted || targetBatch.Status != model.StatusPredicted {
			c.JSON(http.StatusBadRequest, gin.H{"error": "cross-batch move is only supported in predicted columns"})
			return
		}

		// If target has unbound units (no contract), replace one slot directly.
		// This avoids any in-column shifting when a disposable placeholder exists.
		preferredSlot := slotFromRequest(requestedSlot, 1)
		ejectUnit, err := h.pickEjectableUnboundUnit(tx, req.TargetBatchID, preferredSlot)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		if err := h.repo.MoveToBatch(tx, unitID, req.TargetBatchID, 0); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		if err := h.repo.CompactSlots(tx, sourceBatchID); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		if err := h.fillBatchToCapacity(tx, sourceBatch); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		if ejectUnit != nil {
			if err := tx.Where("unit_id = ?", ejectUnit.UnitID).Delete(&model.Unit{}).Error; err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			newSlot = ejectUnit.SlotIndex
			if err := h.repo.MoveToBatch(tx, unitID, req.TargetBatchID, newSlot); err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			directEjectApplied = true
		} else {
			newSlot = slotFromRequest(requestedSlot, 0)
			if err := h.repo.ReorderBatchWithUnit(tx, req.TargetBatchID, unitID, newSlot); err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			count, err := h.repo.CountByBatch(tx, req.TargetBatchID)
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			if int(count) > targetBatch.Capacity {
				overflowTouchedBatchIDs, err = h.cascadeOverflowBySlot(tx, targetBatch.BatchID, targetMT, unitID)
				if err != nil {
					c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
					return
				}
			}
		}
	}

	gapTouchedBatchIDs, err := h.enforceFamilyGapDays(tx, targetMT)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	overflowTouchedBatchIDs = append(overflowTouchedBatchIDs, gapTouchedBatchIDs...)

	sourceBatchMT := engine.NormalizeModelType(sourceBatch.ModelType)
	if sourceBatchMT == targetMT {
		ratioBatchIDs := append([]string{sourceBatchID, req.TargetBatchID}, overflowTouchedBatchIDs...)
		if err := h.rebalanceBatchesUnboundUnitsByRatio(tx, targetMT, ratioBatchIDs...); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	} else {
		if err := h.rebalanceBatchesUnboundUnitsByRatio(tx, sourceBatchMT, sourceBatchID); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		targetRatioBatchIDs := append([]string{req.TargetBatchID}, overflowTouchedBatchIDs...)
		if err := h.rebalanceBatchesUnboundUnitsByRatio(tx, targetMT, targetRatioBatchIDs...); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	}

	if !directEjectApplied {
		sortOrderMap, err := h.loadModelSortOrderMap(tx)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		sortBatchIDs := append([]string{sourceBatchID, req.TargetBatchID}, overflowTouchedBatchIDs...)
		if err := h.sortTouchedBatchesByModelDictionary(tx, sortOrderMap, sortBatchIDs...); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	}

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true, "new_slot": newSlot})
}

func (h *UnitHandler) MoveToSpecial(c *gin.Context) {
	tx := h.db.Begin()
	defer tx.Rollback()

	unit, err := h.repo.LockForUpdate(tx, c.Param("id"))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "unit not found"})
		return
	}
	if unit.IsLocked {
		c.JSON(http.StatusBadRequest, gin.H{"error": "unit is locked"})
		return
	}
	if unit.ContractNo == nil || strings.TrimSpace(*unit.ContractNo) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "备货空卡不能转移到特殊批次"})
		return
	}

	sourceBatch, err := h.batchRepo.LockBatchForUpdate(tx, unit.BatchID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "source batch not found"})
		return
	}
	if sourceBatch.Status != model.StatusPredicted {
		c.JSON(http.StatusBadRequest, gin.H{"error": "只能转移预测批次中的合同卡片"})
		return
	}
	if strings.EqualFold(strings.TrimSpace(sourceBatch.ModelType), "SPECIAL") {
		c.JSON(http.StatusBadRequest, gin.H{"error": "该卡片已经在特殊批次中"})
		return
	}
	sourceCategory := fillCategoryForBatch(engine.NormalizeModelType(sourceBatch.ModelType), sourceBatch.Capacity)
	if sourceCategory != "中大型XS" && sourceCategory != "中大型AUTO" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "只有中大型卡片可以转移到特殊批次"})
		return
	}

	targetBatch, targetSlot, err := h.findAvailableSpecialBatch(tx)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.repo.MoveToBatch(tx, unit.UnitID, targetBatch.BatchID, 0); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.repo.CompactSlots(tx, sourceBatch.BatchID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.fillBatchToCapacity(tx, sourceBatch); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.repo.ReorderBatchWithUnit(tx, targetBatch.BatchID, unit.UnitID, targetSlot); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.normalizeSpecialBatchSlots(tx, targetBatch.BatchID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success":         true,
		"target_batch_id": targetBatch.BatchID,
		"new_slot":        targetSlot,
	})
}

func (h *UnitHandler) CreateSpecialCard(c *gin.Context) {
	var req struct {
		BatchID     string `json:"batch_id" binding:"required"`
		ContractNo  string `json:"contract_no"`
		Customer    string `json:"customer"`
		DealerName  string `json:"dealer_name"`
		ModelType   string `json:"model_type" binding:"required"`
		DueDate     string `json:"due_date"`
		OrderRemark string `json:"order_remark"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	req.BatchID = strings.TrimSpace(req.BatchID)
	req.ContractNo = strings.TrimSpace(req.ContractNo)
	req.Customer = strings.TrimSpace(req.Customer)
	req.DealerName = strings.TrimSpace(req.DealerName)
	req.ModelType = strings.TrimSpace(req.ModelType)
	req.DueDate = strings.TrimSpace(req.DueDate)
	req.OrderRemark = strings.TrimSpace(req.OrderRemark)
	if req.ModelType == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "model_type is required"})
		return
	}

	var dueDate *time.Time
	if req.DueDate != "" {
		parsedDueDate, err := time.Parse("2006-01-02", req.DueDate)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "due_date must be YYYY-MM-DD"})
			return
		}
		dueDate = &parsedDueDate
	}

	tx := h.db.Begin()
	defer tx.Rollback()

	batch, err := h.batchRepo.LockBatchForUpdate(tx, req.BatchID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "target batch not found"})
		return
	}
	if batch.Status != model.StatusPredicted || !strings.EqualFold(strings.TrimSpace(batch.ModelType), "SPECIAL") {
		c.JSON(http.StatusBadRequest, gin.H{"error": "target batch must be a Predicted SPECIAL column"})
		return
	}

	const specialCardLimit = 15
	cardCount, err := h.countSpecialCards(tx, batch.BatchID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if cardCount >= specialCardLimit {
		c.JSON(http.StatusBadRequest, gin.H{"error": "special column is full (15 cards)"})
		return
	}

	maxSlot, err := h.repo.GetMaxSlotInBatch(tx, batch.BatchID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	newSlot := maxSlot + 1
	unitID, err := h.nextAutoFillUnitID(tx, batch.BatchID, newSlot)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	now := time.Now()
	unit := model.Unit{
		UnitID:      unitID,
		BatchID:     batch.BatchID,
		SlotIndex:   newSlot,
		ModelType:   req.ModelType,
		Status:      "Pending",
		ContractNo:  optionalStringPtr(req.ContractNo),
		Customer:    optionalStringPtr(req.Customer),
		DealerName:  optionalStringPtr(req.DealerName),
		DueDate:     dueDate,
		OrderRemark: optionalStringPtr(req.OrderRemark),
		CreatedAt:   now,
		UpdatedAt:   now,
	}
	if err := tx.Create(&unit).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.normalizeSpecialBatchSlots(tx, batch.BatchID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true, "unit": unit})
}

func (h *UnitHandler) findAvailableSpecialBatch(tx *gorm.DB) (*model.Batch, int, error) {
	batches, err := h.batchRepo.ListPredictedByModelForUpdate(tx, "SPECIAL")
	if err != nil {
		return nil, 0, err
	}
	if len(batches) == 0 {
		return nil, 0, fmt.Errorf("没有可用的特殊批次列")
	}

	for i := range batches {
		b := &batches[i]
		capacity := b.Capacity
		if capacity <= 0 {
			capacity = 15
		}

		var contractCount int64
		if err := tx.Model(&model.Unit{}).
			Where("batch_id = ?", b.BatchID).
			Where("contract_no IS NOT NULL AND TRIM(contract_no) <> ''").
			Count(&contractCount).Error; err != nil {
			return nil, 0, err
		}
		if int(contractCount) < capacity {
			return b, int(contractCount) + 1, nil
		}
	}

	return nil, 0, fmt.Errorf("两个特殊批次列均已满，无法转移")
}

func (h *UnitHandler) moveSpecialUnitToRegularBatch(tx *gorm.DB, unit *model.Unit, sourceBatch *model.Batch, targetBatch *model.Batch, requestedSlot *int) (int, error) {
	unitID := strings.TrimSpace(unit.UnitID)
	if unitID == "" {
		return 0, fmt.Errorf("unit id is empty")
	}
	if unit.ContractNo == nil || strings.TrimSpace(*unit.ContractNo) == "" {
		return 0, fmt.Errorf("empty special slot cannot move to regular columns")
	}
	if sourceBatch.Status != model.StatusPredicted || targetBatch.Status != model.StatusPredicted {
		return 0, fmt.Errorf("cross-batch move is only supported in predicted columns")
	}

	targetMT := engine.NormalizeModelType(targetBatch.ModelType)
	if !isLargeFamilyBatch(targetBatch) || engine.ProductionGroupForModel(unit.ModelType) != engine.ProductionGroupLarge {
		return 0, fmt.Errorf("only special <-> large XS/AUTO cross-column moves are allowed")
	}

	preferredSlot := slotFromRequest(requestedSlot, 1)
	ejectUnit, err := h.pickEjectableUnboundUnit(tx, targetBatch.BatchID, preferredSlot)
	if err != nil {
		return 0, err
	}

	if err := h.repo.MoveToBatch(tx, unitID, targetBatch.BatchID, 0); err != nil {
		return 0, err
	}
	if err := h.normalizeSpecialBatchSlots(tx, sourceBatch.BatchID); err != nil {
		return 0, err
	}

	newSlot := 0
	overflowTouchedBatchIDs := []string{}
	directEjectApplied := false
	if ejectUnit != nil {
		if err := tx.Where("unit_id = ?", ejectUnit.UnitID).Delete(&model.Unit{}).Error; err != nil {
			return 0, err
		}
		newSlot = ejectUnit.SlotIndex
		if err := h.repo.MoveToBatch(tx, unitID, targetBatch.BatchID, newSlot); err != nil {
			return 0, err
		}
		directEjectApplied = true
	} else {
		newSlot = slotFromRequest(requestedSlot, 0)
		if err := h.repo.ReorderBatchWithUnit(tx, targetBatch.BatchID, unitID, newSlot); err != nil {
			return 0, err
		}
		count, err := h.repo.CountByBatch(tx, targetBatch.BatchID)
		if err != nil {
			return 0, err
		}
		if int(count) > targetBatch.Capacity {
			overflowTouchedBatchIDs, err = h.cascadeOverflowBySlot(tx, targetBatch.BatchID, targetMT, unitID)
			if err != nil {
				return 0, err
			}
		}
	}

	gapTouchedBatchIDs, err := h.enforceFamilyGapDays(tx, targetMT)
	if err != nil {
		return 0, err
	}
	overflowTouchedBatchIDs = append(overflowTouchedBatchIDs, gapTouchedBatchIDs...)

	ratioBatchIDs := append([]string{targetBatch.BatchID}, overflowTouchedBatchIDs...)
	if err := h.rebalanceBatchesUnboundUnitsByRatio(tx, targetMT, ratioBatchIDs...); err != nil {
		return 0, err
	}

	if !directEjectApplied {
		sortOrderMap, err := h.loadModelSortOrderMap(tx)
		if err != nil {
			return 0, err
		}
		sortBatchIDs := append([]string{targetBatch.BatchID}, overflowTouchedBatchIDs...)
		if err := h.sortTouchedBatchesByModelDictionary(tx, sortOrderMap, sortBatchIDs...); err != nil {
			return 0, err
		}
	}

	return newSlot, nil
}

func (h *UnitHandler) moveRegularUnitToSpecialBatch(tx *gorm.DB, unit *model.Unit, sourceBatch *model.Batch, targetBatch *model.Batch, requestedSlot *int) (int, error) {
	unitID := strings.TrimSpace(unit.UnitID)
	if unitID == "" {
		return 0, fmt.Errorf("unit id is empty")
	}
	if unit.ContractNo == nil || strings.TrimSpace(*unit.ContractNo) == "" {
		return 0, fmt.Errorf("stock/empty unit cannot move across columns")
	}
	if sourceBatch.Status != model.StatusPredicted || targetBatch.Status != model.StatusPredicted {
		return 0, fmt.Errorf("cross-batch move is only supported in predicted columns")
	}
	if !strings.EqualFold(strings.TrimSpace(targetBatch.ModelType), "SPECIAL") {
		return 0, fmt.Errorf("target must be special column")
	}
	if !isLargeFamilyBatch(sourceBatch) || engine.ProductionGroupForModel(unit.ModelType) != engine.ProductionGroupLarge {
		return 0, fmt.Errorf("only large XS/AUTO can move to special columns")
	}

	newSlot := slotFromRequest(requestedSlot, 1)
	if err := h.repo.MoveToBatch(tx, unitID, targetBatch.BatchID, 0); err != nil {
		return 0, err
	}
	if err := h.repo.CompactSlots(tx, sourceBatch.BatchID); err != nil {
		return 0, err
	}
	if err := h.fillBatchToCapacity(tx, sourceBatch); err != nil {
		return 0, err
	}
	if err := h.repo.ReorderBatchWithUnit(tx, targetBatch.BatchID, unitID, newSlot); err != nil {
		return 0, err
	}
	if err := h.normalizeSpecialBatchSlots(tx, targetBatch.BatchID); err != nil {
		return 0, err
	}
	return newSlot, nil
}

func isLargeFamilyBatch(batch *model.Batch) bool {
	if batch == nil {
		return false
	}
	return engine.ProductionGroupForBatch(batch.ModelType, batch.Capacity) == engine.ProductionGroupLarge
}

func (h *UnitHandler) moveSpecialUnit(tx *gorm.DB, unit *model.Unit, sourceBatchID string, targetBatchID string, requestedSlot *int) (int, error) {
	unitID := strings.TrimSpace(unit.UnitID)
	if unitID == "" {
		return 0, fmt.Errorf("unit id is empty")
	}
	isSameBatch := sourceBatchID == targetBatchID
	isEmptySlot := unit.ContractNo == nil || strings.TrimSpace(*unit.ContractNo) == ""

	newSlot := slotFromRequest(requestedSlot, 1)
	if isSameBatch {
		if err := h.repo.ReorderBatchWithUnit(tx, targetBatchID, unitID, newSlot); err != nil {
			return 0, err
		}
		if err := h.normalizeSpecialBatchSlots(tx, targetBatchID); err != nil {
			return 0, err
		}
		return newSlot, nil
	}

	if isEmptySlot {
		return 0, fmt.Errorf("empty special slot cannot move across columns")
	}
	if err := h.repo.MoveToBatch(tx, unitID, targetBatchID, 0); err != nil {
		return 0, err
	}
	if err := h.normalizeSpecialBatchSlots(tx, sourceBatchID); err != nil {
		return 0, err
	}
	if err := h.repo.ReorderBatchWithUnit(tx, targetBatchID, unitID, newSlot); err != nil {
		return 0, err
	}
	if err := h.normalizeSpecialBatchSlots(tx, targetBatchID); err != nil {
		return 0, err
	}
	return newSlot, nil
}

func (h *UnitHandler) normalizeSpecialBatchSlots(tx *gorm.DB, batchID string) error {
	cardCount, err := h.countSpecialCards(tx, batchID)
	if err != nil {
		return err
	}

	if cardCount > 0 {
		if err := tx.Where("batch_id = ?", batchID).
			Where(specialPlaceholderWhere()).
			Delete(&model.Unit{}).Error; err != nil {
			return err
		}
		return h.repo.CompactSlots(tx, batchID)
	}

	if err := tx.Where("batch_id = ?", batchID).Delete(&model.Unit{}).Error; err != nil {
		return err
	}
	unitID, err := h.nextAutoFillUnitID(tx, batchID, 1)
	if err != nil {
		return err
	}
	now := time.Now()
	return tx.Create(&model.Unit{
		UnitID:    unitID,
		BatchID:   batchID,
		SlotIndex: 1,
		ModelType: "SPECIAL",
		Status:    "Pending",
		CreatedAt: now,
		UpdatedAt: now,
	}).Error
}

func (h *UnitHandler) countSpecialCards(tx *gorm.DB, batchID string) (int64, error) {
	var count int64
	err := tx.Model(&model.Unit{}).
		Where("batch_id = ?", batchID).
		Where("NOT (" + specialPlaceholderWhere() + ")").
		Count(&count).Error
	return count, err
}

func specialPlaceholderWhere() string {
	return "UPPER(TRIM(model_type)) = 'SPECIAL' AND (contract_no IS NULL OR TRIM(contract_no) = '') AND (customer IS NULL OR TRIM(customer) = '') AND (dealer_name IS NULL OR TRIM(dealer_name) = '') AND due_date IS NULL AND (order_remark IS NULL OR TRIM(order_remark) = '')"
}

func (h *UnitHandler) fillBatchToCapacity(tx *gorm.DB, b *model.Batch) error {
	count, err := h.repo.CountByBatch(tx, b.BatchID)
	if err != nil {
		return err
	}
	missing := b.Capacity - int(count)
	if missing <= 0 {
		return nil
	}

	ratio := loadCapacityRatioCfg(h.db)
	models := h.chooseInventoryAwareFillModels(tx, b, missing, ratio, nil)
	if len(models) < missing {
		models = chooseFillModelsForBatch(engine.NormalizeModelType(b.ModelType), b.Capacity, missing, ratio)
	}
	if len(models) < missing {
		for len(models) < missing {
			models = append(models, defaultFillModelForBatch(engine.NormalizeModelType(b.ModelType), b.Capacity))
		}
	}
	now := time.Now()
	startSlot := int(count) + 1

	for i := 0; i < missing; i++ {
		slot := startSlot + i
		unitID, err := h.nextAutoFillUnitID(tx, b.BatchID, slot)
		if err != nil {
			return err
		}
		modelName := models[i]
		unit := model.Unit{
			UnitID:    unitID,
			BatchID:   b.BatchID,
			SlotIndex: slot,
			ModelType: modelName,
			Status:    "Pending",
			CreatedAt: now,
			UpdatedAt: now,
		}
		if err := tx.Create(&unit).Error; err != nil {
			return err
		}
	}
	return nil
}

func (h *UnitHandler) enqueueOverflowUnit(tx *gorm.DB, u *model.Unit, family string) error {
	if !queueHasColumns(tx, "production_queue", "payload", "priority") {
		contractNo := strings.TrimSpace(strPtrVal(u.ContractNo))
		if contractNo == "" {
			contractNo = "EMPTY-" + u.UnitID
		}
		due := time.Now().Format("2006-01-02")
		if u.DueDate != nil {
			due = u.DueDate.Format("2006-01-02")
		}
		row := map[string]interface{}{
			"model_type":         family,
			"contract_no":        contractNo,
			"customer":           strPtrVal(u.Customer),
			"dealer":             strPtrVal(u.DealerName),
			"due_date":           due,
			"quantity_remaining": 1,
			"status":             model.QueueWaiting,
		}
		return tx.Table("production_queue").Create(row).Error
	}

	payload := map[string]interface{}{
		"unit_id":      u.UnitID,
		"batch_id":     u.BatchID,
		"slot_index":   u.SlotIndex,
		"model_type":   u.ModelType,
		"family":       family,
		"contract_no":  strPtrVal(u.ContractNo),
		"customer":     strPtrVal(u.Customer),
		"dealer_name":  strPtrVal(u.DealerName),
		"sales_id":     strPtrVal(u.SalesID),
		"order_remark": strPtrVal(u.OrderRemark),
	}
	if u.DueDate != nil {
		payload["due_date"] = u.DueDate.Format("2006-01-02")
	}

	raw, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	var maxPriority int
	if err := tx.Model(&model.ProductionQueue{}).
		Where("model_type = ? AND status = ?", family, model.QueueWaiting).
		Select("COALESCE(MAX(priority), -1)").
		Scan(&maxPriority).Error; err != nil {
		return err
	}

	entry := model.ProductionQueue{
		ModelType:  family,
		ContractNo: u.ContractNo,
		Payload:    datatypes.JSON(raw),
		Status:     model.QueueWaiting,
		Priority:   maxPriority + 1,
	}
	return tx.Create(&entry).Error
}

func queueHasColumns(tx *gorm.DB, table string, cols ...string) bool {
	for _, col := range cols {
		var count int64
		if err := tx.Raw(`
SELECT COUNT(*)
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = ?
  AND COLUMN_NAME = ?`, table, col).Scan(&count).Error; err != nil {
			return false
		}
		if count == 0 {
			return false
		}
	}
	return true
}

func strPtrVal(v *string) string {
	if v == nil {
		return ""
	}
	return *v
}

func optionalStringPtr(v string) *string {
	v = strings.TrimSpace(v)
	if v == "" {
		return nil
	}
	return &v
}

func (h *UnitHandler) pickEjectableUnboundUnit(tx *gorm.DB, batchID string, preferredSlot int) (*model.Unit, error) {
	units, err := h.repo.ListByBatchIDsForUpdate(tx, []string{batchID})
	if err != nil {
		return nil, err
	}

	if preferredSlot > 0 {
		for i := range units {
			u := units[i]
			if u.SlotIndex == preferredSlot && (u.ContractNo == nil || strings.TrimSpace(*u.ContractNo) == "") {
				return &u, nil
			}
		}
	}

	for i := len(units) - 1; i >= 0; i-- {
		u := units[i]
		if u.ContractNo == nil || strings.TrimSpace(*u.ContractNo) == "" {
			return &u, nil
		}
	}
	return nil, nil
}

func (h *UnitHandler) cascadeOverflowBySlot(tx *gorm.DB, targetBatchID string, family string, protectedUnitID string) ([]string, error) {
	batches, err := h.batchRepo.ListPredictedByModelForUpdate(tx, family)
	if err != nil {
		return nil, err
	}

	targetIdx := -1
	for i := range batches {
		if batches[i].BatchID == targetBatchID {
			targetIdx = i
			break
		}
	}
	if targetIdx < 0 {
		return nil, nil
	}

	touched := []string{}
	seen := map[string]bool{}
	addTouched := func(batchID string) {
		bid := strings.TrimSpace(batchID)
		if bid == "" || seen[bid] {
			return
		}
		seen[bid] = true
		touched = append(touched, bid)
	}

	protectID := protectedUnitID
	for i := targetIdx; i < len(batches); i++ {
		batch := batches[i]
		count, err := h.repo.CountByBatch(tx, batch.BatchID)
		if err != nil {
			return touched, err
		}
		if int(count) <= batch.Capacity {
			if err := h.repo.CompactSlots(tx, batch.BatchID); err != nil {
				return touched, err
			}
			addTouched(batch.BatchID)
			return touched, nil
		}

		units, err := h.repo.ListByBatchIDsForUpdate(tx, []string{batch.BatchID})
		if err != nil {
			return touched, err
		}
		if len(units) == 0 {
			return touched, fmt.Errorf("batch %s has no units after overflow", batch.BatchID)
		}

		overflowIdx := len(units) - 1
		if protectID != "" && units[overflowIdx].UnitID == protectID && len(units) > 1 {
			overflowIdx = len(units) - 2
		}
		overflowUnit := units[overflowIdx]
		addTouched(batch.BatchID)

		nextIdx := -1
		for j := i + 1; j < len(batches); j++ {
			if batches[j].Capacity == batch.Capacity {
				nextIdx = j
				break
			}
		}

		if nextIdx < 0 {
			newBatch, err := h.createOverflowExtensionBatch(tx, &batch)
			if err != nil {
				return touched, err
			}
			if err := h.repo.MoveToBatch(tx, overflowUnit.UnitID, newBatch.BatchID, 1); err != nil {
				return touched, err
			}
			if err := h.repo.CompactSlots(tx, batch.BatchID); err != nil {
				return touched, err
			}
			if err := h.fillBatchToCapacity(tx, newBatch); err != nil {
				return touched, err
			}
			addTouched(newBatch.BatchID)
			return touched, nil
		}

		nextBatchID := batches[nextIdx].BatchID
		// If next batch has unbound placeholders, replace one directly and stop chain.
		nextEjectUnit, err := h.pickEjectableUnboundUnit(tx, nextBatchID, 0)
		if err != nil {
			return touched, err
		}
		if nextEjectUnit != nil {
			if err := tx.Where("unit_id = ?", nextEjectUnit.UnitID).Delete(&model.Unit{}).Error; err != nil {
				return touched, err
			}
			if err := h.repo.MoveToBatch(tx, overflowUnit.UnitID, nextBatchID, nextEjectUnit.SlotIndex); err != nil {
				return touched, err
			}
			if err := h.repo.CompactSlots(tx, batch.BatchID); err != nil {
				return touched, err
			}
			addTouched(nextBatchID)
			return touched, nil
		}

		if err := h.repo.MoveToBatch(tx, overflowUnit.UnitID, nextBatchID, 0); err != nil {
			return touched, err
		}
		// Overflow enters the next column at the first position when next column is fully bound.
		if err := h.repo.ReorderBatchWithUnit(tx, nextBatchID, overflowUnit.UnitID, 1); err != nil {
			return touched, err
		}
		if err := h.repo.CompactSlots(tx, batch.BatchID); err != nil {
			return touched, err
		}
		addTouched(nextBatchID)
		protectID = overflowUnit.UnitID
		i = nextIdx - 1
	}

	return touched, nil
}

func (h *UnitHandler) createOverflowExtensionBatch(tx *gorm.DB, ref *model.Batch) (*model.Batch, error) {
	if ref == nil {
		return nil, fmt.Errorf("reference batch is nil")
	}
	var maxBatchNo int
	if err := tx.Model(&model.Batch{}).
		Where("status = ? AND model_type = ?", model.StatusPredicted, ref.ModelType).
		Select("COALESCE(MAX(batch_no), 0)").
		Scan(&maxBatchNo).Error; err != nil {
		return nil, err
	}
	nextNo := maxBatchNo + 1
	now := time.Now()
	newBatchID := fmt.Sprintf("BATCH-%s-%s-%03d-%06d",
		now.Format("200601"),
		strings.ToUpper(strings.TrimSpace(ref.ModelType)),
		nextNo,
		rand.Intn(1000000),
	)
	newBatch := &model.Batch{
		BatchID:      newBatchID,
		BatchNo:      nextNo,
		ModelType:    ref.ModelType,
		Capacity:     ref.Capacity,
		Status:       model.StatusPredicted,
		DueDateStart: ref.DueDateStart,
		DueDateEnd:   ref.DueDateEnd,
		Source:       "overflow_extend",
		CreatedAt:    now,
		UpdatedAt:    now,
	}
	if err := tx.Create(newBatch).Error; err != nil {
		return nil, err
	}
	slot := model.ForecastBatchSlot{
		SlotNo:    nextNo,
		ModelType: ref.ModelType,
		Capacity:  ref.Capacity,
		BatchID:   &newBatch.BatchID,
		Source:    "overflow_extend",
		CreatedAt: now,
		UpdatedAt: now,
	}
	if err := tx.Create(&slot).Error; err != nil {
		return nil, err
	}
	return newBatch, nil
}

func (h *UnitHandler) findNextPredictedBatchWithSpace(tx *gorm.DB, targetBatchID string, family string) (string, bool, error) {
	batches, err := h.batchRepo.ListPredictedByModelForUpdate(tx, family)
	if err != nil {
		return "", false, err
	}

	targetIdx := -1
	for i := range batches {
		if batches[i].BatchID == targetBatchID {
			targetIdx = i
			break
		}
	}
	if targetIdx < 0 {
		return "", false, nil
	}

	for i := targetIdx + 1; i < len(batches); i++ {
		cnt, err := h.repo.CountByBatch(tx, batches[i].BatchID)
		if err != nil {
			return "", false, err
		}
		if int(cnt) < batches[i].Capacity {
			return batches[i].BatchID, true, nil
		}
	}
	return "", false, nil
}

func (h *UnitHandler) rebalanceBatchesUnboundUnitsByRatio(tx *gorm.DB, family string, batchIDs ...string) error {
	ratio := loadCapacityRatioCfg(h.db)
	seen := map[string]bool{}
	exclude := map[string]bool{}
	for _, batchID := range batchIDs {
		bid := strings.TrimSpace(batchID)
		if bid != "" {
			exclude[bid] = true
		}
	}
	baseline, err := h.inventoryAndPredictedStockCounts(tx, exclude)
	if err != nil {
		return err
	}
	allocator := engine.NewStockRatioAllocator(engine.RatioConfig{
		Level2Global: ratio.Level2Global,
		Level2:       ratio.Level2,
		Level3:       ratio.Level3,
	}, baseline)
	for _, batchID := range batchIDs {
		bid := strings.TrimSpace(batchID)
		if bid == "" || seen[bid] {
			continue
		}
		seen[bid] = true
		batch, err := h.batchRepo.LockBatchForUpdate(tx, bid)
		if err != nil {
			return err
		}
		if err := h.rebalanceSingleBatchUnboundUnitsByRatio(tx, batch, family, ratio, allocator); err != nil {
			return err
		}
	}
	return nil
}

func (h *UnitHandler) rebalanceSingleBatchUnboundUnitsByRatio(tx *gorm.DB, batch *model.Batch, family string, ratio capacityRatioCfg, allocator *engine.StockRatioAllocator) error {
	units, err := h.repo.ListByBatchIDsForUpdate(tx, []string{batch.BatchID})
	if err != nil {
		return err
	}
	if len(units) == 0 {
		return nil
	}

	unbound := make([]model.Unit, 0)
	for _, u := range units {
		if u.ContractNo == nil || strings.TrimSpace(*u.ContractNo) == "" {
			unbound = append(unbound, u)
		}
	}
	if len(unbound) == 0 {
		return nil
	}

	sort.SliceStable(unbound, func(i, j int) bool {
		if unbound[i].SlotIndex != unbound[j].SlotIndex {
			return unbound[i].SlotIndex < unbound[j].SlotIndex
		}
		return unbound[i].UnitID < unbound[j].UnitID
	})

	category := fillCategoryForBatch(family, batch.Capacity)
	models := []string(nil)
	if allocator != nil && category != "" {
		models = allocator.TakeModelsForCategory(category, len(unbound))
	}
	if len(models) < len(unbound) {
		models = chooseFillModelsForBatch(family, batch.Capacity, len(unbound), ratio)
	}
	if len(models) < len(unbound) {
		for len(models) < len(unbound) {
			models = append(models, defaultFillModelForBatch(family, batch.Capacity))
		}
	}

	now := time.Now()
	for i := range unbound {
		uid := unbound[i].UnitID
		modelName := models[i]
		if err := tx.Model(&model.Unit{}).
			Where("unit_id = ?", uid).
			Updates(map[string]interface{}{
				"model_type":   modelName,
				"order_remark": nil,
				"updated_at":   now,
			}).Error; err != nil {
			return err
		}
	}
	return nil
}

func (h *UnitHandler) chooseInventoryAwareFillModels(tx *gorm.DB, b *model.Batch, slots int, ratio capacityRatioCfg, exclude map[string]bool) []string {
	if slots <= 0 || b == nil {
		return nil
	}
	baseline, err := h.inventoryAndPredictedStockCounts(tx, exclude)
	if err != nil {
		return nil
	}
	allocator := engine.NewStockRatioAllocator(engine.RatioConfig{
		Level2Global: ratio.Level2Global,
		Level2:       ratio.Level2,
		Level3:       ratio.Level3,
	}, baseline)
	category := fillCategoryForBatch(engine.NormalizeModelType(b.ModelType), b.Capacity)
	if category == "" {
		return nil
	}
	return allocator.TakeModelsForCategory(category, slots)
}

func (h *UnitHandler) inventoryAndPredictedStockCounts(tx *gorm.DB, excludeBatchIDs map[string]bool) (map[string]int, error) {
	counts, err := engine.LoadStockBaselineModelCounts(tx)
	if err != nil {
		return nil, err
	}

	rows := make([]struct {
		BatchID   string `gorm:"column:batch_id"`
		ModelType string `gorm:"column:model_type"`
		Count     int    `gorm:"column:count"`
	}, 0, 128)
	q := tx.Table("units u").
		Select("u.batch_id AS batch_id, TRIM(u.model_type) AS model_type, COUNT(*) AS count").
		Joins("JOIN batches b ON b.batch_id = u.batch_id").
		Where("b.status = ?", model.StatusPredicted).
		Where("(u.contract_no IS NULL OR TRIM(u.contract_no) = '')").
		Group("u.batch_id, TRIM(u.model_type)")
	if err := q.Scan(&rows).Error; err != nil {
		return nil, err
	}
	for _, row := range rows {
		if excludeBatchIDs != nil && excludeBatchIDs[strings.TrimSpace(row.BatchID)] {
			continue
		}
		modelName := strings.TrimSpace(row.ModelType)
		if modelName == "" || row.Count <= 0 {
			continue
		}
		counts[modelName] += row.Count
	}
	return counts, nil
}

func (h *UnitHandler) loadModelSortOrderMap(tx *gorm.DB) (map[string]int, error) {
	var rows []struct {
		ModelName string `gorm:"column:model_name"`
		SortOrder int    `gorm:"column:sort_order"`
	}
	if err := tx.Table("model_dictionary").
		Select("model_name, sort_order").
		Where("enabled = 1").
		Scan(&rows).Error; err != nil {
		return nil, err
	}

	orderMap := make(map[string]int, len(rows))
	for _, row := range rows {
		key := normalizeModelKey(row.ModelName)
		if key == "" {
			continue
		}
		prev, exists := orderMap[key]
		if !exists || row.SortOrder < prev {
			orderMap[key] = row.SortOrder
		}
	}
	return orderMap, nil
}

func (h *UnitHandler) sortTouchedBatchesByModelDictionary(tx *gorm.DB, orderMap map[string]int, batchIDs ...string) error {
	seen := map[string]bool{}
	for _, batchID := range batchIDs {
		bid := strings.TrimSpace(batchID)
		if bid == "" || seen[bid] {
			continue
		}
		seen[bid] = true
		if err := h.sortOneBatchByModelDictionary(tx, bid, orderMap); err != nil {
			return err
		}
	}
	return nil
}

func (h *UnitHandler) sortOneBatchByModelDictionary(tx *gorm.DB, batchID string, orderMap map[string]int) error {
	units, err := h.repo.ListByBatchIDsForUpdate(tx, []string{batchID})
	if err != nil {
		return err
	}
	if len(units) == 0 {
		return nil
	}

	sort.SliceStable(units, func(i, j int) bool {
		ai := modelSortRank(units[i].ModelType, orderMap)
		aj := modelSortRank(units[j].ModelType, orderMap)
		if ai != aj {
			return ai < aj
		}

		am := normalizeModelKey(units[i].ModelType)
		bm := normalizeModelKey(units[j].ModelType)
		if am != bm {
			return am < bm
		}
		return units[i].SlotIndex < units[j].SlotIndex
	})

	ids := make([]string, 0, len(units))
	for _, u := range units {
		ids = append(ids, u.UnitID)
	}
	return h.repo.RewriteBatchAssignments(tx, map[string][]string{batchID: ids})
}

func modelSortRank(modelName string, orderMap map[string]int) int {
	key := normalizeModelKey(modelName)
	if v, ok := orderMap[key]; ok {
		return v
	}
	return 1_000_000
}

func normalizeModelKey(s string) string {
	return strings.ToUpper(strings.TrimSpace(s))
}

func (h *UnitHandler) nextAutoFillUnitID(tx *gorm.DB, batchID string, slot int) (string, error) {
	base := fmt.Sprintf("%s-AF-%02d", batchID, slot)
	for i := 0; i < 20; i++ {
		candidate := fmt.Sprintf("%s-%06d", base, rand.Intn(1000000))
		var cnt int64
		if err := tx.Model(&model.Unit{}).Where("unit_id = ?", candidate).Count(&cnt).Error; err != nil {
			return "", err
		}
		if cnt == 0 {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("failed to generate unique unit_id for batch %s slot %d", batchID, slot)
}

func (h *UnitHandler) getBatchBreakDays() int {
	const fallback = 30
	cfgRepo := repo.NewConfigRepo(h.db)

	var wrapper struct {
		V int `json:"V"`
	}
	if err := cfgRepo.GetJSON("batch_break_days", map[string]int{"V": fallback}, &wrapper); err == nil && wrapper.V > 0 {
		return wrapper.V
	}

	var num int
	if err := cfgRepo.GetJSON("batch_break_days", fallback, &num); err == nil && num > 0 {
		return num
	}

	var s string
	if err := cfgRepo.GetJSON("batch_break_days", "", &s); err == nil {
		if v, convErr := strconv.Atoi(strings.TrimSpace(s)); convErr == nil && v > 0 {
			return v
		}
	}
	return fallback
}

func (h *UnitHandler) enforceFamilyGapDays(tx *gorm.DB, family string) ([]string, error) {
	gapDays := h.getBatchBreakDays()
	batches, err := h.batchRepo.ListPredictedByModelForUpdate(tx, family)
	if err != nil {
		return nil, err
	}

	touched := []string{}
	seen := map[string]bool{}
	addTouched := func(batchID string) {
		bid := strings.TrimSpace(batchID)
		if bid == "" || seen[bid] {
			return
		}
		seen[bid] = true
		touched = append(touched, bid)
	}

	findNextSameCapacityIdx := func(curIdx int) int {
		if curIdx < 0 || curIdx >= len(batches) {
			return -1
		}
		curCap := batches[curIdx].Capacity
		for j := curIdx + 1; j < len(batches); j++ {
			if batches[j].Capacity == curCap {
				return j
			}
		}
		return -1
	}

	for i := 0; i < len(batches); i++ {
		batchID := batches[i].BatchID

		for {
			units, err := h.repo.ListByBatchIDsForUpdate(tx, []string{batchID})
			if err != nil {
				return touched, err
			}

			var minDue *time.Time
			var maxDue *time.Time
			var candidate *model.Unit
			for j := range units {
				u := units[j]
				if u.IsLocked {
					continue
				}
				if u.ContractNo == nil || strings.TrimSpace(*u.ContractNo) == "" || u.DueDate == nil {
					continue
				}

				d := *u.DueDate
				if minDue == nil || d.Before(*minDue) {
					tmp := d
					minDue = &tmp
				}
				if maxDue == nil || d.After(*maxDue) || (d.Equal(*maxDue) && candidate != nil && u.SlotIndex > candidate.SlotIndex) {
					tmp := d
					maxDue = &tmp
					uCopy := u
					candidate = &uCopy
				}
			}

			if minDue == nil || maxDue == nil || candidate == nil {
				break
			}
			spanDays := maxDue.Sub(*minDue).Hours() / 24.0
			if spanDays <= float64(gapDays) {
				break
			}

			addTouched(batchID)

			nextIdx := findNextSameCapacityIdx(i)
			if nextIdx < 0 {
				newBatch, err := h.createOverflowExtensionBatch(tx, &batches[i])
				if err != nil {
					return touched, err
				}
				if err := h.repo.MoveToBatch(tx, candidate.UnitID, newBatch.BatchID, 1); err != nil {
					return touched, err
				}
				if err := h.repo.CompactSlots(tx, batchID); err != nil {
					return touched, err
				}
				if err := h.fillBatchToCapacity(tx, &batches[i]); err != nil {
					return touched, err
				}
				if err := h.fillBatchToCapacity(tx, newBatch); err != nil {
					return touched, err
				}
				addTouched(newBatch.BatchID)
				continue
			}

			nextBatchID := batches[nextIdx].BatchID
			nextEjectUnit, err := h.pickEjectableUnboundUnit(tx, nextBatchID, 0)
			if err != nil {
				return touched, err
			}
			if nextEjectUnit != nil {
				if err := tx.Where("unit_id = ?", nextEjectUnit.UnitID).Delete(&model.Unit{}).Error; err != nil {
					return touched, err
				}
				if err := h.repo.MoveToBatch(tx, candidate.UnitID, nextBatchID, nextEjectUnit.SlotIndex); err != nil {
					return touched, err
				}
				if err := h.repo.CompactSlots(tx, batchID); err != nil {
					return touched, err
				}
				if err := h.fillBatchToCapacity(tx, &batches[i]); err != nil {
					return touched, err
				}
				addTouched(nextBatchID)
				continue
			}

			if err := h.repo.MoveToBatch(tx, candidate.UnitID, nextBatchID, 0); err != nil {
				return touched, err
			}
			if err := h.repo.ReorderBatchWithUnit(tx, nextBatchID, candidate.UnitID, 1); err != nil {
				return touched, err
			}
			if err := h.repo.CompactSlots(tx, batchID); err != nil {
				return touched, err
			}
			if err := h.fillBatchToCapacity(tx, &batches[i]); err != nil {
				return touched, err
			}
			addTouched(nextBatchID)

			count, err := h.repo.CountByBatch(tx, nextBatchID)
			if err != nil {
				return touched, err
			}
			if int(count) > batches[nextIdx].Capacity {
				extraTouched, err := h.cascadeOverflowBySlot(tx, nextBatchID, family, candidate.UnitID)
				if err != nil {
					return touched, err
				}
				for _, bid := range extraTouched {
					addTouched(bid)
				}
			}
		}
	}
	return touched, nil
}

func supplementLevel3FromModelDict(db *gorm.DB, cfg *capacityRatioCfg) {
	if cfg == nil {
		return
	}
	if cfg.Level3 == nil {
		cfg.Level3 = map[string]map[string]int{}
	}
	supplementLevel3MapFromModelDict(db, cfg.Level3)
}

func supplementLevel3MapFromModelDict(db *gorm.DB, level3 map[string]map[string]int) {
	if db == nil || level3 == nil {
		return
	}

	var rows []struct {
		ModelName   string `gorm:"column:model_name"`
		ModelFamily string `gorm:"column:model_family"`
	}
	if err := db.Table("model_dictionary").
		Select("model_name, model_family").
		Where("enabled = 1").
		Scan(&rows).Error; err != nil {
		return
	}

	dictModelsByCat := map[string][]string{}
	dictCatByModel := map[string]string{}
	for _, row := range rows {
		modelName := strings.TrimSpace(row.ModelName)
		if modelName == "" || modelName == "G" || modelName == "XS" || modelName == "AUTO" {
			continue
		}
		cat := modelCategoryOf(modelName)
		if cat == "" || cat == "特殊" {
			continue
		}
		mf := strings.TrimSpace(row.ModelFamily)
		if mf != "" {
			cat = normalizeCategoryFromFamily(mf, modelName)
		}
		dictCatByModel[normalizeModelKey(modelName)] = cat
		dictModelsByCat[cat] = append(dictModelsByCat[cat], modelName)
	}

	rehomeLevel3ModelsByDictionary(level3, dictCatByModel)

	for cat, dictModels := range dictModelsByCat {
		if _, exists := level3[cat]; !exists || len(level3[cat]) == 0 {
			level3[cat] = map[string]int{dictModels[0]: 100}
			continue
		}

		missingModels := []string{}
		for _, m := range dictModels {
			if v, ok := level3[cat][m]; !ok || v <= 0 {
				missingModels = append(missingModels, m)
			}
		}
		if len(missingModels) == 0 {
			continue
		}

		for _, mm := range missingModels {
			dominantModel := ""
			dominantRatio := 0
			for m, r := range level3[cat] {
				if r > dominantRatio {
					dominantRatio = r
					dominantModel = m
				}
			}
			if dominantRatio >= 10 {
				level3[cat][dominantModel] = dominantRatio - 5
				level3[cat][mm] = 5
			}
		}
	}
	normalizeUnitLevel3RatioSums(level3)
}

func normalizeUnitLevel3RatioSums(level3 map[string]map[string]int) {
	for _, category := range []string{"中小型G", "中小型XS", "中大型XS", "中小型AUTO", "中大型AUTO"} {
		ratios := level3[category]
		if len(ratios) == 0 {
			continue
		}
		sum := 0
		for _, value := range ratios {
			if value > 0 {
				sum += value
			}
		}
		if sum == 100 {
			continue
		}
		keys := make([]string, 0, len(ratios))
		for key := range ratios {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		if sum <= 0 {
			for _, key := range keys {
				ratios[key] = 0
			}
			if len(keys) > 0 {
				ratios[keys[0]] = 100
			}
			continue
		}
		type remainder struct {
			key string
			rem float64
		}
		used := 0
		remainders := make([]remainder, 0, len(keys))
		for _, key := range keys {
			exact := float64(ratios[key]) * 100.0 / float64(sum)
			base := int(math.Floor(exact))
			ratios[key] = base
			used += base
			remainders = append(remainders, remainder{key: key, rem: exact - float64(base)})
		}
		sort.SliceStable(remainders, func(i, j int) bool {
			if remainders[i].rem != remainders[j].rem {
				return remainders[i].rem > remainders[j].rem
			}
			return remainders[i].key < remainders[j].key
		})
		for i := 0; used < 100 && i < len(remainders); i++ {
			ratios[remainders[i].key]++
			used++
		}
	}
}

func rehomeLevel3ModelsByDictionary(level3 map[string]map[string]int, dictCatByModel map[string]string) {
	if len(level3) == 0 || len(dictCatByModel) == 0 {
		return
	}
	next := map[string]map[string]int{}
	for category, ratios := range level3 {
		cat := canonicalCategory(category)
		if next[cat] == nil {
			next[cat] = map[string]int{}
		}
		for modelName, ratio := range ratios {
			targetCat := dictCatByModel[normalizeModelKey(modelName)]
			if targetCat == "" {
				targetCat = cat
			}
			if next[targetCat] == nil {
				next[targetCat] = map[string]int{}
			}
			next[targetCat][modelName] += ratio
		}
	}
	for category := range level3 {
		delete(level3, category)
	}
	for category, ratios := range next {
		level3[category] = ratios
	}
}

func normalizeCategoryFromFamily(family string, modelName string) string {
	f := canonicalCategory(strings.TrimSpace(family))
	if f == "中小型G" || f == "中小型XS" || f == "中大型XS" || f == "中小型AUTO" || f == "中大型AUTO" || f == "特殊" || f == "SPECIAL" {
		if f == "SPECIAL" {
			return "特殊"
		}
		return f
	}
	return modelCategoryOf(modelName)
}

func loadCapacityRatioCfg(db *gorm.DB) capacityRatioCfg {
	fallback := capacityRatioCfg{
		Level2Global: map[string]int{"涓皬鍨婫": 24, "涓皬鍨媂S": 38, "涓ぇ鍨媂S": 38, "涓皬鍨婣UTO": 0, "涓ぇ鍨婣UTO": 0, "鐗规畩": 0},
		Level2: map[string]map[string]int{
			"G":    {"中小型G": 92, "特殊": 8},
			"XS":   {"中小型XS": 75, "中大型XS": 25},
			"AUTO": {"中小型AUTO": 75, "中大型AUTO": 25},
		},
		Level3: map[string]map[string]int{
			"中小型G": {"FR-400G": 60, "FH-300C": 40},
		},
	}
	cfg := fallback
	_ = repo.NewConfigRepo(db).GetJSON("capacity_ratio", fallback, &cfg)
	if cfg.Level2 == nil {
		cfg.Level2 = fallback.Level2
	}
	cfg.Level2Global = normalizeIntRatioKeys(cfg.Level2Global)
	if cfg.Level2Global == nil {
		cfg.Level2Global = fallback.Level2Global
	}
	cfg.Level2 = normalizeUnitLevel2RatioKeys(cfg.Level2)
	cfg.Level3 = normalizeLevel3RatioKeys(cfg.Level3)
	supplementLevel3FromModelDict(db, &cfg)
	cfg.Level2 = buildEffectiveLevel2ForUnit(cfg.Level2, cfg.Level3)
	return cfg
}

func normalizeUnitLevel2RatioKeys(in map[string]map[string]int) map[string]map[string]int {
	if in == nil {
		return nil
	}
	out := map[string]map[string]int{}
	for family, ratios := range in {
		if out[family] == nil {
			out[family] = map[string]int{}
		}
		for k, v := range ratios {
			out[family][canonicalCategory(k)] += v
		}
	}
	return out
}

func buildEffectiveLevel2ForUnit(level2 map[string]map[string]int, level3 map[string]map[string]int) map[string]map[string]int {
	if len(level2) == 0 || len(level3) == 0 {
		return level2
	}
	eff := map[string]map[string]int{}
	for family, catMap := range level2 {
		if eff[family] == nil {
			eff[family] = map[string]int{}
		}
		for category, catRatio := range catMap {
			modelRatios := level3[category]
			if len(modelRatios) == 0 {
				eff[family][category] += catRatio
				continue
			}
			for model, modelRatio := range modelRatios {
				eff[family][model] += int(math.Round(float64(catRatio*modelRatio) / 100.0))
			}
		}
	}
	return eff
}

func chooseFillModels(family string, slots int, level2 map[string]map[string]int) []string {
	if slots <= 0 {
		return nil
	}
	dist := distributeByRatioForSlots(family, slots, level2)
	out := make([]string, 0, slots)
	for sizeKey, count := range dist {
		modelName := concreteModelByFamilyAndSize(family, sizeKey)
		for i := 0; i < count; i++ {
			out = append(out, modelName)
		}
	}
	sort.Strings(out)
	return out
}

func chooseFillModelsForBatch(family string, capacity int, slots int, ratio capacityRatioCfg) []string {
	if slots <= 0 {
		return nil
	}
	category := fillCategoryForBatch(family, capacity)
	if category != "" {
		if models := chooseFillModelsFromRatios(family, slots, ratio.Level3[category]); len(models) > 0 {
			return models
		}
		out := make([]string, 0, slots)
		fallback := defaultFillModelForBatch(family, capacity)
		for i := 0; i < slots; i++ {
			out = append(out, fallback)
		}
		return out
	}
	return chooseFillModels(family, slots, ratio.Level2)
}

func chooseFillModelsForBatchWithOrderedUnits(family string, capacity int, slots int, ratio capacityRatioCfg, units []model.Unit) []string {
	models := chooseFillModelsForBatch(family, capacity, slots, ratio)
	if slots <= 0 || len(models) == 0 {
		return models
	}
	category := fillCategoryForBatch(family, capacity)
	ratios := ratio.Level3[category]
	if len(ratios) == 0 {
		return models
	}

	counts := map[string]int{}
	for _, modelName := range models {
		counts[modelName]++
	}

	type candidate struct {
		model string
		ratio int
	}
	seen := map[string]bool{}
	candidates := make([]candidate, 0)
	for _, u := range units {
		if u.ContractNo == nil || strings.TrimSpace(*u.ContractNo) == "" {
			continue
		}
		modelName := strings.TrimSpace(u.ModelType)
		if modelName == "" || seen[normalizeModelKey(modelName)] {
			continue
		}
		r := 0
		for key, value := range ratios {
			if normalizeModelKey(key) == normalizeModelKey(modelName) {
				r = value
				modelName = concreteModelByFamilyAndSize(family, key)
				break
			}
		}
		if r <= 0 {
			continue
		}
		seen[normalizeModelKey(modelName)] = true
		candidates = append(candidates, candidate{model: modelName, ratio: r})
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].ratio != candidates[j].ratio {
			return candidates[i].ratio > candidates[j].ratio
		}
		return candidates[i].model < candidates[j].model
	})

	for _, cand := range candidates {
		if counts[cand.model] > 0 {
			continue
		}
		donor := ""
		donorCount := 1
		for modelName, count := range counts {
			if normalizeModelKey(modelName) == normalizeModelKey(cand.model) {
				continue
			}
			if count > donorCount {
				donor = modelName
				donorCount = count
			}
		}
		if donor == "" {
			continue
		}
		counts[donor]--
		counts[cand.model]++
	}

	out := make([]string, 0, slots)
	for modelName, count := range counts {
		for i := 0; i < count; i++ {
			out = append(out, modelName)
		}
	}
	sort.Strings(out)
	return out
}

func chooseFillModelsFromRatios(family string, slots int, ratios map[string]int) []string {
	if slots <= 0 || len(ratios) == 0 {
		return nil
	}
	level2 := map[string]map[string]int{
		family: ratios,
	}
	dist := distributeByRatioForSlots(family, slots, level2)
	out := make([]string, 0, slots)
	for modelKey, count := range dist {
		modelName := concreteModelByFamilyAndSize(family, modelKey)
		for i := 0; i < count; i++ {
			out = append(out, modelName)
		}
	}
	sort.Strings(out)
	return out
}

func fillCategoryForBatch(family string, capacity int) string {
	switch strings.ToUpper(strings.TrimSpace(family)) {
	case "G":
		return "中小型G"
	case "XS":
		if capacity == 16 {
			return "中大型XS"
		}
		return "中小型XS"
	case "AUTO":
		if capacity == 16 {
			return "中大型AUTO"
		}
		return "中小型AUTO"
	default:
		return ""
	}
}

func defaultFillModelForBatch(family string, capacity int) string {
	category := fillCategoryForBatch(family, capacity)
	switch category {
	case "中大型XS", "中大型AUTO":
		return concreteModelByFamilyAndSize(family, "600")
	default:
		return concreteModelByFamilyAndSize(family, "400")
	}
}

func distributeByRatioForSlots(family string, slots int, level2 map[string]map[string]int) map[string]int {
	ratios := level2[family]
	if len(ratios) == 0 {
		return map[string]int{"400": slots}
	}

	type item struct {
		key    string
		ratio  int
		weight int
	}
	items := make([]item, 0, len(ratios))
	positive := 0
	for k, v := range ratios {
		if v <= 0 {
			continue
		}
		items = append(items, item{key: k, ratio: v, weight: v})
		positive++
	}
	if len(items) == 0 {
		return map[string]int{"400": slots}
	}

	result := make(map[string]int, len(items))
	if slots < positive {
		r := rand.New(rand.NewSource(time.Now().UnixNano()))
		totalWeight := 0
		for _, it := range items {
			totalWeight += it.weight
		}
		for i := 0; i < slots; i++ {
			pick := r.Intn(totalWeight) + 1
			acc := 0
			chosen := items[0].key
			for _, it := range items {
				acc += it.weight
				if pick <= acc {
					chosen = it.key
					break
				}
			}
			result[chosen]++
		}
		return result
	}

	allocated := 0
	remainders := make(map[string]float64, len(items))
	for _, it := range items {
		exact := float64(slots) * float64(it.ratio) / 100.0
		base := int(math.Floor(exact))
		result[it.key] = base
		allocated += base
		remainders[it.key] = exact - float64(base)
	}
	for allocated < slots {
		bestKey := items[0].key
		bestRem := -1.0
		for _, it := range items {
			if remainders[it.key] > bestRem {
				bestRem = remainders[it.key]
				bestKey = it.key
			}
		}
		result[bestKey]++
		remainders[bestKey] = -1.0
		allocated++
	}
	return result
}

func concreteModelByFamilyAndSize(family string, sizeKey string) string {
	f := strings.ToUpper(strings.TrimSpace(family))
	trimmed := strings.TrimSpace(sizeKey)
	if strings.HasPrefix(strings.ToUpper(trimmed), "FR-") {
		return trimmed
	}
	s := strings.ToLower(trimmed)
	if strings.Contains(trimmed, "大机") {
		s = "600"
	}
	if strings.Contains(trimmed, "中大型") {
		s = "600"
	}
	if strings.Contains(trimmed, "小机") {
		s = "400"
	}
	if strings.Contains(trimmed, "中小型") {
		s = "400"
	}
	if strings.Contains(trimmed, "特殊") {
		s = "600"
	}
	switch s {
	case "big":
		s = "600"
	case "other":
		s = "400"
	case "":
		s = "400"
	}
	if s == "300" {
		s = "400"
	}

	switch f {
	case "G":
		switch s {
		case "500":
			return "FR-500G"
		case "600":
			return "FR-600G"
		default:
			return "FR-400G"
		}
	case "XS":
		switch s {
		case "500":
			return "FR-500XS(PRO)"
		case "600":
			return "FR-600XS(PRO)"
		default:
			return "FR-400XS(PRO)"
		}
	case "AUTO":
		switch s {
		case "500":
			return "FR-500AUTO"
		case "600":
			return "FR-600AUTO"
		default:
			return "FR-400AUTO"
		}
	default:
		return family
	}
}

func slotFromRequest(slot *int, fallback int) int {
	if slot != nil && *slot > 0 {
		return *slot
	}
	return fallback
}

func (h *UnitHandler) SwapContent(c *gin.Context) {
	var req service.SwapContentReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}
	if err := h.rushSvc.SwapContent(req, actor); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *UnitHandler) RushInsert(c *gin.Context) {
	var req service.RushInsertReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}
	if err := h.rushSvc.RushInsert(req, actor); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *UnitHandler) EmptyContainers(c *gin.Context) {
	modelType := c.Query("model_type")
	units, err := h.repo.FindEmptyContainers(modelType)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if units == nil {
		units = []model.Unit{}
	}
	sanitizeUnitsRemarkForResponse(units)
	c.JSON(http.StatusOK, gin.H{"units": units})
}

func (h *UnitHandler) ReorderSlot(c *gin.Context) {
	var req struct {
		NewSlotIndex int `json:"new_slot_index" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if req.NewSlotIndex < 1 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "new_slot_index must be >= 1"})
		return
	}

	tx := h.db.Begin()
	defer tx.Rollback()

	unit, err := h.repo.LockForUpdate(tx, c.Param("id"))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "unit not found"})
		return
	}
	if unit.IsLocked {
		c.JSON(http.StatusBadRequest, gin.H{"error": "unit is locked"})
		return
	}

	batchID := unit.BatchID
	newSlot := req.NewSlotIndex

	if unit.SlotIndex == newSlot {
		c.JSON(http.StatusOK, gin.H{"success": true, "message": "no change"})
		return
	}

	if err := h.repo.MoveToBatch(tx, c.Param("id"), batchID, 0); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.repo.ReorderBatchWithUnit(tx, batchID, c.Param("id"), newSlot); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *UnitHandler) RepairFamilyMismatches(c *gin.Context) {
	type mismatchRow struct {
		UnitID         string
		BatchID        string
		SlotIndex      int
		ModelType      string
		BatchModelType string
		BatchCapacity  int
	}
	var rows []mismatchRow
	if err := h.db.Raw(`
SELECT
  u.unit_id,
  u.batch_id,
  u.slot_index,
  u.model_type,
  b.model_type AS batch_model_type,
  b.capacity AS batch_capacity
FROM units u
JOIN batches b ON b.batch_id = u.batch_id
WHERE b.status IN ('Predicted', 'Confirmed', 'In_Production')
  AND u.contract_no IS NOT NULL
`).Scan(&rows).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	mismatches := make([]mismatchRow, 0)
	for _, r := range rows {
		unitGroup := engine.ProductionGroupForModel(r.ModelType)
		batchGroup := engine.ProductionGroupForBatch(r.BatchModelType, r.BatchCapacity)
		if unitGroup != "" && batchGroup != "" && unitGroup != batchGroup {
			mismatches = append(mismatches, r)
		}
	}

	fixed := make([]gin.H, 0)
	failed := make([]gin.H, 0)
	for _, item := range mismatches {
		tx := h.db.Begin()
		var src mismatchRow
		if err := tx.Raw(`
SELECT u.unit_id, u.batch_id, u.slot_index, u.model_type, b.model_type AS batch_model_type, b.capacity AS batch_capacity
FROM units u
JOIN batches b ON b.batch_id = u.batch_id
WHERE u.unit_id = ?
FOR UPDATE
`, item.UnitID).Scan(&src).Error; err != nil {
			tx.Rollback()
			failed = append(failed, gin.H{"unit_id": item.UnitID, "error": err.Error()})
			continue
		}
		srcGroup := engine.ProductionGroupForBatch(src.BatchModelType, src.BatchCapacity)
		unitGroup := engine.ProductionGroupForModel(src.ModelType)
		if srcGroup == "" || unitGroup == "" || srcGroup == unitGroup {
			tx.Rollback()
			continue
		}

		var groupExpr string
		switch unitGroup {
		case engine.ProductionGroupLarge:
			groupExpr = "(b2.capacity = 16 AND (UPPER(b2.model_type) LIKE '%XS%' OR UPPER(b2.model_type) LIKE '%AUTO%'))"
		case engine.ProductionGroupSmallAUTO:
			groupExpr = "(b2.capacity <> 16 AND UPPER(b2.model_type) LIKE '%AUTO%')"
		case engine.ProductionGroupSmallXS:
			groupExpr = "(b2.capacity <> 16 AND UPPER(b2.model_type) LIKE '%XS%')"
		case engine.ProductionGroupSmallG:
			groupExpr = "(UPPER(b2.model_type) = 'G' OR UPPER(b2.model_type) LIKE '%G')"
		case engine.ProductionGroupSpecial:
			groupExpr = "UPPER(TRIM(b2.model_type)) = 'SPECIAL'"
		default:
			tx.Rollback()
			failed = append(failed, gin.H{"unit_id": item.UnitID, "error": "unsupported production group " + unitGroup})
			continue
		}

		var fb struct {
			UnitID    string
			BatchID   string
			SlotIndex int
		}
		if err := tx.Raw(`
SELECT u2.unit_id, u2.batch_id, u2.slot_index
FROM units u2
JOIN batches b2 ON b2.batch_id = u2.batch_id
WHERE b2.status IN ('Predicted', 'Confirmed', 'In_Production')
  AND ` + groupExpr + `
  AND u2.contract_no IS NULL
  AND u2.is_locked = 0
ORDER BY b2.due_date_start ASC, u2.slot_index ASC
LIMIT 1
FOR UPDATE
`).Scan(&fb).Error; err != nil {
			tx.Rollback()
			failed = append(failed, gin.H{"unit_id": item.UnitID, "error": err.Error()})
			continue
		}
		if strings.TrimSpace(fb.UnitID) == "" {
			tx.Rollback()
			failed = append(failed, gin.H{"unit_id": item.UnitID, "error": "no empty slot found in target family batches"})
			continue
		}

		if err := tx.Model(&model.Unit{}).Where("unit_id = ?", src.UnitID).Updates(map[string]interface{}{
			"batch_id":   fb.BatchID,
			"slot_index": 900001,
		}).Error; err != nil {
			tx.Rollback()
			failed = append(failed, gin.H{"unit_id": item.UnitID, "error": err.Error()})
			continue
		}
		if err := tx.Model(&model.Unit{}).Where("unit_id = ?", fb.UnitID).Updates(map[string]interface{}{
			"batch_id":   src.BatchID,
			"slot_index": 900002,
			"model_type": src.BatchModelType,
		}).Error; err != nil {
			tx.Rollback()
			failed = append(failed, gin.H{"unit_id": item.UnitID, "error": err.Error()})
			continue
		}
		if err := tx.Model(&model.Unit{}).Where("unit_id = ?", src.UnitID).Update("slot_index", fb.SlotIndex).Error; err != nil {
			tx.Rollback()
			failed = append(failed, gin.H{"unit_id": item.UnitID, "error": err.Error()})
			continue
		}
		if err := tx.Model(&model.Unit{}).Where("unit_id = ?", fb.UnitID).Update("slot_index", src.SlotIndex).Error; err != nil {
			tx.Rollback()
			failed = append(failed, gin.H{"unit_id": item.UnitID, "error": err.Error()})
			continue
		}

		if err := tx.Commit().Error; err != nil {
			failed = append(failed, gin.H{"unit_id": item.UnitID, "error": err.Error()})
			continue
		}
		fixed = append(fixed, gin.H{
			"unit_id":       src.UnitID,
			"from_batch_id": src.BatchID,
			"to_batch_id":   fb.BatchID,
			"swapped_with":  fb.UnitID,
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"success":        true,
		"mismatch_count": len(mismatches),
		"fixed_count":    len(fixed),
		"fixed":          fixed,
		"failed":         failed,
	})
}

func (h *UnitHandler) MarkSpot(c *gin.Context) {
	tx := h.db.Begin()
	defer tx.Rollback()

	unitID := c.Param("id")
	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}
	unit, err := h.repo.LockForUpdate(tx, unitID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "unit not found"})
		return
	}

	var contractNo string
	if unit.ContractNo != nil {
		contractNo = strings.TrimSpace(*unit.ContractNo)
	}

	if err := h.repo.ClearOrderFields(tx, unitID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := h.repo.UnlockUnitDB(tx, unitID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if contractNo != "" {
		if err := tx.Exec(
			"UPDATE factory_plan SET 状态 = '已取消' "+
				"WHERE TRIM(COALESCE(合同号, '')) COLLATE utf8mb4_general_ci = ? COLLATE utf8mb4_general_ci",
			contractNo,
		).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update factory_plan: " + err.Error()})
			return
		}

		if err := tx.Exec(
			"DELETE FROM production_queue "+
				"WHERE TRIM(COALESCE(contract_no, '')) COLLATE utf8mb4_general_ci = ? COLLATE utf8mb4_general_ci "+
				"AND status = 'Waiting'",
			contractNo,
		).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to clear production_queue: " + err.Error()})
			return
		}

		if err := tx.Exec(
			"UPDATE rush_order_queue SET status = 'deleted' "+
				"WHERE TRIM(COALESCE(contract_no, '')) COLLATE utf8mb4_general_ci = ? COLLATE utf8mb4_general_ci "+
				"AND status = 'pending'",
			contractNo,
		).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to clear rush_order_queue: " + err.Error()})
			return
		}

		type UnitBatch struct {
			UnitID string
			Status string
		}
		var siblingUnits []UnitBatch
		if err := tx.Raw(`
			SELECT u.unit_id, b.status 
			FROM units u 
			JOIN batches b ON u.batch_id = b.batch_id 
			WHERE TRIM(COALESCE(u.contract_no, '')) COLLATE utf8mb4_general_ci = ? COLLATE utf8mb4_general_ci
			  AND u.unit_id != ?
		`, contractNo, unitID).Scan(&siblingUnits).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to find sibling units: " + err.Error()})
			return
		}

		for _, su := range siblingUnits {
			// 强制清除所有状态的兄弟卡片（Predicted / Confirmed / In_Production）
			if err := h.repo.ClearOrderFields(tx, su.UnitID); err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to clear sibling unit: " + err.Error()})
				return
			}
			if err := h.repo.UnlockUnitDB(tx, su.UnitID); err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to unlock sibling unit: " + err.Error()})
				return
			}
		}
	}

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if contractNo != "" {
		go h.NotifyContractCancelToPython(contractNo, actor, "mark-spot")
		h.hub.Broadcast("unit:updated", gin.H{"contract_no": contractNo, "unit_id": unitID, "mode": "contract-cancelled-by-mark-spot"})
	} else {
		h.hub.Broadcast("unit:updated", gin.H{"unit_id": unitID, "mode": "mark-spot"})
	}

	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *UnitHandler) ConvertToRush(c *gin.Context) {
	tx := h.db.Begin()
	defer tx.Rollback()

	unitID := c.Param("id")
	unit, err := h.repo.LockForUpdate(tx, unitID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "unit not found"})
		return
	}

	var batch model.Batch
	if err := tx.Where("batch_id = ?", unit.BatchID).First(&batch).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "batch not found"})
		return
	}
	if batch.Status != model.StatusPredicted {
		c.JSON(http.StatusBadRequest, gin.H{"error": "only Predicted batch units can be converted to rush orders"})
		return
	}
	if unit.IsLocked {
		c.JSON(http.StatusBadRequest, gin.H{"error": "unit is locked"})
		return
	}

	contractNo := strings.TrimSpace(strPtrVal(unit.ContractNo))
	modelType := strings.TrimSpace(unit.ModelType)
	if contractNo == "" || modelType == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "empty or stock placeholder cannot be converted to rush order"})
		return
	}

	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}
	var dueDate interface{}
	if unit.DueDate != nil {
		dueDate = unit.DueDate.Format("2006-01-02")
	}
	if err := tx.Exec(`
		INSERT INTO rush_order_queue
			(contract_no, customer, dealer_name, model_type, due_date, remark, source, status, created_by, updated_by)
		VALUES
			(?, ?, ?, ?, ?, ?, 'sandbox-card', 'pending', ?, ?)
	`,
		contractNo,
		strings.TrimSpace(strPtrVal(unit.Customer)),
		strings.TrimSpace(strPtrVal(unit.DealerName)),
		modelType,
		dueDate,
		strings.TrimSpace(strPtrVal(unit.OrderRemark)),
		actor,
		actor,
	).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create rush order: " + err.Error()})
		return
	}

	if err := h.repo.ClearOrderFields(tx, unitID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := tx.Model(&model.Unit{}).Where("unit_id = ?", unitID).Update("is_contract_pinned", false).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	h.hub.Broadcast("unit:updated", gin.H{"unit_id": unitID, "mode": "convert-to-rush"})
	c.JSON(http.StatusOK, gin.H{"success": true})
}
func (h *UnitHandler) NotifyUpdate(c *gin.Context) {
	unitID := c.Param("id")
	sn := strings.TrimSpace(c.Query("sn"))

	if unitID == "" || (unitID == "lookup" && sn == "") {
		c.JSON(http.StatusBadRequest, gin.H{"error": "unit id or sn required"})
		return
	}
	// Pull latest FG info and persist it into every matching sandbox unit.
	var updatedUnits []model.Unit
	query := h.db.Table("units").
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
		Where("1 = 1")
	if unitID == "lookup" {
		query = query.Where("TRIM(COALESCE(units.serial_no, '')) = ? OR TRIM(COALESCE(units.forecast_serial_no, '')) = ?", sn, sn)
	} else {
		query = query.Where("units.unit_id = ?", unitID)
	}
	if err := query.Find(&updatedUnits).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to load unit update: " + err.Error()})
		return
	}
	if len(updatedUnits) == 0 {
		c.JSON(http.StatusOK, gin.H{"success": true, "updated_units": 0, "message": "sn not found in sandbox, no broadcast"})
		return
	}

	updatedCount := 0
	for _, updatedUnit := range updatedUnits {
		persistUpdates := map[string]interface{}{}
		if updatedUnit.FgContractNo != nil {
			persistUpdates["contract_no"] = strings.TrimSpace(*updatedUnit.FgContractNo)
		}
		if updatedUnit.FgCustomer != nil {
			persistUpdates["customer"] = strings.TrimSpace(*updatedUnit.FgCustomer)
		}
		if updatedUnit.FgDealer != nil {
			persistUpdates["dealer_name"] = strings.TrimSpace(*updatedUnit.FgDealer)
		}
		if updatedUnit.FgRemark != nil {
			persistUpdates["order_remark"] = strings.TrimSpace(*updatedUnit.FgRemark)
		}
		if updatedUnit.FgSalesID != nil {
			persistUpdates["sales_id"] = strings.TrimSpace(*updatedUnit.FgSalesID)
		}
		if updatedUnit.FgModel != nil && strings.TrimSpace(*updatedUnit.FgModel) != "" {
			persistUpdates["model_type"] = strings.TrimSpace(*updatedUnit.FgModel)
		}

		if len(persistUpdates) > 0 {
			if err := h.db.Model(&model.Unit{}).Where("unit_id = ?", updatedUnit.UnitID).Updates(persistUpdates).Error; err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to persist unit update: " + err.Error()})
				return
			}
			updatedCount++
		}
		h.hub.Broadcast("unit:updated", gin.H{"unit_id": updatedUnit.UnitID})
	}

	c.JSON(http.StatusOK, gin.H{"success": true, "updated_units": updatedCount})
}
