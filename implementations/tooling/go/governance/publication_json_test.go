package governance

import (
	"testing"
)

func TestPublicationJSONReference(t *testing.T) {
	for i, tc := range readReference[[]struct {
		Source, Canonical string
		Error             bool
	}](t, "publication-json-reference") {
		value, err := decodeJSON([]byte(tc.Source), 0, false)
		if err != nil {
			t.Fatalf("case %d source: %v", i, err)
		}
		data, err := publicationJSON(value)
		if (err != nil) != tc.Error {
			t.Fatalf("case %d publication JSON error=%v want refusal=%t", i, err, tc.Error)
		}
		if tc.Error {
			continue
		}
		if string(data) != tc.Canonical {
			t.Errorf("case %d canonical=%q want=%q", i, data, tc.Canonical)
		}
	}
}

func TestPublicationJSONDeepContainers(t *testing.T) {
	for _, kind := range []string{"array", "object", "mixed"} {
		source := jsonDepthSource(kind, governanceJSONDepth-1)
		value, err := decodeJSON(source, 0, false)
		if err != nil {
			t.Fatal(err)
		}
		canonical, err := publicationJSON(value)
		if err != nil || string(canonical) != string(source) {
			t.Fatalf("kind=%s deep-container identity changed: error=%v", kind, err)
		}
	}
}
