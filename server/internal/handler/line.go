package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"smart-scheduling/server/internal/model"
	"smart-scheduling/server/internal/service"
)

type LineHandler struct {
	db  *gorm.DB
	svc *service.BatchSvc
}

func NewLineHandler(db *gorm.DB, svc *service.BatchSvc) *LineHandler {
	return &LineHandler{db: db, svc: svc}
}

func (h *LineHandler) List(c *gin.Context) {
	var lines []model.ProductionLine
	if err := h.db.Order("display_order ASC").Find(&lines).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if lines == nil {
		lines = []model.ProductionLine{}
	}

	// Load units for busy lines
	for i := range lines {
		lines[i].LineID = lines[i].ProductionLineID
		if lines[i].CurrentBatchID != nil {
			var units []model.Unit
			h.db.Where(
				"batch_id = ? AND production_line_id = ? AND status = ?",
				*lines[i].CurrentBatchID,
				lines[i].ProductionLineID,
				model.StatusInProduction,
			).
				Order("slot_index ASC").Find(&units)
			sanitizeUnitsRemarkForResponse(units)
			lines[i].Units = units
		}
	}

	c.JSON(http.StatusOK, gin.H{"lines": lines})
}

func (h *LineHandler) Assign(c *gin.Context) {
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
	if err := h.svc.AssignToLine(req.BatchID, c.Param("id"), actor); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *LineHandler) ManualComplete(c *gin.Context) {
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
