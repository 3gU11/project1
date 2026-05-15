package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

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
		"level2_global": map[string]int{"中小型G": 24, "中小型XS": 38, "中大型XS": 38, "中小型AUTO": 0, "中大型AUTO": 0, "特殊": 0},
		"level3": map[string]map[string]int{
			"中小型G":    {"FR-400G": 60, "FH-300C": 40},
			"中小型XS":   {"FR-400XS(PRO)": 100},
			"中大型XS":   {"FR-600XS(PRO)": 100},
			"中小型AUTO": {"FR-400AUTO": 100},
			"中大型AUTO": {"FR-600AUTO": 100},
		},
	}
	if err := h.repo.GetJSON("capacity_ratio", fallback, &result); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	normalizeCapacityRatioPayload(result)
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
	normalizeCapacityRatioPayload(req)

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

func canonicalCapacityCategory(value string) string {
	v := strings.TrimSpace(value)
	switch v {
	case "小机G":
		return "中小型G"
	case "小机XS", "小机/XS":
		return "中小型XS"
	case "小机AUTO":
		return "中小型AUTO"
	case "大机XS":
		return "中大型XS"
	case "大机AUTO":
		return "中大型AUTO"
	case "SPECIAL":
		return "特殊"
	default:
		if strings.EqualFold(v, "SPECIAL") {
			return "特殊"
		}
		return v
	}
}

func normalizeCapacityRatioPayload(data map[string]interface{}) {
	if data == nil {
		return
	}
	if l2g, ok := data["level2_global"]; ok {
		data["level2_global"] = normalizeFlatRatioMap(l2g)
	}
	if l2, ok := data["level2"]; ok {
		data["level2"] = normalizeNestedRatioMap(l2, false, true)
	}
	if l3, ok := data["level3"]; ok {
		data["level3"] = normalizeNestedRatioMap(l3, true, false)
	}
}

func normalizeFlatRatioMap(raw interface{}) map[string]interface{} {
	var src map[string]interface{}
	if m, ok := raw.(map[string]interface{}); ok {
		src = m
	} else {
		_ = json.Unmarshal(toJSON(raw), &src)
	}
	out := map[string]interface{}{}
	for k, v := range src {
		cat := canonicalCapacityCategory(k)
		out[cat] = toInt(out[cat]) + toInt(v)
	}
	return out
}

func normalizeNestedRatioMap(raw interface{}, normalizeOuter bool, normalizeInner bool) map[string]interface{} {
	var src map[string]interface{}
	if m, ok := raw.(map[string]interface{}); ok {
		src = m
	} else {
		_ = json.Unmarshal(toJSON(raw), &src)
	}
	out := map[string]interface{}{}
	for outerKey, innerRaw := range src {
		key := strings.TrimSpace(outerKey)
		if normalizeOuter {
			key = canonicalCapacityCategory(key)
		}
		if normalizeInner {
			out[key] = normalizeFlatRatioMap(innerRaw)
			continue
		}
		var inner map[string]interface{}
		if m, ok := innerRaw.(map[string]interface{}); ok {
			inner = m
		} else {
			_ = json.Unmarshal(toJSON(innerRaw), &inner)
		}
		existing, _ := out[key].(map[string]interface{})
		if existing == nil {
			existing = map[string]interface{}{}
		}
		for k, v := range inner {
			existing[k] = toInt(existing[k]) + toInt(v)
		}
		out[key] = existing
	}
	return out
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
	sum := toInt(l2g["中小型G"]) + toInt(l2g["中小型XS"]) + toInt(l2g["中大型XS"]) + toInt(l2g["中小型AUTO"]) + toInt(l2g["中大型AUTO"])
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
	for _, category := range []string{"中小型G", "中小型XS", "中大型XS", "中小型AUTO", "中大型AUTO"} {
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
