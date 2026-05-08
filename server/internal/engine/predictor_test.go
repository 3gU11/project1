package engine

import "testing"

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
			modelFamily: "小机G",
			want:        "小机G",
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
