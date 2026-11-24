package realization

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

// These isolated Python evaluator tests bypass bind_operating_system_observations.
// Their recorded helper outputs remain intact, but are not native public-boundary
// expectations when operating_system_observation_binding_valid refuses the context.
func helperOnlyOSContextRefused(t *testing.T, name string, plan binding.ProvisioningPlanV1, snapshot binding.RuntimeSnapshotV1, options EvaluationOptions) bool {
	t.Helper()
	var declared evaluatedPlan
	var returned evaluatedSnapshot
	requireNoError(t, json.Unmarshal(requireJSON(t, plan), &declared))
	requireNoError(t, json.Unmarshal(requireJSON(t, snapshot), &returned))
	for _, observation := range returned.Observations {
		if observation.Kind != termOperatingSystem {
			continue
		}
		// Source binding requires the actual operation and independently selected
		// envelope/configuration; binding_verified alone cannot supply those inputs.
		if declared.OperationID == "" || declared.OperationID != observation.OperationID || options.Envelope == nil {
			t.Logf("%s supplies OS evidence without the current operation and selected apparatus", name)
			return true
		}
		configuration := sourceValue(options.Envelope.Configuration)
		if observation.EnvelopeDigest != sourceValue(options.Envelope.Digest) || observation.ConfigurationDigest != sourceValue(configuration.ConfigurationDigest) {
			t.Logf("%s supplies OS evidence for a different apparatus", name)
			return true
		}
	}
	return false
}

func assertHelperOnlyOSContextRefusal(t *testing.T, requirements []Requirement, result Evaluation) {
	t.Helper()
	for _, entry := range result.Provenance {
		if observationKind(entry.Kind) == termOperatingSystem {
			t.Fatal("isolated helper context gained native OS provenance")
		}
	}
	for _, requirement := range requirements {
		if observationKind(requirement.Kind) != termOperatingSystem {
			continue
		}
		if !hasOSReferenceRefusal(result, requirement) {
			t.Fatalf("source-binder-invalid helper context did not refuse %s", requirement.Kind)
		}
	}
	t.Log("helper-only output retained; native boundary refuses the source observation-binding precondition")
}

func hasOSReferenceRefusal(result Evaluation, requirement Requirement) bool {
	for _, finding := range result.Diagnostics {
		if finding.Code == "runtime.backend-contract-invalid" && finding.Address == requirement.Address && strings.Contains(finding.Message, "'"+requirement.Kind+"'") {
			return true
		}
	}
	return false
}
