package validation

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestSDLPatternsPreservePublishedValidation(t *testing.T) {
	owner, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, c := range []struct {
		name, definition, data string
		published, constructed bool
	}{
		{"strict-end", "ArtifactIdentity", `{"artifact_id":"a\n","version":"1","digest":"sha256:` + strings.Repeat("a", 64) + `","media_type":"x"}`, true, false},
		{"unicode-space", "MixedControlPermittedTransition", `{"transition_kind":"proposal","from_state_ref":"a","to_state_ref":"b","valid_from_order":0,"valid_until_order":1,"evidence_refs":["\u001f"]}`, false, true},
	} {
		t.Run(c.name, func(t *testing.T) {
			limits := ingress.Limits{MaxBytes: len(c.data)}
			pointer := "#/$defs/" + c.definition
			for _, id := range []string{"sdl-authoring-input-v1", "materialized-scenario-v1"} {
				_, publishedErr := owner.DecodeObjectFragment(id, pointer, []byte(c.data), limits)
				constructionErr := owner.CheckSDLConstruction(id, pointer, []byte(c.data), limits, func(SchemaInstance) error { return nil })
				if (publishedErr == nil) != c.published || (constructionErr == nil) != c.constructed {
					t.Fatalf("%s: published=%v constructed=%v", id, publishedErr, constructionErr)
				}
			}
		})
	}
}

func TestSDLPatternFactsRejectDrift(t *testing.T) {
	for _, fact := range []sdlFieldPattern{
		{Pattern: "^b$"},
		{Pattern: "^a$", Path: []string{"properties"}},
		{Pattern: "^a$", Path: make([]string, 17)},
		{Pattern: "^a$", SchemaSHA256: strings.Repeat("0", 64)},
		{Pattern: "^a$", MinLength: new(-1)},
	} {
		if _, err := applySDLPatternFacts(nil, map[string]any{"pattern": "^a$"}, []sdlFieldPattern{fact}); err == nil {
			t.Fatalf("unverified field pattern accepted: %+v", fact)
		}
	}
	if _, _, err := rewriteSDLPattern(nil, map[string]any{"pattern": "a"}, sdlFieldPattern{Pattern: "a"}, 32); err == nil {
		t.Fatal("unbounded reference traversal")
	}
	if _, err := rustSDLPattern(`[\S]`); err == nil {
		t.Fatal("unsupported negated character class accepted")
	}
}

func TestSDLPatternRecordRejectsInvalidShape(t *testing.T) {
	for _, raw := range []string{`{}`, `{"unknown":true}`, string(sdlPatternJSON) + `{}`} {
		if _, err := decodeSDLPatterns([]byte(raw)); err == nil {
			t.Fatal("invalid pattern record accepted")
		}
	}
	var record map[string]any
	if err := json.Unmarshal(sdlPatternJSON, &record); err != nil {
		t.Fatal(err)
	}
	contracts, ok := record["contracts"].(map[string]any)
	if !ok {
		t.Fatal("missing record contracts")
	}
	delete(contracts, "materialized-scenario-v1")
	raw, err := json.Marshal(record)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := decodeSDLPatterns(raw); err == nil {
		t.Fatal("missing native contract accepted")
	}
}
