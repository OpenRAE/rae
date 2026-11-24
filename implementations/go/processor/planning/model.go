package planning

import (
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

// Result contains the owner-issued plan, resource counts, and ordered diagnostics.
type Result struct {
	Plan        ExecutionPlan
	Resources   map[string]int
	Diagnostics []diagnostic.Diagnostic
}

// ExecutionPlan is issued only by the planner. Projections return copies.
type ExecutionPlan interface {
	Valid() bool
	Model() processor.RuntimeModel
	Manifest() binding.BackendManifestV2
	Provisioning() binding.ProvisioningPlanV1
	Orchestration() binding.OrchestrationPlanV1
	Evaluation() binding.EvaluationPlanV1
	Context() PlanningContext
	ObservationOwner() string
	plannerProduced()
}

// Scope supplies authoritative target, run, and instantiation identities.
type Scope struct{ TargetName, RunID, InstantiationID *string }

// Closure records a frozen apparatus decision for a delegated requirement.
type Closure string

// OpenWorld and ClosedWorld are the supported apparatus closure decisions.
const (
	OpenWorld   Closure = "open-world"
	ClosedWorld Closure = "closed-world"
)

// ApparatusDefaultResolver decides one delegated requirement against the selected manifest.
type ApparatusDefaultResolver interface {
	Resolve(requirement admission.Fragment, manifest binding.BackendManifestV2) (Closure, error)
}

// ArtifactAvailability records explicit availability and verified evidence for one artifact requirement.
type ArtifactAvailability = realization.ArtifactAvailability

// MixedControlAdmission retains the exact model admitted for mixed-control planning.
type MixedControlAdmission interface {
	Model() processor.RuntimeModel
	mixedControlAdmission()
}

// Options supplies explicit snapshot, target, profile, and realization inputs for planning.
type Options struct {
	Snapshot              *binding.RuntimeSnapshotV1
	Scope                 *Scope
	ApparatusDefault      ApparatusDefaultResolver
	ArtifactAvailability  []ArtifactAvailability
	ProfileContext        *binding.DomainProfileResolutionContextV1
	MixedControlAdmission MixedControlAdmission
	RefreshEvaluation     bool
	ProcessorManifest     *binding.ProcessorManifestV2
	RealizationEnvelope   *binding.RealizationEnvelopeV1
}

// RequirementKey identifies a delegated concern without relying on rendered payloads.
type RequirementKey struct{ Address, FieldPath, RequirementKind string }

// PlanningContext retains copied inputs and frozen apparatus decisions for the plan.
//
//nolint:revive // The reviewed consumer API fixes this public type name.
type PlanningContext struct {
	OriginalModel         processor.RuntimeModel
	Snapshot              binding.RuntimeSnapshotV1
	Scope                 *Scope
	ApparatusDecisions    map[RequirementKey]Closure
	ArtifactAvailability  []ArtifactAvailability
	ProfileContext        *binding.DomainProfileResolutionContextV1
	MixedControlAdmission MixedControlAdmission
	RefreshEvaluation     bool
	ProcessorManifest     *binding.ProcessorManifestV2
	RealizationEnvelope   *binding.RealizationEnvelopeV1
}

// Actions counts reconciliation actions across the three execution phases.
type Actions struct{ Create, Update, Delete, Unchanged int }

// Reconciliation retains baseline and candidate plans with the assumed baseline state.
type Reconciliation struct {
	Baseline, Candidate Result
	Snapshot            binding.RuntimeSnapshotV1
	Actions             *Actions
}
