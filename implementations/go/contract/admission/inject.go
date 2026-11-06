package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) injectRules() map[string]definition {
	return map[string]definition{
		"inject-trigger-request-local-consistency":        {check: injectRequest},
		"inject-occurrence-local-consistency":             {check: injectOccurrence},
		"inject-occurrence-outcome-local-consistency":     {check: injectOutcomeLocal},
		"inject-occurrence-correlation-local-consistency": {check: injectCorrelationLocal},
		"inject-trigger-exact-retry":                      {check: e.injectRetry, contextual: true, requiresContext: true},
		"inject-occurrence-unique-claims":                 {check: e.injectClaims, contextual: true, requiresContext: true},
		"inject-occurrence-outcome-binding":               {check: e.injectOutcome, contextual: true, requiresContext: true},
		"inject-occurrence-correlation-source":            {check: e.injectCorrelation, contextual: true, requiresContext: true},
	}
}

func injectRequest(i validation.Invocation) error {
	v := i.Instance
	inject, ok := strings.CutPrefix(stringAt(v, termInject), "orchestration.inject.")
	if !ok || stringAt(v, "plan", termContractID) != termOrchestrationPlanV1 {
		return invalid()
	}
	bindings := at(v, termBindings)
	if len(rowTupleSet(bindings, "binding", "instance")) != len(array(bindings)) || !uniqueValues(bindings) {
		return invalid()
	}
	for _, binding := range array(bindings) {
		node, ok := strings.CutPrefix(stringAt(binding, termNode), "provision.node.")
		if !ok {
			return invalid()
		}
		rendered, err := address.Render(termOrchestration, "inject-binding", node, inject)
		if err != nil || rendered != stringAt(binding, "binding") {
			return invalid()
		}
	}
	return injectPlacement(at(v, "placement"))
}

func injectIdentities(v any) []string {
	ids := []string{stringAt(v, "request", "request_key"), stringAt(v, "request", "occurrence_id"), stringAt(v, "operation_id")}
	if stringAt(v, "request", "placement", termKind) == placementSchedule {
		ids = append(ids, stringAt(v, "request", "placement", "slot"))
	}
	return ids
}
func injectOccurrence(i validation.Invocation) error {
	v := i.Instance
	request, admission := at(v, "request"), at(v, termAdmission)
	if err := injectRequest(validation.Invocation{Instance: request}); err != nil {
		return err
	}
	if !uniqueValues(at(v, "admission_evidence")) || !uniqueValues(at(v, "evidence_requirements")) || !fieldsUnique(admission, "authorization_scope") {
		return invalid()
	}
	if stringAt(admission, "operation_kind") != termOrchestration || !equal(at(request, "target_scope"), at(admission, "target_scope")) || !equal(at(request, "run_scope"), at(admission, "run_scope")) || !equal(at(v, termOrder, "scope"), at(request, "run_scope")) || !equal(at(v, termOrder, "predecessor"), at(request, "expected_head")) {
		return invalid()
	}
	return require(unique(injectIdentities(v)))
}

func injectAggregate(bindings any) string {
	allComplete, allAbsent := true, true
	for _, binding := range array(bindings) {
		effect := stringAt(binding, termEffects, "effect")
		if effect == statusUnknown || !boolean(at(binding, termEffects, "cessation_established")) {
			return outcomeIndeterminate
		}
		allComplete = allComplete && effect == statusComplete
		allAbsent = allAbsent && effect == effectAbsent
	}
	if allComplete {
		return injectApplied
	}
	if allAbsent {
		return injectAbsent
	}
	return "known-partial"
}
func injectOutcomeLocal(i validation.Invocation) error {
	v := i.Instance
	bindings := array(at(v, termBindings))
	if stringAt(v, "occurrence", termContractID) != contractInjectOccurrence || len(bindings) == 0 || !uniqueValues(bindings) {
		return invalid()
	}
	selected := make([]any, 0, len(bindings))
	for _, binding := range bindings {
		selected = append(selected, at(binding, "binding"))
		if !strings.HasPrefix(stringAt(binding, "binding", termNode), "provision.node.") {
			return invalid()
		}
		if err := backendEffects(at(binding, termEffects)); err != nil {
			return err
		}
		effect := stringAt(binding, termEffects, "effect")
		if (effect == statusComplete || effect == statusPartial) && at(binding, "readback") == nil {
			return invalid()
		}
	}
	if len(rowTupleSet(selected, "binding", "instance")) != len(bindings) || stringAt(v, "effect") != injectAggregate(bindings) {
		return invalid()
	}
	if err := backendLocal(validation.Invocation{Key: validation.Key{ContractID: termBackendOperationResponseV1}, Instance: at(v, "response")}); err != nil {
		return err
	}
	return injectSettlement(v)
}

func injectCorrelationLocal(i validation.Invocation) error {
	v := i.Instance
	return require(stringAt(v, "occurrence", termContractID) == contractInjectOccurrence && stringAt(v, messageOutcome, termContractID) == termInjectOccurrenceOutcomeV1 && equal(at(v, "occurrence", termArtifactID), at(v, messageOutcome, termArtifactID)))
}

func injectPlacement(placement any) error {
	kind := stringAt(placement, termKind)
	if kind == termEvent || kind == placementSchedule {
		if !strings.HasPrefix(stringAt(placement, termEvent), "orchestration.event.") {
			return invalid()
		}
	}
	if kind == placementSchedule {
		if !strings.HasPrefix(stringAt(placement, "script"), "orchestration.script.") {
			return invalid()
		}
		if at(placement, "story") != nil && !strings.HasPrefix(stringAt(placement, "story"), "orchestration.story.") {
			return invalid()
		}
	}

	return nil
}
func injectSettlement(v any) error {
	message := at(v, "response", "message")
	if stringAt(message, termKind) == messageOutcome {
		expected := map[string]string{statusComplete: injectApplied, effectAbsent: injectAbsent, statusPartial: "known-partial", statusUnknown: outcomeIndeterminate}[stringAt(message, termEffects, "effect")]
		if !boolean(at(message, termEffects, "cessation_established")) {
			expected = outcomeIndeterminate
		}
		return require(expected == stringAt(v, "effect") && (stringAt(message, "proposed_state") != outcomeSucceeded || stringAt(v, "effect") == injectApplied))
	}
	return require(stringAt(message, termKind) == termAcknowledgement && stringAt(message, "disposition") == outcomeRefused && stringAt(v, "effect") == injectAbsent)
}
