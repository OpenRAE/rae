package planning

import (
	"bytes"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

func (plan *executionPlan) attachExecutionPolicies(policies []processor.ExecutionPolicy) error {
	plan.policyDiagnostics = map[string][]diagnostic.Diagnostic{}
	if len(policies) == 0 {
		return nil
	}
	owner, err := planOwner()
	if err != nil {
		return err
	}
	support, err := plan.executionPolicySupport(owner)
	if err != nil {
		return err
	}
	byAddress := map[string][]processor.ExecutionPolicy{}
	for _, policy := range policies {
		byAddress[policy.Address] = append(byAddress[policy.Address], policy)
	}
	for _, domain := range []string{termProvisioning, termOrchestration, termEvaluation} {
		for i := range plan.operations[domain] {
			operation := &plan.operations[domain][i]
			findings, err := attachOperationPolicies(operation, byAddress[operation.Address], support, domain)
			if err != nil {
				return err
			}
			plan.policyDiagnostics[domain] = append(plan.policyDiagnostics[domain], findings...)
		}
	}
	return nil
}

//nolint:ireturn // The shared admission owner returns an optional exact native capability handle.
func (plan *executionPlan) executionPolicySupport(owner *admission.Validator) (admission.Fragment, error) {
	var support admission.Fragment
	if raw := fieldValue(plan.manifest.ExecutionPolicy); len(raw) > 0 && !bytes.Equal(raw, []byte(termNull)) {
		decoder := json.NewDecoder(bytes.NewReader(raw))
		decoder.UseNumber()
		var input any
		if decoder.Decode(&input) != nil {
			return nil, invalidPlan()
		}
		var err error
		support, err = admission.AdmitFragment(owner, admission.OperationPolicyCapabilities, input, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
		if err != nil {
			return nil, err
		}
	}
	return support, nil
}
func attachOperationPolicies(operation *planOperation, policies []processor.ExecutionPolicy, support admission.Fragment, domain string) ([]diagnostic.Diagnostic, error) {
	findings := []diagnostic.Diagnostic{}
	for index, policy := range policies {
		projection := rawProjection(policy.Policy.Document())
		if index == 0 {
			operation.ExecutionPolicy = projection
		} else {
			operation.ExecutionPolicyScopes = append(operation.ExecutionPolicyScopes, projection)
		}
		gaps, err := admission.ExecutionPolicyCapabilityGaps(policy.Policy, support)
		if err != nil {
			return nil, err
		}
		if len(gaps) > 0 {
			findings = append(findings, planDiagnostic("execution-policy."+gaps[0], domain, operation.Address, "The selected realization cannot establish the requested execution policy; no alternative is authorized."))
		}
	}
	return findings, nil
}
