// Package backend defines portable backend roles without registration or invocation policy.
package backend

import (
	"context"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
)

// Manifest is the published backend declaration.
type Manifest = binding.BackendManifestV2

// Provisioner validates and applies provisioning changes.
type Provisioner interface {
	Validate(ctx context.Context, plan binding.ProvisioningPlanV1) ([]diagnostic.Diagnostic, error)
	Apply(ctx context.Context, plan binding.ProvisioningPlanV1, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
}

// PreparingProvisioner commits prospective provisioning effects before apply.
type PreparingProvisioner interface {
	Provisioner
	Prepare(ctx context.Context, plan binding.ProvisioningPlanV1, snapshot binding.RuntimeSnapshotV1) (runtimecontract.RealizationPreparation, error)
}

// ProfilePreparingProvisioner prepares against an explicit domain profile context.
type ProfilePreparingProvisioner interface {
	PreparingProvisioner
	DomainProfileContext() binding.DomainProfileResolutionContextV1
	ValidateProfiles(ctx context.Context, plan binding.ProvisioningPlanV1) ([]diagnostic.Diagnostic, error)
}

// Orchestrator manages portable orchestration state.
type Orchestrator interface {
	Start(ctx context.Context, plan binding.OrchestrationPlanV1, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	Status(ctx context.Context) (map[string]any, error)
	Results(ctx context.Context) (map[string]map[string]any, error)
	History(ctx context.Context) (map[string][]map[string]any, error)
	Stop(ctx context.Context, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
}

// Evaluator manages portable evaluation state.
type Evaluator interface {
	Start(ctx context.Context, plan binding.EvaluationPlanV1, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	Status(ctx context.Context) (map[string]any, error)
	Results(ctx context.Context) (map[string]map[string]any, error)
	History(ctx context.Context) (map[string][]map[string]any, error)
	Stop(ctx context.Context, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
}

// ParticipantRuntime manages episode lifecycle and admitted actions.
type ParticipantRuntime interface {
	Initialize(ctx context.Context, request runtimecontract.EpisodeInitializeRequest, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	Reset(ctx context.Context, request runtimecontract.EpisodeResetRequest, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	Restart(ctx context.Context, request runtimecontract.EpisodeRestartRequest, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	Terminate(ctx context.Context, request runtimecontract.EpisodeTerminateRequest, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	AdmitAction(ctx context.Context, request runtimecontract.ParticipantActionRequest, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	Status(ctx context.Context) (map[string]any, error)
	Results(ctx context.Context) (map[string]map[string]any, error)
	History(ctx context.Context) (map[string][]map[string]any, error)
}

// TimeRuntime exposes the portable time control protocol.
type TimeRuntime interface {
	Initialize(ctx context.Context, model binding.TimeModelV1, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	Advance(ctx context.Context, target string, coordinate int64, coordinate2 int64, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	Pause(ctx context.Context, target string, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	Resume(ctx context.Context, target string, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	Jump(ctx context.Context, target string, coordinate int64, coordinate2 int64, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	Reset(ctx context.Context, target string, reinitialize bool, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	State(ctx context.Context, snapshot binding.RuntimeSnapshotV1) (binding.TimeRuntimeStateV1, error)
}

// AutonomousActionBinding identifies an autonomous action and its temporal contexts.
type AutonomousActionBinding struct {
	ParticipantAddress, ActionContractAddress, ObservationBoundaryAddress, ParticipantImplementationRef, ActionInstanceID string
	TemporalContexts                                                                                                      []admission.Fragment
}

// AutonomousParticipantRuntime binds and admits autonomous action requests.
type AutonomousParticipantRuntime interface {
	ParticipantRuntime
	AdmitAutonomousAction(ctx context.Context, request runtimecontract.ParticipantActionRequest, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ParticipantActionApplyResult, error)
	BindAutonomousAction(ctx context.Context, binding AutonomousActionBinding, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ParticipantActionRequest, error)
}

// ControlledAutonomousParticipantRuntime controls and fences autonomous execution.
type ControlledAutonomousParticipantRuntime interface {
	AutonomousParticipantRuntime
	ControlExecution(ctx context.Context, control binding.ParticipantExecutionControlV1, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
	ExecutionState(ctx context.Context, target string, snapshot binding.RuntimeSnapshotV1) (binding.ParticipantExecutionServiceStateV1, error)
	AdmitActionsConcurrently(ctx context.Context, requests []runtimecontract.ParticipantActionRequest, snapshot binding.RuntimeSnapshotV1, concurrency int) ([]runtimecontract.ParticipantActionApplyResult, error)
}

// CoordinatedParticipantResetRuntime resets a batch of episodes atomically.
type CoordinatedParticipantResetRuntime interface {
	ParticipantRuntime
	ResetMany(ctx context.Context, requests []runtimecontract.EpisodeResetRequest, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
}

// CoordinatedParticipantTimeRuntime coordinates time and participant resets.
type CoordinatedParticipantTimeRuntime interface {
	TimeRuntime
	ResetWithParticipants(ctx context.Context, target string, reinitialize bool, participants CoordinatedParticipantResetRuntime, requests []runtimecontract.EpisodeResetRequest, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
}

// OperationProvider exposes operation admission and supervision.
type OperationProvider interface {
	OperationCapabilities(ctx context.Context) (binding.BackendOperationCapabilitiesV1, error)
	CheckOperation(ctx context.Context, request binding.BackendOperationRequestV1) (binding.BackendOperationResponseV1, error)
	StartOperation(ctx context.Context, request binding.BackendOperationRequestV1) (binding.BackendOperationResponseV1, error)
	ObserveOperation(ctx context.Context, control binding.BackendOperationControlV1) (binding.BackendOperationResponseV1, error)
	CancelOperation(ctx context.Context, control binding.BackendOperationControlV1) (binding.BackendOperationResponseV1, error)
	ReconcileOperation(ctx context.Context, control binding.BackendOperationControlV1) (binding.BackendOperationResponseV1, error)
}

// ParticipantControlProvider resolves version-one control requests.
type ParticipantControlProvider interface {
	Resolve(ctx context.Context, input admission.Fragment) ([]admission.Fragment, error)
}

// ParticipantStageResolver resolves version-two staged control requests.
type ParticipantStageResolver interface {
	ResolveStage(ctx context.Context, input admission.Fragment) ([]admission.Fragment, error)
}

// ParticipantControlProviderV2 preserves the accepted version-two role name.
type ParticipantControlProviderV2 = ParticipantStageResolver
