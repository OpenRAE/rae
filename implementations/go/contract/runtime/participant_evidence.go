package runtime

import (
	"slices"

	"github.com/google/go-cmp/cmp"
)

func resultEvidence(result map[string]any) []string {
	refs := texts(result["evidence_refs"])
	for _, group := range []string{"preconditions", "effects", "temporal_evidence"} {
		rows, _ := result[group].([]any)
		for _, row := range rows {
			object, _ := row.(map[string]any)
			refs = append(refs, texts(object["evidence_refs"])...)
		}
	}
	return refs
}
func participantExposureValid(input ParticipantActionInput, selection map[string]any) bool {
	policy := field(selection, "exposure_policy")
	evidence := slices.Concat(input.EvidenceRefs, resultEvidence(fragmentObject(input.ActionResult)))
	for _, proof := range input.TemporalEvidence {
		evidence = append(evidence, texts(fragmentObject(proof)["evidence_refs"])...)
	}
	emitted := slices.Concat(input.VisibleRefs, input.DisclosedRefs, evidence)
	withheld := texts(policy["withheld_refs"])
	for _, ref := range emitted {
		if slices.Contains(withheld, ref) {
			return false
		}
	}
	return subset(input.VisibleRefs, slices.Concat(texts(policy["disclosed_refs"]), texts(policy["visibility_scope_refs"]))) && subset(input.DisclosedRefs, texts(policy["disclosed_refs"])) && subset(evidence, input.ObservationBoundaryEvidenceRefs)
}

func participantTemporalValid(input ParticipantActionInput) bool {
	ids := map[string]bool{}
	points := []string{}
	shared := []map[string]any{}
	for _, context := range input.TemporalContexts {
		document := fragmentObject(context)
		id := text(document, "temporal_contract_id")
		if ids[id] {
			return false
		}
		ids[id] = true
		points = append(points, text(document, "observation_point"))
		if context := field(document, "shared_time"); context != nil {
			shared = append(shared, context)
		}
	}
	result := fragmentObject(input.ActionResult)
	if result != nil && len(points) > 0 && !slices.Contains(points, text(result, "observation_point")) {
		return false
	}
	if !participantProofsValid(input, shared) {
		return false
	}

	budgets := map[string]bool{}
	for _, requirement := range input.ResourceMeasurementRequirements {
		id := text(fragmentObject(requirement), "budget_state_ref")
		if budgets[id] {
			return false
		}
		budgets[id] = true
	}
	return true
}

func participantProofsValid(input ParticipantActionInput, shared []map[string]any) bool {
	requestProofs := make([]any, len(input.TemporalEvidence))
	for i, proof := range input.TemporalEvidence {
		requestProofs[i] = proof.Document()
	}
	resultProofs, _ := fragmentObject(input.ActionResult)["temporal_evidence"].([]any)
	for _, proofs := range [][]any{requestProofs, resultProofs} {
		if !participantProofGroupValid(proofs, shared, input.ObservationBoundaryAddress) {
			return false
		}
	}
	return true
}
func participantProofGroupValid(proofs []any, shared []map[string]any, boundary string) bool {
	seen := map[string]bool{}
	for _, proof := range proofs {
		document, _ := proof.(map[string]any)
		context := field(document, "context")
		id := text(field(context, "binding"), "temporal_id")
		if seen[id] || text(document, "observation_boundary_address") != boundary {
			return false
		}
		matched := false
		for _, expected := range shared {
			if cmp.Equal(expected, context) {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
		seen[id] = true
	}
	return true
}
