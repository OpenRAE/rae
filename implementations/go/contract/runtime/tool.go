package runtime

import (
	"regexp"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// InvocationToolIdentity binds a port to one active outer invocation.
type InvocationToolIdentity struct {
	InvocationActionInstanceID, ParticipantAddress, EpisodeID, ParticipantImplementationRef, ExecutionScopeRef, ObservationPoint string
	ExecutionGeneration                                                                                                          int64
}

// ToolActionRequest proposes an exact tool binding before native effects.
type ToolActionRequest struct {
	ToolCallID, InvocationActionInstanceID, ParticipantAddress, EpisodeID, ParticipantImplementationRef, ToolAffordanceAddress, ActionContractAddress, ObservationBoundaryAddress, ExecutionScopeRef string
	TargetAddresses                                                                                                                                                                                  []string
	ExecutionGeneration                                                                                                                                                                              int64
}

// ToolActionDecision carries no action ID when admission is refused.
type ToolActionDecision struct {
	ToolCallID                string
	Admitted                  bool
	ActionInstanceID, Refusal *string
}

// ToolActionReceipt records a proposal from the runtime-owned invocation port.
type ToolActionReceipt struct {
	ActionInstanceID    string
	Accepted            bool
	Refusal, Settlement *string
}

var toolCallID = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)

// Validate checks the portable binding without admitting or dispatching effects.
func (request ToolActionRequest) Validate() error {
	if !toolCallID.MatchString(request.ToolCallID) || request.ExecutionGeneration < 0 || len(request.TargetAddresses) == 0 || len(request.TargetAddresses) > value.Runtime().MaxMembers {
		return invalidRequest()
	}
	fields := []string{request.InvocationActionInstanceID, request.ParticipantAddress, request.EpisodeID, request.ParticipantImplementationRef, request.ToolAffordanceAddress, request.ActionContractAddress, request.ObservationBoundaryAddress, request.ExecutionScopeRef}
	if slices.Contains(fields, "") {
		return invalidRequest()
	}
	seen := map[string]bool{}
	for _, target := range request.TargetAddresses {
		if target == "" || seen[target] {
			return invalidRequest()
		}
		seen[target] = true
	}
	if admission.CheckTransportTree(map[string]any{"fields": fields, "targets": request.TargetAddresses}, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return invalidRequest()
	}
	return nil
}
