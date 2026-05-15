package engine

import (
	"testing"

	"smart-scheduling/server/internal/model"
)

func TestModelCategoryOfRespectsSpecialFamily(t *testing.T) {
	tests := []struct {
		name        string
		modelName   string
		modelFamily string
		want        string
	}{
		{
			name:        "Chinese special family wins over G suffix",
			modelName:   "FR-1080G",
			modelFamily: "特殊",
			want:        "特殊",
		},
		{
			name:        "English special family wins over XS marker",
			modelName:   "FR-1080XS",
			modelFamily: "SPECIAL",
			want:        "特殊",
		},
		{
			name:        "Small G family remains small G",
			modelName:   "FH-300C",
			modelFamily: "中小型G",
			want:        "中小型G",
		},
		{
			name:        "Dictionary family wins over special name",
			modelName:   "特殊-FR-8060XS(PRO)",
			modelFamily: "中大型XS",
			want:        "中大型XS",
		},
		{
			name:        "8060 XS falls back to medium-large",
			modelName:   "FR-8060XS(PRO)",
			modelFamily: "",
			want:        "中大型XS",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := modelCategoryOf(tt.modelName, tt.modelFamily); got != tt.want {
				t.Fatalf("modelCategoryOf(%q, %q) = %q, want %q", tt.modelName, tt.modelFamily, got, tt.want)
			}
		})
	}
}

func TestRehomeLevel3ModelsByDictionary(t *testing.T) {
	level3 := map[string]map[string]int{
		"中小型XS": {
			"FR-400XS(PRO)":  80,
			"FR-8060XS(PRO)": 20,
		},
		"中小型AUTO": {
			"FR-8060AUTO": 15,
		},
	}
	rehomeLevel3ModelsByDictionary(level3, map[string]string{
		"FR-8060XS(PRO)": "中大型XS",
		"FR-8060AUTO":    "中大型AUTO",
	})

	if _, ok := level3["中小型XS"]["FR-8060XS(PRO)"]; ok {
		t.Fatalf("FR-8060XS(PRO) should be moved out of 中小型XS")
	}
	if got := level3["中大型XS"]["FR-8060XS(PRO)"]; got != 20 {
		t.Fatalf("FR-8060XS(PRO) ratio = %d, want 20 in 中大型XS", got)
	}
	if _, ok := level3["中小型AUTO"]["FR-8060AUTO"]; ok {
		t.Fatalf("FR-8060AUTO should be moved out of 中小型AUTO")
	}
	if got := level3["中大型AUTO"]["FR-8060AUTO"]; got != 15 {
		t.Fatalf("FR-8060AUTO ratio = %d, want 15 in 中大型AUTO", got)
	}
}

func TestDistributeEmptySlotsForBatchKeepsOrderedPositiveRatioModels(t *testing.T) {
	contract := "HT-1"
	dist := distributeEmptySlotsForBatch("涓皬鍨婣UTO", 5, RatioConfig{
		Level3: map[string]map[string]int{
			"涓皬鍨婣UTO": {
				"FR-400AUTO": 60,
				"FR-500AUTO": 5,
				"FR-600AUTO": 35,
			},
		},
	}, []model.Unit{
		{ModelType: "FR-400AUTO", ContractNo: &contract},
		{ModelType: "FR-500AUTO", ContractNo: &contract},
		{ModelType: "FR-600AUTO", ContractNo: &contract},
	})

	if got := dist["FR-500AUTO"]; got != 1 {
		t.Fatalf("FR-500AUTO stock count = %d, want 1", got)
	}
	total := 0
	for _, count := range dist {
		total += count
	}
	if total != 5 {
		t.Fatalf("total stock count = %d, want 5", total)
	}
}

