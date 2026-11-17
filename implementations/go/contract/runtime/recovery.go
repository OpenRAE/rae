package runtime

import (
	"regexp"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// RecoveryObservationRequest carries value-free context for one read-only observation.
type RecoveryObservationRequest struct {
	OperationID, OperationKind, TargetScope, RunScope, RequestCommitment string
	BaselineSnapshot                                                     binding.RuntimeSnapshotV1
}

// RecoveryObservationResult proposes a closed classification, not redispatch authority.
type RecoveryObservationResult struct {
	Classification, OperationID, RequestCommitment string
	Snapshot                                       *binding.RuntimeSnapshotV1
	ChangedAddresses                               []string
}

var recoveryCommitment = regexp.MustCompile(`^sha256:[a-f0-9]{64}$`)

func recoveryText(text string) bool {
	return utf8.ValidString(text) && len(text) > 0 && utf8.RuneCountInString(text) <= 256
}

// Validate checks request identity and bounds without observing native resources.
func (request RecoveryObservationRequest) Validate() error {
	if !recoveryText(request.OperationID) || !recoveryText(request.TargetScope) || !recoveryText(request.RunScope) || !recoveryCommitment.MatchString(request.RequestCommitment) {
		return invalidRequest()
	}
	switch request.OperationKind {
	case "provisioning", "orchestration", "evaluation", "workflow-cancellation", "workflow-timeout-reconciliation", "participant-action", "participant-control", "participant-crossing", "composition-phase", "indeterminate-resolution":
	default:
		return invalidRequest()
	}
	return admission.CheckPreparedSnapshot(request.BaselineSnapshot)
}

// Validate enforces the snapshot/classification coupling and changed-address grammar.
func (result RecoveryObservationResult) Validate() error {
	if !recoveryText(result.OperationID) || !recoveryCommitment.MatchString(result.RequestCommitment) || len(result.ChangedAddresses) > value.Runtime().MaxMembers {
		return invalidRequest()
	}
	switch result.Classification {
	case "effect-absent", "effect-applied", "indeterminate":
	default:
		return invalidRequest()
	}
	applied := result.Classification == "effect-applied"
	if applied != (result.Snapshot != nil) || (!applied && len(result.ChangedAddresses) > 0) {
		return invalidRequest()
	}
	seen := map[string]bool{}
	for _, changed := range result.ChangedAddresses {
		if !address.Valid(changed) || seen[changed] {
			return invalidRequest()
		}
		seen[changed] = true
	}
	if result.Snapshot != nil {
		return admission.CheckPreparedSnapshot(*result.Snapshot)
	}
	return nil
}
