package realization

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func plannedUnexpected(err error) error {
	if category, _ := fault.CategoryOf(err); category == fault.InvalidInput {
		return nil
	}
	return err
}
func plannedViewFailure(err error, plan evaluatedPlan) (*diagnostic.Diagnostic, error) {
	if unexpected := plannedUnexpected(err); unexpected != nil {
		return nil, unexpected
	}
	return plannedRuntimeViewFinding(plan), nil
}
func plannedEvaluationFailure(err error, plan evaluatedPlan) (Evaluation, error) {
	finding, unexpected := plannedViewFailure(err, plan)
	if unexpected != nil {
		return Evaluation{}, unexpected
	}
	return Evaluation{Diagnostics: []diagnostic.Diagnostic{*finding}, Provenance: []Provenance{}}, nil
}
func plannedOptionalValue(raw []byte) (any, error) {
	if len(raw) == 0 {
		return nil, nil //nolint:nilnil // An omitted published optional carrier projects to JSON null.
	}
	return nativeValue(raw)
}

type plannedAuthority struct {
	Address      string          `json:"address"`
	FieldPath    string          `json:"field_path"`
	Domain       string          `json:"domain"`
	Kind         string          `json:"requirement_kind"`
	Pointer      string          `json:"payload_pointer"`
	Mode         string          `json:"mode"`
	Source       string          `json:"source"`
	Provenance   string          `json:"provenance"`
	Scope        string          `json:"governing_scope"`
	Verification string          `json:"verification_scope"`
	Strength     string          `json:"required_observation_strength"`
	Bounds       []plannedBound  `json:"bounds"`
	Structure    json.RawMessage `json:"structure"`
	Constraint   json.RawMessage `json:"constraint_document"`
	Binding      string          `json:"constraint_binding"`
}
type plannedBound struct {
	Identity string          `json:"identity_digest"`
	Pointer  string          `json:"value_pointer"`
	Domain   json.RawMessage `json:"domain"`
}
type plannedConstraint struct {
	Address    string          `json:"address"`
	FieldPath  string          `json:"field_path"`
	Concern    string          `json:"concern"`
	Posture    string          `json:"posture"`
	Domain     json.RawMessage `json:"value_domain"`
	Scope      string          `json:"governing_scope"`
	Provenance string          `json:"provenance"`
}

// PlannedAuthorityDiagnostics checks complete portable authority against its
// operations and independent selected apparatus before any readback claim.
func PlannedAuthorityDiagnostics(plan binding.ProvisioningPlanV1, options EvaluationOptions) ([]diagnostic.Diagnostic, error) {
	state, err := newEvaluationPlan(plan, options)
	if err != nil {
		return nil, err
	}
	if err := state.checkEvaluationTarget(); err != nil {
		return nil, err
	}
	return state.plannedDiagnostics()
}

// PlannedRequirements recovers non-closed native concern views from bounded,
// admitted portable authority. It derives no authored or observation authority.
func PlannedRequirements(plan binding.ProvisioningPlanV1) ([]Requirement, error) {
	state, err := newEvaluationPlan(plan, EvaluationOptions{})
	if err != nil {
		return nil, err
	}
	return state.plannedRequirements()
}

// EvaluatePlanned checks portable plan authority before deriving ordered,
// value-free readback findings and provenance through the registered evaluator.
func EvaluatePlanned(plan binding.ProvisioningPlanV1, snapshot binding.RuntimeSnapshotV1, options EvaluationOptions) (Evaluation, error) {
	state, err := newEvaluationState(plan, snapshot, options)
	if err != nil {
		return Evaluation{}, err
	}
	findings, err := state.plannedDiagnostics()
	if err != nil {
		return Evaluation{}, err
	}
	if len(findings) > 0 {
		return Evaluation{Diagnostics: findings, Provenance: []Provenance{}}, nil
	}
	return state.evaluatePlannedValues(false)
}

// CleanupPlannedDiagnostics validates original authority before relaxing only
// omitted flat open readback floors in a private cleanup view. It grants no
// successful realization provenance and preserves supplemental native bounds.
func CleanupPlannedDiagnostics(plan binding.ProvisioningPlanV1, snapshot binding.RuntimeSnapshotV1, requirements []Requirement, options EvaluationOptions) ([]diagnostic.Diagnostic, error) {
	if err := checkRequirementBatch(requirements); err != nil {
		return nil, err
	}
	state, err := newEvaluationState(plan, snapshot, options)
	if err != nil {
		return nil, err
	}
	findings, err := state.plannedDiagnostics()
	if err != nil || len(findings) > 0 {
		return findings, err
	}
	state.plan.Demands = nil
	result, err := state.evaluatePlannedValues(true)
	if err != nil {
		return nil, err
	}
	for _, requirement := range requirements {
		local := state.cleanupRequirement(requirement)
		finding, _, evaluateErr := state.evaluate(local)
		if evaluateErr != nil {
			return nil, evaluateErr
		}
		if finding != nil {
			result.Diagnostics = append(result.Diagnostics, *finding)
		}
	}
	return result.Diagnostics, nil
}

func (s *evaluationState) cleanupRequirement(requirement Requirement) Requirement {
	if requirement.Posture != nil && *requirement.Posture == termOpen && requirement.Structure == nil && requirement.Constraint == nil {
		definition, known := concernDefinitionFor(requirement.Kind)
		if !known || missingValue(s.concernValue(requirement, definition.payload)) {
			requirement.ObservationScope, requirement.ObservationStrength = "", ""
		}
	}
	return requirement
}

func plannedRuntimeViewFinding(plan evaluatedPlan) *diagnostic.Diagnostic {
	address := "runtime.realization-authority"
	for _, authority := range plan.Authority {
		if authority.Mode != termClosed {
			address = authority.Address
			break
		}
	}
	return &diagnostic.Diagnostic{Code: "realization.authority-demand-invalid", Domain: termRuntimeRealization, Address: address, Message: "Provisioning plan authority cannot reconstruct its canonical realization demand.", Severity: termError}
}

func plannedFailure(authority plannedAuthority, code, message string) *diagnostic.Diagnostic {
	return &diagnostic.Diagnostic{Code: code, Domain: authority.Domain, Address: authority.Address, Message: message, Severity: termError}
}

func plannedNativeFragment(raw json.RawMessage, profile admission.FragmentProfile) (admission.Fragment, error) { //nolint:ireturn // The closed native fragment is the existing shared owner.
	if len(raw) == 0 || string(raw) == "null" {
		return nil, nil //nolint:nilnil // Published nullable metadata has no fragment.
	}
	document, err := nativeValue(raw)
	if err != nil {
		return nil, invalidRealization()
	}
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	return admission.AdmitFragment(owner, profile, document, plannedFragmentLimits())
}
