package engine

import (
	"encoding/json"
	"fmt"
	"math"
	"math/rand"
	"sort"
	"strconv"
	"strings"
	"time"

	"gorm.io/datatypes"
	"gorm.io/gorm"

	"smart-scheduling/server/internal/model"
	"smart-scheduling/server/internal/repo"
)

type CapacityConfig struct {
	G    int `json:"G"`
	XS   int `json:"XS"`
	AUTO int `json:"AUTO"`
}

type RatioConfig struct {
	Level2Global map[string]int            `json:"level2_global"`
	Level2       map[string]map[string]int `json:"level2"`
	Level3       map[string]map[string]int `json:"level3"`
}

var categoryAliases = map[string]string{
	"小机G":     "中小型G",
	"小机XS":    "中小型XS",
	"小机/XS":   "中小型XS",
	"小机AUTO":  "中小型AUTO",
	"大机XS":    "中大型XS",
	"大机AUTO":  "中大型AUTO",
	"SPECIAL": "特殊",
}

var productionCategories = []string{"中小型G", "中小型XS", "中大型XS", "中小型AUTO", "中大型AUTO"}

func canonicalCategory(value string) string {
	v := strings.TrimSpace(value)
	if v == "" {
		return ""
	}
	if mapped, ok := categoryAliases[v]; ok {
		return mapped
	}
	if strings.EqualFold(v, "SPECIAL") {
		return "特殊"
	}
	return v
}

func normalizeIntMapKeys(in map[string]int) map[string]int {
	if in == nil {
		return nil
	}
	out := map[string]int{}
	for k, v := range in {
		out[canonicalCategory(k)] += v
	}
	return out
}

func normalizeNestedRatioKeys(in map[string]map[string]int) map[string]map[string]int {
	if in == nil {
		return nil
	}
	out := map[string]map[string]int{}
	for family, ratios := range in {
		cleanFamily := strings.TrimSpace(family)
		if out[cleanFamily] == nil {
			out[cleanFamily] = map[string]int{}
		}
		for k, v := range ratios {
			out[cleanFamily][canonicalCategory(k)] += v
		}
	}
	return out
}

