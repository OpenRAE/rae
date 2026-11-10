package authoring

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestRegressionSiblingEnumDefaultSurvivesReference(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	payload := map[string]any{"name": "defaults", "assertions": map[string]any{"a": map[string]any{"proposition": "p", "role": "postcondition"}}}
	queries := newScopeQueries(parser, authoringContract, payload)
	if _, err = queries.resolve("/assertions/a/polarity"); err != nil {
		t.Fatalf("sibling enum default did not resolve: %v", err)
	}
	polarity := object(object(object(queries.value)["assertions"])["a"])["polarity"]
	if polarity != "positive" {
		t.Fatalf("polarity = %v, want positive", polarity)
	}
	if _, present := object(object(payload["assertions"])["a"])["polarity"]; present {
		t.Fatal("default query mutated the input")
	}
}

func TestRegressionMixedControlFindingUsesTypedTransitionPointer(t *testing.T) {
	raw, err := readCompressedFixture("testdata/migrations.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []struct {
			Name   string `json:"name"`
			Source string `json:"source"`
		} `json:"cases"`
	}
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, row := range fixture.Cases {
		if row.Name != "mixed-issue-1678-handoff-pointer" {
			continue
		}
		document, err := parser.Decode(Request{Source: []byte(row.Source)})
		if err != nil {
			t.Fatal(err)
		}
		_, _, err = parser.Validate(document)
		failure, ok := errors.AsType[diagnostic.Error](err)
		if !ok {
			t.Fatalf("expected semantic refusal: %v", err)
		}
		findings := failure.Diagnostics()
		if len(findings) != 1 || findings[0].Pointer != "/behavior_specifications/controlled-red/mixed_control/transitions/take" {
			t.Fatalf("transition finding has the wrong typed location: %+v", findings)
		}
		return
	}
	t.Fatal("missing independent transition input")
}

func TestRegressionPolicyRewriteKeepsRootScope(t *testing.T) {
	value := map[string]any{
		"nodes":              map[string]any{"web": map[string]any{}},
		"augmentation_scope": map[string]any{"default": "closed", "scopes": []any{map[string]any{"scope": "/nodes/web", "permission": "open"}}},
	}
	symbols := importSymbols{"nodes": map[string]string{"web": "front"}}
	rewritten, err := rewriteAugmentation(value, symbols, "")
	if err != nil {
		t.Fatal(err)
	}
	rules := array(rewritten["scopes"])
	if rewritten["default"] != "closed" || len(rules) != 1 || object(rules[0])["scope"] != "/nodes/front" || len(array(object(rules[0])["namespace"])) != 0 {
		t.Fatalf("root policy changed: %v", rewritten)
	}
}
