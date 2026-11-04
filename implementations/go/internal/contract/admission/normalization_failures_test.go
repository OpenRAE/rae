package admission

import (
	"encoding/json"
	"math"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// Normalized projections must remain finite inert JSON, including when an
// internal caller supplies a Go value rather than serialized ingress bytes.
func TestNormalizedSemanticProjectionsRefuseNonJSONValues(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	checks := map[string]func(validation.Invocation) error{
		"comparison-request":     e.comparisonRequest,
		"comparison-result":      e.comparisonResult,
		"projection-partition":   e.projectionPartition,
		"projection-witnesses":   e.projectionWitnesses,
		"exploit-evidence":       e.exploitEvidence,
		"opacity-evidence":       e.opacityEvidence,
		"opacity-model-evidence": e.opacityModelEvidence,
		"synthesis-source":       e.synthesisSource,
		"synthesis-profile":      e.synthesisProfile,
		"synthesis-shape":        e.synthesisShape,
		"synthesis-provenance":   e.synthesisProvenance,
		"realization-envelope":   e.envelope,
		"runtime-facts":          e.factPlane,
		"temporal-history":       e.temporalHistory,
		"decision-surface":       e.decisionV2,
		"mixed-composition":      e.mixedCompositionLocal,
		"realized-time":          e.runTimeModel,
	}
	cycle := map[string]any{}
	cycle["cycle"] = cycle
	for name, candidate := range map[string]any{
		"function":       func() {},
		"channel":        make(chan struct{}),
		"nonfinite":      math.Inf(1),
		"invalid-number": json.Number("NaN"),
		"cycle":          cycle,
	} {
		t.Run(name, func(t *testing.T) {
			for checkName, check := range checks {
				t.Run(checkName, func(t *testing.T) {
					v := map[string]any{"unencodable": candidate, "realized_time_model": candidate}
					err := check(validation.Invocation{Instance: v})
					if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
						t.Fatalf("non-JSON projection must be invalid input: %v", err)
					}
				})
			}
		})
	}
}
