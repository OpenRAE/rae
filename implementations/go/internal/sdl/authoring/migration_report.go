package authoring

import "github.com/OpenRAE/rae/implementations/go/base/digest"

type migrationReportProfile struct {
	operation, source, canonical, preservation, precondition, postcondition string
	limitations                                                             []string
}

func simpleMigrationReport(data []byte, output *Document, profile migrationReportProfile, policyDigest string, affected []string, diagnostics []any) (map[string]any, error) {
	sourceDigest := digest.SHA256(data)
	derivation, err := jsonIdentity(map[string]any{"operation": profile.operation, "source": sourceDigest, policyField: policyDigest})
	if err != nil {
		return nil, err
	}
	status, outcome := termRefused, termFailed
	var targetDigest any
	postconditions := []any{}
	if output != nil {
		status, outcome = termSuccess, termPassed
		identity, err := output.CanonicalDigest()
		if err != nil {
			return nil, err
		}
		targetDigest = identity
		postconditions = append(postconditions, transformationCheck(profile.postcondition, termPassed))
	}
	return map[string]any{termSchemaVersion: termArtifactTransformationReportV1, termOperationProfile: profile.operation, termStatus: status, termArtifactKind: termSdlAuthoring, termSourceProfile: profile.source, termTargetProfile: termSdlAuthoringInputV1, termCanonicalizationProfile: profile.canonical, termSourceDigest: sourceDigest, termTargetDigest: targetDigest, termPolicyDigest: policyDigest, termDerivationDigest: derivation, termPreconditions: []any{transformationCheck(profile.precondition, outcome)}, termPostconditions: postconditions, termAffectedIdentities: affected, termIdentityMap: []any{}, termPreservation: map[string]any{termProfile: profile.preservation, termOutcome: termNotApplicable, termEvidenceDigests: []any{}, termLimitations: profile.limitations}, termLosses: []any{}, termDiagnostics: diagnostics}, nil
}
