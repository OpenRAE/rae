package realization

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func TestProcessSupportNeedsTheExactConfiguredDomain(t *testing.T) {
	requirement := processSupportRequirement(t)
	maximum := json.Number("100")
	matching := processCapability{Resource: "open_file_descriptors", Scopes: []string{"process"}, Minimum: "10", Maximum: &maximum}
	changed := matching
	changedMaximum := json.Number("200")
	changed.Maximum = &changedMaximum
	tests := []struct {
		name     string
		declared []processCapability
		envelope string
		observed bool
		code     string
	}{
		{"matching", []processCapability{matching}, "matching", true, ""},
		{"declaration-cannot-borrow-larger-apparatus", []processCapability{changed}, "matching", true, "realization.process-resource-limit-domain-mismatch"},
		{"apparatus-cannot-borrow-declaration-scope", []processCapability{matching}, "subtree", true, "realization.process-resource-limit-domain-mismatch"},
		{"support-needs-effective-observation", []processCapability{matching}, "matching", false, "realization.unsupported-process-resource-limits"},
		{"missing-apparatus", []processCapability{matching}, "", true, "realization.process-resource-limit-domain-mismatch"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			declaration := supportDeclaration{exact: []string{"declared-capability-match"}, processLimits: test.declared, observations: map[string]observationCapability{}}
			if test.observed {
				declaration.observations[observationKind(requirement.Kind)] = observationCapability{requirement.ObservationScope, requirement.ObservationStrength}
			}
			var envelope *binding.RealizationEnvelopeV1
			if test.envelope != "" {
				envelope = processSupportEnvelope(t, test.envelope)
			}
			finding, err := processSupportDiagnostic(requirement, []supportDeclaration{declaration}, envelope)
			if err != nil {
				t.Fatal(err)
			}
			assertProcessSupportFinding(t, finding, test.code)
		})
	}
}
func assertProcessSupportFinding(t *testing.T, finding *diagnostic.Diagnostic, code string) {
	t.Helper()
	if code == "" {
		if finding != nil {
			t.Fatalf("unexpected process support refusal: %+v", finding)
		}
	} else if finding == nil || finding.Code != code {
		t.Fatalf("finding=%+v want=%s", finding, code)
	}
}

func processSupportRequirement(t *testing.T) Requirement {
	t.Helper()
	compiled := compileRealizationFixture(t, `name: process-support
nodes:
  host:
    type: compute
    runtime:
      processes: [{name: worker}]
      operational_policy:
        resource_limits:
          process_limits:
            - resource: open_file_descriptors
              subject: {name: worker}
              scope: process
              soft: 32
              hard: 64
`)
	for _, requirement := range compiled.Requirements {
		if requirement.Kind == termProcessResourceLimits {
			return requirement
		}
	}
	t.Fatal("missing process requirement")
	return Requirement{}
}
func processSupportEnvelope(t *testing.T, name string) *binding.RealizationEnvelopeV1 {
	t.Helper()
	raw, err := os.ReadFile("testdata/process-support-envelopes.json")
	if err != nil {
		t.Fatal(err)
	}
	var records map[string]json.RawMessage
	if checkErr := json.Unmarshal(raw, &records); checkErr != nil {
		t.Fatal(checkErr)
	}
	raw = records[name]
	if len(raw) == 0 {
		t.Fatal("missing process envelope", name)
	}
	owner, err := realizationOwner()
	if err != nil {
		t.Fatal(err)
	}
	if checkErr := owner.CheckPortable("realization-envelope-v1", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}); checkErr != nil {
		t.Fatal(checkErr)
	}
	var envelope binding.RealizationEnvelopeV1
	if checkErr := json.Unmarshal(raw, &envelope); checkErr != nil {
		t.Fatal(checkErr)
	}
	return &envelope
}
