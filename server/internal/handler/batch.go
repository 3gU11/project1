package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"smart-scheduling/server/internal/model"
	"smart-scheduling/server/internal/repo"
	"smart-scheduling/server/internal/service"
)

type BatchHandler struct {
	db       *gorm.DB
	repo     *repo.BatchRepo
	unitRepo *repo.UnitRepo
	svc      *service.BatchSvc
}

func NewBatchHandler(db *gorm.DB, r *repo.BatchRepo, ur *repo.UnitRepo, svc *service.BatchSvc) *BatchHandler {
	return &BatchHandler{db: db, repo: r, unitRepo: ur, svc: svc}
}

func (h *BatchHandler) List(c *gin.Context) {
	status := c.Query("status")
	modelType := c.Query("model_type")
	batches, err := h.repo.List(status, modelType)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if batches == nil {
		batches = []model.Batch{}
	}
	var baselineIDs []string
	if err := h.db.Table("sandbox_batch_baselines").Pluck("batch_id", &baselineIDs).Error; err == nil {
		manual := make(map[string]bool, len(baselineIDs))
		for _, id := range baselineIDs {
			manual[id] = true
		}
		for i := range batches {
			batches[i].IsManuallyAdjusted = manual[batches[i].BatchID]
		}
	}
	// updated_at is a data-change timestamp, not evidence that the predictor ran.
	// Use the persisted asynchronous job completion time; leave it zero so the UI
	// can display "unknown" on older data where no job record exists.
	var lastRecomputeAt *time.Time
	_ = h.db.Table("sandbox_recompute_jobs").
		Select("completed_at").
		Where("status = ? AND completed_at IS NOT NULL", "succeeded").
		Order("completed_at DESC").
		Limit(1).
		Scan(&lastRecomputeAt).Error
	for i := range batches {
		populatePredictionSummary(&batches[i])
		if lastRecomputeAt != nil && batches[i].Status == model.StatusPredicted {
			batches[i].LastRecomputeAt = *lastRecomputeAt
		}
	}
	sanitizeBatchesRemarkForResponse(batches)
	c.JSON(http.StatusOK, gin.H{"batches": batches})
}

func populatePredictionSummary(batch *model.Batch) {
	if batch == nil {
		return
	}
	batch.AlgorithmVersion = "heuristic-edd-v1"
	// The sandbox has no execution schedule from which an inbound date can be
	// predicted. Only a user-saved value is exposed; the due window must never
	// be presented as an estimated inbound date.
	if batch.ExpectedInboundDate == nil {
		batch.ExpectedInboundSource = "待人工填写"
	} else {
		batch.ExpectedInboundSource = "人工填写"
	}
	batch.LastRecomputeAt = time.Time{}
	// List and impact paths may both enrich the same loaded entity. Reset every
	// derived value so a second enrichment remains a read-only operation.
	batch.OrderedCount = 0
	batch.StockCount = 0
	batch.EmptyCount = 0
	batch.EarliestDueDate = nil
	batch.DueGapDays = nil
	batch.RiskCount = 0
	batch.Risks = []model.BatchRisk{}
	capacityOverflowIDs := make(map[string]struct{})
	for _, unit := range batch.Units {
		if unit.ContractNo != nil && strings.TrimSpace(*unit.ContractNo) != "" {
			batch.OrderedCount++
			if unit.DueDate != nil && (batch.EarliestDueDate == nil || unit.DueDate.Before(*batch.EarliestDueDate)) {
				due := *unit.DueDate
				batch.EarliestDueDate = &due
			}
		} else {
			batch.StockCount++
		}
	}
	batch.EmptyCount = batch.Capacity - len(batch.Units)
	if batch.EmptyCount < 0 {
		batch.EmptyCount = 0
		ids := make([]string, 0, len(batch.Units)-batch.Capacity)
		for _, unit := range batch.Units[batch.Capacity:] {
			ids = append(ids, unit.UnitID)
			capacityOverflowIDs[unit.UnitID] = struct{}{}
		}
		batch.Risks = append(batch.Risks, model.BatchRisk{Code: "capacity_overflow", Severity: "error", Blocking: true, Message: fmt.Sprintf("卡片数超出容量 %d 台", len(batch.Units)-batch.Capacity), UnitIDs: ids})
	}
	// A locked card is not itself a risk. It becomes a blocking conflict only
	// when that lock prevents resolving an actual capacity violation.
	lockedConflictIDs := make([]string, 0)
	for _, unit := range batch.Units {
		if !unit.IsLocked {
			continue
		}
		if _, overflow := capacityOverflowIDs[unit.UnitID]; overflow {
			lockedConflictIDs = append(lockedConflictIDs, unit.UnitID)
			continue
		}
	}
	if len(lockedConflictIDs) > 0 {
		batch.Risks = append(batch.Risks, model.BatchRisk{Code: "locked_constraint_conflict", Severity: "error", Blocking: true, Message: fmt.Sprintf("锁定卡片与当前约束冲突 %d 台，需先解锁或调整", len(lockedConflictIDs)), UnitIDs: lockedConflictIDs})
	}
	// ExpectedInboundDate is manually entered by planning staff. It is retained
	// as a display/audit field, but it is not a predictor output and therefore
	// must not produce an inferred due-date risk or gap metric.
	batch.DueGapDays = nil
	batch.RiskCount = len(batch.Risks)
}

