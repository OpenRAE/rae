package admission

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type executionPolicyRule struct {
	namespace []string
	scope     string
	policy    any
}

// ResolveExecutionPolicy selects one complete lexical rule. It never combines
// fields from different policies or grants authority to execute that policy.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func ResolveExecutionPolicy(v *Validator, document Fragment, scope string, namespace []string, evidence map[string]Fragment) (Fragment, error) {
	if v == nil || !canonicalPointer(scope) || len(scope) > 4*4096 || len(namespace) > 31 || len(evidence) > 4096 {
		return nil, fragmentInvalid()
	}
	if err := v.checkExecutionPolicyQuery(scope, namespace); err != nil {
		return nil, err
	}
	if document == nil {
		return nil, nil //nolint:nilnil // Absence is a valid optional result in this declared relation.
	}
	if err := CheckFragment(document, OperationPolicyDocument); err != nil {
		return nil, err
	}
	owned, ok := document.(fragment)
	if !ok {
		return nil, fragmentInvalid()
	}
	selected := selectExecutionPolicyRule(owned.Document(), scope, namespace)
	if selected == nil {
		return nil, nil //nolint:nilnil // Absence is a valid optional result in this declared relation.
	}
	policy, err := v.defaultExecutionPolicy(selected.policy)
	if err != nil {
		return nil, err
	}
	resolvedEvidence, err := executionPolicyEvidence(policy, evidence)
	if err != nil {
		return nil, err
	}
	governing := selected.scope
	if governing == "" {
		governing = "/"
	}
	unit := "native-operation"
	if strings.HasPrefix(scope, "/workflows/") && strings.Contains(scope, "/steps/") {
		unit = "workflow-step"
	}
	ns := make([]any, len(selected.namespace))
	for i, component := range selected.namespace {
		ns[i] = component
	}
	return AdmitFragment(v, OperationExecutionPolicy, map[string]any{
		processLimitScopeField: scope, "retry_unit": unit, "namespace": ns,
		termGoverningScope: strings.Join(selected.namespace, ".") + "#" + governing,
		"policy":           policy, "evidence_requirements": resolvedEvidence,
	}, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
}

func (e *Validator) checkExecutionPolicyQuery(scope string, namespace []string) error {
	ns := make([]any, len(namespace))
	for i, component := range namespace {
		ns[i] = component
	}
	// Apply the published grammar through its owner, even when no rule matches.
	query, err := value.Encode(map[string]any{processLimitScopeField: scope, "namespace": ns, "policy": map[string]any{"policy_id": "scope-query", "response": termTerminate}}, value.Runtime())
	if err != nil {
		return fragmentInvalid()
	}
	if e.checkModelFragment(termInstantiatedScenarioV1, schemaDefinitionsPrefix+"ExecutionPolicyScope", query, ingress.Limits{MaxBytes: 64 << 10, MaxDepth: 8}) != nil {
		return fragmentInvalid()
	}
	return nil
}

func selectExecutionPolicyRule(input any, scope string, namespace []string) *executionPolicyRule {
	var selected *executionPolicyRule
	for _, rule := range array(at(input, "scopes")) {
		candidate := executionPolicyRule{namespace: stringsOf(at(rule, termNamespace)), scope: stringAt(rule, processLimitScopeField), policy: at(rule, termPolicy)}
		if !candidate.applies(scope, namespace) {
			continue
		}
		if selected == nil || candidate.nearer(*selected) {
			selected = &candidate
		}
	}
	if selected != nil {
		return selected
	}
	if fallback := at(input, termDefault); fallback != nil {
		return &executionPolicyRule{policy: fallback}
	}
	return nil
}

func (rule executionPolicyRule) applies(scope string, namespace []string) bool {
	return len(rule.namespace) <= len(namespace) && slices.Equal(rule.namespace, namespace[:len(rule.namespace)]) && pointerContains(rule.scope, scope)
}

func (rule executionPolicyRule) nearer(other executionPolicyRule) bool {
	if len(rule.namespace) != len(other.namespace) {
		return len(rule.namespace) > len(other.namespace)
	}
	return len(jsonpointer.Tokens(rule.scope)) > len(jsonpointer.Tokens(other.scope))
}

func executionPolicyEvidence(policy any, evidence map[string]Fragment) (map[string]any, error) {
	resolved := map[string]any{}
	for _, ref := range stringsOf(at(policy, fieldEvidenceRefs)) {
		item, present := evidence[ref]
		owned, native := item.(fragment)
		if !present || !native || owned.profile != RealizationValue {
			return nil, fragmentInvalid()
		}
		resolved[ref] = owned.Document()
	}
	return resolved, nil
}

func defaultOperationRetry() map[string]any {
	return map[string]any{termMaxAttempts: json.Number("1"), "after_effect_policy": retryDisallow}
}

func (e *Validator) defaultExecutionPolicy(input any) (map[string]any, error) {
	policy := object(input)
	if _, present := policy[termRetry]; !present {
		policy[termRetry] = defaultOperationRetry()
	}
	// These are the existing retry model's factory defaults. The published
	// schema deliberately does not advertise factories as static defaults.
	retry := object(policy[termRetry])
	for _, field := range []string{"reset_obligation_refs", "compensation_refs"} {
		if _, present := retry[field]; !present {
			retry[field] = []any{}
		}
	}
	raw, err := value.Encode(policy, value.Runtime())
	if err != nil {
		return nil, fragmentInvalid()
	}
	return e.low.DefaultedObjectFragment(termInstantiatedScenarioV1, schemaDefinitionsPrefix+"ExecutionPolicy", raw, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
}

// ExecutionPolicyCapabilityGaps returns the first required authority or
// installed-support gap, in the portable policy's defined priority order.
func ExecutionPolicyCapabilityGaps(effective, support Fragment) ([]string, error) {
	if CheckFragment(effective, OperationExecutionPolicy) != nil || support != nil && CheckFragment(support, OperationPolicyCapabilities) != nil {
		return nil, fragmentInvalid()
	}
	policy := at(effective.Document(), termPolicy)
	retry := defaultMember(policy, termRetry, defaultOperationRetry())
	code := ""
	switch {
	case stringAt(policy, "response") == termResume:
		code = "continuation-unsupported"
	case stringAt(policy, "response") == responseNewTrial || stringAt(policy, stepExhausted) == responseNewTrial:
		code = "trial-allocation-authority-required"
	case slices.Contains([]string{retryReset, termCompensate}, stringAt(retry, "after_effect_policy")):
		code = "cleanup-authority-required"
	case support == nil:
		code = "response-unsupported"
	default:
		capability := support.Document()
		if !set(at(capability, "responses"))[stringAt(policy, "response")] {
			code = "response-unsupported"
		} else {
			attempts, ok := defaultNumber(retry, termMaxAttempts, 1)
			maximum, valid := defaultNumber(capability, termMaxAttempts, 1)
			afterEffects := defaultMember(capability, "after_effect_policies", []any{retryDisallow})
			if !ok || !valid || attempts.Cmp(maximum) > 0 || !set(afterEffects)[stringAt(retry, "after_effect_policy")] {
				code = "retry-unsupported"
			}
		}
	}
	if code == "" {
		return []string{}, nil
	}
	return []string{code}, nil
}
