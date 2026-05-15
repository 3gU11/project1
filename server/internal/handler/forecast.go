package handler

import (
	"io"
	"math"
	"net/http"
	"sort"
	"strings"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"smart-scheduling/server/internal/engine"
	"smart-scheduling/server/internal/repo"
	"smart-scheduling/server/internal/service"
)

type ForecastHandler struct {
	svc *service.RecomputeSvc
	db  *gorm.DB
}

func NewForecastHandler(db *gorm.DB, svc *service.RecomputeSvc) *ForecastHandler {
	return &ForecastHandler{db: db, svc: svc}
}

func (h *ForecastHandler) Recompute(c *gin.Context) {
	var req struct {
		TargetSlotNo int `json:"target_slot_no"`
	}
	if err := c.ShouldBindJSON(&req); err != nil && err != io.EOF {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	result, err := h.svc.Recompute(req.TargetSlotNo)
	if err != nil {
		status := http.StatusInternalServerError
		if err.Error() == "recompute already in progress" {
			status = http.StatusConflict
		}
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}
	achievement, aErr := h.computeAchievementPayload()
	if aErr == nil {
		if m, ok := result.(map[string]interface{}); ok {
			m["achievement"] = achievement
		}
	}
	c.JSON(http.StatusOK, result)
}

func (h *ForecastHandler) Achievement(c *gin.Context) {
	achievement, err := h.computeAchievementPayload()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"achievement": achievement})
}

type ratioCfg struct {
	Level2Global map[string]int            `json:"level2_global"`
	Level3       map[string]map[string]int `json:"level3"`
}

type modelCountRow struct {
	ModelType string `gorm:"column:model_type"`
	Count     int    `gorm:"column:count"`
}

func (h *ForecastHandler) computeAchievementPayload() (gin.H, error) {
	rows := make([]modelCountRow, 0, 128)
	if err := h.db.Raw(`
		SELECT TRIM(` + "`机型`" + `) AS model_type, COUNT(*) AS count
		FROM finished_goods_data
		WHERE ` + "`状态`" + ` LIKE '库存中%' OR ` + "`状态`" + ` = '待入库'
		GROUP BY TRIM(` + "`机型`" + `)`).Scan(&rows).Error; err != nil {
		return nil, err
	}

	cfgRepo := repo.NewConfigRepo(h.db)
	fallback := ratioCfg{
		Level2Global: map[string]int{"中小型G": 24, "中小型XS": 38, "中大型XS": 38, "中小型AUTO": 0, "中大型AUTO": 0, "特殊": 0},
		Level3: map[string]map[string]int{
			"中小型G":    {"FR-400G": 60, "FH-300C": 40},
			"中小型XS":   {"FR-400XS(PRO)": 100},
			"中大型XS":   {"FR-7055XS(PRO)": 100},
			"中小型AUTO": {"FR-400AUTO": 100},
			"中大型AUTO": {"FR-7055AUTO": 100},
		},
	}
	cfg := fallback
	_ = cfgRepo.GetJSON("capacity_ratio", fallback, &cfg)
	cfg.Level2Global = normalizeIntRatioKeys(cfg.Level2Global)
	cfg.Level3 = normalizeLevel3RatioKeys(cfg.Level3)
	if cfg.Level2Global == nil {
		cfg.Level2Global = fallback.Level2Global
	}
	if cfg.Level3 == nil {
		cfg.Level3 = fallback.Level3
	}
	supplementLevel3MapFromModelDict(h.db, cfg.Level3)
	familyMap := h.loadModelFamilyMap()

	modelCurrentQty := map[string]int{}
	categoryCurrentQty := map[string]int{
		"中小型G": 0, "中小型XS": 0, "中大型XS": 0, "中小型AUTO": 0, "中大型AUTO": 0,
	}
	totalBaseQty := 0
	for _, row := range rows {
		modelName := strings.TrimSpace(row.ModelType)
		if modelName == "" {
			continue
		}
		cat := modelCategoryOf(modelName, familyMap[strings.ToUpper(modelName)])
		if cat == "" || cat == "特殊" {
			continue
		}
		modelCurrentQty[modelName] += row.Count
		categoryCurrentQty[cat] += row.Count
		totalBaseQty += row.Count
	}

	categories := []string{"中小型G", "中小型XS", "中大型XS", "中小型AUTO", "中大型AUTO"}
	categoryTargetQty := allocateByRatio(categories, map[string]int{
		"中小型G":    cfg.Level2Global["中小型G"],
		"中小型XS":   cfg.Level2Global["中小型XS"],
		"中大型XS":   cfg.Level2Global["中大型XS"],
		"中小型AUTO": cfg.Level2Global["中小型AUTO"],
		"中大型AUTO": cfg.Level2Global["中大型AUTO"],
	}, totalBaseQty)

	modelTargetQty := map[string]int{}
	for _, cat := range categories {
		modelKeys := make([]string, 0)
		for m := range cfg.Level3[cat] {
			modelKeys = append(modelKeys, strings.TrimSpace(m))
		}
		for m := range modelCurrentQty {
			if modelCategoryOf(m, familyMap[strings.ToUpper(m)]) == cat {
				modelKeys = append(modelKeys, m)
			}
		}
		modelKeys = uniqueSorted(modelKeys)
		if len(modelKeys) == 0 {
			continue
		}
		modelRatio := map[string]int{}
		if len(cfg.Level3[cat]) > 0 {
			for _, m := range modelKeys {
				modelRatio[m] = cfg.Level3[cat][m]
			}
		}
		if sumMap(modelRatio) == 0 {
			for _, m := range modelKeys {
				modelRatio[m] = 1
			}
		}
		local := allocateByRatio(modelKeys, modelRatio, categoryTargetQty[cat])
		for k, v := range local {
			modelTargetQty[k] += v
		}
	}

	modelRows := make([]gin.H, 0, len(modelTargetQty))
	modelNames := make([]string, 0, len(modelTargetQty))
	for m := range modelTargetQty {
		modelNames = append(modelNames, m)
	}
	sort.Strings(modelNames)
	for _, m := range modelNames {
		cur := modelCurrentQty[m]
		tgt := modelTargetQty[m]
		modelRows = append(modelRows, toAchievementRow(m, cur, tgt, totalBaseQty))
	}

	categoryRows := make([]gin.H, 0, len(categories))
	for _, cat := range categories {
		categoryRows = append(categoryRows, toAchievementRow(cat, categoryCurrentQty[cat], categoryTargetQty[cat], totalBaseQty))
	}

	return gin.H{
		"total_base_qty": totalBaseQty,
		"models":         modelRows,
		"categories":     categoryRows,
	}, nil
}

