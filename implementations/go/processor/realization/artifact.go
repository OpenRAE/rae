package realization

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// ArtifactAvailability retains independently verified facts for one compiled
// requirement address. Facts from another address cannot satisfy it.
type ArtifactAvailability struct {
	Address                                                                                                              string
	AvailableArtifactDigests, AvailableCandidateIDs, VerifiedLockedInputIDs, SatisfiedConstraintIDs                      []string
	AvailableMaterializationSpecificationDigests                                                                         []string
	VerifiedIntegrityRefs, VerifiedAuthenticityRefs, VerifiedAdmissionRefs, VerifiedProvenanceRefs, VerifiedEvidenceRefs []string
}
type artifactIdentity struct {
	ID        string `json:"artifact_id"`
	Version   string `json:"version"`
	Digest    string `json:"digest"`
	MediaType string `json:"media_type"`
}
type artifactMechanism struct {
	Mechanism string `json:"mechanism"`
	Profile   string `json:"profile"`
	Version   string `json:"version"`
	Digest    string `json:"digest"`
}
type artifactRoute struct {
	Mechanism   artifactMechanism `json:"mechanism"`
	Acquisition string            `json:"acquisition"`
	Timing      string            `json:"timing"`
}
type artifactCapability struct {
	Mechanism artifactMechanism `json:"mechanism"`
	Kinds     []string          `json:"supported_requirement_kinds"`
	Routes    []struct {
		Acquisition string `json:"acquisition"`
		Timing      string `json:"timing"`
	} `json:"supported_routes"`
}
type artifactConstraint struct {
	ID string `json:"constraint_id"`
}
type artifactCandidate struct {
	ID       string           `json:"candidate_id"`
	Artifact artifactIdentity `json:"artifact"`
}
type artifactInput struct {
	ID       string `json:"input_id"`
	Trust    string `json:"trust_policy_ref"`
	Manifest string `json:"associated_artifact_manifest_ref"`
}
type artifactSpecification struct {
	ID      string            `json:"specification_id"`
	Profile artifactMechanism `json:"profile"`
	Digest  string            `json:"digest"`
	Inputs  []string          `json:"locked_input_ids"`
}
type artifactContract struct {
	ID             string                  `json:"requirement_id"`
	Posture        string                  `json:"explicitness"`
	Exact          *artifactIdentity       `json:"exact_artifact"`
	Constraints    []artifactConstraint    `json:"constraints"`
	Candidates     []artifactCandidate     `json:"candidates"`
	Inputs         []artifactInput         `json:"locked_inputs"`
	Specifications []artifactSpecification `json:"materialization_specifications"`
	Routes         []artifactRoute         `json:"permitted_routes"`
	Trust          []string                `json:"trust_policy_refs"`
	Manifests      []string                `json:"associated_artifact_manifest_refs"`
}

func loadArtifactContract(input binding.ArtifactRequirementV1) (artifactContract, error) {
	var document struct {
		Source struct {
			Requirement artifactContract `json:"artifact_requirement"`
		} `json:"source"`
	}
	if err := decodeEvaluationTransport("artifact-requirement-v1", input, &document); err != nil {
		return artifactContract{}, err
	}
	return document.Source.Requirement, nil
}
func decodeArtifactCapability(input any) (artifactCapability, error) {
	raw, err := json.Marshal(input)
	if err != nil {
		return artifactCapability{}, invalidRealization()
	}
	var result artifactCapability
	if json.Unmarshal(raw, &result) != nil {
		return artifactCapability{}, invalidRealization()
	}
	return result, nil
}

