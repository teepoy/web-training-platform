package resolve

import "testing"

func TestZipIndexForDefectUsesOneBasedDefectIDs(t *testing.T) {
	tests := map[int]int{
		1:     0,
		500:   0,
		501:   1,
		75015: 150,
	}
	for defectID, want := range tests {
		if got := zipIndexForDefect(defectID); got != want {
			t.Fatalf("zipIndexForDefect(%d) = %d, want %d", defectID, got, want)
		}
	}
}
