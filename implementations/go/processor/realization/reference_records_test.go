package realization

import "github.com/OpenRAE/rae/implementations/go/contract/diagnostic"

// These records describe local reference fixtures. Consumer API records keep
// their reviewed field layout and do not become additional wire contracts.
type referenceDiagnostic struct {
	Code     string `json:"code"`
	Domain   string `json:"domain"`
	Address  string `json:"address"`
	Message  string `json:"message"`
	Severity string `json:"severity"`
}

func referenceDiagnostics(input []diagnostic.Diagnostic) []referenceDiagnostic {
	result := make([]referenceDiagnostic, len(input))
	for index, item := range input {
		result[index] = referenceDiagnostic{Code: item.Code, Domain: item.Domain, Address: item.Address, Message: item.Message, Severity: item.Severity}
	}
	return result
}

type referenceAvailability struct {
	Address                                      string   `json:"Address"`
	AvailableArtifactDigests                     []string `json:"AvailableArtifactDigests"`
	AvailableCandidateIDs                        []string `json:"AvailableCandidateIDs"`
	VerifiedLockedInputIDs                       []string `json:"VerifiedLockedInputIDs"`
	SatisfiedConstraintIDs                       []string `json:"SatisfiedConstraintIDs"`
	AvailableMaterializationSpecificationDigests []string `json:"AvailableMaterializationSpecificationDigests"`
	VerifiedIntegrityRefs                        []string `json:"VerifiedIntegrityRefs"`
	VerifiedAuthenticityRefs                     []string `json:"VerifiedAuthenticityRefs"`
	VerifiedAdmissionRefs                        []string `json:"VerifiedAdmissionRefs"`
	VerifiedProvenanceRefs                       []string `json:"VerifiedProvenanceRefs"`
	VerifiedEvidenceRefs                         []string `json:"VerifiedEvidenceRefs"`
}

func referenceFacts(input []referenceAvailability) []ArtifactAvailability {
	result := make([]ArtifactAvailability, len(input))
	for index, item := range input {
		result[index] = ArtifactAvailability(item)
	}
	return result
}
