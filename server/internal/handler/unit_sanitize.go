package handler

import (
	"smart-scheduling/server/internal/model"
)

func sanitizeUnitRemarkForResponse(u *model.Unit) {
	if u == nil {
		return
	}
}

func sanitizeUnitsRemarkForResponse(units []model.Unit) {
	for i := range units {
		sanitizeUnitRemarkForResponse(&units[i])
	}
}

func sanitizeBatchRemarkForResponse(batch *model.Batch) {
	if batch == nil {
		return
	}
	sanitizeUnitsRemarkForResponse(batch.Units)
}

func sanitizeBatchesRemarkForResponse(batches []model.Batch) {
	for i := range batches {
		sanitizeUnitsRemarkForResponse(batches[i].Units)
	}
}
