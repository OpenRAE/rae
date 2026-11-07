package governance

import (
	"encoding/json"
	"testing"
)

type extractionReference struct {
	Name, Label, ErrorType, Error string
	Data                          []byte
	Rows                          json.RawMessage
}

func TestVocabularyExtractionReference(t *testing.T) {
	for _, tc := range readReference[[]extractionReference](t, "vocabulary-extraction-reference") {
		t.Run(tc.Name, func(t *testing.T) { checkVocabularyExtraction(t, tc) })
	}
}
func extractionRows(tc extractionReference) ([]any, error) {
	var rows []any
	var err error
	switch tc.Label {
	case "ATT&CK", "ATLAS":
		rows, err = extractTacticSnapshot(tc.Label, tc.Data)
	case nistVocabulary:
		rows, err = extractNISTCategories(tc.Data)
	case "ActivityStreams":
		var names []string
		names, err = extractActivityNames(tc.Data)
		rows = stringsAsValues(names)
	}
	return rows, err
}
func checkVocabularyExtraction(t *testing.T, tc extractionReference) {
	t.Helper()
	rows, err := extractionRows(tc)

	if tc.ErrorType != "" {
		if err == nil {
			t.Fatalf("reference %s became extracted rows %+v", tc.ErrorType, rows)
		}
		if tc.ErrorType == "InvalidInputError" && err.Error() != tc.Error {
			t.Errorf("error=%v want=%q", err, tc.Error)
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	expected, err := decodeJSON(tc.Rows, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if !publicationEqual(rows, expected) {
		t.Fatalf("rows=%s want=%s", pythonRepr(rows), pythonRepr(expected))
	}
}
