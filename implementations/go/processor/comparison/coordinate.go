package comparison

import (
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// Coordinate derives an owner-specific digest-bound coordinate without I/O.
//
//nolint:ireturn // The existing coordinate fragment owner validates output.
func Coordinate(artifact Artifact, scenarioProjectionVersion string, exactRepresentation admission.Fragment) (admission.Fragment, error) {
	owned, err := native(artifact)
	if err != nil {
		return nil, err
	}
	var exact *representationData
	if exactRepresentation != nil {
		raw, fragmentErr := fragmentBytes(exactRepresentation, admission.ExactRepresentation)
		if fragmentErr != nil {
			return nil, fragmentErr
		}
		exact = &representationData{}
		if decode(raw, exact) != nil {
			return nil, invalid()
		}
	}
	derived, err := owned.coordinate(scenarioProjectionVersion, exact)
	if err != nil {
		return nil, err
	}
	return admitFragment(admission.ComparisonCoordinate, derived)
}
func (a *artifact) coordinate(revision string, exact *representationData) (coordinate, error) {
	if revision != "1" && revision != "2" {
		return coordinate{}, invalid()
	}
	result := coordinate{Kind: a.kind, Phase: "portable-contract", Identity: a.kind + ":" + a.name, Canonicalization: "rfc8785-jcs-sha256/v1", Digest: a.digest, Exact: exact, Schema: a.schema}
	switch a.kind {
	case kindScenario:
		result.Phase, result.Schema = "normalized-authoring", ""
		result.SourceProfile = "sdl-normalized-authoring/v1"
		result.ScenarioID, result.ScenarioVersion = a.name, a.version
		result.Canonicalization = "raes-canonical-sdl/v" + revision
		result.Digest = a.projections[revision].subjects[0].representation
	case kindModule:
		result.Phase = "resolved-import"
		result.ProvenanceProfile = "resolved-import-provenance/v1"
		result.ModuleID, result.ModuleVersion = a.name, a.version
	case kindTask:
		result.TaskID, result.TaskVersion = a.name, a.version
	case kindRun:
		result.RunID, result.RunVersion = a.name, a.version
	case kindCapture:
		result.Identity = "capture-spec:" + a.name
		result.CaptureID, result.SpecVersion = a.name, a.version
	case kindStudy:
		result.StudyID, result.StudyVersion = a.name, a.version
	case kindExternal:
		result.BindingID, result.BindingVersion = a.name, a.version
	default:
		return coordinate{}, invalid()
	}
	return result, nil
}

// BuildImpactScope binds a sorted exact two-sided artifact set and closure claim.
//
//nolint:ireturn // The existing impact scope fragment owner validates output.
func BuildImpactScope(before, after []Artifact, roots []string, closureStatus, scopeID, scenarioProjectionVersion string) (admission.Fragment, error) {
	value, err := buildScope(before, after, roots, closureStatus, scopeID, scenarioProjectionVersion)
	if err != nil {
		return nil, err
	}
	return admitFragment(admission.ComparisonImpactScope, value)
}
func buildScope(before, after []Artifact, roots []string, status, id, revision string) (scope, error) {
	if len(before) > 4096 || len(after) > 4096 || len(roots) > 4096 {
		return scope{}, invalid()
	}
	budget := wireBudget{remaining: 8 << 20}
	if err := budget.record(256, id, status, revision); err != nil {
		return scope{}, err
	}
	if err := budget.record(0, roots...); err != nil {
		return scope{}, err
	}
	result := scope{ID: id, Policy: "declared-exact-artifact-set/v1", Status: status, Roots: sortedUnique(roots)}
	var err error
	result.Before, err = scopeCoordinates(before, revision)
	if err != nil {
		return scope{}, err
	}
	result.After, err = scopeCoordinates(after, revision)
	if err != nil {
		return scope{}, err
	}
	budget = wireBudget{remaining: 8 << 20}
	if scopeErr := budget.scope(result); scopeErr != nil {
		return scope{}, scopeErr
	}
	// The signed owner excludes only scope_digest from its canonical digest input.
	unsigned := struct {
		ID     string       `json:"scope_id"`
		Policy string       `json:"closure_policy"`
		Status string       `json:"closure_status"`
		Roots  []string     `json:"traversal_roots"`
		Before []coordinate `json:"before_artifacts"`
		After  []coordinate `json:"after_artifacts"`
	}{result.ID, result.Policy, result.Status, result.Roots, result.Before, result.After}
	result.Digest, err = hash(unsigned)
	return result, err
}
func scopeCoordinates(artifacts []Artifact, revision string) ([]coordinate, error) {
	result := make([]coordinate, 0, len(artifacts))
	for _, input := range artifacts {
		owned, err := native(input)
		if err != nil {
			return nil, err
		}
		item, err := owned.coordinate(revision, nil)
		if err != nil {
			return nil, err
		}
		result = append(result, item)
	}
	slices.SortFunc(result, lessCoordinate)
	return result, nil
}
func ownerProfile(input coordinate) string {
	if input.SourceProfile != "" {
		return input.SourceProfile
	}
	if input.ProvenanceProfile != "" {
		return input.ProvenanceProfile
	}
	return input.Schema
}