func normalizeLevel3Keys(in map[string]map[string]int) map[string]map[string]int {
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

func normalizeRatioConfig(cfg *RatioConfig) {
	if cfg == nil {
		return
	}
	cfg.Level2Global = normalizeIntMapKeys(cfg.Level2Global)
	cfg.Level2 = normalizeNestedRatioKeys(cfg.Level2)
	cfg.Level3 = normalizeLevel3Keys(cfg.Level3)
}

type Predictor struct {
	db        *gorm.DB
	batchRepo *repo.BatchRepo
	unitRepo  *repo.UnitRepo
	cfgRepo   *repo.ConfigRepo
}

func NewPredictor(db *gorm.DB, br *repo.BatchRepo, ur *repo.UnitRepo, cr *repo.ConfigRepo) *Predictor {
	return &Predictor{db: db, batchRepo: br, unitRepo: ur, cfgRepo: cr}
}

func (p *Predictor) getCapacityConfig() CapacityConfig {
	var cfg CapacityConfig
	if err := p.cfgRepo.GetJSON("model_capacity", CapacityConfig{G: 30, XS: 30, AUTO: 27}, &cfg); err != nil {
		cfg = CapacityConfig{G: 30, XS: 30, AUTO: 27}
	}
	if cfg.G <= 0 {
		cfg.G = 30
	}
	if cfg.XS <= 0 {
		cfg.XS = 30
	}
	if cfg.AUTO <= 0 {
		cfg.AUTO = 27
	}
	return cfg
}

func supplementLevel3FromModelDictionary(db *gorm.DB, cfg *RatioConfig) {
	if cfg == nil || db == nil {
		return
	}
	if cfg.Level3 == nil {
		cfg.Level3 = map[string]map[string]int{}
	}

	var rows []struct {
		ModelName   string `gorm:"column:model_name"`
		ModelFamily string `gorm:"column:model_family"`
	}
	if err := db.Table("model_dictionary").
		Select("model_name, model_family").
		Where("enabled = 1").
		Scan(&rows).Error; err != nil {
		return
	}

	// Group enabled models by category, excluding special
	dictModelsByCat := map[string][]string{}
	catFirstModel := map[string]string{}
	dictCatByModel := map[string]string{}
	for _, row := range rows {
		modelName := strings.TrimSpace(row.ModelName)
		if modelName == "" || modelName == "G" || modelName == "XS" || modelName == "AUTO" {
			continue
		}
		cat := modelCategoryOf(modelName, strings.TrimSpace(row.ModelFamily))
		if cat == "" || cat == "特殊" {
			continue
		}
		dictCatByModel[normalizeModelKey(modelName)] = cat
		dictModelsByCat[cat] = append(dictModelsByCat[cat], modelName)
		if _, exists := catFirstModel[cat]; !exists {
			catFirstModel[cat] = modelName
		}
	}

	rehomeLevel3ModelsByDictionary(cfg.Level3, dictCatByModel)

	// For each category, give missing/zero-ratio dict models a minimal share
	// WITHOUT overriding existing non-zero ratios.
	for cat, dictModels := range dictModelsByCat {
		if _, exists := cfg.Level3[cat]; !exists || len(cfg.Level3[cat]) == 0 {
			cfg.Level3[cat] = map[string]int{dictModels[0]: 100}
			continue
		}

		missingModels := []string{}
		for _, m := range dictModels {
			if v, ok := cfg.Level3[cat][m]; !ok || v <= 0 {
				missingModels = append(missingModels, m)
			}
		}
		if len(missingModels) == 0 {
			continue
		}

		// Take 5% from the dominant model for each missing model
		for _, mm := range missingModels {
			dominantModel := ""
			dominantRatio := 0
			for m, r := range cfg.Level3[cat] {
				if r > dominantRatio {
					dominantRatio = r
					dominantModel = m
				}
			}
			if dominantRatio >= 10 {
				cfg.Level3[cat][dominantModel] = dominantRatio - 5
				cfg.Level3[cat][mm] = 5
			}
		}
	}
}

func rehomeLevel3ModelsByDictionary(level3 map[string]map[string]int, dictCatByModel map[string]string) {
	if len(level3) == 0 || len(dictCatByModel) == 0 {
		return
	}
	next := map[string]map[string]int{}
	for category, ratios := range level3 {
		cat := canonicalCategory(category)
		if next[cat] == nil {
			next[cat] = map[string]int{}
		}
		for modelName, ratio := range ratios {
			targetCat := dictCatByModel[normalizeModelKey(modelName)]
			if targetCat == "" {
				targetCat = cat
			}
			if next[targetCat] == nil {
				next[targetCat] = map[string]int{}
			}
			next[targetCat][modelName] += ratio
		}
	}
	for category := range level3 {
		delete(level3, category)
	}
	for category, ratios := range next {
		level3[category] = ratios
	}
}

func (p *Predictor) getRatioConfig() RatioConfig {
	var cfg RatioConfig
	fallback := RatioConfig{
		Level2Global: map[string]int{"中小型G": 24, "中小型XS": 38, "中大型XS": 38, "中小型AUTO": 0, "中大型AUTO": 0, "特殊": 0},
		Level2: map[string]map[string]int{
			"G":    {"中小型G": 100},
			"XS":   {"中小型XS": 50, "中大型XS": 50},
			"AUTO": {"中小型AUTO": 50, "中大型AUTO": 50},
		},
		Level3: map[string]map[string]int{
			"中小型G": {"FR-400G": 60, "FH-300C": 40},
		},
	}
	if err := p.cfgRepo.GetJSON("capacity_ratio", fallback, &cfg); err != nil {
		return fallback
	}
	normalizeRatioConfig(&cfg)
	supplementLevel3FromModelDictionary(p.db, &cfg)
	cfg.Level2 = buildEffectiveLevel2(cfg.Level2, cfg.Level3)
	return cfg
}

func (p *Predictor) loadAvailableInventoryModelCounts() (map[string]int, error) {
	return LoadStockBaselineModelCounts(p.db)
}

func LoadAvailableInventoryModelCounts(db *gorm.DB) (map[string]int, error) {
	counts := map[string]int{}
	if db == nil {
		return counts, nil
	}
	var rows []struct {
		ModelType string `gorm:"column:model_type"`
		Count     int    `gorm:"column:count"`
	}
	if err := db.Raw(`
		SELECT TRIM(`+"`机型`"+`) AS model_type, COUNT(*) AS count
		FROM finished_goods_data
		WHERE `+"`状态`"+` LIKE ? OR `+"`状态`"+` = ?
		GROUP BY TRIM(`+"`机型`"+`)`,
		"库存中%", "待入库",
	).Scan(&rows).Error; err != nil {
		return nil, err
	}
	for _, row := range rows {
		modelName := strings.TrimSpace(row.ModelType)
		if modelName == "" || row.Count <= 0 {
			continue
		}
		counts[modelName] += row.Count
	}
	return counts, nil
}

func LoadStockBaselineModelCounts(db *gorm.DB) (map[string]int, error) {
	counts, err := LoadAvailableInventoryModelCounts(db)
	if err != nil {
		return nil, err
	}
	if db == nil {
		return counts, nil
	}
	rows := make([]struct {
		ModelType string `gorm:"column:model_type"`
		Count     int    `gorm:"column:count"`
	}, 0, 128)
	if err := db.Table("units u").
		Select("TRIM(u.model_type) AS model_type, COUNT(*) AS count").
		Joins("JOIN batches b ON b.batch_id = u.batch_id").
		Where("b.status IN ?", []string{model.StatusConfirmed, model.StatusInProduction}).
		Where("(u.contract_no IS NULL OR TRIM(u.contract_no) = '')").
		Group("TRIM(u.model_type)").
		Scan(&rows).Error; err != nil {
		return nil, err
	}
	for _, row := range rows {
		modelName := strings.TrimSpace(row.ModelType)
		if modelName == "" || row.Count <= 0 {
			continue
		}
		counts[modelName] += row.Count
	}
	return counts, nil
}

func buildEffectiveLevel2(level2 map[string]map[string]int, level3 map[string]map[string]int) map[string]map[string]int {
	if len(level2) == 0 {
		return level2
	}
	if len(level3) == 0 {
		return level2
	}
	eff := map[string]map[string]int{}
	for family, catMap := range level2 {
		if eff[family] == nil {
			eff[family] = map[string]int{}
		}
		for category, catRatio := range catMap {
			modelRatios := level3[category]
			if len(modelRatios) == 0 {
				eff[family][category] += catRatio
				continue
			}
			for model, modelRatio := range modelRatios {
				eff[family][model] += int(math.Round(float64(catRatio*modelRatio) / 100.0))
			}
		}
	}
	return eff
}

func (p *Predictor) getMaxBatches() int {
	return p.getIntConfig("max_batch_slots", 20)
}

func (p *Predictor) getGapDays() int {
	return p.getIntConfig("batch_break_days", 30)
}

func (p *Predictor) getIntConfig(key string, fallback int) int {
	var wrapper struct {
		V int `json:"V"`
	}
	if err := p.cfgRepo.GetJSON(key, map[string]int{"V": fallback}, &wrapper); err == nil && wrapper.V > 0 {
		return wrapper.V
	}

	var num int
	if err := p.cfgRepo.GetJSON(key, fallback, &num); err == nil && num > 0 {
		return num
	}

	var s string
	if err := p.cfgRepo.GetJSON(key, "", &s); err == nil {
		if v, convErr := strconv.Atoi(strings.TrimSpace(s)); convErr == nil && v > 0 {
			return v
		}
	}
	return fallback
}

func capacityFor(modelType string, caps CapacityConfig) int {
	switch modelType {
	case "G":
		return caps.G
	case "XS":
		return caps.XS
	case "AUTO":
		return caps.AUTO
	default:
		return 30
	}
}

func capacityForCategory(category string, caps CapacityConfig) int {
	switch category {
	case "中大型XS", "中大型AUTO":
		return 16
	default:
		return capacityFor(familyOfCategory(category), caps)
	}
}

func generateBatchID(modelType string, seq int) string {
	now := time.Now()
	suffix := fmt.Sprintf("%s%04d", now.Format("0405"), rand.Intn(9000)+1000)
	return fmt.Sprintf("BATCH-%s-%s-%03d-%s",
		now.Format("200601"), modelType, seq, suffix)
}

func generateUnitID(batchID string, slot int) string {
	return fmt.Sprintf("%s-S%02d", batchID, slot)
}

// FullRecompute runs the complete prediction pipeline within a transaction.
// lockedUnitSnapshot holds the contract data of a locked unit that was sitting
// in a Predicted batch before the recompute wipes it. We restore it afterwards.
type lockedUnitSnapshot struct {
	ContractNo  string     `gorm:"column:contract_no"`
	Customer    string     `gorm:"column:customer"`
	DealerName  string     `gorm:"column:dealer_name"`
	ModelType   string     `gorm:"column:model_type"` // specific model, e.g. "FR-400G加高"
	Family      string     `gorm:"column:family"`     // batch-level family: G / XS / AUTO / SPECIAL
	DueDate     *time.Time `gorm:"column:due_date"`
	SalesID     string     `gorm:"column:sales_id"`
	OrderRemark string     `gorm:"column:order_remark"`
	LockedBy    *string    `gorm:"column:locked_by"`
	LockedAt    *time.Time `gorm:"column:locked_at"`
}

func (p *Predictor) FullRecompute(targetSlotNo int) ([]model.Batch, error) {
	if targetSlotNo <= 0 {
		targetSlotNo = 1
	}
	// Clear old waiting queue entries before recompute
	p.db.Where("status = ?", model.QueueWaiting).Delete(&model.ProductionQueue{})

	// ── Pre-step: snapshot every locked unit sitting in a Predicted batch. ──────
	// These will be re-planted into the freshly-generated Predicted batches after
	// the recompute so that manually-locked (or rush-inserted) cards are never
	// silently discarded by the full rebuild.
	var lockedSnapshots []lockedUnitSnapshot
	if snapErr := p.db.Raw(`
		SELECT
		  u.contract_no, u.customer, u.dealer_name, u.model_type,
		  b.model_type AS family,
		  u.due_date, u.sales_id, u.order_remark, u.locked_by, u.locked_at
		FROM units u
		JOIN batches b ON b.batch_id = u.batch_id
		WHERE b.status = ?
		  AND u.is_locked = 1
		  AND u.contract_no IS NOT NULL
		  AND TRIM(u.contract_no) != ''`,
		model.StatusPredicted,
	).Scan(&lockedSnapshots).Error; snapErr != nil {
		return nil, fmt.Errorf("snapshot locked predicted units: %w", snapErr)
	}

	contractRepo := repo.NewContractRepo(p.db)
	allUnits, err := contractRepo.ReadValidContractUnits()
	if err != nil {
		return nil, fmt.Errorf("read contracts: %w", err)
	}

	placedCounts, err := p.loadPlacedContractCounts()
	if err != nil {
		return nil, fmt.Errorf("read placed contracts: %w", err)
	}

	grouped := map[string][]model.ContractUnit{}
	for _, u := range allUnits {
		if placedCounts[u.ContractNo] > 0 {
			placedCounts[u.ContractNo]--
			continue
		}
		cat := modelCategoryOf(u.ModelName, u.ModelType)
		if cat == "" {
			cat = "特殊"
		}
		if cat != "特殊" {
			u.ModelType = familyOfCategory(cat)
		}
		grouped[cat] = append(grouped[cat], u)
	}

	maxBatches := p.getMaxBatches()
	gapDays := p.getGapDays()
	caps := p.getCapacityConfig()
	ratios := p.getRatioConfig()
	inventoryCounts, err := p.loadAvailableInventoryModelCounts()
	if err != nil {
		return nil, fmt.Errorf("read available inventory: %w", err)
	}
	slotPlan := plannedModelCategories(maxBatches, ratios)
	sortOrderMap, err := p.loadModelSortOrderMap()
	if err != nil {
		return nil, fmt.Errorf("load model sort order: %w", err)
	}

	batchesByCategory := map[string][]model.Batch{}
	for _, cat := range productionCategories {
		contracts := grouped[cat]
		if len(contracts) == 0 {
			continue
		}
		sort.Slice(contracts, func(i, j int) bool {
			return contracts[i].DueDate.Before(contracts[j].DueDate)
		})

		batchesByCategory[cat] = splitIntoBatches(contracts, capacityForCategory(cat, caps), gapDays)
	}

	var allBatches []model.Batch
	nextByCategory := map[string]int{}

	for slotIdx, cat := range slotPlan {
		next := nextByCategory[cat]
		var b model.Batch
		if next < len(batchesByCategory[cat]) {
			b = batchesByCategory[cat][next]
		}
		nextByCategory[cat] = next + 1
		family := familyOfCategory(cat)

		b.BatchID = generateBatchID(family, slotIdx+1)
		b.BatchNo = slotIdx + 1
		b.ModelType = family
		b.Capacity = capacityForCategory(cat, caps)
		b.Status = model.StatusPredicted
		b.Source = "algorithm"
		var stockAllocator *StockRatioAllocator
		if b.BatchNo == targetSlotNo {
			stockAllocator = NewStockRatioAllocator(ratios, inventoryCounts)
		}
		b.Units = buildFilledUnitsByCategory(b, caps, ratios, family, cat, stockAllocator)
		b.Units = sortAndReindexUnitsByModelDictionary(b.BatchID, b.Units, sortOrderMap)
		allBatches = append(allBatches, b)
	}

	// 特殊机型固定两条线：不参与比例，仅承载合同卡片。没有待排特殊合同时保留空占位列，供手动新增特殊卡片。
	specialContracts := grouped["特殊"]
	const specialCapacity = 15
	var specialLines [2][]model.ContractUnit
	if len(specialContracts) > 0 {
		sort.Slice(specialContracts, func(i, j int) bool {
			return specialContracts[i].DueDate.Before(specialContracts[j].DueDate)
		})
		specialLines = splitSpecialContractsIntoLines(specialContracts, specialCapacity, gapDays)
	}
	for _, lineContracts := range specialLines {
		b := model.Batch{
			BatchID:   generateBatchID("SPECIAL", len(allBatches)+1),
			BatchNo:   len(allBatches) + 1,
			ModelType: "SPECIAL",
			Capacity:  specialCapacity,
			Status:    model.StatusPredicted,
			Source:    "special",
			Units:     buildSpecialUnits(specialCapacity, lineContracts),
			CreatedAt: time.Now(),
			UpdatedAt: time.Now(),
		}
		allBatches = append(allBatches, b)
	}

	for _, cat := range productionCategories {
		family := familyOfCategory(cat)
		used := nextByCategory[cat]
		if used > len(batchesByCategory[cat]) {
			used = len(batchesByCategory[cat])
		}
		for _, rb := range batchesByCategory[cat][used:] {
			saveToWaitingQueue(p.db, extractContracts(rb.Units, family), family)
		}
	}

	tx := p.db.Begin()
	defer tx.Rollback()

	for _, mt := range []string{"G", "XS", "AUTO", "SPECIAL"} {
		if err := p.batchRepo.DeleteOldPredictedByModel(tx, mt); err != nil {
			return nil, fmt.Errorf("delete old %s: %w", mt, err)
		}
	}
	if err := tx.Exec("DELETE FROM forecast_batch_slots").Error; err != nil {
		return nil, fmt.Errorf("delete forecast batch slots: %w", err)
	}

	now := time.Now()
	slots := make([]model.ForecastBatchSlot, 0, len(allBatches))
	for i := range allBatches {
		b := &allBatches[i]
		if b.CreatedAt.IsZero() {
			b.CreatedAt = now
		}
		b.UpdatedAt = now

		if err := tx.Omit("Units").Create(b).Error; err != nil {
			return nil, fmt.Errorf("create batch %s: %w", b.BatchID, err)
		}
		batchID := b.BatchID
		slotSource := "ratio"
		if b.ModelType == "SPECIAL" {
			slotSource = "special"
		}
		slots = append(slots, model.ForecastBatchSlot{
			SlotNo:    b.BatchNo,
			ModelType: b.ModelType,
			Capacity:  b.Capacity,
			BatchID:   &batchID,
			Source:    slotSource,
			CreatedAt: now,
			UpdatedAt: now,
		})
		for j := range b.Units {
			b.Units[j].BatchID = b.BatchID
			if strings.TrimSpace(b.Units[j].UnitID) == "" {
				slot := b.Units[j].SlotIndex
				if slot <= 0 {
					slot = j + 1
					b.Units[j].SlotIndex = slot
				}
				b.Units[j].UnitID = generateUnitID(b.BatchID, slot)
			}
			b.Units[j].CreatedAt = now
			b.Units[j].UpdatedAt = now
		}
		if err := tx.Create(&b.Units).Error; err != nil {
			return nil, fmt.Errorf("create units for batch %s: %w", b.BatchID, err)
		}
	}
	if len(slots) > 0 {
		if err := tx.Create(&slots).Error; err != nil {
			return nil, fmt.Errorf("create forecast batch slots: %w", err)
		}
	}

	// ── Post-step: re-plant locked unit snapshots into the new Predicted batches. ─
	// For each snapshot we first try to find an empty slot whose model_type exactly
	// matches the locked unit's specific model (e.g. "FR-400G加高"). If none is
	// available we fall back to any empty slot in the same batch-level family. The
	// slot's contract fields and is_locked flag are then overwritten so the card
	// survives on the kanban board as before.
	for _, snap := range lockedSnapshots {
		if strings.TrimSpace(snap.ContractNo) == "" || strings.TrimSpace(snap.Family) == "" {
			continue
		}
		// Attempt 1 – exact model_type match within the family.
		var targetID struct {
			UnitID string `gorm:"column:unit_id"`
		}
		exactErr := tx.Raw(`
			SELECT u.unit_id
			FROM units u
			JOIN batches b ON b.batch_id = u.batch_id
			WHERE b.status = ?
			  AND b.model_type = ?
			  AND (u.contract_no IS NULL OR TRIM(u.contract_no) = '')
			  AND TRIM(u.model_type) = ?
			ORDER BY b.batch_no ASC, u.slot_index ASC
			LIMIT 1`,
			model.StatusPredicted, snap.Family, strings.TrimSpace(snap.ModelType),
		).Scan(&targetID).Error
		if exactErr != nil || targetID.UnitID == "" {
			// Attempt 2 – any empty slot in the same family.
			tx.Raw(`
				SELECT u.unit_id
				FROM units u
				JOIN batches b ON b.batch_id = u.batch_id
				WHERE b.status = ?
				  AND b.model_type = ?
				  AND (u.contract_no IS NULL OR TRIM(u.contract_no) = '')
				ORDER BY b.batch_no ASC, u.slot_index ASC
				LIMIT 1`,
				model.StatusPredicted, snap.Family,
			).Scan(&targetID)
		}
		if targetID.UnitID == "" {
			// No suitable empty slot – skip; the rush-insert overflow queue handles this.
			continue
		}
		updates := map[string]interface{}{
			"contract_no":  snap.ContractNo,
			"customer":     snap.Customer,
			"dealer_name":  snap.DealerName,
			"due_date":     snap.DueDate,
			"sales_id":     snap.SalesID,
			"order_remark": snap.OrderRemark,
			"model_type":   strings.TrimSpace(snap.ModelType),
			"is_locked":    true,
			"locked_by":    snap.LockedBy,
			"locked_at":    snap.LockedAt,
			"updated_at":   time.Now(),
		}
		if updateErr := tx.Table("units").Where("unit_id = ?", targetID.UnitID).Updates(updates).Error; updateErr != nil {
			return nil, fmt.Errorf("replant locked unit (contract=%s): %w", snap.ContractNo, updateErr)
		}
	}

	if err := tx.Commit().Error; err != nil {
		return nil, fmt.Errorf("commit: %w", err)
	}
	return allBatches, nil
}

func (p *Predictor) loadModelSortOrderMap() (map[string]int, error) {
	var rows []struct {
		ModelName string `gorm:"column:model_name"`
		SortOrder int    `gorm:"column:sort_order"`
	}
	if err := p.db.Table("model_dictionary").
		Select("model_name, sort_order").
		Where("enabled = 1").
		Scan(&rows).Error; err != nil {
		return nil, err
	}

	orderMap := make(map[string]int, len(rows))
	for _, row := range rows {
		key := normalizeModelKey(row.ModelName)
		if key == "" {
			continue
		}
		prev, exists := orderMap[key]
		if !exists || row.SortOrder < prev {
			orderMap[key] = row.SortOrder
		}
	}
	return orderMap, nil
}

func sortAndReindexUnitsByModelDictionary(batchID string, units []model.Unit, orderMap map[string]int) []model.Unit {
	if len(units) == 0 {
		return units
	}

	sort.SliceStable(units, func(i, j int) bool {
		ri := modelSortRank(units[i].ModelType, orderMap)
		rj := modelSortRank(units[j].ModelType, orderMap)
		if ri != rj {
			return ri < rj
		}
		mi := normalizeModelKey(units[i].ModelType)
		mj := normalizeModelKey(units[j].ModelType)
		if mi != mj {
			return mi < mj
		}
		return units[i].SlotIndex < units[j].SlotIndex
	})

	for i := range units {
		slot := i + 1
		units[i].SlotIndex = slot
		units[i].BatchID = batchID
		units[i].UnitID = generateUnitID(batchID, slot)
	}
	return units
}

func modelSortRank(modelName string, orderMap map[string]int) int {
	key := normalizeModelKey(modelName)
	if v, ok := orderMap[key]; ok {
		return v
	}
	return 1_000_000
}

func normalizeModelKey(s string) string {
	return strings.ToUpper(strings.TrimSpace(s))
}

func (p *Predictor) loadPlacedContractCounts() (map[string]int, error) {
	var rows []struct {
		ContractNo string `gorm:"column:contract_no"`
		Count      int    `gorm:"column:count"`
	}
	err := p.db.Table("units AS u").
		Select("u.contract_no AS contract_no, COUNT(*) AS count").
		Joins("JOIN batches AS b ON b.batch_id = u.batch_id").
		Where("u.contract_no IS NOT NULL AND u.contract_no <> ''").
		Where("b.status <> ?", model.StatusPredicted).
		Group("u.contract_no").
		Scan(&rows).Error
	if err != nil {
		return nil, err
	}

	counts := make(map[string]int, len(rows))
	for _, row := range rows {
		counts[row.ContractNo] = row.Count
	}
	return counts, nil
}

type batchGroup struct {
	units []model.ContractUnit
}

func splitIntoBatches(units []model.ContractUnit, capacity int, gapDays int) []model.Batch {
	var batches []model.Batch
	if len(units) == 0 {
		return batches
	}

	current := model.Batch{}
	current.Units = make([]model.Unit, 0, capacity)
	slotIdx := 1

	for _, cu := range units {
		if len(current.Units) > 0 {
			startDue := current.Units[0].DueDate
			cuDue := cu.DueDate
			if startDue != nil && !cuDue.IsZero() {
				diff := cuDue.Sub(*startDue)
				if diff.Hours() > float64(gapDays*24) {
					batches = append(batches, current)
					current = model.Batch{}
					current.Units = make([]model.Unit, 0, capacity)
					slotIdx = 1
				}
			}
		}

		if len(current.Units) >= capacity {
			batches = append(batches, current)
			current = model.Batch{}
			current.Units = make([]model.Unit, 0, capacity)
			slotIdx = 1
		}

		cn := cu.ContractNo
		cust := cu.Customer
		dn := cu.DealerName
		sid := cu.SalesID
		rem := cu.Remark

		current.Units = append(current.Units, model.Unit{
			SlotIndex:   slotIdx,
			ModelType:   unitModelType(cu),
			Status:      "Pending",
			ContractNo:  &cn,
			Customer:    &cust,
			DealerName:  &dn,
			DueDate:     &cu.DueDate,
			SalesID:     &sid,
			OrderRemark: &rem,
		})
		slotIdx++
	}

	if len(current.Units) > 0 {
		batches = append(batches, current)
	}

	for i := range batches {
		start := batches[i].Units[0].DueDate
		end := batches[i].Units[len(batches[i].Units)-1].DueDate
		batches[i].DueDateStart = start
		batches[i].DueDateEnd = end
	}

	return batches
}

func splitSpecialContractsIntoLines(contracts []model.ContractUnit, capacity int, gapDays int) [2][]model.ContractUnit {
	var lines [2][]model.ContractUnit
	lineIdx := 0
	for _, cu := range contracts {
		if lineIdx == 0 && len(lines[0]) > 0 {
			startDue := lines[0][0].DueDate
			overCapacity := len(lines[0]) >= capacity
			overGap := !startDue.IsZero() && !cu.DueDate.IsZero() && cu.DueDate.Sub(startDue).Hours() > float64(gapDays*24)
			if overCapacity || overGap {
				lineIdx = 1
			}
		}
		lines[lineIdx] = append(lines[lineIdx], cu)
	}
	return lines
}

func buildSpecialUnits(capacity int, contracts []model.ContractUnit) []model.Unit {
	if capacity <= 0 {
		return nil
	}
	// 有合同卡片时仅展示合同卡片；仅当该列无合同时才展示空槽位。
	limit := capacity
	if len(contracts) > 0 {
		limit = len(contracts)
	} else {
		limit = 1
	}
	out := make([]model.Unit, 0, limit)
	for i := 0; i < limit; i++ {
		slot := i + 1
		if i < len(contracts) {
			cu := contracts[i]
			cn := cu.ContractNo
			cust := cu.Customer
			dn := cu.DealerName
			sid := cu.SalesID
			rem := cu.Remark
			out = append(out, model.Unit{
				SlotIndex:   slot,
				ModelType:   unitModelType(cu),
				Status:      "Pending",
				ContractNo:  &cn,
				Customer:    &cust,
				DealerName:  &dn,
				DueDate:     &cu.DueDate,
				SalesID:     &sid,
				OrderRemark: &rem,
			})
			continue
		}
		if len(contracts) == 0 {
			out = append(out, model.Unit{
				SlotIndex: slot,
				ModelType: "SPECIAL",
				Status:    "Pending",
			})
		}
	}
	return out
}

func unitModelType(cu model.ContractUnit) string {
	if cu.ModelName != "" {
		return cu.ModelName
	}
	return cu.ModelType
}

func derefString(v *string) string {
	if v == nil {
		return ""
	}
	return *v
}

type StockRatioAllocator struct {
	weights     map[string]float64
	modelCat    map[string]string
	counts      map[string]int
	totalWeight float64
	totalCount  int
}

func NewStockRatioAllocator(ratios RatioConfig, baseline map[string]int) *StockRatioAllocator {
	weights, modelCat := finalStockModelWeights(ratios)
	if len(weights) == 0 {
		return &StockRatioAllocator{weights: map[string]float64{}, modelCat: map[string]string{}, counts: map[string]int{}}
	}
	counts := make(map[string]int, len(weights))
	for modelName := range weights {
		counts[modelName] = 0
	}
	for inventoryModel, count := range baseline {
		if count <= 0 {
			continue
		}
		targetModel := canonicalRatioModelName(inventoryModel, weights)
		if targetModel == "" {
			continue
		}
		counts[targetModel] += count
	}
	totalWeight := 0.0
	totalCount := 0
	for modelName, weight := range weights {
		if weight > 0 {
			totalWeight += weight
			totalCount += counts[modelName]
		}
	}
	return &StockRatioAllocator{
		weights:     weights,
		modelCat:    modelCat,
		counts:      counts,
		totalWeight: totalWeight,
		totalCount:  totalCount,
	}
}

func (a *StockRatioAllocator) TakeModelsForCategory(category string, slots int) []string {
	if a == nil || slots <= 0 {
		return nil
	}
	out := make([]string, 0, slots)
	for i := 0; i < slots; i++ {
		modelName := a.TakeModelForCategory(category)
		if strings.TrimSpace(modelName) == "" {
			break
		}
		out = append(out, modelName)
	}
	return out
}

func (a *StockRatioAllocator) TakeModelForCategory(category string) string {
	if a == nil {
		return ""
	}
	cat := canonicalCategory(category)
	categoryWeight := 0.0
	categoryCount := 0
	for modelName, weight := range a.weights {
		if weight <= 0 || a.modelCat[modelName] != cat {
			continue
		}
		categoryWeight += weight
		categoryCount += a.counts[modelName]
	}
	if categoryWeight <= 0 {
		return ""
	}

	bestModel := ""
	bestScore := math.Inf(-1)
	for modelName, weight := range a.weights {
		if weight <= 0 || a.modelCat[modelName] != cat {
			continue
		}
		targetAfter := (float64(categoryCount+1) * weight) / categoryWeight
		score := targetAfter - float64(a.counts[modelName]+1)
		if bestModel == "" || score > bestScore || (score == bestScore && modelName < bestModel) {
			bestModel = modelName
			bestScore = score
		}
	}
	if bestModel == "" {
		return ""
	}
	a.counts[bestModel]++
	a.totalCount++
	return bestModel
}

func finalStockModelWeights(ratios RatioConfig) (map[string]float64, map[string]string) {
	categoryRatios := normalizedGlobalCategoryRatios(ratios)
	weights := map[string]float64{}
	modelCat := map[string]string{}
	for _, category := range productionCategories {
		catWeight := categoryRatios[category]
		if catWeight <= 0 {
			continue
		}
		level3 := ratios.Level3[category]
		level3Sum := 0
		for _, ratio := range level3 {
			if ratio > 0 {
				level3Sum += ratio
			}
		}
		if level3Sum <= 0 {
			modelName := defaultModelForCategory(category)
			weights[modelName] += catWeight
			modelCat[modelName] = category
			continue
		}
		for modelName, modelRatio := range level3 {
			if modelRatio <= 0 {
				continue
			}
			cleanModel := strings.TrimSpace(modelName)
			if cleanModel == "" {
				cleanModel = defaultModelForCategory(category)
			}
			weights[cleanModel] += catWeight * float64(modelRatio) / float64(level3Sum)
			modelCat[cleanModel] = category
		}
	}
	return weights, modelCat
}

func normalizedGlobalCategoryRatios(ratios RatioConfig) map[string]float64 {
	out := map[string]float64{}
	sum := 0
	for _, category := range productionCategories {
		v := pickRatio(ratios.Level2Global, category)
		if v < 0 {
			v = 0
		}
		out[category] = float64(v)
		sum += v
	}
	if sum == 0 {
		fallback := map[string]int{"涓皬鍨婫": 24, "涓皬鍨媂S": 38, "涓ぇ鍨媂S": 38, "涓皬鍨婣UTO": 0, "涓ぇ鍨婣UTO": 0}
		for _, category := range productionCategories {
			out[category] = float64(fallback[category])
		}
		return out
	}
	if sum != 100 {
		for _, category := range productionCategories {
			out[category] = out[category] * 100.0 / float64(sum)
		}
	}
	return out
}

func canonicalRatioModelName(modelName string, weights map[string]float64) string {
	clean := strings.TrimSpace(modelName)
	if clean == "" {
		return ""
	}
	if _, ok := weights[clean]; ok {
		return clean
	}
	norm := normalizeModelKey(clean)
	for target := range weights {
		if normalizeModelKey(target) == norm {
			return target
		}
	}
	return ""
}

func buildFilledUnitsByCategory(b model.Batch, caps CapacityConfig, ratios RatioConfig, family string, category string, stockAllocator *StockRatioAllocator) []model.Unit {
	capacity := b.Capacity
	if capacity <= 0 {
		capacity = capacityForCategory(category, caps)
	}
	existing := len(b.Units)
	if existing > capacity {
		existing = capacity
		b.Units = b.Units[:capacity]
	}

	filled := make([]model.Unit, capacity)
	copy(filled, b.Units)

	remaining := capacity - existing
	if remaining <= 0 {
		for i := range filled {
			filled[i].SlotIndex = i + 1
			id := filled[i].UnitID
			if id == "" {
				filled[i].UnitID = generateUnitID(b.BatchID, i+1)
			}
		}
		return filled
	}

	emptyModels := []string(nil)
	if stockAllocator != nil {
		emptyModels = stockAllocator.TakeModelsForCategory(category, remaining)
	}
	if len(emptyModels) < remaining {
		dist := distributeEmptySlotsByCategory(category, remaining-len(emptyModels), ratios)
		for modelName, count := range dist {
			mt := strings.TrimSpace(modelName)
			if mt == "" {
				mt = defaultModelForCategory(category)
			}
			for i := 0; i < count; i++ {
				emptyModels = append(emptyModels, mt)
			}
		}
	}
	sort.Strings(emptyModels)

	idx := existing
	for _, mt := range emptyModels {
		if idx >= capacity {
			break
		}
		slot := idx + 1
		unitID := generateUnitID(b.BatchID, slot)
		filled[idx] = model.Unit{
			UnitID:    unitID,
			SlotIndex: slot,
			ModelType: mt,
			Status:    "Pending",
		}
		idx++
	}

	for i := range filled {
		filled[i].SlotIndex = i + 1
		filled[i].BatchID = b.BatchID
		if filled[i].UnitID == "" {
			filled[i].UnitID = generateUnitID(b.BatchID, i+1)
		}
		if filled[i].Status == "" {
			filled[i].Status = "Pending"
		}
	}

	return filled
}

func emptySlotConcreteModel(modelType string, sizeKey string) string {
	if strings.HasPrefix(strings.ToUpper(strings.TrimSpace(sizeKey)), "FR-") {
		return strings.TrimSpace(sizeKey)
	}
	family := NormalizeModelType(modelType)
	size := normalizeSizeKey(sizeKey)
	if size == "default" || size == "other" {
		size = "400"
	}
	if size == "300" {
		size = "400"
	}

	switch family {
	case "G":
		switch size {
		case "500":
			return "FR-500G"
		case "600":
			return "FR-600G"
		default:
			return "FR-400G"
		}
	case "XS":
		switch size {
		case "500":
			return "FR-500XS(PRO)"
		case "600":
			return "FR-600XS(PRO)"
		default:
			return "FR-400XS(PRO)"
		}
	case "AUTO":
		switch size {
		case "500":
			return "FR-500AUTO"
		case "600":
			return "FR-600AUTO"
		default:
			return "FR-400AUTO"
		}
	default:
		return modelType
	}
}

func normalizeSizeKey(sizeKey string) string {
	raw := strings.TrimSpace(sizeKey)
	if strings.Contains(raw, "大机") {
		return "600"
	}
	if strings.Contains(raw, "中大型") {
		return "600"
	}
	if strings.Contains(raw, "小机") {
		return "400"
	}
	if strings.Contains(raw, "中小型") {
		return "400"
	}
	if strings.Contains(raw, "特殊") {
		return "600"
	}
	v := strings.ToLower(raw)
	if v == "" {
		return "default"
	}
	if v == "big" {
		return "600"
	}
	return v
}

func distributeEmptySlotsByCategory(category string, total int, ratios RatioConfig) map[string]int {
	l3, ok := ratios.Level3[category]
	if !ok || len(l3) == 0 {
		return map[string]int{defaultModelForCategory(category): total}
	}

	type kv struct {
		key   string
		ratio int
	}
	var items []kv
	for k, v := range l3 {
		items = append(items, kv{k, v})
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].ratio != items[j].ratio {
			return items[i].ratio > items[j].ratio
		}
		return items[i].key < items[j].key
	})

	result := make(map[string]int)
	allocated := 0
	remainders := make(map[string]float64)

	for _, it := range items {
		exact := float64(total) * float64(it.ratio) / 100.0
		floor := int(math.Floor(exact))
		result[it.key] = floor
		allocated += floor
		remainders[it.key] = exact - float64(floor)
	}

	// Distribute remainder to items with largest fractional parts
	for allocated < total {
		best := ""
		bestRem := -1.0
		for _, it := range items {
			if remainders[it.key] > bestRem {
				bestRem = remainders[it.key]
				best = it.key
			}
		}
		if best == "" {
			break
		}
		result[best]++
		allocated++
		remainders[best] = -1.0
	}

	// If somehow still under, pad first item
	for allocated < total {
		result[items[0].key]++
		allocated++
	}

	return result
}

