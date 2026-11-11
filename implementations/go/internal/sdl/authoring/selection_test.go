package authoring

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestRecordedSelectionRequiresCompleteValidOutcomes(t *testing.T) {
	parser := operationParser(t)
	owner := parser
	document := operationDocument(t, parser, `name: family
description: ${choice}
variables:
  choice: {type: string, default: first, allowed_values: [first, second]}
variation_points:
  pick:
    kind: parameter
    target: {kind: variable, variable: choice}
    domain: {kind: enum, values: [first, second]}
`)
	family, err := owner.AdmitFamily(document)
	if err != nil {
		t.Fatal(err)
	}
	before := family.JSON()
	selected, err := owner.Select(family, []byte(`{"pick":{"kind":"literal","value":"second"}}`), nil)
	if err != nil || selected == nil || !selected.Instantiated() {
		t.Fatalf("selection = %v, %v; want admitted concrete document", selected, err)
	}
	if !bytes.Contains(selected.JSON(), []byte(`"description":"second"`)) || !bytes.Equal(before, family.JSON()) {
		t.Fatal("selection did not preserve the family and apply the recorded value")
	}
	for _, outcomes := range []string{`{}`, `{"pick":{"kind":"literal","value":"outside"}}`, `{"pick":{"kind":"member","member_id":"first"}}`, `{"pick":{"kind":"literal","value":"second"},"extra":{"kind":"literal","value":true}}`, `{"pick":{"kind":"literal","value":"first","extra":true}}`} {
		if result, err := owner.Select(family, []byte(outcomes), nil); result != nil || err == nil {
			t.Fatalf("outcomes %s were admitted", outcomes)
		}
	}
}

func TestSelectionTrialInputBound(t *testing.T) {
	limits := source.DefaultLimits()
	limits.MaxInputBytes = 512
	parser, err := New(limits)
	if err != nil {
		t.Fatal(err)
	}
	hash := "sha256:" + strings.Repeat("0", 64)
	raw, err := json.Marshal(map[string]any{
		"scenario_family_id": "family", "scenario_family_digest": hash,
		"plan_id": "plan", "plan_digest": hash, "plan_entry_id": "entry",
		"entry_digest": hash, "run_id": "run", "coordinate": map[string]any{},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = parser.selectionTrial(raw); err != nil {
		t.Fatalf("valid trial: %v", err)
	}
	padded := append(bytes.Clone(raw), bytes.Repeat([]byte{' '}, 512)...)
	if _, err = parser.selectionTrial(padded); err == nil {
		t.Fatal("oversized trial was admitted")
	}
}
