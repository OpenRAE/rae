package authoring

import (
	"maps"
	"testing"
)

func TestMigrationSnapshotCopiesDefaultsAndTreatsLocatorsAsInertData(t *testing.T) {
	term := map[string]any{"concept_id": "term"}
	input := map[string]any{"scheme_id": "scheme", "authority": "owner", "revision": "1", "source_locator": "https://example.invalid/inert", "source_digest": "sha256:fixture", "concepts": []any{term}}
	normalized, snapshot, err := migrationSnapshot(input)
	if err != nil || len(snapshot.Concepts) != 1 || snapshot.Concepts[0].Status != "current" || normalized == nil {
		t.Fatalf("snapshot wire normalization changed: %+v %v", snapshot, err)
	}
	if _, present := term["status"]; present {
		t.Fatal("snapshot normalization changed its supplied source")
	}
	for _, field := range []string{"scheme_id", "concepts"} {
		changed := maps.Clone(input)
		changed[field] = true
		if _, _, err := migrationSnapshot(changed); err == nil {
			t.Fatalf("invalid snapshot %s accepted", field)
		}
	}
	for _, concept := range []any{true, map[string]any{"concept_id": true}, map[string]any{"concept_id": "term", "status": func() {}}, map[string]any{"concept_id": "term", "unknown": true}} {
		changed := maps.Clone(input)
		changed["concepts"] = []any{concept}
		if _, _, err := migrationSnapshot(changed); err == nil {
			t.Fatal("invalid concept snapshot term accepted")
		}
	}
}

func TestMigrationBindingContextsRefuseMalformedOrUnadmittedEvidence(t *testing.T) {
	p := operationParser(t)
	for _, input := range []map[string]any{
		{"bindings": func() {}}, {"bindings": map[string]any{}}, {"existing": true}, {"snapshots": true},
		{"existing": []any{nil}}, {"existing": []any{map[string]any{}}}, {"snapshots": []any{true}},
	} {
		if _, err := p.migrationBindingContext(input); err == nil {
			t.Fatal("unadmitted migration evidence accepted")
		}
	}
}
