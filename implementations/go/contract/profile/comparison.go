package profile

import (
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/domainprofile"
)

// ComparisonLimits are the governed bounds of one comparison profile.
type ComparisonLimits struct{ MaxSubjects, MaxDependencyEdges, MaxPathDepth, MaxPaths, MaxDiagnostics int }

// ComparisonProfile is one packaged semantic-comparison profile. Digest is
// the RFC 8785 digest of its document with the published defaults.
type ComparisonProfile struct {
	ProfileID, AnalyzerProfile, ProjectionProfile, ImpactClosurePolicy string
	IdentityAxis, TextualAxis, StructuralAxis, SemanticAxis            string
	DependencyRuleVersions, OwnerProjectionVersions                    map[string]string
	Limits                                                             ComparisonLimits
	Digest                                                             string
}

type comparisonLimitsWire struct {
	MaxSubjects        *int `json:"max_subjects"`
	MaxDependencyEdges *int `json:"max_dependency_edges"`
	MaxPathDepth       *int `json:"max_path_depth"`
	MaxPaths           *int `json:"max_paths"`
	MaxDiagnostics     *int `json:"max_diagnostics"`
}

type comparisonWire struct {
	ProfileID               *string               `json:"profile_id"`
	AnalyzerProfile         string                `json:"analyzer_profile"`
	ProjectionProfile       string                `json:"projection_profile"`
	ImpactClosurePolicy     string                `json:"impact_closure_policy"`
	IdentityAxis            string                `json:"identity_axis"`
	TextualAxis             string                `json:"textual_axis"`
	StructuralAxis          string                `json:"structural_axis"`
	SemanticAxis            string                `json:"semantic_axis"`
	DependencyRuleVersions  map[string]string     `json:"dependency_rule_versions"`
	OwnerProjectionVersions map[string]string     `json:"owner_projection_versions"`
	Limits                  *comparisonLimitsWire `json:"limits"`
}

// comparisonRules returns the closed dependency rules of a comparison
// profile in order.
func comparisonRules() []string {
	return []string{"experiment-capture-scope-reference", "experiment-run-scenario-snapshot-reference", "experiment-run-task-reference", "experiment-study-membership", "experiment-task-scenario-reference", "external-concept-subject", "scenario-import"}
}

// comparisonOwners maps each artifact kind to whether it supports projection
// revision 2.
func comparisonOwners() map[string]bool {
	return map[string]bool{"evidence-specification": false, "external-concept-bindings": false, "module": false, "run": true, "scenario": true, "study": true, "task": true}
}

func (p *Profiles) decodeComparisons(documents map[string][]byte) error {
	p.comparisons = map[string]ComparisonProfile{}
	for _, name := range []string{"reference-v1", "reference-v2"} {
		profile, err := decodeComparison(documents[comparisonDir+name+".json"])
		if err != nil {
			return err
		}
		p.comparisons[name] = profile
	}
	return nil
}