func predictionFamily(modelType string) string {
	v := strings.ToUpper(strings.TrimSpace(modelType))
	switch {
	case strings.Contains(v, "AUTO"):
		return "AUTO"
	case strings.Contains(v, "XS"):
		return "XS"
	case v == "G" || strings.HasSuffix(v, "G"):
		return "G"
	default:
		return ""
	}
}

func (h *BatchHandler) GetByID(c *gin.Context) {
	batch, err := h.repo.GetByID(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "batch not found"})
		return
	}
	sanitizeBatchRemarkForResponse(batch)
	c.JSON(http.StatusOK, gin.H{"batch": batch})
}

type batchAuditUnit struct {
	UnitID      string     `json:"unit_id"`
	BatchID     string     `json:"batch_id"`
	SlotIndex   int        `json:"slot_index"`
	ModelType   string     `json:"model_type"`
	ContractNo  *string    `json:"contract_no"`
	Customer    *string    `json:"customer"`
	DealerName  *string    `json:"dealer_name"`
	DueDate     *time.Time `json:"due_date"`
	OrderRemark *string    `json:"order_remark"`
	IsLocked    bool       `json:"is_locked"`
}

func batchAuditSnapshot(unit model.Unit) batchAuditUnit {
	return batchAuditUnit{UnitID: unit.UnitID, BatchID: unit.BatchID, SlotIndex: unit.SlotIndex,
		ModelType: unit.ModelType, ContractNo: unit.ContractNo, Customer: unit.Customer,
		DealerName: unit.DealerName, DueDate: unit.DueDate, OrderRemark: unit.OrderRemark, IsLocked: unit.IsLocked}
}