func distributeEmptySlotsForBatch(category string, total int, ratios RatioConfig, existingUnits []model.Unit) map[string]int {
	result := distributeEmptySlotsByCategory(category, total, ratios)
	if total <= 0 {
		return result
	}
	l3 := ratios.Level3[category]
	if len(l3) == 0 {
		return result
	}

	type candidate struct {
		model string
		ratio int
	}
	seen := map[string]bool{}
	candidates := make([]candidate, 0)
	for _, u := range existingUnits {
		if u.ContractNo == nil || strings.TrimSpace(*u.ContractNo) == "" {
			continue
		}
		modelName := strings.TrimSpace(u.ModelType)
		if modelName == "" {
			continue
		}
		if seen[normalizeModelKey(modelName)] {
			continue
		}
		ratio := 0
		for key, value := range l3 {
			if normalizeModelKey(key) == normalizeModelKey(modelName) {
				ratio = value
				modelName = key
				break
			}
		}
		if ratio <= 0 {
			continue
		}
		seen[normalizeModelKey(modelName)] = true
		candidates = append(candidates, candidate{model: modelName, ratio: ratio})
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].ratio != candidates[j].ratio {
			return candidates[i].ratio > candidates[j].ratio
		}
		return candidates[i].model < candidates[j].model
	})

	for _, cand := range candidates {
		if result[cand.model] > 0 {
			continue
		}
		donor := ""
		donorCount := 1
		for modelName, count := range result {
			if normalizeModelKey(modelName) == normalizeModelKey(cand.model) {
				continue
			}
			if count > donorCount {
				donor = modelName
				donorCount = count
			}
		}
		if donor == "" {
			continue
		}
		result[donor]--
		result[cand.model]++
	}
	return result
}

