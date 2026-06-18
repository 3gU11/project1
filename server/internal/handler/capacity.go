package handler

import (
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"sort"
	"strings"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"smart-scheduling/server/internal/repo"
)

type CapacityHandler struct {
	db   *gorm.DB
	repo *repo.ConfigRepo
}

func NewCapacityHandler(db *gorm.DB, r *repo.ConfigRepo) *CapacityHandler {
	return &CapacityHandler{db: db, repo: r}
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
	supplementCapacityRatioFromModelDictionary(h.db, result)
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

func supplementCapacityRatioFromModelDictionary(db *gorm.DB, data map[string]interface{}) {
	if db == nil || data == nil {
		return
	}
	level3, _ := data["level3"].(map[string]interface{})
	if level3 == nil {
		level3 = map[string]interface{}{}
		data["level3"] = level3
	}

	var rows []struct {
		ModelName   string `gorm:"column:model_name"`
		ModelFamily string `gorm:"column:model_family"`
	}
	if err := db.Table("model_dictionary").
		Select("model_name, model_family").
		Where("enabled = 1").
		Where("UPPER(TRIM(model_name)) NOT IN ?", []string{"G", "XS", "AUTO"}).
		Order("sort_order ASC, model_name ASC").
		Scan(&rows).Error; err != nil {
		return
	}

	dictCategoryByModel := map[string]string{}
	for _, row := range rows {
		modelName := strings.TrimSpace(row.ModelName)
		if modelName == "" {
			continue
		}
		category := modelCategoryOf(modelName, strings.TrimSpace(row.ModelFamily))
		if category == "" {
			continue
		}
		dictCategoryByModel[normalizeCapacityModelKey(modelName)] = category
	}

	if len(dictCategoryByModel) > 0 {
		rehomed := map[string]interface{}{}
		for category, rawInner := range level3 {
			cleanCategory := canonicalCapacityCategory(category)
			inner, _ := rawInner.(map[string]interface{})
			if inner == nil {
				continue
			}
			for modelName, value := range inner {
				targetCategory := dictCategoryByModel[normalizeCapacityModelKey(modelName)]
				if targetCategory == "" {
					targetCategory = cleanCategory
				}
				targetInner, _ := rehomed[targetCategory].(map[string]interface{})
				if targetInner == nil {
					targetInner = map[string]interface{}{}
					rehomed[targetCategory] = targetInner
				}
				targetInner[modelName] = toInt(targetInner[modelName]) + toInt(value)
			}
		}
		for category := range level3 {
			delete(level3, category)
		}
		for category, inner := range rehomed {
			level3[category] = inner
		}
	}

	for _, row := range rows {
		modelName := strings.TrimSpace(row.ModelName)
		if modelName == "" {
			continue
		}
		category := dictCategoryByModel[normalizeCapacityModelKey(modelName)]
		if category == "" {
			continue
		}
		inner, _ := level3[category].(map[string]interface{})
		if inner == nil {
			inner = map[string]interface{}{}
			level3[category] = inner
		}
		if _, exists := inner[modelName]; !exists {
			inner[modelName] = 0
		}
	}

	normalizeCapacityLevel3Sums(level3)
}

func normalizeCapacityModelKey(value string) string {
	return strings.ToUpper(strings.ReplaceAll(strings.TrimSpace(value), " ", ""))
}

func normalizeCapacityLevel3Sums(level3 map[string]interface{}) {
	for _, category := range []string{"中小型G", "中小型XS", "中大型XS", "中小型AUTO", "中大型AUTO"} {
		inner, _ := level3[category].(map[string]interface{})
		if len(inner) == 0 {
			continue
		}
		sum := 0
		for _, value := range inner {
			sum += toInt(value)
		}
		if sum == 100 {
			continue
		}
		keys := make([]string, 0, len(inner))
		for key := range inner {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		if sum <= 0 {
			for _, key := range keys {
				inner[key] = 0
			}
			if len(keys) > 0 {
				inner[keys[0]] = 100
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
			exact := float64(toInt(inner[key])) * 100.0 / float64(sum)
			base := int(math.Floor(exact))
			inner[key] = base
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
			inner[remainders[i].key] = toInt(inner[remainders[i].key]) + 1
			used++
		}
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
