package admission

import (
	"encoding/json"
	"io/fs"
	"os"
	"strconv"
	"testing"
)

func TestMetadataPatternSyntaxMatchesPython(t *testing.T) {
	checkMetadataPatterns(t, "testdata/metadata-regex-verdicts.json", 130)
}

func TestMetadataPatternLiteralSyntaxRegressions(t *testing.T) {
	checkMetadataPatterns(t, "testdata/cpython-pattern-verdicts.json", 347)
}

func checkMetadataPatterns(t *testing.T, file string, count int) {
	t.Helper()
	raw, err := fs.ReadFile(os.DirFS("."), file)
	if err != nil {
		t.Fatal(err)
	}
	var recorded struct {
		Cases []struct {
			Pattern string `json:"pattern"`
			Valid   bool   `json:"valid"`
		} `json:"cases"`
	}
	if err = json.Unmarshal(raw, &recorded); err != nil {
		t.Fatal(err)
	}
	if len(recorded.Cases) != count {
		t.Fatal("metadata syntax inventory changed")
	}
	for index, c := range recorded.Cases {
		t.Run(strconv.Itoa(index), func(t *testing.T) {
			if got := pythonPatternValid(c.Pattern); got != c.Valid {
				t.Fatalf("syntax=%v reference=%v pattern=%q", got, c.Valid, c.Pattern)
			}
		})
	}
}
