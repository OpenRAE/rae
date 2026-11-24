package backend

import (
	"context"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// InventoryReporter reports fresh materialized SDL without changing infrastructure.
type InventoryReporter interface {
	RefreshInventory(ctx context.Context, plan binding.ProvisioningPlanV1, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error)
}

// RecoveryObserver observes an interrupted effect; a result does not permit redispatch.
type RecoveryObserver interface {
	ObserveEffect(ctx context.Context, request runtimecontract.RecoveryObservationRequest) (runtimecontract.RecoveryObservationResult, error)
}

// AugmentationPreparer describes prospective effects before ordinary apply.
// The admitted plan retains its published provisioning, orchestration or evaluation ID.
type AugmentationPreparer interface {
	PrepareAugmentation(ctx context.Context, plan validation.Value, snapshot binding.RuntimeSnapshotV1) (binding.BackendAugmentationScopeV1, error)
}

// MixedBridge proposes bound stage evidence through the shared operation protocol.
type MixedBridge interface {
	OperationProvider
	ExecutionBinding(ctx context.Context) (binding.MixedBackendExecutionBindingV1, error)
	StageReports(ctx context.Context, control binding.BackendOperationControlV1) ([]binding.MixedBackendStageReportV1, error)
}

// MixedTimeCoordinator grants an order and advances no clock.
type MixedTimeCoordinator interface {
	Grant(ctx context.Context, request binding.BackendOperationRequestV1, state binding.TimeRuntimeStateV1) (binding.MixedBackendStageReportV1, error)
}

// MixedStageReader supplies one independently authorized, read-only stage observation.
type MixedStageReader interface {
	ReadStage(ctx context.Context, control binding.BackendOperationControlV1) (binding.MixedBackendStageReportV1, error)
}

// InvocationToolActionPort is issued by runtime for one outer invocation.
// Calls must be thread-safe and must not call back into the runtime manager.
// A dispatch receipt is a one-use grant; cancellation is not cessation evidence.
type InvocationToolActionPort interface {
	Identity() runtimecontract.InvocationToolIdentity
	Closed() bool
	Admit(ctx context.Context, request runtimecontract.ToolActionRequest) (runtimecontract.ToolActionDecision, error)
	Dispatch(ctx context.Context, target string) (runtimecontract.ToolActionReceipt, error)
	Complete(ctx context.Context, target string, input admission.Fragment) (runtimecontract.ToolActionReceipt, error)
	Cancel(ctx context.Context, target string) (runtimecontract.ToolActionReceipt, error)
	ReportUnknown(ctx context.Context, target string, target2 string) (runtimecontract.ToolActionReceipt, error)
}

// InvocationToolParticipantRuntime receives only its matching invocation's port.
// Implementations drop the port when that invocation returns.
type InvocationToolParticipantRuntime interface {
	AutonomousParticipantRuntime
	AttachInvocationToolActions(ctx context.Context, port InvocationToolActionPort) error
}