// Audit returns the persistent first-manual-change baseline and an explicit
// difference summary for the prediction-column drawer.
func (h *BatchHandler) Audit(c *gin.Context) {
	batchID := c.Param("id")
	var baselineRow struct {
		BaselineJSON []byte     `gorm:"column:baseline_json"`
		CapturedBy   *string    `gorm:"column:captured_by"`
		CapturedAt   *time.Time `gorm:"column:captured_at"`
	}
	err := h.db.Table("sandbox_batch_baselines").Where("batch_id = ?", batchID).First(&baselineRow).Error
	if err != nil && err != gorm.ErrRecordNotFound {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err == gorm.ErrRecordNotFound {
		c.JSON(http.StatusOK, gin.H{"is_manually_adjusted": false, "baseline": nil, "changes": []interface{}{}, "difference_summary": nil})
		return
	}
	var units []model.Unit
	if err := h.db.Where("batch_id = ?", batchID).Order("slot_index ASC").Find(&units).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	var baseline []batchAuditUnit
	if len(baselineRow.BaselineJSON) > 0 {
		if parseErr := json.Unmarshal(baselineRow.BaselineJSON, &baseline); parseErr != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "invalid sandbox baseline: " + parseErr.Error()})
			return
		}
	}
	current := make([]batchAuditUnit, 0, len(units))
	for _, unit := range units {
		current = append(current, batchAuditSnapshot(unit))
	}
	baselineByID := make(map[string]batchAuditUnit, len(baseline))
	for _, unit := range baseline {
		baselineByID[unit.UnitID] = unit
	}
	currentByID := make(map[string]batchAuditUnit, len(current))
	for _, unit := range current {
		currentByID[unit.UnitID] = unit
	}
	added, removed, changed := 0, 0, 0
	for id, unit := range currentByID {
		before, exists := baselineByID[id]
		if !exists {
			added++
			continue
		}
		beforeJSON, _ := json.Marshal(before)
		afterJSON, _ := json.Marshal(unit)
		if string(beforeJSON) != string(afterJSON) {
			changed++
		}
	}
	for id := range baselineByID {
		if _, exists := currentByID[id]; !exists {
			removed++
		}
	}
	unitIDs := make([]string, 0, len(baselineByID)+len(currentByID))
	seenUnitIDs := make(map[string]struct{}, len(baselineByID)+len(currentByID))
	for id := range baselineByID {
		seenUnitIDs[id] = struct{}{}
	}
	for id := range currentByID {
		seenUnitIDs[id] = struct{}{}
	}
	for id := range seenUnitIDs {
		unitIDs = append(unitIDs, id)
	}
	sort.Strings(unitIDs)

	type auditLogRow struct {
		LogID      uint64    `gorm:"column:log_id"`
		Actor      string    `gorm:"column:actor"`
		Action     string    `gorm:"column:action"`
		TargetType string    `gorm:"column:target_type"`
		TargetID   string    `gorm:"column:target_id"`
		Detail     []byte    `gorm:"column:detail"`
		CreatedAt  time.Time `gorm:"column:created_at"`
	}
	var auditRows []auditLogRow
	logQuery := h.db.Table("operation_log").Where("(target_type = ? AND target_id = ?)", "batch", batchID)
	if len(unitIDs) > 0 {
		logQuery = logQuery.Or("(target_type = ? AND target_id IN ?)", "unit", unitIDs)
	}
	if err := logQuery.Order("created_at DESC").Limit(200).Find(&auditRows).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	changes := make([]gin.H, 0, len(auditRows))
	for _, row := range auditRows {
		changes = append(changes, gin.H{
			"id": row.LogID, "operated_at": row.CreatedAt, "operated_by": row.Actor,
			"action_type": row.Action, "target_type": row.TargetType, "target_id": row.TargetID,
			"detail": json.RawMessage(row.Detail),
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"is_manually_adjusted": true,
		"baseline":             gin.H{"units": baseline, "captured_by": baselineRow.CapturedBy, "captured_at": baselineRow.CapturedAt},
		"changes":              changes,
		"difference_summary":   gin.H{"baseline_count": len(baseline), "current_count": len(current), "added_count": added, "removed_count": removed, "changed_count": changed},
	})
}

