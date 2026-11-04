package admission

import (
	"github.com/OpenRAE/rae/implementations/go/internal/base/timestamp"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) backendRules() map[string]definition {
	return map[string]definition{
		"backend-operation-local-consistency":    {check: backendLocal},
		"backend-operation-response-binding":     {check: e.backendResponse, contextual: true, requiresContext: true},
		"backend-operation-contextual-admission": {check: e.backendAdmission, contextual: true, requiresContext: true},
	}
}

func backendLocal(i validation.Invocation) error {
	v := i.Instance
	switch i.Key.ContractID {
	case termBackendOperationRequestV1:
		if !uniqueValues(at(v, "requirement_refs")) || !fieldsUnique(v, "required_guarantees") {
			return invalid()
		}
	case termBackendOperationCapabilitiesV1:
		return require(fieldsUnique(v, "supported_operation_kinds", "guarantees"))
	case termBackendOperationControlV1:
		if !fieldsUnique(v, "authorization_scope") {
			return invalid()
		}
	case termBackendOperationResponseV1:
		if err := backendMessage(at(v, "message")); err != nil {
			return err
		}
	}
	if at(v, "budget") != nil {
		budget := at(v, "budget")
		if _, err := timestamp.ParseRFC3339("started_at", stringAt(budget, "started_at")); err != nil {
			return invalid()
		}
		remaining, rok := number(at(budget, "remaining_ms"))
		limit, lok := number(at(budget, "limit_ms"))
		if !rok || !lok || remaining.Cmp(limit) > 0 {
			return invalid()
		}
	}
	return backendBinding(at(v, "binding"))
}

func uniqueValues(values any) bool {
	seen := map[string]bool{}
	for _, value := range array(values) {
		key, err := jsonDigest(value)
		if err != nil || seen[key] {
			return false
		}
		seen[key] = true
	}
	return true
}

func backendBinding(v any) error {
	if !fieldsUnique(at(v, "context"), "authorization_scope") {
		return invalid()
	}
	scope := at(v, "effect_scope")
	if scope == nil {
		return nil
	}
	if !fieldsUnique(scope, "addresses") {
		return invalid()
	}
	if stringAt(scope, termKind) == scopeResources {
		return require(len(array(at(scope, "addresses"))) > 0 && at(scope, "independence") != nil)
	}
	return require(len(array(at(scope, "addresses"))) == 0 && at(scope, "independence") == nil)
}

func backendMessage(v any) error {
	switch stringAt(v, termKind) {
	case termAdmission, termAcknowledgement:
		return require((stringAt(v, "disposition") == outcomeRefused) == (at(v, "reason") != nil))
	case termProgress:
		return require(uniqueValues(at(v, fieldEvidenceRefs)))
	case messageOutcome, messageReconciliation:
		if err := backendEffects(at(v, termEffects)); err != nil {
			return err
		}
		if stringAt(v, termKind) == messageOutcome {
			return backendOutcome(v)
		}
	case messageControl:
		return nil
	default:
		return invalid()
	}
	return nil
}

func backendEffects(v any) error {
	if !uniqueValues(at(v, fieldEvidenceRefs)) || !fieldsUnique(v, "residual_scope") {
		return invalid()
	}
	effect := stringAt(v, "effect")
	if (effect != statusUnknown || boolean(at(v, "cessation_established")) || at(v, "external_fence") != nil) && len(array(at(v, fieldEvidenceRefs))) == 0 {
		return invalid()
	}
	residual := at(v, "residual_state")
	if (len(array(at(v, "residual_scope"))) > 0) != (residual != nil) {
		return invalid()
	}
	if effect == statusPartial && residual == nil || effect == effectAbsent && residual != nil {
		return invalid()
	}
	return require(residual == nil || stringAt(residual, termContractID) == termRuntimeSnapshotV1)
}

func backendOutcome(v any) error {
	state := stringAt(v, "proposed_state")
	known := stringAt(v, termEffects, "effect") != statusUnknown && boolean(at(v, termEffects, "cessation_established"))
	if state != outcomeIndeterminate && !known {
		return invalid()
	}
	if state == outcomeSucceeded && (stringAt(v, "satisfaction") != termSatisfied || !boolean(at(v, "release_gates_satisfied")) || at(v, "result") == nil || stringAt(v, termEffects, "effect") == statusPartial) {
		return invalid()
	}
	if state == outcomeFailed && stringAt(v, "satisfaction") != "unsatisfied" {
		return invalid()
	}
	return require(boolean(at(v, "cancellation_established")) == (state == outcomeCancelled))
}
