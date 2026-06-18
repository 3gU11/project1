package handler

import (
	"fmt"
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
