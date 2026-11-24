package trial

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestTrialControlsReadDeclaredNestedSupervision(t *testing.T) {
	var backend binding.BackendManifestV2
	if err := json.Unmarshal([]byte(`{"capabilities":{"cleanup":{"supported_action_kinds":[],"supported_verification_methods":[],"supports_reusable_state":false,"supports_residual_state_disclosure":false},"operation_supervision":{"name":"installed","guarantees":["cancellation","cessation-evidence","effect-observation"]}}}`), &backend); err != nil {
		t.Fatal(err)
	}
	var cleanup cleanupTemplate
	if err := json.Unmarshal([]byte(`{"clean_state":{"mode":"unspecified"},"retry_policy":{"max_attempts":2,"after_effect_policy":"disallow"}}`), &cleanup); err != nil {
		t.Fatal(err)
	}
	if err := admitTrialControls(backend, executionControls{OnTimeout: "cancel"}, cleanup); err != nil {
		t.Fatal(err)
	}
}