func (h *ForecastHandler) loadModelFamilyMap() map[string]string {
	var rows []struct {
		ModelName   string `gorm:"column:model_name"`
		ModelFamily string `gorm:"column:model_family"`
	}
	_ = h.db.Table("model_dictionary").
		Select("model_name, model_family").
		Where("enabled = 1").
		Scan(&rows).Error
	out := map[string]string{}
	for _, row := range rows {
		name := strings.ToUpper(strings.TrimSpace(row.ModelName))
		if name != "" {
			out[name] = strings.TrimSpace(row.ModelFamily)
		}
	}
	return out
}

func modelCategoryOf(model string, modelFamily ...string) string {
	if len(modelFamily) > 0 {
		if cat := canonicalCategory(modelFamily[0]); cat != "" {
			switch cat {
			case "中小型G", "中小型XS", "中大型XS", "中小型AUTO", "中大型AUTO", "特殊":
				return cat
			}
		}
	}
	v := strings.ToUpper(strings.TrimSpace(model))
	if v == "" {
		return ""
	}
	if v == "FH-300C" {
		return "中小型G"
	}
	if strings.Contains(v, "特殊") {
		return "特殊"
	}
	if strings.Contains(v, "AUTO") {
		if strings.Contains(v, "8055") || strings.Contains(v, "7055") || strings.Contains(v, "8060") {
			return "中大型AUTO"
		}
		return "中小型AUTO"
	}
	if strings.Contains(v, "XS") {
		if strings.Contains(v, "8055") || strings.Contains(v, "7055") || strings.Contains(v, "8060") {
			return "中大型XS"
		}
		return "中小型XS"
	}
	if engine.NormalizeModelType(v) == "G" {
		return "中小型G"
	}
	return ""
}

func canonicalCategory(value string) string {
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

func normalizeIntRatioKeys(in map[string]int) map[string]int {
	if in == nil {
		return nil
	}
	out := map[string]int{}
	for k, v := range in {
		out[canonicalCategory(k)] += v
	}
	return out
}

func normalizeLevel3RatioKeys(in map[string]map[string]int) map[string]map[string]int {
	if in == nil {
		return nil
	}
	out := map[string]map[string]int{}
	for category, ratios := range in {
		cat := canonicalCategory(category)
		if out[cat] == nil {
			out[cat] = map[string]int{}
		}
		for modelName, v := range ratios {
			out[cat][modelName] += v
		}
	}
	return out
}

func uniqueSorted(in []string) []string {
	m := map[string]struct{}{}
	for _, x := range in {
		x = strings.TrimSpace(x)
		if x == "" {
			continue
		}
		m[x] = struct{}{}
	}
	out := make([]string, 0, len(m))
	for x := range m {
		out = append(out, x)
	}
	sort.Strings(out)
	return out
}

func sumMap(m map[string]int) int {
	s := 0
	for _, v := range m {
		s += v
	}
	return s
}

func allocateByRatio(keys []string, ratio map[string]int, total int) map[string]int {
	out := map[string]int{}
	if total <= 0 || len(keys) == 0 {
		for _, k := range keys {
			out[k] = 0
		}
		return out
	}
	type item struct {
		key   string
		ratio int
		frac  float64
	}
	items := make([]item, 0, len(keys))
	sum := 0
	for _, k := range keys {
		r := ratio[k]
		if r < 0 {
			r = 0
		}
		sum += r
		items = append(items, item{key: k, ratio: r})
	}
	if sum <= 0 {
		sum = len(items)
		for i := range items {
			items[i].ratio = 1
		}
	}

	allocated := 0
	for i := range items {
		exact := float64(total) * float64(items[i].ratio) / float64(sum)
		base := int(math.Floor(exact))
		out[items[i].key] = base
		allocated += base
		items[i].frac = exact - float64(base)
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].frac != items[j].frac {
			return items[i].frac > items[j].frac
		}
		return items[i].key < items[j].key
	})
	for i := 0; allocated < total && i < len(items); i++ {
		out[items[i].key]++
		allocated++
	}
	for allocated < total {
		out[items[0].key]++
		allocated++
	}
	return out
}

func toAchievementRow(name string, currentQty int, targetQty int, total int) gin.H {
	currentPct := 0.0
	targetPct := 0.0
	if total > 0 {
		currentPct = float64(currentQty) * 100.0 / float64(total)
		targetPct = float64(targetQty) * 100.0 / float64(total)
	}
	return gin.H{
		"name":        name,
		"target_pct":  targetPct,
		"current_pct": currentPct,
		"gap_pct":     currentPct - targetPct,
		"target_qty":  targetQty,
		"current_qty": currentQty,
	}
}
