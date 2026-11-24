package planning

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

type authorityWire struct {
	Address      string          `json:"address"`
	Path         string          `json:"field_path"`
	Domain       string          `json:"domain"`
	Kind         string          `json:"requirement_kind"`
	Pointer      string          `json:"payload_pointer"`
	Mode         string          `json:"mode"`
	Source       string          `json:"source"`
	Provenance   string          `json:"provenance"`
	Scope        *string         `json:"governing_scope"`
	Bounds       []boundWire     `json:"bounds"`
	Verification *string         `json:"verification_scope"`
	Strength     *string         `json:"required_observation_strength"`
	Structure    json.RawMessage `json:"structure,omitempty"`
	Constraint   json.RawMessage `json:"constraint_document,omitempty"`
	Binding      string          `json:"constraint_binding,omitempty"`
}
type boundWire struct {
	Identity *string `json:"identity_digest"`
	Pointer  string  `json:"value_pointer"`
	Domain   any     `json:"domain"`
}
type constraintWire struct {
	Address    string `json:"address"`
	Path       string `json:"field_path"`
	Concern    string `json:"concern"`
	Posture    string `json:"posture"`
	Domain     any    `json:"value_domain"`
	Scope      string `json:"governing_scope"`
	Provenance string `json:"provenance"`
}

func (plan *executionPlan) project(resolved realization.Resolution) error {
	authority, diagnostics := projectAuthority(plan.resources, resolved)
	plan.diagnostics = append(plan.diagnostics, diagnostics...)
	plan.diagnostics = append(plan.diagnostics, plan.provisioningDiagnostics...)
	for _, domain := range []string{termProvisioning, termOrchestration, termEvaluation} {
		plan.diagnostics = append(plan.diagnostics, plan.policyDiagnostics[domain]...)
	}
	plan.diagnostics = append(plan.diagnostics, plan.materializationDiagnostics...)
	constraints := projectComputeConstraints(resolved.Requirements)
	var runID, instantiationID *string
	if plan.context.Scope != nil {
		runID, instantiationID = plan.context.Scope.RunID, plan.context.Scope.InstantiationID
	}
	provisioning := plan.phaseProjection(termProvisioning)
	provisioning["profile_authority"] = plan.profileAuthority
	if plan.profileAuthority == nil {
		delete(provisioning, "profile_authority")
	}
	if len(plan.preparation) > 0 {
		provisioning["preparation"] = plan.preparation
	}
	provisioning["realization_authority"] = authority
	provisioning["realization_constraints"] = constraints
	provisioning["realization_envelope"] = fieldValue(plan.manifest.RealizationEnvelope)
	provisioning["run_id"], provisioning["instantiation_id"], provisioning["operation_id"] = runID, instantiationID, nil
	orchestration := plan.phaseProjection(termOrchestration)
	orchestration["startup_order"] = applyOrder(plan.operations[termOrchestration])
	evaluation := plan.phaseProjection(termEvaluation)
	evaluation["startup_order"] = applyOrder(plan.operations[termEvaluation])
	evaluation["run_id"], evaluation["instantiation_id"] = runID, instantiationID
	if err := emitPhase("provisioning-plan-v1", provisioning, &plan.provisioning); err != nil {
		return err
	}
	if err := emitPhase("orchestration-plan-v1", orchestration, &plan.orchestration); err != nil {
		return err
	}
	return emitPhase("evaluation-plan-v1", evaluation, &plan.evaluation)
}

func projectComputeConstraints(requirements []realization.Requirement) []constraintWire {
	constraints := []constraintWire{}
	for _, requirement := range requirements {
		if requirement.Kind == "compute-substrate" && requirement.Posture != nil {
			scope := requirement.GoverningScope
			if scope == "" {
				scope = "#/"
			}
			provenance := requirement.ConstraintProvenance
			if provenance == "" {
				provenance = "author-declared"
			}
			var domain any
			if requirement.ValueDomain != nil {
				domain = requirement.ValueDomain.Document()
			}
			constraints = append(constraints, constraintWire{Address: requirement.Address, Path: requirement.FieldPath, Concern: requirement.Kind, Posture: *requirement.Posture, Domain: domain, Scope: scope, Provenance: provenance})
		}
	}

	return constraints
}

