package comparison

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/profile"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type analysisWork struct{ remaining int }

func (w *analysisWork) spend(count int) error {
	if count < 0 || count > w.remaining {
		return invalid()
	}
	w.remaining -= count
	return nil
}

type reasonSet map[string]bool

func (r reasonSet) list() []string {
	result := make([]string, 0, len(r))
	for reason := range r {
		result = append(result, reason)
	}
	slices.Sort(result)
	return result
}

// Analyze compares owner-admitted artifacts against a governed, digest-pinned request.
func Analyze(governed profile.ComparisonProfile, request validation.Value, before, after Artifact, options Options) (validation.Value, error) {
	admitted, err := profile.AdmitComparisonProfile(governed)
	if err != nil {
		return validation.Value{}, err
	}
	input, err := admitRequest(request, admitted)
	if err != nil {
		return validation.Value{}, err
	}
	context, err := admitContext(options)
	if err != nil {
		return validation.Value{}, err
	}
	work := analysisWork{remaining: 100000}
	left, right, scopeBefore, scopeAfter, err := prepareProjections(admitted, input, before, after, options, &work)
	if err != nil {
		return validation.Value{}, err
	}
	reasons := reasonSet{}
	changes := compareSubjects(input, left, right, context, reasons)
	dependencies := compareDependencies(input, scopeBefore, scopeAfter, reasons)
	paths := impactPaths(input, changes, dependencies, reasons)
	if input.Scope.Status != "complete" {
		reasons["impact-scope-"+input.Scope.Status] = true
	}
	if context.report != nil && len(context.report.Preservation.Limitations) > 0 {
		reasons["transformation-evidence-lossy"] = true
	}
	requestDigest, err := hash(input)
	if err != nil {
		return validation.Value{}, err
	}
	output := result{Schema: "semantic-comparison-result/v1", Profile: input.Profile, ProfileDigest: input.ProfileDigest, Analyzer: input.Analyzer, RequestDigest: requestDigest, Before: input.Before, After: input.After, Scope: input.Scope, ScopeDigest: input.Scope.Digest, Changes: changes, Dependencies: dependencies, Paths: paths, Completeness: completeness(reasons), Reasons: reasons.list(), Context: context.digests, Diagnostics: []json.RawMessage{}}
	return admitResult(output)
}
func admitRequest(source validation.Value, governed profile.ComparisonProfile) (request, error) {
	if source.ContractID() != "semantic-comparison-request-v1" {
		return request{}, invalid()
	}
	owner, err := owners()
	if err != nil {
		return request{}, err
	}
	raw := source.JSON()
	if owner.admitted.CheckPortable(source.ContractID(), raw, inputLimits()) != nil {
		return request{}, invalid()
	}
	defaulted, err := owner.low.Defaulted(source.ContractID(), raw, inputLimits())
	if err != nil {
		return request{}, invalid()
	}
	raw, err = json.Marshal(defaulted)
	if err != nil {
		return request{}, invalid()
	}
	var result request
	if decode(raw, &result) != nil {
		return request{}, invalid()
	}
	if result.Profile != governed.ProfileID || result.ProfileDigest != governed.Digest || result.Analyzer != governed.AnalyzerProfile {
		return request{}, invalid()
	}
	for _, bound := range [][2]int{{result.Limits.Subjects, governed.Limits.MaxSubjects}, {result.Limits.Edges, governed.Limits.MaxDependencyEdges}, {result.Limits.Depth, governed.Limits.MaxPathDepth}, {result.Limits.Paths, governed.Limits.MaxPaths}, {result.Limits.Diagnostics, governed.Limits.MaxDiagnostics}} {
		if bound[0] > bound[1] {
			return request{}, invalid()
		}
	}
	return result, nil
}
func admitContext(options Options) (context, error) {
	if len(options.EvidenceDigests) > 4096 || !slices.Equal(options.EvidenceDigests, sortedUnique(options.EvidenceDigests)) {
		return context{}, invalid()
	}
	result := context{digests: append([]string{}, options.EvidenceDigests...)}
	for _, item := range result.digests {
		if !digest.Valid(item) {
			return context{}, invalid()
		}
	}
	if options.TransformationReport.ContractID() == "" {
		return result, nil
	}
	source := options.TransformationReport
	if source.ContractID() != "artifact-transformation-report-v1" {
		return context{}, invalid()
	}
	owner, err := owners()
	if err != nil {
		return context{}, err
	}
	raw := source.JSON()
	if owner.admitted.CheckPortable(source.ContractID(), raw, inputLimits()) != nil {
		return context{}, invalid()
	}
	document, err := owner.low.Defaulted(source.ContractID(), raw, inputLimits())
	if err != nil {
		return context{}, invalid()
	}
	normalized, err := normalizeOwner("ArtifactTransformationReportModel", document)
	if err != nil {
		return context{}, err
	}
	reportDigest, err := hash(normalized)
	if err != nil {
		return context{}, err
	}
	raw, err = json.Marshal(normalized)
	if err != nil {
		return context{}, invalid()
	}
	result.report = &transformation{}
	if decode(raw, result.report) != nil {
		return context{}, invalid()
	}
	result.digests = sortedUnique(append(result.digests, reportDigest))
	return result, nil
}
func prepareProjections(governed profile.ComparisonProfile, input request, before, after Artifact, options Options, work *analysisWork) (ownerProjection, ownerProjection, []ownerProjection, []ownerProjection, error) {
	beforeScope, afterScope := options.BeforeScope, options.AfterScope
	if len(beforeScope) == 0 {
		beforeScope = []Artifact{before}
	}
	if len(afterScope) == 0 {
		afterScope = []Artifact{after}
	}
	revision := governed.OwnerProjectionVersions[kindScenario]
	if err := requireScope(input.Scope, beforeScope, afterScope, revision); err != nil {
		return ownerProjection{}, ownerProjection{}, nil, nil, err
	}
	left, err := project(governed, before, input.Before, work)
	if err != nil {
		return ownerProjection{}, ownerProjection{}, nil, nil, err
	}
	right, err := project(governed, after, input.After, work)
	if err != nil {
		return ownerProjection{}, ownerProjection{}, nil, nil, err
	}
	scopeBefore, err := projectScope(governed, beforeScope, work)
	if err != nil {
		return ownerProjection{}, ownerProjection{}, nil, nil, err
	}
	scopeAfter, err := projectScope(governed, afterScope, work)
	return left, right, scopeBefore, scopeAfter, err
}
func requireScope(expected scope, before, after []Artifact, revision string) error {
	if len(before) != len(expected.Before) || len(after) != len(expected.After) || len(before) > 4096 || len(after) > 4096 {
		return invalid()
	}
	for _, side := range []struct {
		artifacts   []Artifact
		coordinates []coordinate
	}{{before, expected.Before}, {after, expected.After}} {
		actual, err := scopeCoordinates(side.artifacts, revision)
		if err != nil {
			return err
		}
		for index, item := range actual {
			if !equalCoordinates(item, side.coordinates[index]) {
				return invalid()
			}
		}
	}
	return nil
}
func project(governed profile.ComparisonProfile, input Artifact, expected coordinate, work *analysisWork) (ownerProjection, error) {
	owned, err := native(input)
	if err != nil {
		return ownerProjection{}, err
	}
	revision := governed.OwnerProjectionVersions[owned.kind]
	if (owned.kind == kindScenario || owned.kind == kindTask || owned.kind == kindRun || owned.kind == kindStudy) && revision != "2" {
		return ownerProjection{}, invalid()
	}
	actual, err := owned.coordinate(governed.OwnerProjectionVersions[kindScenario], expected.Exact)
	if err != nil || !equalCoordinates(actual, expected) {
		return ownerProjection{}, invalid()
	}
	original, ok := owned.projections[revision]
	if !ok {
		return ownerProjection{}, invalid()
	}
	if err := work.spend(len(original.subjects) + len(original.dependencies)); err != nil {
		return ownerProjection{}, err
	}
	result := ownerProjection{identity: original.identity, subjects: append([]subject{}, original.subjects...), dependencies: original.dependencies}
	for index := range result.subjects {
		item := &result.subjects[index]
		item.representation = ""
		if item.identity == actual.Identity && expected.Exact != nil {
			item.representation = expected.Exact.ByteDigest
		}
		item.structuralProfile = owned.kind + "-structural-projection/v" + revision
		item.semanticProfile = owned.kind + "-semantic-projection/v" + revision
	}
	return result, nil
}
func projectScope(governed profile.ComparisonProfile, input []Artifact, work *analysisWork) ([]ownerProjection, error) {
	result := make([]ownerProjection, 0, len(input))
	for _, artifact := range input {
		owned, err := native(artifact)
		if err != nil {
			return nil, err
		}
		derived, err := owned.coordinate(governed.OwnerProjectionVersions[kindScenario], nil)
		if err != nil {
			return nil, err
		}
		projection, err := project(governed, artifact, derived, work)
		if err != nil {
			return nil, err
		}
		result = append(result, projection)
	}
	return result, nil
}
func completeness(reasons reasonSet) string {
	if len(reasons) == 0 {
		return "complete"
	}
	for reason := range reasons {
		if reason != reasonSubjects && reason != reasonEdges && reason != reasonPaths {
			return "indeterminate"
		}
	}
	return "bounded"
}
func admitResult(output result) (validation.Value, error) {
	if err := boundResult(output); err != nil {
		return validation.Value{}, err
	}
	raw, err := json.Marshal(output)
	if err != nil || len(raw) > 8<<20 {
		return validation.Value{}, invalid()
	}
	owner, err := owners()
	if err != nil {
		return validation.Value{}, err
	}
	return owner.admitted.Validate("semantic-comparison-result-v1", raw, inputLimits(), nil)
}
