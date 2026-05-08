package handler

import (
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"

	"smart-scheduling/server/internal/repo"
)

type CapacityHandler struct {
	repo *repo.ConfigRepo
}

func NewCapacityHandler(r *repo.ConfigRepo) *CapacityHandler {
	return &CapacityHandler{repo: r}
}

func (h *CapacityHandler) Get(c *gin.Context) {
	var result map[string]interface{}
	fallback := map[string]interface{}{
		"level2_global": map[string]int{"小机G": 24, "小机XS": 38, "大机XS": 38, "小机AUTO": 0, "大机AUTO": 0, "特殊": 0},
		"level3": map[string]map[string]int{
			"小机G":    {"FR-400G": 60, "FH-300C": 40},
			"小机XS":   {"FR-400XS(PRO)": 100},
			"大机XS":   {"FR-600XS(PRO)": 100},
			"小机AUTO": {"FR-400AUTO": 100},
			"大机AUTO": {"FR-600AUTO": 100},
		},
	}
	if err := h.repo.GetJSON("capacity_ratio", fallback, &result); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ratio": result})
}

func (h *CapacityHandler) Update(c *gin.Context) {
	actor := c.GetString("username")
	if actor == "" {
		actor = "system"
	}

	var req map[string]interface{}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid JSON"})
		return
	}

	if err := validateRatio(req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.repo.UpsertJSON("capacity_ratio", req, "两级产能比例配置", actor); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func validateRatio(data map[string]interface{}) error {
	l2gRaw, ok := data["level2_global"]
	if !ok {
		return fmt.Errorf("level2_global is required")
	}
	l2g, ok := l2gRaw.(map[string]interface{})
	if !ok {
		if err := json.Unmarshal(toJSON(l2gRaw), &l2g); err != nil {
			return fmt.Errorf("invalid level2_global structure")
		}
	}
	sum := toInt(l2g["小机G"]) + toInt(l2g["小机XS"]) + toInt(l2g["大机XS"]) + toInt(l2g["小机AUTO"]) + toInt(l2g["大机AUTO"])
	if sum != 100 {
		return fmt.Errorf("level2_global sum must equal 100, got %d", sum)
	}

	l3Raw, ok := data["level3"]
	if !ok {
		return fmt.Errorf("level3 is required")
	}
	l3, ok := l3Raw.(map[string]interface{})
	if !ok {
		return fmt.Errorf("invalid level3 structure")
	}
	for _, category := range []string{"小机G", "小机XS", "大机XS", "小机AUTO", "大机AUTO"} {
		inner, exists := l3[category]
		if !exists {
			return fmt.Errorf("level3.%s is required", category)
		}
		innerMap, ok := inner.(map[string]interface{})
		if !ok {
			return fmt.Errorf("invalid level3.%s structure", category)
		}
		sum := 0
		for _, v := range innerMap {
			sum += toInt(v)
		}
		if sum != 100 {
			return fmt.Errorf("level3.%s sum must equal 100, got %d", category, sum)
		}
	}
	return nil
}

func toInt(v interface{}) int {
	switch val := v.(type) {
	case float64:
		return int(val)
	case int:
		return val
	case int64:
		return int(val)
	case json.Number:
		i, _ := val.Int64()
		return int(i)
	}
	return 0
}

func toJSON(v interface{}) []byte {
	b, _ := json.Marshal(v)
	return b
}
