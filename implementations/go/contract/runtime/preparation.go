package runtime

import (
	"sync"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

var validator = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Only immutable packaged contracts are shared; request state remains local.

// PrepareForRequest commits to the current plan and predecessor before apply.
func PrepareForRequest(plan binding.ProvisioningPlanV1, snapshot binding.RuntimeSnapshotV1, operations []ProvisionOperation, success bool, diagnostics []diagnostic.Diagnostic) (RealizationPreparation, error) {
	owner, err := validator()
	if err != nil {
		return RealizationPreparation{}, err
	}
	request, previous, err := admission.BackendPreparationCommitments(owner, plan, snapshot)
	if err != nil {
		return RealizationPreparation{}, err
	}
	copiedOperations, err := ownOperations(operations)
	if err != nil {
		return RealizationPreparation{}, err
	}
	copiedDiagnostics, err := ownDiagnostics(diagnostics)
	if err != nil {
		return RealizationPreparation{}, err
	}
	return RealizationPreparation{RequestDigest: request, PredecessorDigest: previous, Operations: copiedOperations, Success: success, Diagnostics: copiedDiagnostics}, nil
}
