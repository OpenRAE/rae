package realization

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type artifactBackend struct {
	Name    string `json:"name"`
	Version string `json:"version"`
}
type artifactSatisfaction struct {
	ID                  string            `json:"requirement_id"`
	Artifact            artifactIdentity  `json:"artifact"`
	Mechanism           artifactMechanism `json:"mechanism"`
	Acquisition         string            `json:"acquisition"`
	Timing              string            `json:"timing"`
	Backend             artifactBackend   `json:"backend"`
	Candidate           *string           `json:"candidate_id"`
	Specification       *string           `json:"materialization_specification_id"`
	SpecificationDigest *string           `json:"materialization_specification_digest"`
	Constraints         []string          `json:"satisfied_constraint_ids"`
	Inputs              []string          `json:"locked_input_ids"`
	Integrity           []string          `json:"integrity_refs"`
	Authenticity        []string          `json:"authenticity_refs"`
	Admission           []string          `json:"admission_refs"`
	Provenance          []string          `json:"provenance_refs"`
	Evidence            []string          `json:"evidence_refs"`
}

func (s *evaluationState) evaluateArtifact(requirement Requirement) (*diagnostic.Diagnostic, *Provenance, error) {
	contract, err := loadArtifactContract(*requirement.ArtifactRequirement)
	if err != nil {
		return nil, nil, err
	}
	entry := s.snapshot.Entries[requirement.Address]
	satisfaction, fragment, err := admitArtifactSatisfaction(entry.Payload["artifact_satisfaction"])
	if err != nil {
		return projectionFailureAsApproximation(requirement, err)
	}
	facts := s.artifacts[requirement.Address]
	if s.artifactSatisfactionInvalid(requirement, contract, satisfaction, facts) {
		return silentApproximation(requirement), nil, nil
	}
	honoured := contract.Posture == termExact && contract.Exact != nil && *contract.Exact == satisfaction.Artifact
	provenance := realizationProvenance(requirement, honoured)
	provenance.ArtifactSatisfaction = fragment
	return nil, provenance, nil
}
func projectionFailureAsApproximation(requirement Requirement, err error) (*diagnostic.Diagnostic, *Provenance, error) {
	finding, provenance, failure := projectionFailure(requirement, err)
	if finding != nil {
		finding = silentApproximation(requirement)
	}
	return finding, provenance, failure
}

