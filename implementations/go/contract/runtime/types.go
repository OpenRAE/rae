package runtime

import (
	"context"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

// RealizationObservationDisclosure carries corroboration for a realized inventory concern.
type RealizationObservationDisclosure struct {
	Address, FieldPath, Domain, RequirementKind, VerificationScope, ObservationStrength string
	ObservedValue                                                                       *string
	OperatingSystem                                                                     *ObservedOperatingSystemIdentity
	OperationID, EnvelopeDigest, ConfigurationDigest, ObserverVersion                   *string
	Sequence                                                                            *int64
	BindingVerified                                                                     bool
}

// ObservedOperatingSystemIdentity identifies an independently observed operating system.
type ObservedOperatingSystemIdentity struct{ Family, Distribution, Version string }

// ProvisionOperation owns the portable inputs for a proposed provisioning effect.
type ProvisionOperation struct {
	Action, Address, ResourceType             string
	Payload                                   map[string]any
	OrderingDependencies, RefreshDependencies []string
	ExecutionPolicy                           admission.Fragment
	ExecutionPolicyScopes                     []admission.Fragment
	ProfileBindings                           []binding.DomainProfileBindingV1
}

// RealizationPreparation binds prospective effects to a plan and predecessor.
type RealizationPreparation struct {
	RequestDigest, PredecessorDigest string
	Operations                       []ProvisionOperation
	Success                          bool
	Diagnostics                      []diagnostic.Diagnostic
}

// ApplyResult returns detached inventory and effect disclosures.
type ApplyResult struct {
	Success                            bool
	Snapshot                           binding.RuntimeSnapshotV1
	Diagnostics                        []diagnostic.Diagnostic
	ChangedAddresses                   []string
	Details                            map[string]any
	OperationalRealizationObservations []RealizationObservationDisclosure
	MaterializationAttestation         *MaterializationSubmission
}

// EpisodeInitializeRequest identifies an episode to initialize.
type EpisodeInitializeRequest struct {
	ParticipantAddress string
	EpisodeID          *string
}

// EpisodeResetRequest identifies an episode to reset and its reason.
type EpisodeResetRequest struct {
	ParticipantAddress string
	EpisodeID          *string
	Reason             string
}

// EpisodeRestartRequest identifies an episode to restart and its reason.
type EpisodeRestartRequest struct {
	ParticipantAddress string
	EpisodeID          *string
	Reason             string
}

// EpisodeTerminateRequest identifies an episode to terminate and its outcome.
type EpisodeTerminateRequest struct{ ParticipantAddress, TerminalReason, Detail string }

// ParticipantActionRequest is an admitted portable action binding, without effect authority.
type ParticipantActionRequest interface {
	Input() ParticipantActionInput
	admittedAction()
}

// ParticipantActionInput contains the portable joins for action admission.
type ParticipantActionInput struct {
	ParticipantAddress, ActionContractAddress, ObservationBoundaryAddress, ActionInstanceID string
	ImplementationManifest                                                                  binding.ParticipantImplementationManifestV1
	ImplementationSelection                                                                 admission.Fragment
	EvidenceRefs, VisibleRefs, DisclosedRefs, ObservationBoundaryEvidenceRefs               []string
	TemporalContexts                                                                        []admission.Fragment
	ActionResult                                                                            admission.Fragment
	ValidatedSelection                                                                      admission.Fragment
	StateTransitionKind                                                                     string
	PostStateDigest                                                                         *string
	RequiresTerminalOutcome                                                                 bool
	TargetAddresses                                                                         []string
	ExecutionScopeRef                                                                       *string
	ExecutionGeneration                                                                     *int64
	ResourceMeasurementRequirements, TemporalEvidence                                       []admission.Fragment
}

// ParticipantActionApplyResult adds a typed outcome to an apply result.
type ParticipantActionApplyResult struct {
	ApplyResult

	ActionResult admission.Fragment
}

// NativeActionOutcome returns a proposed native action effect and outcome.
type NativeActionOutcome struct {
	ApplyResult     ApplyResult
	ActionResult    admission.Fragment
	PostStateDigest *string
}

// NativeActionInvoker invokes native effects after external runtime authorization.
type NativeActionInvoker interface {
	Invoke(ctx context.Context, request ParticipantActionRequest, snapshot binding.RuntimeSnapshotV1) (NativeActionOutcome, error)
}

// NativeActionExecution preserves the accepted native action role name.
type NativeActionExecution = NativeActionInvoker
