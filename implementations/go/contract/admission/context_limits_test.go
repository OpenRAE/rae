package admission

import (
	"strings"
	"testing"
)

// A trusted port cannot make its result an unbounded allocation or parse job.
// These owner collection limits apply before individual document decoding.
func TestTrustedDocumentCollectionsEnforceCountAndByteBudgets(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	oversized := make([]byte, 64*1048576+1)
	resolution := controlResolution{owner: e, id: "participant-control-evaluation-v2", v2: true}
	mixed := mixedResolution{owner: e}
	flow := flowControl{owner: e}
	for name, check := range map[string]func() error{
		"experiment-count":       func() error { _, err := e.experimentDocuments("experiment-run-v1", make([][]byte, 4097)); return err },
		"experiment-bytes":       func() error { _, err := e.experimentDocuments("experiment-run-v1", [][]byte{oversized}); return err },
		"control-history-count":  func() error { _, _, err := e.controlHistoryDocuments(make([][]byte, 4097)); return err },
		"control-history-bytes":  func() error { _, _, err := e.controlHistoryDocuments([][]byte{oversized}); return err },
		"control-policies-count": func() error { _, err := e.controlPolicies(make([][]byte, 4097)); return err },
		"control-policies-bytes": func() error { _, err := e.controlPolicies([][]byte{oversized}); return err },
		"control-target-count":   func() error { return controlAvailableTargets(make([]AvailableControlTarget, 4097)) },
		"crossing-count":         func() error { return e.crossingRecords(&crossingIndex{}, make([][]byte, 4097)) },
		"crossing-bytes":         func() error { return e.crossingRecords(&crossingIndex{}, [][]byte{oversized}) },
		"control-index-bytes": func() error {
			_, err := resolution.loadIndex("ControlArtifactReferenceModel", map[string][]byte{"owner": oversized})
			return err
		},
		"control-index-key": func() error {
			_, err := resolution.loadIndex("ControlArtifactReferenceModel", map[string][]byte{"": []byte(`{}`)})
			return err
		},
		"composition-index-bytes": func() error {
			_, err := mixed.index("MixedCompositionComponentModel", map[[2]string][]byte{{"profile", "component"}: oversized})
			return err
		},
		"composition-scenario-bytes": func() error { _, err := mixed.scenarioIndex(map[string][]byte{"owner": oversized}); return err },
		"flow-fragment-count": func() error {
			_, err := e.flowOwnerFragments("ParticipantActionResultModel", make([][]byte, 4097))
			return err
		},
		"flow-fragment-bytes": func() error {
			_, err := e.flowOwnerFragments("ParticipantActionResultModel", [][]byte{oversized})
			return err
		},
		"flow-index-bytes": func() error {
			_, err := flow.fragments("ParticipantEffectiveFlowLabelModel", map[string][]byte{"owner": oversized})
			return err
		},
		"phase-requirement-bytes": func() error { _, err := materializationRequirements([][]byte{oversized}); return err },
		"phase-resource-bytes":    func() error { return e.materializationResources(&materializationCompiled{}, [][]byte{oversized}) },
		"identity-path-length": func() error {
			return materializationIdentityProfiles(map[string][]string{strings.Repeat("a", 4097): {"name"}})
		},
		"identity-field-count": func() error {
			return materializationIdentityProfiles(map[string][]string{"": {"a", "b", "c", "d", "e", "f", "g", "h", "i"}})
		},
		"identity-field-bytes": func() error {
			return materializationIdentityProfiles(map[string][]string{"": {strings.Repeat("a", 8*1048576+1)}})
		},
		"action-reference-count": func() error { return require(flowUniqueReferences(make([]string, 100001))) },
		"action-reference-bytes": func() error { return require(flowUniqueReferences([]string{strings.Repeat("a", 8*1048576+1)})) },
	} {
		t.Run(name, func(t *testing.T) {
			if err := check(); err == nil {
				t.Fatal("accepted unbounded trusted owner data")
			}
		})
	}
}