//nolint:ireturn // A native fragment retains the published satisfaction owner.
func admitArtifactSatisfaction(input any) (artifactSatisfaction, admission.Fragment, error) {
	owner, err := realizationOwner()
	if err != nil {
		return artifactSatisfaction{}, nil, err
	}
	fragment, err := admission.AdmitFragment(owner, admission.ArtifactSatisfaction, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return artifactSatisfaction{}, nil, err
	}
	raw, err := json.Marshal(fragment.Document())
	if err != nil {
		return artifactSatisfaction{}, nil, invalidRealization()
	}
	var satisfaction artifactSatisfaction
	if json.Unmarshal(raw, &satisfaction) != nil {
		return artifactSatisfaction{}, nil, invalidRealization()
	}
	return satisfaction, fragment, nil
}
func (s *evaluationState) artifactSatisfactionInvalid(requirement Requirement, contract artifactContract, actual artifactSatisfaction, facts ArtifactAvailability) bool {
	return s.artifactIdentityOrRouteInvalid(requirement, contract, actual, facts) || artifactCandidateInvalid(contract, actual, facts) || artifactSpecificationInvalid(contract, actual, facts) || artifactInputsInvalid(contract, actual, facts) || !artifactTrustVerified(contract, actual, facts)
}
func (s *evaluationState) artifactIdentityOrRouteInvalid(requirement Requirement, contract artifactContract, actual artifactSatisfaction, facts ArtifactAvailability) bool {
	if s.options.Manifest == nil {
		return true
	}
	identity := sourceValue(s.options.Manifest.Identity)
	if actual.Backend != (artifactBackend{sourceValue(identity.Name), sourceValue(identity.Version)}) || actual.ID != contract.ID {
		return true
	}
	route := artifactRoute{actual.Mechanism, actual.Acquisition, actual.Timing}
	if !slices.Contains(contract.Routes, route) || !artifactRouteSupported(requirement.Kind, route, s.supportDeclarations(requirement)) {
		return true
	}
	return contract.Exact != nil && (*contract.Exact != actual.Artifact || !slices.Contains(facts.AvailableArtifactDigests, contract.Exact.Digest))
}
func artifactCandidateInvalid(contract artifactContract, actual artifactSatisfaction, facts ArtifactAvailability) bool {
	if actual.Candidate == nil {
		return len(contract.Candidates) > 0
	}
	for _, candidate := range contract.Candidates {
		if candidate.ID == *actual.Candidate {
			return candidate.Artifact != actual.Artifact || !slices.Contains(facts.AvailableCandidateIDs, candidate.ID)
		}
	}
	return true
}
func selectedArtifactSpecification(contract artifactContract, actual artifactSatisfaction) (artifactSpecification, bool) {
	if actual.Specification != nil {
		for _, specification := range contract.Specifications {
			if specification.ID == *actual.Specification {
				return specification, true
			}
		}
	}
	return artifactSpecification{}, false
}
func artifactSpecificationInvalid(contract artifactContract, actual artifactSatisfaction, facts ArtifactAvailability) bool {
	selected, present := selectedArtifactSpecification(contract, actual)
	if actual.Specification != nil && !present {
		return true
	}
	if present {
		return selected.Profile != actual.Mechanism || actual.SpecificationDigest == nil || *actual.SpecificationDigest != selected.Digest || !slices.Contains(facts.AvailableMaterializationSpecificationDigests, selected.Digest)
	}
	if actual.SpecificationDigest != nil {
		return true
	}
	return slices.ContainsFunc(contract.Specifications, func(specification artifactSpecification) bool { return specification.Profile == actual.Mechanism })
}
func artifactInputsInvalid(contract artifactContract, actual artifactSatisfaction, facts ArtifactAvailability) bool {
	required := make([]string, len(contract.Inputs))
	for index, input := range contract.Inputs {
		required[index] = input.ID
	}
	if selected, present := selectedArtifactSpecification(contract, actual); present {
		required = selected.Inputs
	}
	constraints := make([]string, len(contract.Constraints))
	for index, constraint := range contract.Constraints {
		constraints[index] = constraint.ID
	}
	return !artifactSameSet(actual.Inputs, required) || !artifactSubset(required, facts.VerifiedLockedInputIDs) || !artifactSameSet(actual.Constraints, constraints) || !artifactSubset(constraints, facts.SatisfiedConstraintIDs)
}
func artifactTrustVerified(contract artifactContract, actual artifactSatisfaction, facts ArtifactAvailability) bool {
	admission := slices.Clone(contract.Trust)
	evidence := slices.Clone(contract.Manifests)
	for _, input := range contract.Inputs {
		admission = append(admission, input.Trust)
		evidence = append(evidence, input.Manifest)
	}
	return slices.Contains(actual.Integrity, actual.Artifact.Digest) && artifactSubset(actual.Integrity, facts.VerifiedIntegrityRefs) && artifactSubset(actual.Authenticity, facts.VerifiedAuthenticityRefs) && artifactSubset(admission, actual.Admission) && artifactSubset(actual.Admission, facts.VerifiedAdmissionRefs) && artifactSubset(actual.Provenance, facts.VerifiedProvenanceRefs) && artifactSubset(evidence, actual.Evidence) && artifactSubset(actual.Evidence, facts.VerifiedEvidenceRefs)
}
func artifactSubset(required, available []string) bool {
	offered := make(map[string]bool, len(available))
	for _, value := range available {
		offered[value] = true
	}
	for _, value := range required {
		if !offered[value] {
			return false
		}
	}
	return true
}
func artifactSameSet(first, second []string) bool {
	return artifactSubset(first, second) && artifactSubset(second, first)
}
