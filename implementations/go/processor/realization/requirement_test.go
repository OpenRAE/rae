package realization

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestRequirementAdmissionChecksNativeFragmentsAndAuthorityInvariants(t *testing.T) {
	result := compileRealizationFixture(t, "name: example\nnodes:\n  server: {type: compute, os: linux}\n")
	for _, requirement := range result.Requirements {
		fragment, err := AdmitRequirement(requirement)
		if err != nil {
			t.Fatalf("kind=%s: %v", requirement.Kind, err)
		}
		if admission.CheckFragment(fragment, admission.CompiledRealizationRequirement) != nil {
			t.Fatal("incorrect requirement owner")
		}
	}
	input := exactRequirement("provision.node.server", "nodes.server.os", "os-family", "author-declared", "#/nodes/server/os")
	input.Delegated = true
	if _, err := AdmitRequirement(input); err == nil {
		t.Fatal("conflicting delegated posture accepted")
	}
	input.Delegated = false
	input.ValueDomain = replacedValue{}
	if _, err := AdmitRequirement(input); err == nil {
		t.Fatal("foreign bound accepted")
	}
}
