package engine

import "strings"

const (
	ProductionGroupSmallG    = "SMALL_G"
	ProductionGroupSmallXS   = "SMALL_XS"
	ProductionGroupSmallAUTO = "SMALL_AUTO"
	ProductionGroupLarge     = "LARGE"
	ProductionGroupSpecial   = "SPECIAL"
)

func ProductionGroupForCategory(value string) string {
	category := strings.TrimSpace(value)
	switch category {
	case "大机XS", "大机AUTO", "中大型XS", "中大型AUTO":
		return ProductionGroupLarge
	case "小机G", "中小型G":
		return ProductionGroupSmallG
	case "小机XS", "小机/XS", "中小型XS":
		return ProductionGroupSmallXS
	case "小机AUTO", "中小型AUTO":
		return ProductionGroupSmallAUTO
	case "特殊", "SPECIAL":
		return ProductionGroupSpecial
	default:
		return ""
	}
}

func ProductionGroupForModel(modelType string) string {
	if group := ProductionGroupForCategory(modelType); group != "" {
		return group
	}
	upper := strings.ToUpper(strings.TrimSpace(modelType))
	family := NormalizeModelType(modelType)
	if (family == "XS" || family == "AUTO") &&
		(strings.Contains(upper, "7055") || strings.Contains(upper, "8055") || strings.Contains(upper, "8060")) {
		return ProductionGroupLarge
	}
	switch family {
	case "G":
		return ProductionGroupSmallG
	case "XS":
		return ProductionGroupSmallXS
	case "AUTO":
		return ProductionGroupSmallAUTO
	case "SPECIAL":
		return ProductionGroupSpecial
	default:
		return ""
	}
}

func ProductionGroupForBatch(modelType string, capacity int) string {
	family := NormalizeModelType(modelType)
	if capacity == 16 && (family == "XS" || family == "AUTO") {
		return ProductionGroupLarge
	}
	switch family {
	case "G":
		return ProductionGroupSmallG
	case "XS":
		return ProductionGroupSmallXS
	case "AUTO":
		return ProductionGroupSmallAUTO
	case "SPECIAL":
		return ProductionGroupSpecial
	default:
		return ""
	}
}

func ProductionGroupsCompatible(source string, target string) bool {
	return source != "" && target != "" && source == target
}

func ProductionRegionForGroup(group string) string {
	switch group {
	case ProductionGroupLarge:
		return "LARGE"
	case ProductionGroupSpecial:
		return "SPECIAL"
	case ProductionGroupSmallG, ProductionGroupSmallXS, ProductionGroupSmallAUTO:
		return "SMALL"
	default:
		return ""
	}
}

func ProductionRegionForBatch(modelType string, capacity int) string {
	return ProductionRegionForGroup(ProductionGroupForBatch(modelType, capacity))
}
