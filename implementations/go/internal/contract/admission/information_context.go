package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// InformationSourceCoordinate supplies the trusted exact-cut membership of a
// source. It is separate from the portable source payload's claims.
type InformationSourceCoordinate struct {
	ParticipantAddress, EpisodeID, AudienceScopeRef, VisibilityProjectionRef string
	ProjectionPolicyRevision, RedactionPolicyRef, RedactionPolicyRevision    string
	StateCut                                                                 json.RawMessage
}

// InformationSource binds one explicitly resolved typed source and coordinate.
type InformationSource struct {
	ContractID, Reference string
	Document              []byte
	Coordinate            InformationSourceCoordinate
}

// InformationStateContext supplies exact histories, sources and proof digests.
// Its artifact documents are bounded and checked before agreement is tested.
type InformationStateContext interface {
	InformationSources() []InformationSource
	InformationHistories() map[string][][]byte
	InformationProofDigests() map[string]string
	InformationDecisionSurfaces() [][]byte
}

func (e *Validator) informationRules() map[string]definition {
	return map[string]definition{"participant-information-state-context-resolution": {check: e.informationState, contextual: true, requiresContext: true}}
}

func informationLocal(v any) error {
	if len(rowTupleSet(at(v, "source_refs"), termContractID, "ref")) != len(array(at(v, "source_refs"))) || !fieldsUnique(v, "predecessor_information_state_refs") || set(at(v, "predecessor_information_state_refs"))[stringAt(v, "information_state_ref")] || equal(at(v, "information_state_ref"), at(v, "supersedes_information_state_ref")) {
		return invalid()
	}
	if (stringAt(v, "participant_memory_scope") == "episode_local_reset") != (at(v, "memory_reset_authority_ref") != nil) {
		return invalid()
	}
	if informationStrong(v) {
		for _, field := range []string{"occurrence_history_ref", "reconstruction_profile_ref", "reconstruction_algorithm_id", "reconstruction_algorithm_version", "reconstruction_proof_ref", "reconstructed_state_digest"} {
			if at(v, field) == nil {
				return invalid()
			}
		}
		if !equal(at(v, "reconstructed_state_digest"), at(v, "information_state_digest")) {
			return invalid()
		}
	}
	if stringAt(v, "information_guarantee") == "perfect_recall" && at(v, "occurrence_order_witness_ref") == nil {
		return invalid()
	}
	return require(stringAt(v, "information_guarantee") != "lossy_projection" || len(array(at(v, "loss_disclosures"))) > 0)
}

func informationStrong(v any) bool {
	return stringAt(v, "information_guarantee") == "history_consistent" || stringAt(v, "information_guarantee") == "perfect_recall"
}

func (e *Validator) informationState(i validation.Invocation) error {
	context, ok := i.Context.(InformationStateContext)
	if !ok {
		return contextRequired()
	}
	v, err := e.defaulted(termParticipantInformationStateRecordV1, i.Instance)
	if err != nil {
		return err
	}
	if err = informationLocal(v); err != nil {
		return err
	}
	profile, err := e.informationProfileFor(v)
	if err != nil {
		return err
	}
	sources := context.InformationSources()
	if len(sources) > 4096 {
		return invalid()
	}
	index := map[string]InformationSource{}
	remaining := 64 * 1048576
	for _, source := range sources {
		key := join(source.ContractID, source.Reference)
		if _, exists := index[key]; exists || len(source.Document) > remaining {
			return invalid()
		}
		remaining -= len(source.Document)
		index[key] = source
	}
	if err := e.informationSources(v, profile, index); err != nil {
		return err
	}
	return e.informationEvidence(v, profile, context)
}

func (e *Validator) informationProfileFor(v any) (any, error) {
	id := stringAt(v, "reconstruction_profile_ref")
	// The production reference resolves any named profile even for a weak claim.
	if id != "" && id != "occurrence-prefix-evidence-v1" {
		return nil, invalid()
	}
	if !informationStrong(v) {
		return map[string]any{}, nil
	}
	profile := e.informationProfile
	if id != stringAt(profile, termProfileID) || !equal(at(profile, "information_state_schema_version"), at(v, termSchemaVersion)) || !equal(at(profile, "projection_version"), at(v, "projection_version")) || !equal(at(profile, "algorithm_id"), at(v, "reconstruction_algorithm_id")) || !equal(at(profile, "algorithm_version"), at(v, "reconstruction_algorithm_version")) || !set(at(profile, "accepted_order_semantics"))[stringAt(v, "state_cut", "cut_kind")] {
		return nil, invalid()
	}
	return profile, nil
}

func (e *Validator) informationHistory(v any, histories map[string][][]byte) error {
	if len(histories) > 4096 {
		return invalid()
	}
	history, err := e.experimentDocuments(termParticipantObservationEnvelopeV1, histories[stringAt(v, "occurrence_history_ref")])
	if err != nil {
		return err
	}
	if len(history) == 0 {
		return invalid()
	}
	declared := rowTupleSet(at(v, "source_refs"), termContractID, "ref")
	for _, observation := range history {
		if !declared[join(termParticipantObservationEnvelopeV1, stringAt(observation, "observation_ref"))] || !matchingFields(v, observation, fieldParticipantAddress, fieldEpisodeID, "visibility_projection_ref") || !equal(at(v, "occurrence_history_ref"), at(observation, "action_observation_history_ref")) {
			return invalid()
		}
		if err := informationSequence(v, at(observation, "sequence_number")); err != nil {
			return err
		}
	}
	return nil
}

func informationSequence(v, sequence any) error {
	if stringAt(v, "state_cut", "cut_kind") != termSequencePrefix {
		return nil
	}
	return require(sequence != nil && !numericGreater(sequence, at(v, "state_cut", "anchor_order")))
}

func informationSurface(v, surface any) error {
	view, assurance := at(surface, "participant_view"), at(surface, "assurance")
	if !matchingFields(view, v, fieldParticipantAddress, fieldEpisodeID, "redaction_policy_ref") || !matchingFields(assurance, v, "audience_scope_ref", "projection_policy_revision", "visibility_projection_ref", "participant_memory_scope") || !equal(at(assurance, "memory_reset_authority_ref"), at(v, "memory_reset_authority_ref")) || !equal(at(assurance, "derivation_anchor", "state_cut"), at(v, "state_cut")) {
		return invalid()
	}
	return nil
}

func (e *Validator) informationEvidence(v, profile any, context InformationStateContext) error {
	if len(object(profile)) > 0 {
		if err := e.informationHistory(v, context.InformationHistories()); err != nil {
			return err
		}
		proofs := context.InformationProofDigests()
		if len(proofs) > 100000 || proofs[stringAt(v, "reconstruction_proof_ref")] != stringAt(v, "information_state_digest") {
			return invalid()
		}
	}
	surfaces, err := e.experimentDocuments(termParticipantDecisionSurfaceV2, context.InformationDecisionSurfaces())
	if err != nil {
		return err
	}
	for _, surface := range surfaces {
		if !equal(at(surface, "participant_view", "information_state_ref"), at(v, "information_state_ref")) {
			continue
		}
		if err := informationSurface(v, surface); err != nil {
			return err
		}
	}
	return nil
}