// decodeComparison applies the reference comparison-profile model: the closed
// literals, the complete dependency-rule set, every owner projection version
// and the bounded limits with their defaults.
func decodeComparison(data []byte) (ComparisonProfile, error) {
	var wire comparisonWire
	if err := decodeStrict(data, &wire); err != nil {
		return ComparisonProfile{}, err
	}
	profile := ComparisonProfile{ProfileID: "raes-semantic-comparison/v1", AnalyzerProfile: wire.AnalyzerProfile, ProjectionProfile: wire.ProjectionProfile, ImpactClosurePolicy: wire.ImpactClosurePolicy, IdentityAxis: wire.IdentityAxis, TextualAxis: wire.TextualAxis, StructuralAxis: wire.StructuralAxis, SemanticAxis: wire.SemanticAxis, DependencyRuleVersions: wire.DependencyRuleVersions, OwnerProjectionVersions: wire.OwnerProjectionVersions}
	if wire.ProfileID != nil {
		profile.ProfileID = *wire.ProfileID
	}
	literals := [][2]string{
		{profile.ProfileID, "raes-semantic-comparison/v1"},
		{profile.AnalyzerProfile, "raes-reference-semantic-comparator/v1"},
		{profile.ProjectionProfile, "owner-specific-admitted-artifact-projection/v1"},
		{profile.ImpactClosurePolicy, "declared-exact-artifact-set/v1"},
		{profile.IdentityAxis, "canonical-owner-identity/v1"},
		{profile.TextualAxis, "exact-representation-digest/v1"},
		{profile.StructuralAxis, "owner-shape-projection/v1"},
		{profile.SemanticAxis, "owner-semantic-projection/v1"},
	}
	for _, literal := range literals {
		if literal[0] != literal[1] {
			return ComparisonProfile{}, damaged()
		}
	}
	if !comparisonVersions(profile.DependencyRuleVersions, profile.OwnerProjectionVersions) {
		return ComparisonProfile{}, damaged()
	}
	limits, ok := comparisonLimits(wire.Limits)
	if !ok {
		return ComparisonProfile{}, damaged()
	}
	profile.Limits = limits
	digest, err := domainprofile.Digest(map[string]any{
		"profile_id": profile.ProfileID, "analyzer_profile": profile.AnalyzerProfile, "projection_profile": profile.ProjectionProfile,
		"impact_closure_policy": profile.ImpactClosurePolicy, "identity_axis": profile.IdentityAxis, "textual_axis": profile.TextualAxis,
		"structural_axis": profile.StructuralAxis, "semantic_axis": profile.SemanticAxis,
		"dependency_rule_versions": profile.DependencyRuleVersions, "owner_projection_versions": profile.OwnerProjectionVersions,
		"limits": map[string]int{"max_subjects": limits.MaxSubjects, "max_dependency_edges": limits.MaxDependencyEdges, "max_path_depth": limits.MaxPathDepth, "max_paths": limits.MaxPaths, "max_diagnostics": limits.MaxDiagnostics},
	})
	if err != nil {
		return ComparisonProfile{}, damaged()
	}
	profile.Digest = digest
	return profile, nil
}

func comparisonVersions(rules, owners map[string]string) bool {
	known := comparisonOwners()
	if !slices.Equal(slices.Sorted(maps.Keys(rules)), comparisonRules()) || len(owners) != len(known) {
		return false
	}
	for _, version := range rules {
		if version != "1" {
			return false
		}
	}
	for kind, version := range owners {
		revisionTwo, declared := known[kind]
		if !declared || version != "1" && (version != "2" || !revisionTwo) {
			return false
		}
	}
	return true
}

// comparisonLimits applies the defaults and bounds of the reference limits.
func comparisonLimits(wire *comparisonLimitsWire) (ComparisonLimits, bool) {
	if wire == nil {
		wire = &comparisonLimitsWire{}
	}
	pick := func(value *int, fallback, low, high int) (int, bool) {
		if value == nil {
			return fallback, true
		}
		return *value, *value >= low && *value <= high
	}
	var ok [5]bool
	limits := ComparisonLimits{}
	limits.MaxSubjects, ok[0] = pick(wire.MaxSubjects, 4096, 1, 4096)
	limits.MaxDependencyEdges, ok[1] = pick(wire.MaxDependencyEdges, 8192, 0, 8192)
	limits.MaxPathDepth, ok[2] = pick(wire.MaxPathDepth, 8, 0, 32)
	limits.MaxPaths, ok[3] = pick(wire.MaxPaths, 1024, 0, 4096)
	limits.MaxDiagnostics, ok[4] = pick(wire.MaxDiagnostics, 64, 0, 64)
	return limits, !slices.Contains(ok[:], false)
}

// ComparisonProfile returns the packaged profile with the file name stem,
// for example "reference-v2". An unknown name is a NotFound fault.
func (p *Profiles) ComparisonProfile(name string) (ComparisonProfile, error) {
	profile, ok := p.comparisons[name]
	if !ok {
		return ComparisonProfile{}, notFound("comparison-profile-unknown")
	}
	profile.DependencyRuleVersions, profile.OwnerProjectionVersions = maps.Clone(profile.DependencyRuleVersions), maps.Clone(profile.OwnerProjectionVersions)
	return profile, nil
}
