package handler

import (
	"encoding/json"
	"fmt"
	"math/rand"
	"net/http"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

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
	sanitizeBatchesRemarkForResponse(batches)
	c.JSON(http.StatusOK, gin.H{"batches": batches})
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
		if utf8.RuneCountInString(code) > 64 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "batch_code must be 64 characters or fewer"})
			return
		}
		for _, r := range code {
			if unicode.IsControl(r) {
				c.JSON(http.StatusBadRequest, gin.H{"error": "batch_code contains invalid characters"})
				return
			}
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

func (h *BatchHandler) CreateManualPredicted(c *gin.Context) {
	var req struct {
		ModelFamily string `json:"model_family" binding:"required"`
		Quantity    int    `json:"quantity" binding:"required"`
		Remark      string `json:"remark"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	familyCategory, batchModelType, capacity, err := normalizeManualPredictedFamily(req.ModelFamily)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if req.Quantity <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "quantity must be greater than 0"})
		return
	}
	if req.Quantity > capacity {
		c.JSON(http.StatusBadRequest, gin.H{"error": fmt.Sprintf("quantity cannot exceed %s capacity %d", familyCategory, capacity)})
		return
	}

	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}

	tx := h.db.Begin()
	defer tx.Rollback()

	var maxBatchNo int
	if err := tx.Model(&model.Batch{}).
		Where("status IN ?", []string{model.StatusPredicted, model.StatusConfirmed}).
		Select("COALESCE(MAX(batch_no), 0)").
		Scan(&maxBatchNo).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	var maxSlotNo int
	if err := tx.Model(&model.ForecastBatchSlot{}).
		Select("COALESCE(MAX(slot_no), 0)").
		Scan(&maxSlotNo).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	now := time.Now()
	nextNo := max(maxBatchNo, maxSlotNo) + 1
	batchID := fmt.Sprintf("BATCH-%s-%s-MANUAL-%03d-%06d",
		now.Format("200601"),
		strings.ToUpper(batchModelType),
		nextNo,
		rand.Intn(1000000),
	)
	remark := strings.TrimSpace(req.Remark)
	batch := model.Batch{
		BatchID:   batchID,
		BatchNo:   nextNo,
		ModelType: batchModelType,
		Capacity:  capacity,
		Status:    model.StatusPredicted,
		Source:    "manual",
		CreatedAt: now,
		UpdatedAt: now,
	}
	if err := tx.Create(&batch).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	slotBatchID := batch.BatchID
	slot := model.ForecastBatchSlot{
		SlotNo:    nextNo,
		ModelType: batchModelType,
		Capacity:  capacity,
		BatchID:   &slotBatchID,
		Source:    "manual",
		CreatedAt: now,
		UpdatedAt: now,
	}
	if err := tx.Create(&slot).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	units := make([]model.Unit, 0, req.Quantity)
	for i := 1; i <= req.Quantity; i++ {
		unit := model.Unit{
			UnitID:      fmt.Sprintf("%s-U%02d", batchID, i),
			BatchID:     batchID,
			SlotIndex:   i,
			ModelType:   familyCategory,
			Status:      "Pending",
			OrderRemark: stringPtrIfNotEmpty(remark),
			CreatedAt:   now,
			UpdatedAt:   now,
		}
		units = append(units, unit)
	}
	if err := tx.Create(&units).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	detail, _ := json.Marshal(map[string]interface{}{
		"model_family": familyCategory,
		"batch_model":  batchModelType,
		"quantity":     req.Quantity,
		"remark":       remark,
	})
	_ = tx.Create(&model.OperationLog{
		Actor:      actor,
		Action:     "manual_predicted_batch_create",
		TargetType: "batch",
		TargetID:   batchID,
		Detail:     detail,
		CreatedAt:  now,
	}).Error

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success":      true,
		"batch":        batch,
		"unit_count":   len(units),
		"model_family": familyCategory,
	})
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

func normalizeManualPredictedFamily(raw string) (string, string, int, error) {
	family := strings.TrimSpace(raw)
	aliases := map[string]string{
		"小机G":     "中小型G",
		"小机XS":    "中小型XS",
		"小机/XS":   "中小型XS",
		"小机AUTO":  "中小型AUTO",
		"大机XS":    "中大型XS",
		"大机AUTO":  "中大型AUTO",
		"SPECIAL": "特殊",
	}
	if mapped, ok := aliases[family]; ok {
		family = mapped
	}
	switch family {
	case "中小型G":
		return family, "G", 30, nil
	case "中小型XS":
		return family, "XS", 30, nil
	case "中小型AUTO":
		return family, "AUTO", 27, nil
	case "中大型XS":
		return family, "XS", 16, nil
	case "中大型AUTO":
		return family, "AUTO", 16, nil
	case "特殊":
		return family, "SPECIAL", 15, nil
	default:
		return "", "", 0, fmt.Errorf("model_family must be one of 中小型G/中小型XS/中大型XS/中小型AUTO/中大型AUTO/特殊")
	}
}

func stringPtrIfNotEmpty(value string) *string {
	clean := strings.TrimSpace(value)
	if clean == "" {
		return nil
	}
	return &clean
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
