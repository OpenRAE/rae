package sdl

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

// EnvelopeWitness constructs and instantiates a candidate through ordinary SDL
// admission. The envelope carries its explicit witness policy and seed.
//
//nolint:ireturn // The public API returns an opaque native instantiated handle.
func EnvelopeWitness(envelope binding.RealizationEnvelopeV1) (InstantiatedScenario, []diagnostic.Diagnostic, error) {
	parser, err := scenarioParser(DefaultLimits())
	if err != nil {
		return nil, nil, err
	}
	projection, findings, err := parser.EnvelopeWitnessProjection(envelope)
	if err != nil || len(findings) > 0 {
		return nil, findings, err
	}
	raw, err := json.Marshal(projection.Document())
	if err != nil {
		return nil, nil, invalidScenario()
	}
	scenario, err := Parse(raw, DefaultParseOptions())
	if err == nil {
		instantiated, instantiateErr := Instantiate(scenario, nil)
		if instantiateErr == nil {
			return instantiated, []diagnostic.Diagnostic{}, nil
		}
	}
	expression, _ := envelope.Expression.Value()
	id, _ := expression.Id.Value()
	return nil, []diagnostic.Diagnostic{{Code: "realization-envelope.witness.invalid", Domain: termRealizationEnvelope, Address: id, Severity: termError, Message: "generated witness did not pass SDL structural/semantic validation (the envelope does not fully determine a valid scenario instance)"}}, nil
}