func TestStockRatioAllocatorUsesInventoryBaseline(t *testing.T) {
	category := productionCategories[3]
	allocator := NewStockRatioAllocator(RatioConfig{
		Level2Global: map[string]int{category: 100},
		Level3: map[string]map[string]int{
			category: {
				"FR-400AUTO": 60,
				"FR-500AUTO": 40,
			},
		},
	}, map[string]int{
		"FR-400AUTO": 10,
	})

	models := allocator.TakeModelsForCategory(category, 5)
	if len(models) != 5 {
		t.Fatalf("allocated stock count = %d, want 5", len(models))
	}
	for _, modelName := range models {
		if modelName != "FR-500AUTO" {
			t.Fatalf("allocated model = %q, want FR-500AUTO while FR-400AUTO inventory is over target", modelName)
		}
	}
}

func TestStockRatioAllocatorPrioritizesWithinCategoryRatios(t *testing.T) {
	category := productionCategories[2]
	allocator := NewStockRatioAllocator(RatioConfig{
		Level2Global: map[string]int{category: 100},
		Level3: map[string]map[string]int{
			category: {
				"FR-7055XS(PRO)": 50,
				"FR-8055XS(PRO)": 25,
				"FR-8060XS(PRO)": 25,
			},
		},
	}, map[string]int{
		"FR-7055XS(PRO)": 50,
		"FR-8055XS(PRO)": 18,
		"FR-8060XS(PRO)": 5,
	})

	models := allocator.TakeModelsForCategory(category, 15)
	counts := map[string]int{}
	for _, modelName := range models {
		counts[modelName]++
	}
	if counts["FR-7055XS(PRO)"] != 0 {
		t.Fatalf("FR-7055XS(PRO) allocated = %d, want 0 because it is already above the category target", counts["FR-7055XS(PRO)"])
	}
	if counts["FR-8055XS(PRO)"] == 0 {
		t.Fatalf("FR-8055XS(PRO) should be allocated when it is below the category target")
	}
	if counts["FR-8060XS(PRO)"] <= counts["FR-8055XS(PRO)"] {
		t.Fatalf("allocation = %#v, want more FR-8060XS(PRO) than FR-8055XS(PRO) because 8060 is the larger category gap", counts)
	}
}

func TestBuildFilledUnitsUsesAllocatorOnlyWhenProvided(t *testing.T) {
	category := productionCategories[0]
	ratios := RatioConfig{
		Level2Global: map[string]int{category: 100},
		Level3: map[string]map[string]int{
			category: {
				"FR-400G": 60,
				"FH-300C": 40,
			},
		},
	}
	caps := CapacityConfig{G: 5, XS: 5, AUTO: 5}
	batch := model.Batch{BatchID: "B-1", BatchNo: 1, ModelType: "G", Capacity: 5}

	targetUnits := buildFilledUnitsByCategory(
		batch,
		caps,
		ratios,
		"G",
		category,
		NewStockRatioAllocator(ratios, map[string]int{"FR-400G": 10}),
	)
	for _, u := range targetUnits {
		if u.ModelType != "FH-300C" {
			t.Fatalf("target stock model = %q, want FH-300C while FR-400G baseline is over target", u.ModelType)
		}
	}

	placeholderUnits := buildFilledUnitsByCategory(batch, caps, ratios, "G", category, nil)
	counts := map[string]int{}
	for _, u := range placeholderUnits {
		counts[u.ModelType]++
	}
	if counts["FR-400G"] != 3 || counts["FH-300C"] != 2 {
		t.Fatalf("placeholder distribution = %#v, want static 3/2 ratio placeholders", counts)
	}
}

func TestFinalStockModelWeightsCombinesGlobalAndLevel3Ratios(t *testing.T) {
	gCat := productionCategories[0]
	autoCat := productionCategories[3]
	weights, _ := finalStockModelWeights(RatioConfig{
		Level2Global: map[string]int{gCat: 25, autoCat: 75},
		Level3: map[string]map[string]int{
			gCat: {
				"FR-400G": 80,
				"FH-300C": 20,
			},
			autoCat: {
				"FR-400AUTO": 60,
				"FR-500AUTO": 40,
			},
		},
	})

	if got := weights["FR-400G"]; got != 20 {
		t.Fatalf("FR-400G weight = %v, want 20", got)
	}
	if got := weights["FR-500AUTO"]; got != 30 {
		t.Fatalf("FR-500AUTO weight = %v, want 30", got)
	}
}
