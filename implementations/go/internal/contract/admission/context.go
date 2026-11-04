package admission

import (
	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

// CleanupPlanProvider supplies the exact admitted cleanup plan for one receipt.
// The trusted owner supplies this artifact; payload claims cannot implement it.
type CleanupPlanProvider interface{ CleanupPlan() []byte }

// CleanupContext retains the original name for CleanupPlanProvider.
type CleanupContext = CleanupPlanProvider

// CompletenessTaxonomyProvider supplies the taxonomy revision against which an
// assessment makes its completeness claim.
type CompletenessTaxonomyProvider interface{ CompletenessTaxonomy() []byte }

// CompletenessContext retains the original name for CompletenessTaxonomyProvider.
type CompletenessContext = CompletenessTaxonomyProvider

// BehavioralClaimProvider supplies the independently identified claim joined
// to a standalone behavioral profile during full contextual validation.
type BehavioralClaimProvider interface{ BehavioralClaim() []byte }

// BehavioralClaimContext retains the original name for BehavioralClaimProvider.
type BehavioralClaimContext = BehavioralClaimProvider

// BackendResponseContext supplies the exact request and, for control evidence,
// its independently admitted control. OperationControl may return nil otherwise.
type BackendResponseContext interface {
	OperationRequest() []byte
	OperationControl() []byte
}

// BackendAdmissionContext supplies installed capabilities and the exact request
// and willingness response to which the capability payload must bind.
type BackendAdmissionContext interface {
	OperationRequest() []byte
	AdmissionResponse() []byte
	InstalledCapabilities() []byte
}

func contextRequired() error {
	return fault.New(fault.InvalidInput, "contract-semantic-context-required", nil)
}

func (e *Validator) contextDocument(id string, raw []byte) (any, error) {
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	raw, err := e.prepare(id, raw, limits)
	if err != nil {
		return nil, err
	}
	if err = e.low.CheckLocal(id, raw, limits); err != nil {
		return nil, invalid()
	}
	if err = e.checkModels(id, raw, limits); err != nil {
		return nil, invalid()
	}
	value, err := ingress.Parse(raw, limits, ingress.Object)
	if err != nil {
		return nil, invalid()
	}
	if err := e.localModels(id, value); err != nil {
		return nil, err
	}
	return value, nil
}
