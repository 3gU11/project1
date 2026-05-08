package handler

import (
	"strings"

	"smart-scheduling/server/internal/model"
)

func sanitizeUnitRemarkForResponse(u *model.Unit) {
	if u == nil {
		return
	}
	if u.ContractNo == nil || strings.TrimSpace(*u.ContractNo) == "" {
		u.OrderRemark = nil
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
