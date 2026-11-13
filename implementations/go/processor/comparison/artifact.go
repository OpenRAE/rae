package comparison

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// FromScenario retains the native authored owner's projections once at admission.
//
//nolint:ireturn // Artifact intentionally seals exact native source ownership.
func FromScenario(source sdl.Scenario) (Artifact, error) {
	result := &artifact{kind: kindScenario, projections: map[string]ownerProjection{}}
	for _, revision := range []string{"1", "2"} {
		projected, err := sdl.ProjectComparison(source, revision)
		if err != nil {
			return nil, invalid()
		}
		if revision == "2" {
			result.name, result.version, result.digest = projected.Name, projected.Version, projected.CanonicalDigest
		}
		projection, err := scenarioProjection(projected)
		if err != nil {
			return nil, err
		}
		result.projections[revision] = projection
	}
	return result, nil
}
func scenarioProjection(input sdl.ComparisonProjection) (ownerProjection, error) {
	structural, err := hash(input.Structural.Document())
	if err != nil {
		return ownerProjection{}, err
	}
	semantic, err := hash(input.Semantic.Document())
	if err != nil {
		return ownerProjection{}, err
	}
	result := ownerProjection{identity: scenarioIdentityPrefix + input.Name, subjects: []subject{{identity: scenarioIdentityPrefix + input.Name, structural: structural, semantic: semantic}}, dependencies: []dependency{}}
	// Keep the coordinate digest with the root's private facts; no source is reparsed later.
	result.subjects[0].representation = input.CanonicalDigest
	for _, child := range input.Subjects {
		structural, err := hash(struct {
			Family string   `json:"declaration_family"`
			Type   string   `json:"model_type"`
			Fields []string `json:"present_fields"`
		}{child.Family, child.ModelType, child.PresentFields})
		if err != nil {
			return ownerProjection{}, err
		}
		semantic, err := hash(child.Semantic.Document())
		if err != nil {
			return ownerProjection{}, err
		}
		result.subjects = append(result.subjects, subject{identity: scenarioIdentityPrefix + input.Name + "/" + child.Family + ":" + child.Name, structural: structural, semantic: semantic})
	}
	for _, decl := range input.Imports {
		raw, err := fragmentBytes(decl, admission.RealizationValue)
		if err != nil {
			return ownerProjection{}, err
		}
		var imported struct {
			Namespace string `json:"namespace"`
		}
		if decode(raw, &imported) != nil {
			return ownerProjection{}, invalid()
		}
		provenance, err := hash(json.RawMessage(raw))
		if err != nil {
			return ownerProjection{}, err
		}
		result.dependencies = append(result.dependencies, dependency{dependent: scenarioIdentityPrefix + input.Name, target: "module:" + imported.Namespace, rule: "scenario-import", provenance: provenance})
	}
	slices.SortFunc(result.subjects, func(a, b subject) int { return compareStrings(a.identity, b.identity) })
	return result, nil
}

// FromDocument accepts only the five published comparison artifact owners.
//
//nolint:ireturn // Artifact intentionally seals exact native source ownership.
func FromDocument(source validation.Value) (Artifact, error) {
	switch source.ContractID() {
	case "experiment-task-v1", "experiment-run-v1", "experiment-capture-spec-v1", "experiment-study-v1", "external-concept-bindings-v1":
		return documentArtifact(source.ContractID(), source.JSON())
	default:
		return nil, invalid()
	}
}

// FromModule admits an exact resolved-import provenance handle.
//
//nolint:ireturn // Artifact intentionally seals exact native source ownership.
func FromModule(source admission.Fragment) (Artifact, error) {
	raw, err := fragmentBytes(source, admission.ResolvedImportProvenance)
	if err != nil {
		return nil, err
	}
	return documentArtifact("resolved-import-provenance", raw)
}
func compareStrings(a, b string) int {
	if a < b {
		return -1
	}
	if a > b {
		return 1
	}
	return 0
}
