package sdl_test

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

const trialFamilySource = `name: trial-family
variables:
  path: {type: string, default: /opt/a, allowed_values: [/opt/a, /opt/b]}
nodes:
  host: {type: compute}
content:
  payload: {type: file, target: host, path: '${path}'}
variation_points:
  path:
    kind: parameter
    target: {kind: variable, variable: path}
    domain: {kind: enum, values: [/opt/b, /opt/a]}
`

//nolint:ireturn // Tests consume the public native phase handle.
func trialFamily(t *testing.T) sdl.Scenario {
	t.Helper()
	family, err := sdl.Parse([]byte(trialFamilySource), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	family, err = sdl.AdmitFamily(family)
	if err != nil {
		t.Fatal(err)
	}
	return family
}

//nolint:ireturn // Tests consume the public native fragment handle.
func trialSelectionValue(t *testing.T, document any) admission.Fragment {
	t.Helper()
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	f, err := admission.AdmitFragment(owner, admission.RealizationValue, document, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	return f
}

func TestTrialSelectionUsesNativeFamilyAndRecordedOutcomes(t *testing.T) {
	t.Parallel()
	family := trialFamily(t)
	outcomes, err := sdl.VariationOutcomes(family, "path", 2)
	if err != nil {
		t.Fatal(err)
	}
	var records []any
	for _, outcome := range outcomes {
		records = append(records, outcome.Document())
	}
	raw, err := json.Marshal(records)
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `[{"kind":"literal","value":"/opt/a"},{"kind":"literal","value":"/opt/b"}]` {
		t.Fatal("canonical domain =", string(raw))
	}
	selected, err := sdl.Select(family, trialSelectionValue(t, map[string]any{"path": records[1]}), nil)
	if err != nil {
		t.Fatal(err)
	}
	model, err := sdl.ModelBytes(selected)
	if err != nil {
		t.Fatal(err)
	}
	if !selected.SemanticallyValidated() || !strings.Contains(string(model), `"path":"/opt/b"`) {
		t.Fatal("recorded selection did not produce the selected native scenario")
	}
	before, err := sdl.ModelBytes(family)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(before), "${path}") {
		t.Fatal("selected output mutated the original family")
	}
}

func TestTrialBindingTargetsUseNativeDeclarationAuthority(t *testing.T) {
	family := trialFamily(t)
	resolved, err := sdl.ResolveBindingTarget(family, "trial-family", "path", "variables.path")
	if err != nil {
		t.Fatal(err)
	}
	if resolved.CanonicalTargetID != "variables.path" || resolved.ValueType != "string" || resolved.Owner.ValidatorID != "raes-selected-scenario" {
		t.Fatal("wrong native binding authority", resolved)
	}
	for _, input := range [][3]string{{"foreign", "path", "variables.path"}, {"trial-family", "foreign", "variables.path"}, {"trial-family", "path", "nodes.host"}} {
		if _, err := sdl.ResolveBindingTarget(family, input[0], input[1], input[2]); err == nil {
			t.Fatal("accepted foreign binding target")
		}
	}
}

func TestTrialSelectionRefusesIncompleteForeignAndOutOfDomainInputs(t *testing.T) {
	t.Parallel()
	family := trialFamily(t)
	for _, input := range []any{map[string]any{}, map[string]any{"unknown": map[string]any{"kind": "literal", "value": "/opt/a"}}, map[string]any{"path": map[string]any{"kind": "literal", "value": "private-marker"}}} {
		if _, err := sdl.Select(family, trialSelectionValue(t, input), nil); err == nil {
			t.Fatal("invalid recorded selection admitted")
		}
	}
	if _, err := sdl.VariationOutcomes(family, "path", 1); err == nil {
		t.Fatal("domain exceeded its output budget")
	}
	if _, err := sdl.VariationOutcomes(family, "missing", 2); err == nil {
		t.Fatal("unknown variation point admitted")
	}
	if _, err := sdl.VariationOutcomes(replacedDescriptorScenario{family}, "path", 2); err == nil {
		t.Fatal("foreign family handle admitted")
	}
}
