// Package trial compiles acquired experiment authority into sealed trial plans.
package trial

import (
	"context"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// ParticipantManifestKey selects one exact participant manifest authority.
type ParticipantManifestKey = admission.ParticipantManifestKey

// ApparatusManifestKey selects one exact processor or backend manifest.
type ApparatusManifestKey = admission.ApparatusManifestKey

// ConfigurationValidatorKey names the validator declared by a configuration registry owner.
type ConfigurationValidatorKey struct{ ValidatorID, ValidatorVersion string }

// ControlContextProvider binds an installed control-context validator to the selected scenario.
type ControlContextProvider interface {
	ForScenario(ctx context.Context, family sdl.Scenario) (admission.ParticipantControlContextValidator, error)
}

// Limits bounds coordinate expansion, owner work and admitted plan bytes.
type Limits struct {
	MaxCoordinates, MaxDomainValuesPerPoint, MaxProductOutputs int
	MaxBindingsPerEntry, MaxDrawsPerEntry, MaxDiagnostics      int
	MaxMixedProfiles, MaxMixedContextWork, MaxPlanBytes        int
}

// MixedCompositionLimits bounds supplied composition graphs and their trusted resolution.
type MixedCompositionLimits struct {
	MaxSourceBytes, MaxJSONDepth, MaxJSONNodes, MaxComponents, MaxAllocations int
	MaxEdges, MaxPhases, MaxTransitions, MaxNestedProfiles, MaxContextWork    int
}

// Request contains all acquired inputs for deterministic trial compilation.
type Request struct {
	Family                                   sdl.Scenario
	Task                                     binding.ExperimentTaskV1
	Experiment                               validation.Value
	InputRefs, Apparatus, ExecutionAuthority admission.Fragment
	RealizationEnvelope                      validation.Value
	ApparatusManifests                       map[ApparatusManifestKey]admission.ApparatusManifest
	ParticipantManifests                     map[ParticipantManifestKey]binding.ParticipantImplementationManifestV1
	CaptureSpecs                             map[string]binding.ExperimentCaptureSpecV1
	RealizationAssignments                   map[string]admission.Fragment
	MixedProfiles, MixedRealizationEnvelopes map[string]validation.Value
	MixedProfileContexts                     map[string]admission.MixedCompositionContext
	SourcePlans                              map[string]binding.AdmittedTrialPlanV1
	Limits                                   Limits
	MixedCompositionLimits                   MixedCompositionLimits
	ParticipantConfigurationValidators       map[ConfigurationValidatorKey]admission.ParticipantConfigurationValidator
	ParticipantControlContextValidators      map[ConfigurationValidatorKey]admission.ParticipantControlContextValidator
	ParticipantControlContextFactories       map[ConfigurationValidatorKey]ControlContextProvider
}

// Result contains a complete sealed plan or safe domain diagnostics.
type Result struct {
	Plan        *binding.AdmittedTrialPlanV1
	Diagnostics []diagnostic.Diagnostic
}

// ScheduledEntry records one entry and its zero-based dispatch position.
type ScheduledEntry struct {
	PlanEntryID, RunID string
	DispatchOrdinal    int
}

// BatchSchedule records dispatch order and the admitted parallelism ceiling.
type BatchSchedule struct {
	PlanID, PlanDigest, SchedulingPolicyID string
	// AdmittedParallelismFloor and AdmittedParallelismCeiling come from the
	// authored trial_parallelism; both are one when it is absent.
	AdmittedParallelismFloor, AdmittedParallelismCeiling int
	Entries                                              []ScheduledEntry
}

// ReplacementRequest supplies the original allocation, parent evidence and retained history.
type ReplacementRequest struct {
	Compilation         Request
	OriginalPlan        binding.AdmittedTrialPlanV1
	RootEntryID         string
	ParentRun           binding.ExperimentRunV1
	CleanupReceipts     []binding.TrialCleanupReceiptV1
	PreviousAllocations []ReplacementResult
}

// ReplacementResult contains one immutable successor decision or safe refusal diagnostics.
type ReplacementResult struct {
	Plan                     *binding.AdmittedTrialPlanV1
	SupersededRun, ParentRun *binding.ExperimentRunV1
	CleanupReceipts          []binding.TrialCleanupReceiptV1
	Diagnostics              []diagnostic.Diagnostic
}

// RealizationInputs supplies the sealed entry authority and exact processor inputs.
type RealizationInputs struct {
	Plan                 binding.AdmittedTrialPlanV1
	Family               sdl.Scenario
	Experiment           validation.Value
	Task                 binding.ExperimentTaskV1
	CaptureSpecs         map[string]binding.ExperimentCaptureSpecV1
	ApparatusManifests   map[ApparatusManifestKey]admission.ApparatusManifest
	RealizationEnvelope  validation.Value
	BackendKey           ApparatusManifestKey
	ParticipantManifests map[ParticipantManifestKey]binding.ParticipantImplementationManifestV1
}

// Realization retains the native scenario and all three existing processor projections.
type Realization struct {
	Instantiated              sdl.InstantiatedScenario
	SnapshotDigest            string
	ExecutionPlan             planning.ExecutionPlan
	ProvisioningPlan          binding.ProvisioningPlanV1
	OrchestrationPlan         binding.OrchestrationPlanV1
	EvaluationPlan            binding.EvaluationPlanV1
	ProcessorPlanRefs         []admission.Fragment
	ParticipantConfigurations []binding.ParticipantConfigurationResultV1
}

// RealizationOptions supplies target scope and explicitly acquired artifact availability.
type RealizationOptions struct {
	ArtifactAvailability []planning.ArtifactAvailability
	TargetName           *string
}
