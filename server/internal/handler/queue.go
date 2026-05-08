package handler

import (
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"smart-scheduling/server/internal/model"
)


// QueueHandler 处理待处理队列 (production_queue) 的读取。
type QueueHandler struct {
	db *gorm.DB
}

func NewQueueHandler(db *gorm.DB) *QueueHandler {
	return &QueueHandler{db: db}
}

// QueueItem 是返回给前端的队列条目，包含 payload 的解码字段。
type QueueItem struct {
	QueueID    uint64                 `json:"queue_id"`
	ModelType  string                 `json:"model_type"`
	ContractNo *string                `json:"contract_no"`
	Status     string                 `json:"status"`
	Priority   int                    `json:"priority"`
	CreatedAt  string                 `json:"created_at"`
	Payload    map[string]interface{} `json:"payload"`
}

// List 返回待处理队列，支持按 status 和 model_type 筛选。
// GET /api/production-queue?status=Waiting&model_type=G
func (h *QueueHandler) List(c *gin.Context) {
	status := c.DefaultQuery("status", model.QueueWaiting)
	modelType := c.Query("model_type")

	// 检查新版列是否存在（兼容旧版数据库 schema）
	hasNewCols := queueHasColumns(h.db, "production_queue", "payload", "priority")

	if hasNewCols {
		// 新版 schema：使用 model 查询，按 priority + created_at 排序
		var items []model.ProductionQueue
		q := h.db.Where("status = ?", status)
		if modelType != "" {
			q = q.Where("model_type = ?", modelType)
		}
		if err := q.Order("priority ASC, created_at ASC").Find(&items).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		result := make([]QueueItem, 0, len(items))
		for _, it := range items {
			qi := QueueItem{
				QueueID:    it.QueueID,
				ModelType:  it.ModelType,
				ContractNo: it.ContractNo,
				Status:     it.Status,
				Priority:   it.Priority,
				CreatedAt:  it.CreatedAt.Format("2006-01-02 15:04:05"),
				Payload:    map[string]interface{}{},
			}
			if len(it.Payload) > 0 {
				_ = json.Unmarshal(it.Payload, &qi.Payload)
			}
			result = append(result, qi)
		}
		c.JSON(http.StatusOK, gin.H{"queue": result, "total": len(result)})
		return
	}

	// 旧版 schema：只有 model_type / contract_no / customer / status 等基础列
	var rows []map[string]interface{}
	q := h.db.Table("production_queue").Where("status = ?", status)
	if modelType != "" {
		q = q.Where("model_type = ?", modelType)
	}
	if err := q.Order("created_at ASC").Find(&rows).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	result := make([]QueueItem, 0, len(rows))
	for _, row := range rows {
		qi := QueueItem{
			ModelType: strVal(row["model_type"]),
			Status:    strVal(row["status"]),
			CreatedAt: strVal(row["created_at"]),
			Payload:   map[string]interface{}{},
		}
		if id, ok := row["queue_id"]; ok {
			switch v := id.(type) {
			case uint64:
				qi.QueueID = v
			case int64:
				qi.QueueID = uint64(v)
			}
		}
		if cn, ok := row["contract_no"]; ok && cn != nil {
			s := strVal(cn)
			qi.ContractNo = &s
			qi.Payload["contract_no"] = s
		}
		for _, k := range []string{"customer", "dealer", "dealer_name", "due_date", "model_type"} {
			if v, ok := row[k]; ok && v != nil {
				qi.Payload[k] = strVal(v)
			}
		}
		result = append(result, qi)
	}
	c.JSON(http.StatusOK, gin.H{"queue": result, "total": len(result)})
}

func strVal(v interface{}) string {
	if v == nil {
		return ""
	}
	switch s := v.(type) {
	case string:
		return s
	case []byte:
		return string(s)
	}
	return fmt.Sprintf("%v", v)
}

