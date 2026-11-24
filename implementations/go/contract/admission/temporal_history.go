package admission

import (
	"maps"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) temporalHistory(i validation.Invocation) error {
	v, err := e.defaulted(termRuntimeSnapshotV1, i.Instance)
	if err != nil {
		return err
	}
	if at(v, "time_model_state") != nil {
		if err := timeRuntime(at(v, "time_model_state")); err != nil {
			return err
		}
	}
	clocks := at(v, "time_model_state", "clocks")
	for participant, history := range object(at(v, "participant_behavior_history")) {
		if err := temporalParticipantHistory(participant, array(history), clocks); err != nil {
			return err
		}
	}
	return nil
}
func temporalParticipantHistory(participant string, history []any, clocks any) error {
	attempts := map[string]any{}
	completed := map[string]bool{}
	for _, event := range history {
		if err := temporalParticipantEvent(participant, event, clocks, attempts, completed); err != nil {
			return err
		}
	}
	return require(equalSet(completed, keySet(attempts)))
}
func temporalHistoryEvent(event, attempt, clocks any) error {
	if attempt == nil || !equal(at(event, "temporal_contexts"), at(attempt, "temporal_contexts")) {
		return invalid()
	}
	contexts := make([]any, 0)
	for _, carrier := range array(at(event, "temporal_contexts")) {
		context := at(carrier, "shared_time")
		if context == nil {
			continue
		}
		contexts = append(contexts, context)
		if err := temporalContextClock(context, event, clocks); err != nil {
			return err
		}
	}
	assessments := array(at(event, "temporal_assessments"))
	if stringAt(event, "event_type") != termObservationEmitted {
		return require(len(assessments) == 0)
	}
	if len(assessments) != len(contexts) {
		return invalid()
	}
	proofs := array(at(event, "action_result", "temporal_evidence"))
	if err := temporalEvidenceScope(contexts, proofs, stringAt(event, "observation_boundary_address")); err != nil {
		return err
	}
	disposition := termReported
	if stringAt(attempt, "admission_disposition") == termRejected {
		disposition = "not_dispatched"
	}
	for index, context := range contexts {
		clock := at(clocks, stringAt(context, "binding", "clock_address"))
		if err := temporalAssessment(event, context, assessments[index], clock, disposition); err != nil {
			return err
		}
	}
	return nil
}
func temporalContextClock(context, event, clocks any) error {
	clock := at(clocks, stringAt(context, "binding", "clock_address"))
	history := array(at(clock, "history"))
	sequence, sok := integer(at(context, "clock_sequence"))
	if !matchingFields(context, event, fieldParticipantAddress, fieldEpisodeID, "action_instance_id") || !equal(at(context, "binding", "action_contract_address"), at(event, "action_contract_address")) || clock == nil || !sok || sequence < 0 || sequence >= len(history) {
		return invalid()
	}
	if !equal(at(history[sequence], "resulting"), at(context, "submitted_at")) {
		return invalid()
	}
	for field, bindingField := range map[string]string{"bound_start": termStart, "bound_end": termEnd} {
		var expected any
		if at(context, "binding", bindingField) != nil {
			copyValue := maps.Clone(object(at(context, "binding", bindingField)))
			copyValue["segment"] = at(context, "submitted_at", "segment")
			expected = copyValue
		}
		if !equal(expected, at(context, field)) {
			return invalid()
		}
	}
	return nil
}
func temporalEvidenceScope(contexts, proofs []any, boundary string) error {
	seen := map[string]bool{}
	for _, proof := range proofs {
		found := false
		for _, context := range contexts {
			if equal(at(proof, "context"), context) {
				found = true
			}
		}
		id := stringAt(proof, "context", "binding", "temporal_id")
		if !found || seen[id] || stringAt(proof, "observation_boundary_address") != boundary {
			return invalid()
		}
		seen[id] = true
	}
	return nil
}
func temporalAssessment(event, context, assessment, clock any, disposition string) error {
	sequence, sok := integer(at(assessment, "evaluation_sequence"))
	history := array(at(clock, "history"))
	if stringAt(assessment, "native_execution") != disposition || !equal(context, at(assessment, "context")) || !sok || sequence < 0 || sequence >= len(history) || numericGreater(at(context, "clock_sequence"), at(assessment, "evaluation_sequence")) {
		return invalid()
	}
	proofs := array(at(assessment, termEvidence))
	if disposition == termReported && stringAt(context, "binding", "temporal_kind") == kindDeadline {
		selected := temporalSelectedProofs(event, context)
		if !equal(selected, proofs) {
			return invalid()
		}
	}
	filtered := make([]any, 0)
	for _, proof := range proofs {
		if equal(at(proof, "context"), context) {
			filtered = append(filtered, proof)
		}
	}
	observed := maps.Clone(object(clock))
	observed["coordinate"], observed[termState], observed["sequence"], observed["history"] = at(history[sequence], "resulting"), at(history[sequence], "resulting_state"), at(history[sequence], "sequence"), history[:sequence+1]
	var status, reason string
	if stringAt(context, "binding", "temporal_kind") == kindDeadline {
		status, reason = temporalDeadline(context, filtered, stringAt(event, "observation_boundary_address"), observed, disposition)
	} else {
		status, reason = temporalDwell(context, filtered, observed)
	}
	return require(stringAt(assessment, "status") == status && stringAt(assessment, "reason") == reason && equal(proofs, filtered))
}

func temporalParticipantEvent(participant string, event, clocks any, attempts map[string]any, completed map[string]bool) error {
	if object(event) == nil {
		return invalid()
	}
	key := join(stringAt(event, fieldEpisodeID), stringAt(event, "action_instance_id"))
	explicit := len(array(at(event, "temporal_assessments"))) > 0
	for _, context := range array(at(event, "temporal_contexts")) {
		explicit = explicit || at(context, "shared_time") != nil
	}
	if !explicit && attempts[key] == nil {
		return nil
	}
	if stringAt(event, fieldParticipantAddress) != participant {
		return invalid()
	}
	if stringAt(event, "event_type") == "action_attempted" {
		if attempts[key] != nil {
			return invalid()
		}
		attempts[key] = event
	}
	if err := temporalHistoryEvent(event, attempts[key], clocks); err != nil {
		return err
	}
	if stringAt(event, "event_type") == termObservationEmitted {
		if completed[key] {
			return invalid()
		}
		completed[key] = true
	}

	return nil
}

func temporalSelectedProofs(event, context any) []any {
	selected := make([]any, 0)
	for _, proof := range array(at(event, "action_result", "temporal_evidence")) {
		if equal(at(proof, "context"), context) {
			selected = append(selected, proof)
		}
	}
	return selected
}
