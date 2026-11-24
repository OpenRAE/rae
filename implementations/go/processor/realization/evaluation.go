package realization

import (
	"bytes"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

// EvaluationOptions supplies independent apparatus declarations for pure readback checks.
type EvaluationOptions struct {
	Manifest             *binding.BackendManifestV2
	Envelope             *binding.RealizationEnvelopeV1
	ArtifactAvailability []ArtifactAvailability
}

// Provenance names one realized concern without retaining its value.
type Provenance struct {
	Address, FieldPath, Domain, Kind, Posture, Provenance, GoverningScope string
	ArtifactSatisfaction                                                  admission.Fragment
}

// Evaluation keeps ordered readback findings and value-free provenance.
type Evaluation struct {
	Diagnostics []diagnostic.Diagnostic
	Provenance  []Provenance
}

type evaluatedOperation struct {
	Address      string         `json:"address"`
	Action       string         `json:"action"`
	ResourceType string         `json:"resource_type"`
	Payload      map[string]any `json:"payload"`
}
type evaluatedEntry struct {
	Payload map[string]any `json:"payload"`
}
type evaluatedObservation struct {
	Address             string         `json:"address"`
	FieldPath           string         `json:"field_path"`
	Domain              string         `json:"domain"`
	Kind                string         `json:"requirement_kind"`
	Scope               string         `json:"verification_scope"`
	Strength            string         `json:"observation_strength"`
	OperatingSystem     map[string]any `json:"operating_system"`
	Value               any            `json:"observed_value"`
	EnvelopeDigest      string         `json:"envelope_digest"`
	ConfigurationDigest string         `json:"configuration_digest"`
	OperationID         string         `json:"operation_id"`
	BindingVerified     bool           `json:"binding_verified"`
}
type evaluatedPlan struct {
	Operations  []evaluatedOperation         `json:"operations"`
	Envelope    json.RawMessage              `json:"realization_envelope"`
	OperationID string                       `json:"operation_id"`
	Demands     []evaluatedObservationDemand `json:"observation_demands"`
	Authority   []plannedAuthority           `json:"realization_authority"`
	Constraints []plannedConstraint          `json:"realization_constraints"`
}
type evaluatedSnapshot struct {
	Entries      map[string]evaluatedEntry `json:"entries"`
	Observations []evaluatedObservation    `json:"realization_observations"`
	Envelope     json.RawMessage           `json:"realization_envelope"`
}
type evaluationState struct {
	options           EvaluationOptions
	plan              evaluatedPlan
	snapshot          evaluatedSnapshot
	operations        map[string]evaluatedOperation
	observations      map[observationIdentity]evaluatedObservation
	declarations      map[string][]supportDeclaration
	artifacts         map[string]ArtifactAvailability
	plannedViews      []Requirement
	plannedViewError  error
	plannedViewsReady bool
}
type missingConcern struct{}
type observationIdentity struct {
	requirementIdentity

	domain string
}

// Evaluate checks returned values against an admitted plan without applying it
// or publishing the snapshot. Findings retain requirement order and no values.
func Evaluate(requirements []Requirement, plan binding.ProvisioningPlanV1, snapshot binding.RuntimeSnapshotV1, options EvaluationOptions) (Evaluation, error) {
	result := Evaluation{Diagnostics: []diagnostic.Diagnostic{}, Provenance: []Provenance{}}
	if err := checkRequirementBatch(requirements); err != nil {
		return Evaluation{}, err
	}
	state, err := newEvaluationState(plan, snapshot, options)
	if err != nil {
		return Evaluation{}, err
	}
	for _, requirement := range requirements {
		finding, provenance, err := state.evaluate(requirement)
		if err != nil {
			return Evaluation{}, err
		}
		if finding != nil {
			result.Diagnostics = append(result.Diagnostics, *finding)
		}
		if provenance != nil {
			result.Provenance = append(result.Provenance, *provenance)
		}
	}
	return result, nil
}
func newEvaluationState(plan binding.ProvisioningPlanV1, snapshot binding.RuntimeSnapshotV1, options EvaluationOptions) (*evaluationState, error) {
	state, err := newEvaluationPlan(plan, options)
	if err != nil {
		return nil, err
	}
	if err := decodeEvaluationTransport("runtime-snapshot-v1", snapshot, &state.snapshot); err != nil {
		return nil, err
	}
	if err := state.checkEvaluationTarget(); err != nil {
		return nil, err
	}
	state.indexObservations()
	return state, nil
}
func newEvaluationPlan(plan binding.ProvisioningPlanV1, options EvaluationOptions) (*evaluationState, error) {
	state := &evaluationState{options: options, operations: map[string]evaluatedOperation{}, observations: map[observationIdentity]evaluatedObservation{}, declarations: map[string][]supportDeclaration{}}
	var err error
	state.artifacts, err = artifactAvailabilityIndex(options.ArtifactAvailability)
	if err != nil {
		return nil, err
	}

	if err := decodeEvaluationTransport("provisioning-plan-v1", plan, &state.plan); err != nil {
		return nil, err
	}

	for _, operation := range state.plan.Operations {
		state.operations[operation.Address] = operation
	}
	return state, nil
}
func (s *evaluationState) checkEvaluationTarget() error {
	options := s.options
	if options.Manifest != nil {
		if err := checkResolutionTarget(ResolveOptions{Manifest: *options.Manifest, Envelope: options.Envelope}); err != nil {
			return err
		}
	} else if options.Envelope != nil {
		return invalidRealization()
	}
	return nil
}

func (s *evaluationState) indexObservations() {
	for _, observation := range s.snapshot.Observations {
		key := observationIdentity{requirementIdentity{observation.Address, observation.FieldPath, observation.Kind}, observation.Domain}
		if observation.Kind == termOperatingSystem {
			key.path = ""
		}
		// Keep the first disclosure, as the reference's ordered observation search does.
		if _, exists := s.observations[key]; !exists {
			s.observations[key] = observation
		}
	}
}
func decodeEvaluationTransport(contract string, input, output any) error {
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
	if err := admission.CheckTransport(input, limits); err != nil {
		return err
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return invalidRealization()
	}
	owner, err := realizationOwner()
	if err != nil {
		return err
	}
	if err := owner.CheckPortable(contract, raw, limits); err != nil {
		return err
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if decoder.Decode(output) != nil {
		return invalidRealization()
	}
	return nil
}
func (s *evaluationState) evaluate(requirement Requirement) (*diagnostic.Diagnostic, *Provenance, error) {
	operation, exists := s.operations[requirement.Address]
	if !exists || operation.Action == "delete" {
		return nil, nil, nil
	}
	if requirement.ArtifactRequirement != nil {
		return s.evaluateArtifact(requirement)
	}

	if requirement.Kind == termComputeSubstrate {
		return s.evaluateSubstrate(requirement, operation)
	}
	definition, registered := concernDefinitionFor(requirement.Kind)
	if !registered || requirement.Posture == nil {
		return nil, nil, nil
	}
	realized := s.concernValue(requirement, definition.payload)
	if requirement.StructureError {
		return silentApproximation(requirement), nil, nil
	}
	if *requirement.Posture == termOpen && requirement.Structure == nil && requirement.Constraint == nil {
		return s.evaluateOpen(requirement, realized)
	}
	declared, present := payloadConcern(operation.Payload, definition.payload)
	if !present {
		return nil, nil, nil
	}
	return s.evaluateDeclared(requirement, declared, realized)
}
func (s *evaluationState) observation(requirement Requirement) (evaluatedObservation, bool) {
	key := observationIdentity{requirementIdentity{requirement.Address, requirement.FieldPath, requirement.Kind}, requirement.Domain}
	if observationKind(requirement.Kind) == termOperatingSystem {
		key.kind = termOperatingSystem
		key.path = ""
	}
	observation, present := s.observations[key]
	return observation, present && observation.Domain == requirement.Domain
}
func (s *evaluationState) concernValue(requirement Requirement, path []string) any {
	if observationKind(requirement.Kind) == termOperatingSystem {
		observation, present := s.observation(requirement)
		if !present || observation.OperatingSystem == nil {
			return missingConcern{}
		}
		field := map[string]string{termOsFamily: "family", termOsDistribution: "distribution", termOsVersion: "version"}[requirement.Kind]
		value, present := observation.OperatingSystem[field]
		if !present {
			return missingConcern{}
		}
		return value
	}
	entry, present := s.snapshot.Entries[requirement.Address]
	if !present {
		return missingConcern{}
	}
	value, present := payloadConcern(entry.Payload, path)
	if !present {
		return missingConcern{}
	}
	return value
}
func missingValue(value any) bool { _, missing := value.(missingConcern); return missing }
func realizationProvenance(requirement Requirement, honoured bool) *Provenance {
	provenance := "backend-realized"
	if honoured && (*requirement.Posture == termExact || requirement.Provenance == termProcessorDerived) {
		provenance = requirement.Provenance
	}
	return &Provenance{Address: requirement.Address, FieldPath: requirement.FieldPath, Domain: requirement.Domain, Kind: requirement.Kind, Posture: *requirement.Posture, Provenance: provenance, GoverningScope: requirement.GoverningScope}
}
func silentApproximation(requirement Requirement) *diagnostic.Diagnostic {
	return supportFinding(requirement, "runtime.backend-contract-invalid", "Backend did not realize the exact '"+requirement.Kind+"' requirement at '"+requirement.FieldPath+"' as the author declared it (the realized value is absent or differs); silent approximation or omission of an exact declaration is forbidden (SEM-218 I2).")
}
func invalidObservation(requirement Requirement) *diagnostic.Diagnostic {
	return supportFinding(requirement, "runtime.backend-contract-invalid", "Backend returned an invalid closed observation for '"+requirement.Kind+"' at '"+requirement.FieldPath+"'; the realized concern cannot be admitted or persisted.")
}
