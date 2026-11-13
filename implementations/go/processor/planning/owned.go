package planning

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

type executionPlan struct {
	preparation                json.RawMessage
	materializationSource      json.RawMessage
	materializationDiagnostics []diagnostic.Diagnostic
	augmentationScopeRequired  bool
	purpose                    string
	profileAuthority           *binding.PlanRealizationProfilesV1
	policyDiagnostics          map[string][]diagnostic.Diagnostic
	provisioningDiagnostics    []diagnostic.Diagnostic
	observations               []processor.ObservationDemand
	model                      processor.RuntimeModel
	manifest                   binding.BackendManifestV2
	provisioning               binding.ProvisioningPlanV1
	orchestration              binding.OrchestrationPlanV1
	evaluation                 binding.EvaluationPlanV1
	context                    PlanningContext
	diagnostics                []diagnostic.Diagnostic
	resources                  map[string]plannedResource
	operations                 map[string][]planOperation
}

func (*executionPlan) plannerProduced() {
	// This unexported marker seals the handle to its native owner.
}
func (plan *executionPlan) Valid() bool {
	for _, finding := range plan.diagnostics {
		if finding.Severity == "error" || finding.Severity == "" {
			return false
		}
	}
	return true
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func (plan *executionPlan) Model() processor.RuntimeModel       { return plan.model }
func (plan *executionPlan) Manifest() binding.BackendManifestV2 { return copyTransport(plan.manifest) }
func (plan *executionPlan) Provisioning() binding.ProvisioningPlanV1 {
	return copyTransport(plan.provisioning)
}
func (plan *executionPlan) Orchestration() binding.OrchestrationPlanV1 {
	return copyTransport(plan.orchestration)
}
func (plan *executionPlan) Evaluation() binding.EvaluationPlanV1 {
	return copyTransport(plan.evaluation)
}
func (plan *executionPlan) Context() PlanningContext { return copyContext(plan.context) }

func invalidPlan() error { return fault.New(fault.InvalidInput, "processor-plan-invalid", nil) }

//nolint:ireturn // Each generated instantiation returns its concrete transport type without a runtime interface.
func fieldValue[T any](field binding.Field[T]) T { result, _ := field.Value(); return result }

//nolint:ireturn // Each generated instantiation returns its concrete transport type without a runtime interface.
func copyTransport[T any](input T) T {
	raw, err := json.Marshal(input)
	if err != nil {
		panic("planning: invalid owned transport")
	}
	var result T
	if json.Unmarshal(raw, &result) != nil {
		panic("planning: invalid owned transport")
	}
	return result
}
func copyScope(input *Scope) *Scope {
	if input == nil {
		return nil
	}
	copyText := func(text *string) *string {
		if text == nil {
			return nil
		}
		cloned := *text
		return &cloned
	}
	return &Scope{TargetName: copyText(input.TargetName), RunID: copyText(input.RunID), InstantiationID: copyText(input.InstantiationID)}
}
func copyAvailability(input []ArtifactAvailability) []ArtifactAvailability {
	output := slices.Clone(input)
	for i := range output {
		entry := &output[i]
		entry.AvailableArtifactDigests = slices.Clone(entry.AvailableArtifactDigests)
		entry.AvailableCandidateIDs = slices.Clone(entry.AvailableCandidateIDs)
		entry.VerifiedLockedInputIDs = slices.Clone(entry.VerifiedLockedInputIDs)
		entry.SatisfiedConstraintIDs = slices.Clone(entry.SatisfiedConstraintIDs)
		entry.AvailableMaterializationSpecificationDigests = slices.Clone(entry.AvailableMaterializationSpecificationDigests)
		entry.VerifiedIntegrityRefs = slices.Clone(entry.VerifiedIntegrityRefs)
		entry.VerifiedAuthenticityRefs = slices.Clone(entry.VerifiedAuthenticityRefs)
		entry.VerifiedAdmissionRefs = slices.Clone(entry.VerifiedAdmissionRefs)
		entry.VerifiedProvenanceRefs = slices.Clone(entry.VerifiedProvenanceRefs)
		entry.VerifiedEvidenceRefs = slices.Clone(entry.VerifiedEvidenceRefs)
	}
	return output
}
func copyContext(input PlanningContext) PlanningContext {
	result := input
	result.Snapshot = copyTransport(input.Snapshot)
	result.Scope = copyScope(input.Scope)
	result.ApparatusDecisions = maps.Clone(input.ApparatusDecisions)
	result.ArtifactAvailability = copyAvailability(input.ArtifactAvailability)
	result.ProfileContext = copyTransport(input.ProfileContext)
	result.ProcessorManifest = copyTransport(input.ProcessorManifest)
	result.RealizationEnvelope = copyTransport(input.RealizationEnvelope)
	return result
}
func copyDiagnostics(input []diagnostic.Diagnostic) []diagnostic.Diagnostic {
	result := slices.Clone(input)
	for i := range result {
		if input[i].Range != nil {
			cloned := *input[i].Range
			result[i].Range = &cloned
		}
	}
	return result
}

type mixedControlAdmission struct{ model processor.RuntimeModel }

func (*mixedControlAdmission) mixedControlAdmission() {
	// This unexported marker seals the handle to its native owner.
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func (admission *mixedControlAdmission) Model() processor.RuntimeModel { return admission.model }

// NewMixedControlAdmission binds explicit mixed-control admission to a native model.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func NewMixedControlAdmission(model processor.RuntimeModel) (MixedControlAdmission, error) {
	owned, err := processor.AdmitRuntimeModel(model)
	if err != nil {
		return nil, err
	}
	return &mixedControlAdmission{model: owned}, nil
}

// ObservationOwner selects the established last actionable backend boundary.
func (plan *executionPlan) ObservationOwner() string {
	for _, domain := range []string{termOrchestration, termEvaluation} {
		for _, operation := range plan.operations[domain] {
			if operation.Action != termUnchanged {
				return domain
			}
		}
	}
	return termProvisioning
}
