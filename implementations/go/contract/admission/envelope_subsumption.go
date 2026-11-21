package admission

import (
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

// EnvelopeSubsumptionDiagnostics decides requested-set inclusion using the
// same bounded domain and closure owner as membership. It samples no witnesses.
func EnvelopeSubsumptionDiagnostics(v *Validator, offered, requested binding.RealizationEnvelopeV1) ([]diagnostic.Diagnostic, error) {
	left, err := realizationOfferEnvelope(v, offered)
	if err != nil {
		return nil, err
	}
	right, err := realizationOfferEnvelope(v, requested)
	if err != nil {
		return nil, err
	}
	offer, err := materializationOfferFor(at(left, "expression"))
	if err != nil {
		return nil, err
	}
	request, err := materializationOfferFor(at(right, "expression"))
	if err != nil {
		return nil, err
	}
	findings := append(offer.invalidDiagnostics(), request.invalidDiagnostics()...)
	if len(findings) > 0 {
		return findings, nil
	}
	return append(offer.subsumptionDomains(request), offer.subsumptionClosure(request)...), nil
}
func (o *materializationOffer) subsumptionDomains(request *materializationOffer) []diagnostic.Diagnostic {
	findings := []diagnostic.Diagnostic{}
	paths := slices.Sorted(maps.Keys(o.leaves))
	slices.Sort(paths)
	for _, path := range paths {
		wanted, exists := request.leaves[path]
		if !exists {
			findings = append(findings, realizationOfferFinding("subsumption.requested-unconstrained", path, "requested leaves a path open that offered constrains"))
			continue
		}
		if !materializationDomainSubset(wanted.descriptor, o.leaves[path].descriptor) {
			findings = append(findings, realizationOfferFinding("subsumption.domain-not-subset", path, "requested domain is not a subset of the offered domain"))
		}
	}
	return findings
}
func (o *materializationOffer) subsumptionClosure(request *materializationOffer) []diagnostic.Diagnostic {
	findings := []diagnostic.Diagnostic{}

	paths := slices.Sorted(maps.Keys(o.closed))
	slices.Sort(paths)
	for _, path := range paths {
		label := path
		if label == "" {
			label = "<scenario>"
		}
		requested, exists := request.closed[path]
		if !exists {
			findings = append(findings, realizationOfferFinding("subsumption.closure-mismatch", label, "offered is closed-world where requested is open-world"))
			continue
		}
		if !subset(slices.Sorted(maps.Keys(requested)), o.closed[path]) {
			findings = append(findings, realizationOfferFinding("subsumption.closed-extra", label, "requested admits a closed dimension offered does not"))
		}
	}
	return findings
}
