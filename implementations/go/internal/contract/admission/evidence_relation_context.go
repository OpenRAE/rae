package admission

import "github.com/OpenRAE/rae/implementations/go/internal/contract/validation"

// EvidenceScenario retains a semantically admitted authoring scenario and its
// canonical SDL digest supplied by the owning authority.
type EvidenceScenario struct {
	Value  validation.Value
	Digest string
}

// EvidenceRelationContext supplies exact admitted scenarios and capture specs.
// The rule resolves each lineage coordinate without ambient lookups.
type EvidenceRelationContext interface {
	EvidenceScenarios() []EvidenceScenario
	CaptureSpecs() [][]byte
}
