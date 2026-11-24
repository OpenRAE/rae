package realization

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func realizationEnvelopeDiagnostics(requirements []Requirement, options ResolveOptions) ([]diagnostic.Diagnostic, error) {
	findings := []diagnostic.Diagnostic{}
	for _, requirement := range requirements {
		if requirement.Kind != termComputeSubstrate {
			continue
		}
		finding, err := computeEnvelopeFinding(requirement, options.Envelope)
		if err != nil {
			return nil, err
		}
		if finding != nil {
			findings = append(findings, *finding)
		}
	}
	if options.Envelope == nil || slices.Contains(sourceValue(options.Manifest.SupportedContractVersions), "backend-realization-preparation-v1") {
		return findings, nil
	}
	paths := []string{}
	for _, requirement := range requirements {
		if requirement.Kind != termComputeSubstrate && requirement.Posture != nil && *requirement.Posture == termOpen {
			paths = append(paths, requirement.FieldPath)
		}
	}
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	openFindings, err := admission.RealizationOpenOfferDiagnostics(owner, *options.Envelope, paths)
	if err != nil {
		return nil, err
	}
	return append(findings, openFindings...), nil
}

func computeEnvelopeFinding(requirement Requirement, envelope *binding.RealizationEnvelopeV1) (*diagnostic.Diagnostic, error) {
	if envelope == nil {
		if requirement.Posture != nil && (*requirement.Posture == termExact || *requirement.Posture == termConstrained) {
			return supportFinding(requirement, "realization.compute-substrate-envelope-required", "Selected apparatus provides no realization envelope for the bounded compute-substrate demand at '"+requirement.FieldPath+"'."), nil
		}
		return nil, nil //nolint:nilnil // An unbounded demand has no missing-envelope finding.
	}
	admitted, err := computeSubstrateClaimAdmits(requirement, *envelope)
	if err != nil {
		return nil, err
	}
	if !admitted {
		return supportFinding(requirement, "realization.compute-substrate-not-admitted", "Selected realization envelope cannot satisfy the governed compute-substrate demand at '"+requirement.FieldPath+"'."), nil
	}
	return nil, nil //nolint:nilnil // A supported claim has no diagnostic finding.
}

func computeSubstrateClaimAdmits(requirement Requirement, envelope binding.RealizationEnvelopeV1) (bool, error) {
	for _, concern := range sourceValue(envelope.Concerns) {
		if string(sourceValue(concern.Concern)) != termComputeSubstrate {
			continue
		}
		var mechanism string
		if string(sourceValue(concern.Disposition)) == "unsupported" {
			return false, nil
		}
		if json.Unmarshal(sourceValue(concern.Mechanism), &mechanism) != nil {
			return false, invalidRealization()
		}
		if mechanism == "" {
			return false, nil
		}
		return computeClaimValueAdmits(requirement, mechanism, string(sourceValue(concern.ObservationStrength)))
	}
	return false, nil
}

func computeClaimValueAdmits(requirement Requirement, mechanism, strength string) (bool, error) {
	if requirement.ValueDomain != nil {
		admitted, err := domainAdmitsValue(requirement.ValueDomain, mechanism)
		if err != nil || !admitted {
			return admitted, err
		}
	}
	if requirement.ObservationScope == "" && requirement.ObservationStrength == "" {
		return true, nil
	}
	return observationSatisfied("presence", strength, requirement.ObservationScope, requirement.ObservationStrength), nil
}
