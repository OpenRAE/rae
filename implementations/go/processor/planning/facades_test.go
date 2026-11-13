package planning_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func TestAdmittedManifestFacadeAndMixedControlKeepNativeModel(t *testing.T) {
	compiled := compile(t, basicScenario)
	owner, err := admission.New()
	requireNoError(t, err)
	manifestValue, err := owner.Validate("backend-manifest-v2", requireJSON(t, manifest(t)), ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}, nil)
	requireNoError(t, err)
	result, err := planning.Plan(compiled, manifestValue, planning.Options{})
	requireNoError(t, err)
	if !result.Plan.Valid() || result.Plan.Model().View().Name != "example" || result.Plan.ObservationOwner() != "provisioning" {
		t.Fatal("admitted manifest facade changed model or boundary")
	}
	mixed, err := planning.NewMixedControlAdmission(compiled.Model())
	requireNoError(t, err)
	if mixed.Model().View().Name != "example" {
		t.Fatal("mixed admission lost the native model")
	}
	if _, err := planning.NewMixedControlAdmission(nil); err == nil {
		t.Fatal("mixed admission accepted a missing model")
	}
	if _, err := planning.Plan(compiled, validation.Value{}, planning.Options{}); err == nil {
		t.Fatal("wrong manifest carrier accepted")
	}
}
