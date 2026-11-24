package realization

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

//nolint:ireturn // Tests use the exact native fragment owner.
func selectionTestValue(t *testing.T, input any) admission.Fragment {
	t.Helper()
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		t.Fatal(err)
	}
	return fragment
}
func TestSelectionAdmitsExactAndFiniteCandidatesWithoutDelivery(t *testing.T) {
	requirement := exactRequirement("provision.node.server", "nodes.server.os", "os-family", "author-declared", "#/nodes/server/os")
	requirement.ValueDomain = selectionTestValue(t, map[string]any{"kind": "enum", "values": []any{"linux", "windows"}})
	posture := "constrained"
	requirement.Posture = &posture
	expected := selectionTestValue(t, "linux")
	for _, test := range []struct {
		actual string
		want   bool
	}{{"windows", true}, {"other", false}} {
		admitted, err := SelectionAdmits(requirement, expected, selectionTestValue(t, test.actual))
		if err != nil || admitted != test.want {
			t.Fatalf("candidate %s admitted=%v err=%v", test.actual, admitted, err)
		}
	}
	if _, err := SelectionAdmits(requirement, replacedValue{}, expected); err == nil {
		t.Fatal("foreign expected value accepted")
	}
}
func TestSelectionAdmitsChecksCandidateDisclosureShape(t *testing.T) {
	requirement := exactRequirement("provision.node.server", "nodes.server.runtime.environment", "runtime-environment", "author-declared", "#/nodes/server/runtime/environment")
	expected := selectionTestValue(t, []any{map[string]any{"name": "TOKEN", "value": "fixture", "value_classification": "secret_fixture"}})
	admitted, err := SelectionAdmits(requirement, expected, expected)
	if err != nil || admitted {
		t.Fatalf("backend raw fixture disclosure admitted: %v %v", admitted, err)
	}
}

func TestSelectionAdmitsUnchangedGeneratedArtifactEnvironmentSource(t *testing.T) {
	compiled := compileRealizationFixture(t, `name: artifact-environment
nodes:
 host:
  type: compute
  runtime:
   environment:
   - {name: MODE, value_classification: plain, provenance: runtime, value_from: {generated_artifact: generated_artifacts.token, output: value}}
generated_artifacts:
 token:
  generator: random_value
  lifecycle: reuse_valid
  provenance: test
  regeneration_scope: once
  random_value: {alphabet: hex_lower, length: 32}
  outputs: [{name: value, path: token, sensitivity: public}]
`)
	requirement := requireTestRequirement(t, Resolution{Requirements: compiled.Requirements}, "runtime-environment")
	input := selectionTestValue(t, []any{map[string]any{"name": "MODE", "value": "", "value_classification": "plain", "provenance": "runtime", "source": "", "description": "", "value_from": map[string]any{"generated_artifact": "generated_artifacts.token", "output": "value"}}})
	admitted, err := SelectionAdmits(requirement, input, input)
	requireNoError(t, err)
	if !admitted {
		before, err := projectEvaluationConcern(requirement, input.Document(), false)
		requireNoError(t, err)
		t.Fatalf("unchanged generated artifact source refused; projected=%v constraint=%v", before, requirement.Constraint.Document())
	}
}

func TestDerivedConcernSelectionAndEvaluationUsePublishedPayloadPaths(t *testing.T) {
	for _, test := range []struct{ kind, field string }{
		{"domain-topology", "domain_topology"}, {"generated-artifact", "spec"}, {"persistent-volume", "spec"},
		{"service-content-materialization", "service_materialization"}, {"service-search-index-schema-materialization", "service_materialization"},
	} {
		t.Run(test.kind, func(t *testing.T) {
			requirement := exactRequirement("provision.node.server", "derived", test.kind, "author-declared", "#/nodes/server")
			before := selectionTestValue(t, map[string]any{"name": "original"})
			admitted, err := SelectionAdmits(requirement, before, before)
			requireNoError(t, err)
			if !admitted {
				t.Fatal("unchanged processor-derived concern refused")
			}
			result, err := Evaluate([]Requirement{requirement}, evaluationTestPlan(t, "create", map[string]any{test.field: before.Document()}), evaluationTestSnapshot(t, map[string]any{test.field: map[string]any{"name": "changed"}}), EvaluationOptions{})
			requireNoError(t, err)
			if len(result.Diagnostics) != 1 || len(result.Provenance) != 0 {
				t.Fatal("changed processor-derived concern escaped the exact realization gate")
			}
		})
	}
}
