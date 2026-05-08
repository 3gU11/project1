package handler

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"smart-scheduling/server/internal/engine"
)

type MetaHandler struct {
	db *gorm.DB
}

func NewMetaHandler(db *gorm.DB) *MetaHandler {
	return &MetaHandler{db: db}
}

func (h *MetaHandler) ModelTypes(c *gin.Context) {
	var rows []struct {
		ModelName   string `gorm:"column:model_name"`
		ModelFamily string `gorm:"column:model_family"`
		ModelSize   *int   `gorm:"column:model_size"`
	}
	err := h.db.Table("model_dictionary").
		Select("model_name, model_family, model_size").
		Where("enabled = 1").
		Where("UPPER(TRIM(model_name)) NOT IN ?", []string{"G", "XS", "AUTO"}).
		Order("sort_order ASC, model_name ASC").
		Scan(&rows).Error
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	modelTypes := make([]gin.H, 0, len(rows))
	for _, row := range rows {
		name := strings.TrimSpace(row.ModelName)
		if name == "" {
			continue
		}
		family := strings.ToUpper(strings.TrimSpace(row.ModelFamily))
		if family == "" {
			family = engine.NormalizeModelType(name)
		}
		size := ""
		if row.ModelSize != nil && *row.ModelSize > 0 {
			size = strconv.Itoa(*row.ModelSize)
		}
		modelTypes = append(modelTypes, gin.H{
			"model_type":   name,
			"model_family": family,
			"model_size":   size,
		})
	}
	c.JSON(http.StatusOK, gin.H{"model_types": modelTypes})
}