func (h *BatchHandler) Confirm(c *gin.Context) {
	var req struct {
		BatchCode           string `json:"batch_code"`
		ExpectedInboundDate string `json:"expected_inbound_date"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	var batchCode *string
	code := strings.TrimSpace(req.BatchCode)
	if code != "" {
		if !regexp.MustCompile(`^(0[1-9]|1[0-2])-\d{2}[\x{4e00}-\x{9fa5}A-Za-z0-9_-]{0,20}$`).MatchString(code) {
			c.JSON(http.StatusBadRequest, gin.H{"error": "batch_code format must be MM-SS with an optional suffix of up to 20 characters"})
			return
		}
		if strings.HasSuffix(code, "-00") {
			c.JSON(http.StatusBadRequest, gin.H{"error": "batch_code out of range"})
			return
		}
		batchCode = &code
	}

	var inboundDate *time.Time
	if ds := strings.TrimSpace(req.ExpectedInboundDate); ds != "" {
		t, err := time.Parse("2006-01-02", ds)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "expected_inbound_date format must be YYYY-MM-DD"})
			return
		}
		inboundDate = &t
	}

	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}
	if err := h.svc.Confirm(c.Param("id"), actor, batchCode, inboundDate); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *BatchHandler) Revoke(c *gin.Context) {
	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}
	if err := h.svc.Revoke(c.Param("id"), actor); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *BatchHandler) BatchConfirm(c *gin.Context) {
	var req struct {
		BatchIDs []string `json:"batch_ids" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}
	if err := h.svc.BatchConfirm(req.BatchIDs, actor); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *BatchHandler) SyncStockModels(c *gin.Context) {
	var req struct {
		Stocks []service.StockModelTarget `json:"stocks" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}
	if err := h.svc.SyncStockModels(c.Param("id"), req.Stocks, actor); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *BatchHandler) AssignToLine(c *gin.Context) {
	var req struct {
		BatchID string `json:"batch_id" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}
	stats, err := h.svc.AssignToLine(req.BatchID, c.Param("id"), actor)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"factory_plan_status_update": gin.H{
			"pairs": stats.Pairs,
			"rows":  stats.Rows,
		},
	})
}

func (h *BatchHandler) ManualComplete(c *gin.Context) {
	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}
	if err := h.svc.ManualComplete(c.Param("id"), actor); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *BatchHandler) InsertEmptySlot(c *gin.Context) {
	var req struct {
		BeforeSlotIndex int    `json:"before_slot_index" binding:"required"`
		SizeKey         string `json:"size_key"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if req.BeforeSlotIndex < 1 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "before_slot_index must be >= 1"})
		return
	}
	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}

	tx := h.db.Begin()
	defer tx.Rollback()

	batch, err := h.repo.GetByID(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "batch not found"})
		return
	}

	// Capacity check
	var count int64
	if err := tx.Model(&model.Unit{}).Where("batch_id = ?", batch.BatchID).Count(&count).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if int(count) >= batch.Capacity {
		c.JSON(http.StatusBadRequest, gin.H{"error": "batch is full"})
		return
	}
	if err := service.CaptureSandboxBaselines(tx, actor, batch.BatchID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Shift slots to make room
	unitID := fmt.Sprintf("%s-S%02d", batch.BatchID, req.BeforeSlotIndex)

	now := time.Now()
	unit := model.Unit{
		UnitID:    unitID,
		BatchID:   batch.BatchID,
		SlotIndex: req.BeforeSlotIndex,
		ModelType: batch.ModelType,
		Status:    "Pending",
		CreatedAt: now,
		UpdatedAt: now,
	}
	if err := tx.Create(&unit).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	units, err := h.unitRepo.ListByBatchIDsForUpdate(tx, []string{batch.BatchID})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	ordered := make([]string, 0, len(units))
	insertIdx := req.BeforeSlotIndex - 1
	if insertIdx < 0 {
		insertIdx = 0
	}
	if insertIdx > len(units)-1 {
		insertIdx = len(units) - 1
	}
	inserted := false
	for i, u := range units {
		if !inserted && i == insertIdx {
			ordered = append(ordered, unitID)
			inserted = true
		}
		if u.UnitID != unitID {
			ordered = append(ordered, u.UnitID)
		}
	}
	if !inserted {
		ordered = append(ordered, unitID)
	}
	if err := h.unitRepo.RewriteBatchAssignments(tx, map[string][]string{batch.BatchID: ordered}); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	detail, _ := json.Marshal(map[string]interface{}{
		"unit_id":           unitID,
		"before_slot_index": req.BeforeSlotIndex,
		"size_key":          req.SizeKey,
	})
	if err := tx.Create(&model.OperationLog{
		Actor:      actor,
		Action:     "insert_empty_slot",
		TargetType: "batch",
		TargetID:   batch.BatchID,
		Detail:     detail,
		CreatedAt:  time.Now(),
	}).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true, "unit": unit})
}

func (h *BatchHandler) GetBatchUnits(c *gin.Context) {
	units, err := h.unitRepo.GetByBatch(c.Param("id"))
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
