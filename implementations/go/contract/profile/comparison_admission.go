package profile

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// AdmitComparisonProfile re-admits a copied profile through its existing
// closed decoder. Digest is recomputed and both version maps are independent.
func AdmitComparisonProfile(input ComparisonProfile) (ComparisonProfile, error) {
	if !comparisonVersions(input.DependencyRuleVersions, input.OwnerProjectionVersions) {
		return ComparisonProfile{}, invalidComparisonProfile()
	}
	for _, text := range []string{input.ProfileID, input.AnalyzerProfile, input.ProjectionProfile, input.ImpactClosurePolicy, input.IdentityAxis, input.TextualAxis, input.StructuralAxis, input.SemanticAxis} {
		if len(text) > 128 {
			return ComparisonProfile{}, invalidComparisonProfile()
		}
	}
	limits := input.Limits
	wire := comparisonWire{ProfileID: &input.ProfileID, AnalyzerProfile: input.AnalyzerProfile, ProjectionProfile: input.ProjectionProfile, ImpactClosurePolicy: input.ImpactClosurePolicy, IdentityAxis: input.IdentityAxis, TextualAxis: input.TextualAxis, StructuralAxis: input.StructuralAxis, SemanticAxis: input.SemanticAxis, DependencyRuleVersions: input.DependencyRuleVersions, OwnerProjectionVersions: input.OwnerProjectionVersions, Limits: &comparisonLimitsWire{MaxSubjects: &limits.MaxSubjects, MaxDependencyEdges: &limits.MaxDependencyEdges, MaxPathDepth: &limits.MaxPathDepth, MaxPaths: &limits.MaxPaths, MaxDiagnostics: &limits.MaxDiagnostics}}
	raw, err := json.Marshal(wire)
	if err != nil {
		return ComparisonProfile{}, invalidComparisonProfile()
	}
	admitted, err := decodeComparison(raw)
	if err != nil {
		return ComparisonProfile{}, invalidComparisonProfile()
	}
	return admitted, nil
}
func invalidComparisonProfile() error {
	return fault.New(fault.InvalidInput, "comparison-profile-invalid", nil)
}
