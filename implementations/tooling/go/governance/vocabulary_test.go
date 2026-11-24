package governance

import (
	"encoding/json"
	"path/filepath"
	"testing"
)

func TestVocabularyCurrentRepository(t *testing.T) {
	c := new(checker)
	for _, tool := range []string{attackVocabularyCheck, atlasVocabularyCheck, nistVocabularyCheck, autonomousVocabularyCheck} {
		t.Run(tool, func(t *testing.T) {
			report, err := c.evaluate(t.Context(), Request{Tool: tool, Root: filepath.Join("..", "..", "..", "..")})
			if err != nil {
				t.Fatal(err)
			}
			if report.ExitCode != 0 || len(report.Findings) != 0 {
				t.Fatalf("current vocabulary findings=%v, exit=%d", report.Findings, report.ExitCode)
			}
		})
	}
}

func TestVocabularyPositionReference(t *testing.T) {
	for _, tc := range readReference[[]struct {
		Name, Source string
		Want         *string
	}](t, "vocabulary-position-reference") {
		t.Run(tc.Name, func(t *testing.T) {
			value, err := decodeJSON([]byte(tc.Source), 0, false)
			if err != nil {
				t.Fatal(err)
			}
			normalized := vocabularyPosition(value)
			if tc.Want == nil {
				if normalized != nil {
					t.Fatal("invalid integer representation was accepted")
				}
				return
			}
			number, valid := normalized.(json.Number)
			if !valid || string(number) != *tc.Want {
				t.Fatal("integer normalization differs from the reference")
			}
		})
	}
}
