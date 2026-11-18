package runtime

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type participantRequest struct{ input ParticipantActionInput }

func (*participantRequest) admittedAction() {
	// This marker seals requests to the native owner; it performs no effect.
}

// Input returns a detached view of this request. Admitted fragments remain
// immutable owner handles and each Document call returns its own copy.
func (r *participantRequest) Input() ParticipantActionInput { return copyParticipantInput(r.input) }

func copyPointer[T any](input *T) *T {
	if input == nil {
		return nil
	}
	cloned := *input
	return &cloned
}
func copyParticipantInput(input ParticipantActionInput) ParticipantActionInput {
	result := input
	raw, err := json.Marshal(input.ImplementationManifest)
	if err != nil {
		panic("runtime contract: corrupt owned manifest")
	}
	// Start with a zero record so decoding cannot reuse caller-owned slices.
	result.ImplementationManifest = ParticipantActionInput{}.ImplementationManifest
	if json.Unmarshal(raw, &result.ImplementationManifest) != nil {
		panic("runtime contract: corrupt owned manifest")
	}
	result.EvidenceRefs = slices.Clone(input.EvidenceRefs)
	result.VisibleRefs = slices.Clone(input.VisibleRefs)
	result.DisclosedRefs = slices.Clone(input.DisclosedRefs)
	result.ObservationBoundaryEvidenceRefs = slices.Clone(input.ObservationBoundaryEvidenceRefs)
	result.TargetAddresses = slices.Clone(input.TargetAddresses)
	result.TemporalContexts = slices.Clone(input.TemporalContexts)
	result.ResourceMeasurementRequirements = slices.Clone(input.ResourceMeasurementRequirements)
	result.TemporalEvidence = slices.Clone(input.TemporalEvidence)
	result.PostStateDigest = copyPointer(input.PostStateDigest)
	result.ExecutionScopeRef = copyPointer(input.ExecutionScopeRef)
	result.ExecutionGeneration = copyPointer(input.ExecutionGeneration)
	return result
}

// BindParticipantAction admits portable request joins and owns the inputs.
// It grants neither caller authority nor permission to invoke native effects.
func BindParticipantAction(input ParticipantActionInput) (ParticipantActionRequest, error) { //nolint:ireturn // The declared public API returns the portable role interface.
	if !participantIdentityValid(input) {
		return nil, invalidRequest()
	}
	if admission.CheckTransport(input.ImplementationManifest, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return nil, invalidRequest()
	}
	if checkParticipantFragments(input) != nil {
		return nil, invalidRequest()
	}

	if !participantReferencesValid(input) {
		return nil, invalidRequest()
	}
	manifest, err := participantManifest(input)
	if err != nil {
		return nil, err
	}

	selection := fragmentObject(input.ImplementationSelection)
	if !participantSelectionValid(input, manifest, selection) || !participantExposureValid(input, selection) || !participantTemporalValid(input) {
		return nil, invalidRequest()
	}
	return &participantRequest{input: copyParticipantInput(input)}, nil
}

