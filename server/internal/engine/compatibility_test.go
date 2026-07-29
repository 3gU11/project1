package engine

import "testing"

func TestLargeXSAndAUTOShareProductionGroup(t *testing.T) {
	if got := ProductionGroupForCategory("中大型XS"); got != ProductionGroupLarge {
		t.Fatalf("中大型XS group = %q, want %q", got, ProductionGroupLarge)
	}
	if got := ProductionGroupForCategory("中大型AUTO"); got != ProductionGroupLarge {
		t.Fatalf("中大型AUTO group = %q, want %q", got, ProductionGroupLarge)
	}
	if !ProductionGroupsCompatible(
		ProductionGroupForBatch("XS", 16),
		ProductionGroupForBatch("AUTO", 16),
	) {
		t.Fatal("large XS and AUTO batches should be compatible")
	}
}

func TestSmallAndLargeBatchesAreNotCompatible(t *testing.T) {
	if ProductionGroupsCompatible(
		ProductionGroupForBatch("XS", 30),
		ProductionGroupForBatch("XS", 16),
	) {
		t.Fatal("small XS and large XS batches must not be compatible")
	}
	if ProductionGroupsCompatible(
		ProductionGroupForBatch("AUTO", 27),
		ProductionGroupForBatch("AUTO", 16),
	) {
		t.Fatal("small AUTO and large AUTO batches must not be compatible")
	}
}

func TestLargeConcreteModelsShareProductionGroup(t *testing.T) {
	for _, modelType := range []string{"FR-7055XS(PRO)", "FR-8055AUTO", "FR-8060XS(PRO)"} {
		if got := ProductionGroupForModel(modelType); got != ProductionGroupLarge {
			t.Fatalf("%s group = %q, want %q", modelType, got, ProductionGroupLarge)
		}
	}
}

func TestProductionRegionsKeepSmallAndLargeLinesSeparate(t *testing.T) {
	if got := ProductionRegionForBatch("XS", 16); got != "LARGE" {
		t.Fatalf("large XS batch region = %q, want LARGE", got)
	}
	if got := ProductionRegionForBatch("AUTO", 27); got != "SMALL" {
		t.Fatalf("small AUTO batch region = %q, want SMALL", got)
	}
	if got := ProductionRegionForBatch("SPECIAL", 15); got != "SPECIAL" {
		t.Fatalf("special batch region = %q, want SPECIAL", got)
	}
}
