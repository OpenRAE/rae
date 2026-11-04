package admission

import (
	"encoding/json"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/address"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) executionRules() map[string]definition {
	return map[string]definition{
		"execution-policy-executionpolicy":         {check: func(i validation.Invocation) error { return executionPolicy(i.Instance) }},
		"execution-policy-executionpolicydocument": {check: policyDocument},
		"execution-policy-executionpolicycapabilities": {check: func(i validation.Invocation) error {
			return require(fieldsUnique(i.Instance, "responses", "after_effect_policies") && !set(at(i.Instance, "responses"))["resume"])
		}},
		"execution-policy-effectiveexecutionpolicy":  {check: func(i validation.Invocation) error { return effectivePolicy(i.Instance) }},
		"execution-policy-planoperationmodel":        {check: func(i validation.Invocation) error { return operationPolicies(i.Instance) }},
		"execution-policy-preparationoperationmodel": {check: preparationOperation},
	}
}
func defaultMember(v any, field string, fallback any) any {
	if member, present := object(v)[field]; present {
		return member
	}
	return fallback
}
func defaultNumber(v any, field string, fallback int64) (*big.Rat, bool) {
	member, present := object(v)[field]
	if !present {
		return big.NewRat(fallback, 1), true
	}
	return number(member)
}
func retryPolicy(v any) error {
	if !fieldsUnique(v, "reset_obligation_refs", "compensation_refs") {
		return invalid()
	}
	for field, term := range map[string]string{"reset_obligation_refs": retryReset, "compensation_refs": "compensate"} {
		if (stringAt(v, "after_effect_policy") == term) != (len(array(at(v, field))) > 0) {
			return invalid()
		}
	}
	return nil
}
func executionPolicy(v any) error {
	if !fieldsUnique(v, "failure_classes", "effect_classes", fieldEvidenceRefs) {
		return invalid()
	}
	retry := defaultMember(v, termRetry, map[string]any{"max_attempts": json.Number("1"), "after_effect_policy": retryDisallow})
	if err := retryPolicy(retry); err != nil {
		return err
	}
	if err := operationRetryBounds(retry); err != nil {
		return err
	}
	attempts, _ := number(at(retry, "max_attempts"))
	repeats := attempts.Cmp(big.NewRat(1, 1)) > 0
	if (stringAt(v, "response") == termRetry) != repeats {
		return invalid()
	}
	if err := repetitionPolicy(v, retry, repeats); err != nil {
		return err
	}
	return recoveryPolicy(v, repeats)
}
func operationRetryBounds(retry any) error {
	attempts, ok := number(at(retry, "max_attempts"))
	if !ok || !attempts.IsInt() || attempts.Sign() < 1 || attempts.Cmp(big.NewRat(9007199254740991, 1)) > 0 {
		return invalid()
	}
	refs := append(stringsOf(at(retry, "reset_obligation_refs")), stringsOf(at(retry, "compensation_refs"))...)
	if len(refs) > 64 {
		return invalid()
	}
	for _, ref := range refs {
		if size := len([]rune(ref)); size < 1 || size > 256 {
			return invalid()
		}
	}
	return nil
}
func repetitionPolicy(v, retry any, repeats bool) error {
	delay, ok := defaultNumber(v, "delay_ms", 0)
	if !ok {
		return invalid()
	}
	if repeats {
		budget, valid := number(at(v, "budget_ms"))
		if !valid || delay.Cmp(budget) >= 0 || len(array(at(v, "effect_classes"))) == 0 || len(array(at(v, fieldEvidenceRefs))) == 0 {
			return invalid()
		}
	} else if len(array(at(v, "effect_classes"))) > 0 || delay.Sign() != 0 || stringAt(retry, "after_effect_policy") != retryDisallow {
		return invalid()
	}
	if stringAt(retry, "after_effect_policy") == retryDisallow {
		for _, effect := range stringsOf(at(v, "effect_classes")) {
			if effect != effectAbsent {
				return invalid()
			}
		}
	}
	return nil
}
func recoveryPolicy(v any, repeats bool) error {
	if (stringAt(v, "clock_basis") == strengthSemantic) != (at(v, "clock_ref") != nil) {
		return invalid()
	}
	exhausted := text(defaultMember(v, "on_exhausted", "terminate"))
	fresh := stringAt(v, "response") == responseNewTrial || exhausted == responseNewTrial
	if fresh != (at(v, "fresh_trial_limit") != nil) || (exhausted != "terminate" && !repeats) {
		return invalid()
	}
	switch stringAt(v, "response") {
	case "resume", "continue", "hold", termReconcile, responseNewTrial:
		return require(len(array(at(v, fieldEvidenceRefs))) > 0)
	default:
		return nil
	}
}
func policyDocument(i validation.Invocation) error {
	v := i.Instance
	if at(v, "default") != nil {
		if err := executionPolicy(at(v, "default")); err != nil {
			return err
		}
	}
	identities := []string{}
	for _, rule := range array(at(v, "scopes")) {
		if err := executionPolicy(at(rule, termPolicy)); err != nil {
			return err
		}
		if !canonicalPointer(stringAt(rule, "scope")) {
			return invalid()
		}
		namespace := stringsOf(at(rule, "namespace"))
		if at(v, "default") != nil && len(namespace) == 0 && stringAt(rule, "scope") == "" {
			return invalid()
		}
		identities = append(identities, join(append(namespace, stringAt(rule, "scope"))...))
	}
	return require(unique(identities))
}
func canonicalPointer(pointer string) bool {
	return pointer == "" || strings.HasPrefix(pointer, "/") && jsonpointer.FromTokens(jsonpointer.Tokens(pointer)) == pointer
}
func pointerContains(parent, child string) bool {
	if !canonicalPointer(parent) || !canonicalPointer(child) {
		return false
	}
	parents, children := jsonpointer.Tokens(parent), jsonpointer.Tokens(child)
	return len(parents) <= len(children) && slices.Equal(parents, children[:len(parents)])
}
func effectivePolicy(v any) error {
	if err := executionPolicy(at(v, termPolicy)); err != nil {
		return err
	}
	if !sameKeys(at(v, "evidence_requirements"), set(at(v, termPolicy, fieldEvidenceRefs))) {
		return invalid()
	}
	namespace, scope, found := strings.Cut(stringAt(v, "governing_scope"), "#")
	if !found || namespace != strings.Join(stringsOf(at(v, "namespace")), ".") {
		return invalid()
	}
	if scope == "/" {
		scope = ""
	}
	application := stringAt(v, "scope")
	if !pointerContains(scope, application) {
		return invalid()
	}
	unit := "native-operation"
	if strings.HasPrefix(application, "/workflows/") && strings.Contains(application, "/steps/") {
		unit = "workflow-step"
	}
	return require(text(defaultMember(v, "retry_unit", "native-operation")) == unit)
}
func operationPolicies(v any) error {
	policies := append([]any{}, array(at(v, "execution_policy_scopes"))...)
	if primary := at(v, "execution_policy"); primary != nil {
		policies = append(policies, primary)
	}
	if !unique(rowIDs(policies, "scope")) {
		return invalid()
	}
	for _, policy := range policies {
		if err := effectivePolicy(policy); err != nil {
			return err
		}
	}
	return nil
}
func preparationOperation(i validation.Invocation) error {
	v := i.Instance
	if err := operationPolicies(v); err != nil {
		return err
	}
	compiled := stringAt(v, "address")
	allowed := map[string]bool{termNetwork: true, termNode: true, "feature-binding": true, "content-placement": true, "account-placement": true, "domain-controller-placement": true, "generated-artifact": true, "persistent-volume": true}
	if !address.Valid(compiled) || !strings.HasPrefix(compiled, "provision.") || !allowed[stringAt(v, "resource_type")] {
		return invalid()
	}
	return require(value.Validate(defaultMember(v, "payload", map[string]any{}), value.Default()) == nil)
}
