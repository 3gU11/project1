package service

import (
	"testing"

	"smart-scheduling/server/internal/model"
)

func TestProductionLineRegionUsesConfiguredRegion(t *testing.T) {
	large := "LARGE"
	line := model.ProductionLine{Region: &large, LineName: "产线 14 中大型"}
	if got := productionLineRegion(line); got != "LARGE" {
		t.Fatalf("line region = %q, want LARGE", got)
	}
}

func TestProductionLineRegionFallsBackToLineMetadata(t *testing.T) {
	modelType := "中小型机型线"
	line := model.ProductionLine{ModelType: &modelType, LineName: "产线 01 中小型"}
	if got := productionLineRegion(line); got != "SMALL" {
		t.Fatalf("line region = %q, want SMALL", got)
	}
}

func TestInboundBatchReadyRequiresEveryUnit(t *testing.T) {
	tests := []struct {
		name     string
		progress inboundBatchProgress
		want     bool
	}{
		{name: "empty batch", progress: inboundBatchProgress{}, want: false},
		{name: "partially inbound", progress: inboundBatchProgress{TotalUnits: 3, InboundUnits: 2}, want: false},
		{name: "fully inbound", progress: inboundBatchProgress{TotalUnits: 3, InboundUnits: 3}, want: true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := inboundBatchReady(tt.progress); got != tt.want {
				t.Fatalf("inboundBatchReady(%+v) = %t, want %t", tt.progress, got, tt.want)
			}
		})
	}
}

func TestLineStateAfterBatchCompletion(t *testing.T) {
	completed := "batch-a"
	if status, current := lineStateAfterBatchCompletion(&completed, completed, nil); status != model.LineIdle || current != nil {
		t.Fatalf("empty line state = (%q, %v), want Idle and nil", status, current)
	}

	remaining := []string{"batch-b", "batch-c"}
	status, current := lineStateAfterBatchCompletion(&completed, completed, remaining)
	if status != model.LineBusy || current == nil || *current != "batch-b" {
		t.Fatalf("next batch state = (%q, %v), want Busy and batch-b", status, current)
	}

	existing := "batch-c"
	status, current = lineStateAfterBatchCompletion(&existing, completed, remaining)
	if status != model.LineBusy || current == nil || *current != existing {
		t.Fatalf("preserved batch state = (%q, %v), want Busy and batch-c", status, current)
	}
}
