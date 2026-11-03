package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

type informationTestContext struct {
	sources   []InformationSource
	histories map[string][][]byte
	proofs    map[string]string
}

func (c informationTestContext) InformationSources() []InformationSource    { return c.sources }
func (c informationTestContext) InformationHistories() map[string][][]byte  { return c.histories }
func (c informationTestContext) InformationProofDigests() map[string]string { return c.proofs }
func (c informationTestContext) InformationDecisionSurfaces() [][]byte      { return nil }

func TestInformationStateStrongClaimResolvesExactCut(t *testing.T) {
	e := boundTestOwner(t)
	v := fixtureObject(t, "fixtures/participant-runtime/participant-information-state-record-v1/valid/history-consistent-cut.json")
	observation := fixtureObject(t, "fixtures/participant-runtime/participant-observation-envelope-v1/valid/rl-observation-only.json")
	raw := controlJSON(t, observation)
	coordinate := InformationSourceCoordinate{ParticipantAddress: stringAt(v, "participant_address"), EpisodeID: stringAt(v, "episode_id"), AudienceScopeRef: stringAt(v, "audience_scope_ref"), VisibilityProjectionRef: stringAt(v, "visibility_projection_ref"), ProjectionPolicyRevision: stringAt(v, "projection_policy_revision"), RedactionPolicyRef: stringAt(v, "redaction_policy_ref"), RedactionPolicyRevision: stringAt(v, "redaction_policy_revision"), StateCut: controlJSON(t, at(v, "state_cut"))}
	context := informationTestContext{sources: []InformationSource{{ContractID: "participant-observation-envelope-v1", Reference: stringAt(observation, "observation_ref"), Document: raw, Coordinate: coordinate}}, histories: map[string][][]byte{stringAt(v, "occurrence_history_ref"): {raw}}, proofs: map[string]string{stringAt(v, "reconstruction_proof_ref"): stringAt(v, "information_state_digest")}}
	i := validation.Invocation{Instance: v, Context: context}
	if err := validateTestDocument(t, e, "participant-information-state-record-v1", i.Instance, i.Context); err != nil {
		t.Fatal(err)
	}
	context.sources[0].Coordinate.RedactionPolicyRevision = "foreign"
	if err := validateTestDocument(t, e, "participant-information-state-record-v1", i.Instance, i.Context); err == nil {
		t.Error("accepted unrelated source revision")
	}
	context.sources[0].Coordinate = coordinate
	context.proofs[stringAt(v, "reconstruction_proof_ref")] = "sha256:wrong"
	if err := validateTestDocument(t, e, "participant-information-state-record-v1", i.Instance, i.Context); err == nil {
		t.Error("accepted unrelated proof digest")
	}
	context.proofs[stringAt(v, "reconstruction_proof_ref")] = stringAt(v, "information_state_digest")
	observation["sequence_number"] = json.Number("44")
	context.sources[0].Document = controlJSON(t, observation)
	if err := validateTestDocument(t, e, "participant-information-state-record-v1", i.Instance, i.Context); err == nil {
		t.Error("accepted a source after the committed cut")
	}
	context.sources[0].Document = raw
	context.histories[stringAt(v, "occurrence_history_ref")] = nil
	if err := validateTestDocument(t, e, "participant-information-state-record-v1", i.Instance, i.Context); err == nil {
		t.Error("accepted missing strong occurrence history")
	}
}
