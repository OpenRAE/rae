package trial

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestPolicyGraphsRefuseCyclesDuplicatePointsAndAmbiguousRoots(t *testing.T) {
	spec := experimentSpec{}
	spec.RunPlan.Policies = map[string]selectionPolicy{
		"a":       {ID: "a", Kind: policyFixed, Point: "point", Outcome: selectionOutcome{Kind: "value", Value: json.RawMessage(`1`)}},
		"b":       {ID: "b", Kind: policyFixed, Point: "other", Outcome: selectionOutcome{Kind: "value", Value: json.RawMessage(`2`)}},
		"product": {ID: "product", Kind: "product", Refs: []string{"b", "a"}, Bound: 1},
	}
	rows, err := staticRows(Request{Limits: DefaultLimits()}, spec, "product", map[string]bool{})
	if err != nil || len(rows) != 1 || len(rows[0]) != 2 || rows[0][0].Point != "other" {
		t.Fatal("fixed product lost deterministic ordering", err)
	}
	for _, name := range []string{"cycle", "missing", "unsupported", "duplicate", "cardinality"} {
		t.Run(name, func(t *testing.T) { checkPolicyGraphRefusal(t, spec, name) })
	}
	spec.RunPlan.Policies = map[string]selectionPolicy{"a": {Kind: "enumerate"}, "b": {Kind: "enumerate"}}
	if _, _, err := selectionPolicyRoots(spec); err == nil {
		t.Fatal("ambiguous roots admitted")
	}
	if err := selectionPointsCovered(nil, map[string]json.RawMessage{"point": nil}); err == nil {
		t.Fatal("missing point admitted")
	}
	if err := selectionPointsCovered([]selectionRecord{{Point: "foreign"}}, map[string]json.RawMessage{"point": nil}); err == nil {
		t.Fatal("foreign point admitted")
	}
}
func checkPolicyGraphRefusal(t *testing.T, base experimentSpec, name string) {
	t.Helper()
	raw, err := json.Marshal(base)
	if err != nil {
		t.Fatal(err)
	}
	var spec experimentSpec
	if json.Unmarshal(raw, &spec) != nil {
		t.Fatal("policy fixture")
	}
	p := spec.RunPlan.Policies["product"]
	switch name {
	case "cycle":
		p.Refs = []string{"product"}
	case "missing":
		p.Refs = []string{"foreign"}
	case "unsupported":
		spec.RunPlan.Policies["a"] = selectionPolicy{ID: "a", Kind: "sample"}
	case "duplicate":
		a := spec.RunPlan.Policies["a"]
		a.Point = "other"
		spec.RunPlan.Policies["a"] = a
	case "cardinality":
		p.Bound = 2
	}
	spec.RunPlan.Policies["product"] = p
	if _, err := staticRows(Request{Limits: DefaultLimits()}, spec, "product", map[string]bool{}); err == nil {
		t.Fatal("invalid policy graph admitted")
	}
}
func TestSamplingRejectsUnresolvedControlsProfileChangesAndRepeatedAddresses(t *testing.T) {
	var request Request
	var spec experimentSpec
	var policy selectionPolicy
	for _, ref := range referenceCompilations(t) {
		candidate := compilerRequest(t, ref.Request)
		input, err := prepareInputs(candidate)
		if err != nil {
			t.Fatal(err)
		}
		for _, p := range input.spec.RunPlan.Policies {
			if p.Kind == "sample" {
				request, spec, policy = candidate, input.spec, p
			}
		}
	}
	if policy.ID == "" {
		t.Fatal("sampling fixture missing")
	}
	for _, name := range []string{"missing", "malformed", "not-executable", "profile", "version", "governed", "seed"} {
		t.Run(name, func(t *testing.T) { checkSamplingControlRefusal(t, spec, policy, name) })
	}
	if _, err := sampleRows(request, spec, policy, []coordinate{{}, {}}); err == nil {
		t.Fatal("repeated sampling address admitted")
	}
	raw := json.RawMessage(`{"strata":{"condition":{"stratum_id":"condition","output_count":2,"outcome_ref":"one"}},"outcomes":{"one":{"kind":"value","value":1}}}`)
	var stratified selectionPolicy
	if json.Unmarshal(raw, &stratified) != nil {
		t.Fatal("strata fixture")
	}
	condition := "condition"
	if _, err := stratifiedRows(stratified, []coordinate{{}}); err == nil {
		t.Fatal("uncovered stratum admitted")
	}
	if _, err := stratifiedRows(stratified, []coordinate{{ConditionID: &condition}}); err == nil {
		t.Fatal("stratum count mismatch admitted")
	}
}
func checkSamplingControlRefusal(t *testing.T, base experimentSpec, policy selectionPolicy, name string) {
	t.Helper()
	spec := base
	var control map[string]any
	if json.Unmarshal(base.RunPlan.Controls[0], &control) != nil {
		t.Fatal("control fixture")
	}
	switch name {
	case "missing":
		policy.Control = "foreign"
	case "malformed":
		spec.RunPlan.Controls = []json.RawMessage{json.RawMessage(`{`)}
	default:
		mutateSamplingControl(t, control, name)
		raw, err := json.Marshal(control)
		if err != nil {
			t.Fatal(err)
		}
		spec.RunPlan.Controls = []json.RawMessage{raw}
	}
	if _, _, err := sampleKey(spec, policy); err == nil {
		t.Fatal("unproven sampling control admitted")
	}
}
func mutateSamplingControl(t *testing.T, control map[string]any, name string) {
	t.Helper()
	binding, ok := control["executable_binding"].(map[string]any)
	if !ok {
		t.Fatal("missing executable control")
	}
	profile, ok := binding["profile_ref"].(map[string]any)
	if !ok {
		t.Fatal("missing profile")
	}
	entropy, ok := binding["root_entropy"].(map[string]any)
	if !ok {
		t.Fatal("missing entropy")
	}
	switch name {
	case "not-executable":
		delete(control, "executable_binding")
	case "profile":
		profile["ref_id"] = "foreign"
	case "version":
		profile["ref_version"] = "foreign"
	case "governed":
		entropy["kind"] = "governed"
	case "seed":
		entropy["encoding"] = "foreign"
	}
}
func TestCompilerOwnerFailuresPreserveCancellationAndSanitizeForeignDetails(t *testing.T) {
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if _, err := installedTrialOwner(ctx, func() (bool, error) { t.Fatal("cancelled owner dispatched"); return false, nil }); !errors.Is(err, context.Canceled) {
		t.Fatal(err)
	}
	for _, source := range []error{fault.New(fault.Authorization, "denied", nil), errors.New("private-owner-detail")} {
		_, err := installedTrialOwner(t.Context(), func() (bool, error) { return false, source })
		if err == nil || strings.Contains(err.Error(), "private") {
			t.Fatal("owner detail escaped", err)
		}
	}
	ctx, cancel = context.WithCancel(t.Context())
	if _, err := installedTrialOwner(ctx, func() (bool, error) { cancel(); return true, nil }); !errors.Is(err, context.Canceled) {
		t.Fatal("late result overrode cancellation", err)
	}
	for _, code := range []string{"trial-domain-empty", "trial-domain-not-finite", "trial-domain-kind-unsupported", "unrelated"} {
		result := domainRefusal(fault.New(fault.InvalidInput, code, nil))
		if result == nil {
			t.Fatal("domain error lost")
		}
	}
	foreign := errors.New("foreign")
	if !errors.Is(domainRefusal(foreign), foreign) {
		t.Fatal("unowned domain error changed")
	}
}
