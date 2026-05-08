package modeltype

import (
	"log"
	"regexp"
	"strings"
)

var gModelPattern = regexp.MustCompile(`FR-\d+G`)

func Normalize(raw string) string {
	trimmed := strings.TrimSpace(raw)
	upper := strings.ToUpper(trimmed)
	switch {
	case upper == "FH-300C":
		return "G"
	case strings.Contains(upper, "特殊") || strings.Contains(upper, "鐗规畩"):
		return "SPECIAL"
	case strings.Contains(upper, "AUTO"):
		return "AUTO"
	case strings.Contains(upper, "XS"):
		return "XS"
	case gModelPattern.MatchString(upper):
		return "G"
	case upper == "G" || upper == "XS" || upper == "AUTO":
		return upper
	default:
		if trimmed != "" {
			log.Printf("WARN unknown model type, keep raw value: %s", trimmed)
		}
		return trimmed
	}
}