func participantIdentityValid(input ParticipantActionInput) bool {
	if input.ParticipantAddress == "" || !strings.HasPrefix(input.ActionContractAddress, "participant.action-contract.") || !strings.HasPrefix(input.ObservationBoundaryAddress, "participant.observation-boundary.") || input.ActionInstanceID == "" || input.StateTransitionKind == "" {
		return false
	}
	if input.PostStateDigest != nil && *input.PostStateDigest == "" {
		return false
	}
	if (input.ExecutionScopeRef == nil) != (input.ExecutionGeneration == nil) {
		return false
	}
	return input.ExecutionScopeRef == nil || (*input.ExecutionScopeRef != "" && *input.ExecutionGeneration >= 0 && len(input.TargetAddresses) > 0)
}
func participantReferencesValid(input ParticipantActionInput) bool {
	lists := [][]string{input.EvidenceRefs, input.VisibleRefs, input.DisclosedRefs, input.ObservationBoundaryEvidenceRefs, input.TargetAddresses}
	for _, list := range lists {
		if len(list) > value.Runtime().MaxMembers {
			return false
		}
		seen := map[string]bool{}
		for _, text := range list {
			if text == "" || seen[text] {
				return false
			}
			seen[text] = true
		}
	}
	_, err := ownedObject(map[string]any{"participant": input.ParticipantAddress, "action": input.ActionContractAddress, "boundary": input.ObservationBoundaryAddress, "instance": input.ActionInstanceID, "transition": input.StateTransitionKind, "evidence": input.EvidenceRefs, "visible": input.VisibleRefs, "disclosed": input.DisclosedRefs, "boundary_evidence": input.ObservationBoundaryEvidenceRefs, "targets": input.TargetAddresses, "state_digest": input.PostStateDigest, "scope": input.ExecutionScopeRef, "generation": input.ExecutionGeneration})
	return err == nil
}
func field(input map[string]any, name string) map[string]any {
	result, _ := input[name].(map[string]any)
	return result
}
func text(input map[string]any, name string) string { result, _ := input[name].(string); return result }
func texts(input any) []string {
	values, _ := input.([]any)
	result := make([]string, 0, len(values))
	for _, v := range values {
		if s, ok := v.(string); ok {
			result = append(result, s)
		}
	}
	return result
}
func subset(left, right []string) bool {
	for _, item := range left {
		if !slices.Contains(right, item) {
			return false
		}
	}
	return true
}
func fragmentObject(input admission.Fragment) map[string]any {
	if input == nil {
		return nil
	}
	result, _ := input.Document().(map[string]any)
	return result
}
func participantSelectionValid(input ParticipantActionInput, manifest, selection map[string]any) bool {
	capabilities := field(manifest, "capabilities")
	if text(selection, "participant_address") != input.ParticipantAddress || !cmp.Equal(manifest["identity"], selection["implementation_identity"]) || !subset(texts(selection["participant_contract_versions"]), texts(capabilities["supported_participant_contracts"])) || !slices.Contains(texts(capabilities["supported_decision_surface_modes"]), text(selection, "selected_decision_surface_mode")) || !subset(texts(field(selection, "exposure_policy")["exposure_policy_kinds"]), texts(capabilities["exposure_policy_kinds"])) {
		return false
	}
	if input.ValidatedSelection != nil && text(fragmentObject(input.ValidatedSelection), "action_contract_address") != input.ActionContractAddress {
		return false
	}
	result := fragmentObject(input.ActionResult)
	return result == nil || (text(result, "participant_address") == input.ParticipantAddress && text(result, "action_instance_id") == input.ActionInstanceID && text(result, "action_contract_address") == input.ActionContractAddress)
}

// ParticipantActionInputFor reads only an exact native request owner. An
// embedding implementation cannot substitute a foreign Input callback.
func ParticipantActionInputFor(request ParticipantActionRequest) (ParticipantActionInput, error) {
	owned, ok := request.(*participantRequest)
	if !ok || owned == nil {
		return ParticipantActionInput{}, invalidRequest()
	}
	return copyParticipantInput(owned.input), nil
}

func checkParticipantFragments(input ParticipantActionInput) error {
	if admission.CheckFragment(input.ImplementationSelection, admission.ParticipantImplementationSelection) != nil {
		return invalidRequest()
	}
	for _, entry := range []struct {
		fragment admission.Fragment
		profile  admission.FragmentProfile
	}{{input.ActionResult, admission.ParticipantActionResult}, {input.ValidatedSelection, admission.ValidatedActionSelection}} {
		if entry.fragment != nil && admission.CheckFragment(entry.fragment, entry.profile) != nil {
			return invalidRequest()
		}
	}
	for _, group := range []struct {
		fragments []admission.Fragment
		profile   admission.FragmentProfile
	}{{input.TemporalContexts, admission.ParticipantTemporalContext}, {input.TemporalEvidence, admission.ParticipantTemporalEvidence}, {input.ResourceMeasurementRequirements, admission.ParticipantResourceMeasurement}} {
		if len(group.fragments) > value.Runtime().MaxMembers {
			return invalidRequest()
		}
		for _, fragment := range group.fragments {
			if admission.CheckFragment(fragment, group.profile) != nil {
				return invalidRequest()
			}
		}
	}
	return participantFragmentBudget(input)
}
func participantFragmentBudget(input ParticipantActionInput) error {
	fragments := []admission.Fragment{input.ImplementationSelection}
	for _, optional := range []admission.Fragment{input.ActionResult, input.ValidatedSelection} {
		if optional != nil {
			fragments = append(fragments, optional)
		}
	}
	fragments = append(fragments, input.TemporalContexts...)
	fragments = append(fragments, input.TemporalEvidence...)
	fragments = append(fragments, input.ResourceMeasurementRequirements...)
	if admission.CheckFragmentBudget(fragments, 8<<20) != nil {
		return invalidRequest()
	}
	return nil
}
func participantManifest(input ParticipantActionInput) (map[string]any, error) {
	owner, err := validator()
	if err != nil {
		return nil, err
	}
	raw, err := json.Marshal(input.ImplementationManifest)
	if err != nil || owner.CheckPortable("participant-implementation-manifest-v1", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return nil, invalidRequest()
	}
	decoded, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return nil, invalidRequest()
	}
	manifest, ok := decoded.(map[string]any)
	if !ok {
		return nil, invalidRequest()
	}
	return manifest, nil
}
