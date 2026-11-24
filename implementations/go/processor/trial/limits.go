package trial

import "github.com/OpenRAE/rae/implementations/go/base/fault"

// DefaultLimits returns the trial compiler profile's resource ceilings.
func DefaultLimits() Limits {
	return Limits{10000, 10000, 10000, 256, 256, 128, 256, 1000000, 32 << 20}
}

// Validate refuses non-positive trial resource ceilings.
func (limits Limits) Validate() error {
	for _, n := range []int{limits.MaxCoordinates, limits.MaxDomainValuesPerPoint, limits.MaxProductOutputs, limits.MaxBindingsPerEntry, limits.MaxDrawsPerEntry, limits.MaxDiagnostics, limits.MaxMixedProfiles, limits.MaxMixedContextWork, limits.MaxPlanBytes} {
		if n <= 0 {
			return fault.New(fault.InvalidInput, "trial-limits-invalid", nil)
		}
	}
	return nil
}

// DefaultMixedCompositionLimits returns the composition owner's resource ceilings.
func DefaultMixedCompositionLimits() MixedCompositionLimits {
	return MixedCompositionLimits{1 << 20, 64, 20000, 64, 1024, 1024, 256, 512, 64, 100000}
}

// Validate refuses non-positive composition resource ceilings.
func (limits MixedCompositionLimits) Validate() error {
	for _, n := range []int{limits.MaxSourceBytes, limits.MaxJSONDepth, limits.MaxJSONNodes, limits.MaxComponents, limits.MaxAllocations, limits.MaxEdges, limits.MaxPhases, limits.MaxTransitions, limits.MaxNestedProfiles, limits.MaxContextWork} {
		if n <= 0 {
			return fault.New(fault.InvalidInput, "mixed-composition-limits-invalid", nil)
		}
	}
	return nil
}