func (plan *executionPlan) phaseProjection(domain string) map[string]any {
	demands := make([]json.RawMessage, len(plan.observations))
	for i, demand := range plan.observations {
		demands[i] = rawProjection(demand.Demand.Document())
	}
	findings := []diagnostic.Diagnostic{}
	if domain == termProvisioning {
		findings = append(findings, plan.provisioningDiagnostics...)
	}
	findings = append(findings, plan.policyDiagnostics[domain]...)
	findings = append(findings, plan.materializationDiagnostics...)
	result := map[string]any{"operations": plan.operations[domain], "diagnostics": phaseDiagnostics(findings), "observation_demands": demands}
	if plan.purpose != "" {
		result["purpose"] = plan.purpose
	}
	if len(plan.materializationSource) > 0 {
		result["materialization_source"] = materializationSourceWire(plan.materializationSource)
	}
	if plan.augmentationScopeRequired {
		result["augmentation_scope_required"] = true
	}
	return result
}

func applyOrder(operations []planOperation) []string {
	result := []string{}
	for _, operation := range operations {
		if operation.Action != termDelete {
			result = append(result, operation.Address)
		}
	}
	return result
}
func textPointer(text string) *string {
	if text == "" {
		return nil
	}
	return &text
}
func rawProjection(input any) json.RawMessage {
	raw, err := json.Marshal(input)
	if err != nil {
		panic("planning: invalid owned wire projection")
	}
	return raw
}

func emitPhase[T any](contract string, wire any, output *T) error {
	if err := value.ValidateProjected(wire, value.Plan(), planProjectionValue); err != nil {
		return err
	}
	raw, err := json.Marshal(wire)
	if err != nil {
		return invalidPlan()
	}
	if err := json.Unmarshal(raw, output); err != nil {
		return invalidPlan()
	}
	return checkTransport(contract, output)
}

func projectAuthority(resources map[string]plannedResource, resolved realization.Resolution) ([]authorityWire, []diagnostic.Diagnostic) {
	type identity struct{ address, path, kind string }
	requirements := map[identity]realization.Requirement{}
	for _, requirement := range resolved.Requirements {
		requirements[identity{requirement.Address, requirement.FieldPath, requirement.Kind}] = requirement
	}
	result := []authorityWire{}
	diagnostics := []diagnostic.Diagnostic{}
	for _, authority := range resolved.Authority {
		resource, present := resources[authority.Address]
		if !present || resource.facts.Domain != termProvisioning {
			continue
		}
		requirement := requirements[identity{authority.Address, authority.FieldPath, authority.Concern}]
		if requirement.StructureError || requirement.RecursivePending {
			diagnostics = append(diagnostics, unsafeAuthority(authority))
			continue
		}
		wire := authorityWire{Address: authority.Address, Path: authority.FieldPath, Domain: authority.Domain, Kind: authority.Concern, Pointer: jsonpointer.FromTokens(authority.PayloadPath), Mode: authority.Posture, Source: authority.Source, Provenance: authority.Provenance, Scope: textPointer(authority.GoverningScope), Bounds: []boundWire{}, Verification: textPointer(authority.ObservationScope), Strength: textPointer(authority.ObservationStrength)}
		if !projectAuthorityBounds(&wire, requirement) {
			diagnostics = append(diagnostics, unsafeAuthority(authority))
			continue
		}

		result = append(result, wire)
	}
	return result, diagnostics
}

func projectAuthorityBounds(wire *authorityWire, requirement realization.Requirement) bool {
	if requirement.Constraint != nil {
		wire.Constraint = rawProjection(requirement.Constraint.Document())
		wire.Binding = requirement.ConstraintBinding
	}
	if requirement.Structure != nil {
		wire.Structure = rawProjection(requirement.Structure.Document())
	}
	if wire.Mode == "constrained" {
		if requirement.ValueDomain != nil {
			wire.Bounds = append(wire.Bounds, boundWire{Domain: requirement.ValueDomain.Document()})
		}
		for _, constraint := range requirement.ValueConstraints {
			wire.Bounds = append(wire.Bounds, boundWire{Identity: textPointer(constraint.IdentityDigest), Pointer: "/" + constraint.Leaf, Domain: map[string]any{"kind": "enum", "values": constraint.AllowedValues.Document()}})
		}
		if len(wire.Bounds) == 0 && requirement.Constraint == nil {
			return false
		}
	}
	return true
}

func unsafeAuthority(authority realization.Authority) diagnostic.Diagnostic {
	return planDiagnostic("realization.authority-bound-unavailable", authority.Domain, authority.Address, "No publication-safe typed author bound is available for '"+authority.Concern+"' at '"+authority.FieldPath+"'. This mixed demand needs an owning collection identity and representable leaf bounds; use supported bounded forms or extend the concern contract.")
}
