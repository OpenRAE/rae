package admission

import (
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// EnvelopeProbeField carries native SDL field variants, without admission authority.
type EnvelopeProbeField struct {
	Name                    string
	Variations, EnumMembers []any
}

// EnvelopeProbeScope names a native typed model and its fields.
type EnvelopeProbeScope struct {
	Path   string
	Fields []EnvelopeProbeField
}

// EnvelopeProbeCandidate is a bounded proposal; SDL admission must check it.
type EnvelopeProbeCandidate struct {
	Path, DomainKind, Variation, Digest string
	Payload                             Fragment
}

type envelopeProbeBuilder struct {
	owner     *Validator
	base      []byte
	remaining int
	output    []EnvelopeProbeCandidate
}

// EnvelopeProbeCandidates reuses the bounded envelope relation to propose values.
// Native field metadata supplies enum alternatives, not proof of membership.
func EnvelopeProbeCandidates(v *Validator, envelope binding.RealizationEnvelopeV1, scopes []EnvelopeProbeScope, positive bool) ([]EnvelopeProbeCandidate, []diagnostic.Diagnostic, error) {
	if err := checkProbeScopes(scopes); err != nil {
		return nil, nil, err
	}
	document, err := realizationOfferEnvelope(v, envelope)
	if err != nil {
		return nil, nil, err
	}
	expression := at(document, "expression")
	offer, err := materializationOfferFor(expression)
	if err != nil {
		return nil, nil, err
	}
	if findings := offer.invalidDiagnostics(); len(findings) > 0 {
		return nil, findings, nil
	}
	payload, findings := offer.witnessPayload(object(at(expression, "witness_policy", "selections")))
	if len(findings) > 0 {
		return nil, findings, nil
	}
	raw, err := value.Encode(payload, value.Runtime())
	if err != nil {
		return nil, nil, err
	}
	builder := envelopeProbeBuilder{owner: v, base: raw, remaining: 8 << 20, output: []EnvelopeProbeCandidate{}}
	if positive {
		if err := builder.add(stringAt(expression, "id"), "witness", "base-witness", payload); err != nil {
			return nil, nil, err
		}
	}
	fields, models := probeMetadata(scopes)
	if err := builder.leaves(offer, fields, positive); err != nil {
		return nil, nil, err
	}

	if !positive {
		if err := builder.closed(offer.closed, models); err != nil {
			return nil, nil, err
		}
	}
	return builder.output, []diagnostic.Diagnostic{}, nil
}
func checkProbeScopes(scopes []EnvelopeProbeScope) error {
	if len(scopes) > value.Runtime().MaxMembers {
		return invalid()
	}
	count := 0
	projected := make([]any, 0, len(scopes))
	for _, scope := range scopes {
		count += len(scope.Fields)
		if count > value.Runtime().MaxMembers {
			return invalid()
		}
		fields := make([]any, 0, len(scope.Fields))
		for _, field := range scope.Fields {
			fields = append(fields, map[string]any{"name": field.Name, "variants": field.Variations, "enums": field.EnumMembers})
		}
		projected = append(projected, map[string]any{"path": scope.Path, termFields: fields})
	}
	return CheckTransportTree(projected, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
}
func (b *envelopeProbeBuilder) fresh() (map[string]any, error) {
	decoded, err := ingress.Parse(b.base, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return nil, err
	}
	payload, ok := decoded.(map[string]any)
	if !ok {
		return nil, invalid()
	}
	return payload, nil
}
func (b *envelopeProbeBuilder) add(path, kind, variation string, payload map[string]any) error {
	if len(b.output) >= value.Runtime().MaxMembers {
		return value.ErrLimit
	}
	raw, err := value.Encode(payload, value.Runtime())
	if err != nil {
		return err
	}
	if len(raw) > b.remaining {
		return value.ErrLimit
	}
	b.remaining -= len(raw)
	projection, err := AdmitFragment(b.owner, RealizationValue, payload, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
	if err != nil {
		return err
	}
	canonical, err := canonjson.Sorted(raw, true)
	if err != nil {
		return err
	}
	b.output = append(b.output, EnvelopeProbeCandidate{Path: path, DomainKind: kind, Variation: variation, Digest: digest.SHA256(canonical), Payload: projection})
	return nil
}
func (b *envelopeProbeBuilder) assigned(path, kind, variation string, chosen any, positive bool) error {
	payload, err := b.fresh()
	if err != nil {
		return err
	}
	if assignEnvelopePath(payload, path, chosen) == "" {
		if positive {
			variation = "bounded-member"
		}
		if addErr := b.add(path, kind, variation, payload); addErr != nil {
			return addErr
		}
	}
	tokens := materializationOfferTokens(path)
	if !positive && len(tokens) > 1 && tokens[len(tokens)-1] == "type" {
		payload, err = b.fresh()
		if err != nil {
			return err
		}
		if assignEnvelopePath(payload, materializationOfferPath(tokens[:len(tokens)-1]), map[string]any{"type": chosen}) == "" {
			return b.add(path, kind, variation, payload)
		}
	}
	return nil
}
func (b *envelopeProbeBuilder) omitted(path, kind string) error {
	payload, err := b.fresh()
	if err != nil {
		return err
	}
	tokens := materializationOfferTokens(path)
	if len(tokens) == 0 {
		return nil
	}
	parent := any(payload)
	if len(tokens) > 1 {
		var found bool
		parent, found = materializationOfferAt(payload, materializationOfferPath(tokens[:len(tokens)-1]))
		if !found {
			return nil
		}
	}
	mapping := object(parent)
	if _, present := mapping[tokens[len(tokens)-1]]; !present {
		return nil
	}
	delete(mapping, tokens[len(tokens)-1])
	return b.add(path, kind, "omitted-required-exact", payload)
}
func (b *envelopeProbeBuilder) closed(closed map[string]map[string]bool, models map[string]EnvelopeProbeScope) error {
	for _, path := range slices.Sorted(maps.Keys(closed)) {
		scope, typed := models[path]
		if typed {
			if err := b.closedTyped(path, scope, closed[path]); err != nil {
				return err
			}
		} else {
			if err := b.closedUntyped(path, closed[path]); err != nil {
				return err
			}
		}
	}
	return nil
}

func probeMetadata(scopes []EnvelopeProbeScope) (map[string]EnvelopeProbeField, map[string]EnvelopeProbeScope) {
	fields := map[string]EnvelopeProbeField{}
	models := map[string]EnvelopeProbeScope{}
	for _, scope := range scopes {
		models[scope.Path] = scope
		for _, field := range scope.Fields {
			path := field.Name
			if scope.Path != "" {
				path = scope.Path + "." + field.Name
			}
			fields[path] = field
		}
	}
	return fields, models
}
func (b *envelopeProbeBuilder) leaves(offer *materializationOffer, fields map[string]EnvelopeProbeField, positive bool) error {
	for _, path := range slices.Sorted(maps.Keys(offer.leaves)) {
		leaf := offer.leaves[path]
		var variations []any
		if positive {
			variations = envelopePositiveValues(leaf.descriptor)
		} else {
			variations = envelopeNegativeValues(leaf.descriptor, fields[path].EnumMembers)
		}
		for _, variation := range variations {
			if err := b.assigned(path, stringAt(leaf.descriptor, termKind), "value-outside-domain", variation, positive); err != nil {
				return err
			}
		}
		if !positive && leaf.posture == postureExact {
			if err := b.omitted(path, stringAt(leaf.descriptor, termKind)); err != nil {
				return err
			}
		}
	}
	return nil
}

func (b *envelopeProbeBuilder) closedTyped(path string, scope EnvelopeProbeScope, allowed map[string]bool) error {
	fields := slices.Clone(scope.Fields)
	slices.SortFunc(fields, func(a, c EnvelopeProbeField) int { return strings.Compare(a.Name, c.Name) })
	for _, field := range fields {
		if !allowed[field.Name] {
			target := field.Name
			if path != "" {
				target = path + "." + field.Name
			}
			for _, chosen := range field.Variations {
				if err := b.assigned(target, "closed-scope", "extra-dimension", chosen, false); err != nil {
					return err
				}
			}
		}
	}
	return nil
}

func (b *envelopeProbeBuilder) closedUntyped(path string, allowed map[string]bool) error {
	field := "out_of_envelope"
	for allowed[field] {
		field += "_x"
	}
	target := field
	if path != "" {
		target = path + "." + field
	}
	if err := b.assigned(target, "closed-scope", "extra-dimension", "out-of-envelope", false); err != nil {
		return err
	}
	return nil
}