func plannedModelCategories(total int, ratios RatioConfig) []string {
	if total <= 0 {
		return nil
	}
	targetRatios := map[string]int{
		"中小型G":    pickRatio(ratios.Level2Global, "中小型G"),
		"中小型XS":   pickRatio(ratios.Level2Global, "中小型XS"),
		"中大型XS":   pickRatio(ratios.Level2Global, "中大型XS"),
		"中小型AUTO": pickRatio(ratios.Level2Global, "中小型AUTO"),
		"中大型AUTO": pickRatio(ratios.Level2Global, "中大型AUTO"),
	}
	sum := 0
	for _, k := range productionCategories {
		if targetRatios[k] < 0 {
			targetRatios[k] = 0
		}
		sum += targetRatios[k]
	}
	if sum == 0 {
		targetRatios = map[string]int{"中小型G": 24, "中小型XS": 38, "中大型XS": 38, "中小型AUTO": 0, "中大型AUTO": 0}
	} else if sum != 100 {
		for k, v := range targetRatios {
			targetRatios[k] = int(math.Round(float64(v) * 100.0 / float64(sum)))
		}
	}

	target := make(map[string]int, 5)
	items := []struct {
		k string
		r int
	}{
		{k: "中小型G", r: targetRatios["中小型G"]},
		{k: "中小型XS", r: targetRatios["中小型XS"]},
		{k: "中大型XS", r: targetRatios["中大型XS"]},
		{k: "中小型AUTO", r: targetRatios["中小型AUTO"]},
		{k: "中大型AUTO", r: targetRatios["中大型AUTO"]},
	}

	allocated := 0
	remainders := map[string]float64{}
	for _, it := range items {
		exact := float64(total) * float64(it.r) / 100.0
		base := int(math.Floor(exact))
		target[it.k] = base
		allocated += base
		remainders[it.k] = exact - float64(base)
	}
	for allocated < total {
		best := ""
		bestRem := -1.0
		for _, it := range items {
			if remainders[it.k] > bestRem {
				bestRem = remainders[it.k]
				best = it.k
			}
		}
		if best == "" {
			break
		}
		target[best]++
		remainders[best] = -1.0
		allocated++
	}

	order := productionCategories
	out := make([]string, 0, total)
	for len(out) < total {
		progressed := false
		for _, mt := range order {
			if target[mt] > 0 {
				out = append(out, mt)
				target[mt]--
				progressed = true
				if len(out) >= total {
					break
				}
			}
		}
		if !progressed {
			break
		}
	}
	for len(out) < total {
		out = append(out, "中小型XS")
	}
	return out
}

