package authoring

import (
	"encoding/json"
	"testing"
)

func TestTrialTargetResolvesOneDetectionEngineThroughItsCanonicalIdentity(t *testing.T) {
	engine := declaration{kind: termNetworkDetectionEngines, node: "gateway", tokens: []string{"nodes", "gateway", "runtime", "network_detection_engines", "0", "rule_sources"}}
	model := semanticModel{root: map[string]any{"nodes": map[string]any{"gateway": map[string]any{"runtime": map[string]any{"network_detection_engines": []any{map[string]any{"network_detection_engine_id": "detector"}}}}}}, index: &declarationIndex{aliases: map[string]map[string]declaration{"alias": {"engine": engine}}}}
	point := semanticVariation{}
	point.Target.Owner = "alias"
	point.Target.Slot = slotDetectionRuleSources
	target, err := model.trialTarget(point)
	if err != nil || target != "nodes.gateway.runtime.network_detection_engines.detector.rule_sources" {
		t.Fatal("trial target did not resolve canonical detection-engine identity", target, err)
	}
	model.index.aliases["alias"]["duplicate"] = engine
	if _, err := model.trialTarget(point); err == nil {
		t.Fatal("ambiguous engine alias admitted")
	}
	delete(model.index.aliases["alias"], "duplicate")
	model.root = map[string]any{}
	if _, err := model.trialTarget(point); err == nil {
		t.Fatal("unresolved engine declaration admitted")
	}
	model.index.aliases["alias"] = map[string]declaration{}
	if _, err := model.trialTarget(point); err == nil {
		t.Fatal("missing engine alias admitted")
	}
	point.Target.Slot = "services.unknown"
	if _, err := model.trialTarget(point); err == nil {
		t.Fatal("foreign slot owner admitted")
	}
}
func TestTrialScalarIdentityPreservesNullIntegerAndNumberKinds(t *testing.T) {
	keys := map[string]bool{}
	for _, value := range []any{nil, json.Number("1"), json.Number("1.0"), true, "1"} {
		key, err := trialScalarKey(value)
		if err != nil {
			t.Fatal(err)
		}
		if keys[key] {
			t.Fatal("different scalar kinds collapsed", value)
		}
		keys[key] = true
	}
	if _, err := trialScalarKey(make(chan int)); err == nil {
		t.Fatal("non-JSON scalar admitted")
	}
	if _, err := integerTrialOutcomes(semanticVariationDomain{Lower: 2, Upper: 1, Numeric: integerType}, 4); err == nil {
		t.Fatal("empty integer interval expanded")
	}
	parser := &Parser{}
	if _, err := parser.FiniteVariationOutcomes(nil, "point", 1); err == nil {
		t.Fatal("unowned domain admitted")
	}
	if err := parser.ValidateTreatment(nil, []byte(`{}`)); err == nil {
		t.Fatal("unowned treatment admitted")
	}
}
