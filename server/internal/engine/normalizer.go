package engine

import "smart-scheduling/server/internal/modeltype"

func NormalizeModelType(raw string) string {
	return modeltype.Normalize(raw)
}