func pickRatio(m map[string]int, key string) int {
	if len(m) == 0 {
		return 0
	}
	if v, ok := m[key]; ok {
		return v
	}
	normKey := strings.TrimSpace(strings.ToUpper(key))
	for k, v := range m {
		if strings.TrimSpace(strings.ToUpper(k)) == normKey {
			return v
		}
	}
	return 0
}

func familyOfCategory(category string) string {
	switch strings.TrimSpace(category) {
	case "中小型G":
		return "G"
	case "中小型XS", "中大型XS":
		return "XS"
	case "中小型AUTO", "中大型AUTO":
		return "AUTO"
	default:
		return NormalizeModelType(category)
	}
}

func defaultModelForCategory(category string) string {
	switch strings.TrimSpace(category) {
	case "中小型G":
		return "FR-400G"
	case "中小型XS":
		return "FR-400XS(PRO)"
	case "中大型XS":
		return "FR-7055XS(PRO)"
	case "中小型AUTO":
		return "FR-400AUTO"
	case "中大型AUTO":
		return "FR-7055AUTO"
	default:
		return "FR-400XS(PRO)"
	}
}

func modelCategoryOf(modelName string, modelType string) string {
	raw := strings.TrimSpace(modelName)
	if raw == "" {
		raw = strings.TrimSpace(modelType)
	}
	upper := strings.ToUpper(raw)
	if upper == "" {
		return ""
	}

	// model_family from model_dictionary takes priority over name-based heuristics.
	if familyCategory := canonicalCategory(strings.TrimSpace(modelType)); familyCategory != "" {
		switch familyCategory {
		case "中小型G", "中小型XS", "中大型XS", "中小型AUTO", "中大型AUTO", "特殊":
			return familyCategory
		}
	}

	if strings.Contains(raw, "特殊") {
		return "特殊"
	}
	if upper == "FH-300C" {
		return "中小型G"
	}
	if strings.Contains(upper, "AUTO") {
		if strings.Contains(upper, "7055") || strings.Contains(upper, "8055") || strings.Contains(upper, "8060") {
			return "中大型AUTO"
		}
		return "中小型AUTO"
	}
	if strings.Contains(upper, "XS") {
		if strings.Contains(upper, "7055") || strings.Contains(upper, "8055") || strings.Contains(upper, "8060") {
			return "中大型XS"
		}
		return "中小型XS"
	}
	if strings.HasSuffix(upper, "G") || strings.Contains(upper, "中小型G") {
		return "中小型G"
	}
	return "特殊"
}

