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
		if lines[i].Status == model.LineBusy {
			var batches []model.Batch
			if err := h.db.
				Where("production_line_id = ? AND status = ?", lines[i].ProductionLineID, model.StatusInProduction).
				Order("COALESCE(batch_code, ''), batch_no ASC").
				Find(&batches).Error; err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			lines[i].Batches = batches

			var units []model.Unit
			q := h.db.Table("units u").
				Select("u.*, b.batch_code AS batch_code, b.model_type AS batch_model_type, b.status AS batch_status, md.model_family AS model_family, fg.状态 AS fg_status").
				Joins("JOIN batches b ON b.batch_id = u.batch_id").
				Joins("LEFT JOIN model_dictionary md ON md.model_name = u.model_type COLLATE utf8mb4_general_ci").
				Joins("LEFT JOIN finished_goods_data fg ON fg.流水号 = u.serial_no COLLATE utf8mb4_general_ci").
				Where("u.production_line_id = ? AND u.status = ?", lines[i].ProductionLineID, model.StatusInProduction).
				Order("COALESCE(b.batch_code, ''), b.batch_no ASC, u.slot_index ASC")
			if len(batches) == 0 && lines[i].CurrentBatchID != nil {
				q = q.Where("u.batch_id = ?", *lines[i].CurrentBatchID)
			}
			if err := q.Find(&units).Error; err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
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