// ArtifactSupport reports availability and complete mechanism-route gaps in
// reference order. It grants no trust to provider claims or authored definitions.
func ArtifactSupport(requirements []Requirement, manifest binding.BackendManifestV2, availability []ArtifactAvailability) ([]diagnostic.Diagnostic, error) {
	if len(requirements) > 16384 {
		return nil, invalidRealization()
	}
	facts, err := artifactAvailabilityIndex(availability)
	if err != nil {
		return nil, err
	}
	var admitted binding.BackendManifestV2
	if err := decodeEvaluationTransport("backend-manifest-v2", manifest, &admitted); err != nil {
		return nil, err
	}
	if err := checkRequirementBatch(requirements); err != nil {
		return nil, err
	}
	declarations := map[string][]supportDeclaration{}
	result := []diagnostic.Diagnostic{}
	for _, requirement := range requirements {
		if requirement.ArtifactRequirement == nil {
			continue
		}
		contract, err := loadArtifactContract(*requirement.ArtifactRequirement)
		if err != nil {
			return nil, err
		}
		support, known := declarations[requirement.Domain]
		if !known {
			support, err = declaredSupport(admitted, requirement.Domain)
			if err != nil {
				return nil, err
			}
			declarations[requirement.Domain] = support
		}
		result = append(result, artifactSupportDiagnostics(requirement, contract, facts[requirement.Address], support)...)
	}
	return result, nil
}
func artifactSupportDiagnostics(requirement Requirement, contract artifactContract, facts ArtifactAvailability, support []supportDeclaration) []diagnostic.Diagnostic {
	result := []diagnostic.Diagnostic{}
	add := func(code, reason string) {
		result = append(result, *supportFinding(requirement, code, reason+" Requirement '"+requirement.Kind+"' at '"+requirement.FieldPath+"' cannot be admitted."))
	}
	if contract.Posture == termOpen && !slices.ContainsFunc(support, func(declaration supportDeclaration) bool { return declaration.mode == termOpenRealization }) {
		add("artifact.unsupported-open-realization", "Backend declares no open artifact realization support.")
	}
	if contract.Exact != nil && !slices.Contains(facts.AvailableArtifactDigests, contract.Exact.Digest) {
		add("artifact.unavailable-exact-artifact", "The required immutable artifact is not available.")
	}
	for _, constraint := range contract.Constraints {
		if !slices.Contains(facts.SatisfiedConstraintIDs, constraint.ID) {
			add("artifact.unsatisfied-constraint", "Artifact constraint '"+constraint.ID+"' is not satisfied.")
		}
	}
	for _, input := range contract.Inputs {
		if !slices.Contains(facts.VerifiedLockedInputIDs, input.ID) {
			add("artifact.missing-locked-input", "Locked artifact input '"+input.ID+"' is not verified.")
		}
	}
	if len(contract.Candidates) > 0 && !slices.ContainsFunc(contract.Candidates, func(candidate artifactCandidate) bool {
		return slices.Contains(facts.AvailableCandidateIDs, candidate.ID)
	}) {
		add("artifact.unavailable-candidate", "No declared artifact candidate is available.")
	}
	if len(contract.Specifications) > 0 && !slices.ContainsFunc(contract.Specifications, func(specification artifactSpecification) bool {
		return slices.Contains(facts.AvailableMaterializationSpecificationDigests, specification.Digest)
	}) {
		add("artifact.unavailable-materialization-specification", "No declared digest-bound materialization specification is available.")
	}
	if !slices.ContainsFunc(contract.Routes, func(route artifactRoute) bool { return artifactRouteSupported(requirement.Kind, route, support) }) {
		add("artifact.unsupported-backend-mechanism", "Backend declares no supported artifact mechanism and acquisition/timing route.")
	}
	return result
}
func artifactRouteSupported(kind string, route artifactRoute, declarations []supportDeclaration) bool {
	for _, declaration := range declarations {
		for _, capability := range declaration.artifacts {
			if capability.Mechanism != route.Mechanism || !slices.Contains(capability.Kinds, kind) {
				continue
			}
			for _, offered := range capability.Routes {
				if offered.Acquisition == route.Acquisition && offered.Timing == route.Timing {
					return true
				}
			}
		}
	}
	return false
}
func artifactAvailabilityIndex(input []ArtifactAvailability) (map[string]ArtifactAvailability, error) {
	if len(input) > 16384 || value.ValidateProjected(map[string]any{"requirements": input}, value.Runtime(), artifactAvailabilityValue) != nil {
		return nil, invalidRealization()
	}
	result := make(map[string]ArtifactAvailability, len(input))
	for _, entry := range input {
		if entry.Address == "" {
			return nil, invalidRealization()
		}
		if _, duplicate := result[entry.Address]; duplicate {
			return nil, invalidRealization()
		}
		if err := checkArtifactFacts(entry); err != nil {
			return nil, err
		}
		result[entry.Address] = entry
	}
	return result, nil
}
func checkArtifactFacts(entry ArtifactAvailability) error {
	for key, values := range artifactFactLists(entry) {
		seen := map[string]bool{}
		for _, text := range values {
			if text == "" || seen[text] {
				return invalidRealization()
			}
			seen[text] = true
			if key == "available_materialization_specification_digests" && !artifactSpecificationDigest(text) {
				return invalidRealization()
			}
		}
	}
	return nil
}
func artifactSpecificationDigest(text string) bool {
	return len(text) == 71 && strings.HasPrefix(text, digest.Prefix) && text == strings.ToLower(text) && digest.Valid(text)
}

// Each shallow view is explicitly owned here. The shared iterative walker
// checks the remaining node/depth/scalar budget before projecting its children.
// It never calls caller methods or builds the complete context before checking.
func artifactAvailabilityValue(input any) (any, error) {
	switch entry := input.(type) {
	case []ArtifactAvailability:
		if len(entry) > 16384 {
			return nil, invalidRealization()
		}
		result := make([]any, len(entry))
		for index, item := range entry {
			result[index] = item
		}
		return result, nil
	case ArtifactAvailability:
		result := map[string]any{"address": entry.Address}
		for key, values := range artifactFactLists(entry) {
			result[key] = values
		}
		return result, nil
	case []string:
		if len(entry) > 16384 {
			return nil, invalidRealization()
		}
		return stringValues(entry), nil
	default:
		return input, nil
	}
}

func artifactFactLists(entry ArtifactAvailability) map[string][]string {
	return map[string][]string{"available_artifact_digests": entry.AvailableArtifactDigests, "available_candidate_ids": entry.AvailableCandidateIDs, "verified_locked_input_ids": entry.VerifiedLockedInputIDs, "satisfied_constraint_ids": entry.SatisfiedConstraintIDs, "available_materialization_specification_digests": entry.AvailableMaterializationSpecificationDigests, "verified_integrity_refs": entry.VerifiedIntegrityRefs, "verified_authenticity_refs": entry.VerifiedAuthenticityRefs, "verified_admission_refs": entry.VerifiedAdmissionRefs, "verified_provenance_refs": entry.VerifiedProvenanceRefs, "verified_evidence_refs": entry.VerifiedEvidenceRefs}
}