// extractContracts pulls contract data from batch units (skipping empty slots).
func extractContracts(units []model.Unit, modelType string) []model.ContractUnit {
	var result []model.ContractUnit
	for _, u := range units {
		if u.ContractNo == nil {
			continue
		}
		cu := model.ContractUnit{
			ContractNo: *u.ContractNo,
			ModelType:  modelType,
		}
		if u.Customer != nil {
			cu.Customer = *u.Customer
		}
		if u.DealerName != nil {
			cu.DealerName = *u.DealerName
		}
		if u.DueDate != nil {
			cu.DueDate = *u.DueDate
		}
		if u.SalesID != nil {
			cu.SalesID = *u.SalesID
		}
		if u.OrderRemark != nil {
			cu.Remark = *u.OrderRemark
		}
		result = append(result, cu)
	}
	return result
}

// saveToWaitingQueue persists overflow contracts to the production queue.
func saveToWaitingQueue(db *gorm.DB, contracts []model.ContractUnit, modelType string) {
	supportsPayloadPriority := queueHasColumns(db, "production_queue", "payload", "priority")
	for i, cu := range contracts {
		if !supportsPayloadPriority {
			contractNo := strings.TrimSpace(cu.ContractNo)
			if contractNo == "" {
				contractNo = fmt.Sprintf("OVERFLOW-%d-%d", time.Now().UnixNano(), i)
			}
			row := map[string]interface{}{
				"model_type":         modelType,
				"contract_no":        contractNo,
				"customer":           cu.Customer,
				"dealer":             cu.DealerName,
				"due_date":           cu.DueDate.Format("2006-01-02"),
				"quantity_remaining": 1,
				"status":             model.QueueWaiting,
			}
			db.Table("production_queue").Create(row)
			continue
		}

		payload, _ := json.Marshal(map[string]interface{}{
			"contract_no": cu.ContractNo,
			"customer":    cu.Customer,
			"dealer_name": cu.DealerName,
			"model_type":  modelType,
			"due_date":    cu.DueDate.Format("2006-01-02"),
			"sales_id":    cu.SalesID,
			"remark":      cu.Remark,
		})
		entry := model.ProductionQueue{
			ModelType:  modelType,
			ContractNo: &cu.ContractNo,
			Payload:    datatypes.JSON(payload),
			Status:     model.QueueWaiting,
			Priority:   i,
		}
		db.Create(&entry)
	}
}

func queueHasColumns(db *gorm.DB, table string, cols ...string) bool {
	for _, col := range cols {
		var count int64
		if err := db.Raw(`
SELECT COUNT(*)
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = ?
  AND COLUMN_NAME = ?`, table, col).Scan(&count).Error; err != nil {
			return false
		}
		if count == 0 {
			return false
		}
	}
	return true
}
