package sdl

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

// EnvelopeProbe retains an admitted scenario and its original bounded candidate payload.
type EnvelopeProbe struct {
	Path, DomainKind, Variation, Digest string
	Payload                             admission.Fragment
	Scenario                            InstantiatedScenario
}

// EnvelopeProbes admits every proposed positive or negative probe through
// ordinary SDL construction and the native membership relation.
func EnvelopeProbes(envelope binding.RealizationEnvelopeV1, positive bool) ([]EnvelopeProbe, []diagnostic.Diagnostic, error) {
	base, _, err := EnvelopeWitness(envelope)
	if err != nil {
		return nil, nil, err
	}
	if base == nil {
		return []EnvelopeProbe{}, []diagnostic.Diagnostic{probeNoWitness(envelope, positive)}, nil
	}
	owned, ok := base.(*instantiated)
	if !ok || owned == nil {
		return nil, nil, invalidScenario()
	}
	candidates, findings, err := owned.parser.EnvelopeProbeCandidates(owned.document, envelope, positive)
	if err != nil || len(findings) > 0 {
		return nil, findings, err
	}
	return collectEnvelopeProbes(candidates, envelope, positive)
}
func collectEnvelopeProbes(candidates []admission.EnvelopeProbeCandidate, envelope binding.RealizationEnvelopeV1, positive bool) ([]EnvelopeProbe, []diagnostic.Diagnostic, error) {
	findings := []diagnostic.Diagnostic{}
	probes := []EnvelopeProbe{}
	seen := map[[2]string]bool{}
	for _, candidate := range candidates {
		scenario, valid := admitEnvelopeProbe(candidate, envelope, positive)
		if !valid {
			if positive {
				findings = append(findings, diagnostic.Diagnostic{Code: "realization-envelope.positive-probe.invalid-candidate", Domain: termRealizationEnvelope, Address: candidate.Path, Severity: termError, Message: "bounded variation did not pass ordinary SDL and membership validation"})
			}
			continue
		}
		key := [2]string{candidate.Path, candidate.Digest}
		if positive {
			key[0] = ""
		}
		if seen[key] {
			continue
		}
		seen[key] = true
		probes = append(probes, EnvelopeProbe{Path: candidate.Path, DomainKind: candidate.DomainKind, Variation: candidate.Variation, Digest: candidate.Digest, Payload: candidate.Payload, Scenario: scenario})
	}
	return probes, findings, nil
}

//nolint:ireturn // Only an exact instantiated scenario from the native owner is returned.
func admitEnvelopeProbe(candidate admission.EnvelopeProbeCandidate, envelope binding.RealizationEnvelopeV1, positive bool) (InstantiatedScenario, bool) {
	raw, err := json.Marshal(candidate.Payload.Document())
	if err != nil {
		return nil, false
	}
	parsed, err := Parse(raw, DefaultParseOptions())
	if err != nil {
		return nil, false
	}
	instantiated, err := Instantiate(parsed, nil)
	if err != nil {
		return nil, false
	}
	membership, err := EnvelopeMembershipDiagnostics(instantiated, envelope)
	if err != nil || (len(membership) == 0) != positive {
		return nil, false
	}
	return instantiated, true
}
func probeNoWitness(envelope binding.RealizationEnvelopeV1, positive bool) diagnostic.Diagnostic {
	expression, _ := envelope.Expression.Value()
	id, _ := expression.Id.Value()
	code, message := "negative-probe.no-witness", "cannot derive a witness base for negative probes"
	if positive {
		code, message = "positive-probe.no-witness", "cannot derive positive probes from a non-constructive envelope"
	}
	return diagnostic.Diagnostic{Code: "realization-envelope." + code, Domain: termRealizationEnvelope, Address: id, Severity: termError, Message: message}
}
