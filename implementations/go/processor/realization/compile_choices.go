package realization

import (
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func bindScalarChoices(input admission.Fragment) (admission.Fragment, error) {
	if admission.CheckFragment(input, admission.RealizationConstraint) != nil {
		return nil, invalidRealization()
	}
	document := ownedProjection[map[string]any](input.Document())
	remaining := 4096
	if err := visitScalarChoices(ownedProjection[map[string]any](document["root"]), &remaining); err != nil {
		return nil, err
	}
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	return admission.AdmitFragment(owner, admission.RealizationConstraint, document, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 256})
}

func visitScalarChoices(rule map[string]any, remaining *int) error {
	switch rule[termKind] {
	case termRecursiveRecord:
		for _, child := range ownedProjection[map[string]any](rule["fields"]) {
			if err := visitScalarChoices(ownedProjection[map[string]any](child), remaining); err != nil {
				return err
			}
		}
	case termSequence:
		for _, child := range ownedProjection[[]any](rule["items"]) {
			if err := visitScalarChoices(ownedProjection[map[string]any](child), remaining); err != nil {
				return err
			}
		}
	case termKeyedCollection:
		return bindCollectionChoices(rule, remaining)
	}
	return nil
}

type scalarChoiceAliases struct {
	remaining  *int
	identities map[string]string
	aliases    []any
}

func bindCollectionChoices(rule map[string]any, remaining *int) error {
	state := scalarChoiceAliases{remaining: remaining, identities: map[string]string{}, aliases: []any{}}
	members := ownedProjection[[]any](rule["members"])
	for _, item := range members {
		member := ownedProjection[map[string]any](item)
		key, err := projectionDigest(member["identity"])
		if err != nil {
			return err
		}
		state.identities[key] = key
	}
	for _, item := range members {
		member := ownedProjection[map[string]any](item)
		if err := visitScalarChoices(ownedProjection[map[string]any](member["constraint"]), remaining); err != nil {
			return err
		}
		if err := state.member(rule, member); err != nil {
			return err
		}
	}
	rule["aliases"] = state.aliases
	return nil
}
func (s *scalarChoiceAliases) member(rule, member map[string]any) error {
	choices, err := memberIdentityChoices(rule, member)
	if err != nil || choices == nil {
		return err
	}
	original := ownedProjection[[]any](member["identity"])
	canonical, err := projectionDigest(original)
	if err != nil {
		return err
	}
	positions := make([]int, len(choices))
	for {
		*s.remaining--
		if *s.remaining < 0 {
			return invalidRealization()
		}
		candidate, err := scalarChoiceIdentity(choices, positions)
		if err != nil {
			return err
		}
		if err := s.record(candidate, original, canonical); err != nil {
			return err
		}
		if !advanceChoice(choices, positions) {
			return nil
		}
	}
}
func scalarChoiceIdentity(choices [][]any, positions []int) ([]any, error) {
	candidate := make([]any, len(choices))
	for index, values := range choices {
		if len(values) == 0 {
			return nil, invalidRealization()
		}
		candidate[index] = values[positions[index]]
		switch scalar := candidate[index].(type) {
		case string, bool:
		case json.Number:
			if strings.ContainsAny(string(scalar), ".eE") {
				return nil, invalidRealization()
			}
		default:
			return nil, invalidRealization()
		}
	}
	return candidate, nil
}
func (s *scalarChoiceAliases) record(candidate, original []any, canonical string) error {
	key, err := projectionDigest(candidate)
	if err != nil {
		return err
	}
	if previous, exists := s.identities[key]; exists {
		if previous != canonical {
			return invalidRealization()
		}
		return nil
	}
	s.identities[key] = canonical
	s.aliases = append(s.aliases, map[string]any{"identity": candidate, termTarget: original})
	return nil
}
func advanceChoice(choices [][]any, positions []int) bool {
	for index := len(positions) - 1; index >= 0; index-- {
		positions[index]++
		if positions[index] < len(choices[index]) {
			return true
		}
		positions[index] = 0
	}
	return false
}

func memberIdentityChoices(rule, member map[string]any) ([][]any, error) {
	child := ownedProjection[map[string]any](member["constraint"])
	if child[termKind] != termRecursiveRecord {
		return nil, nil
	}
	fields := ownedProjection[map[string]any](child["fields"])
	identities := ownedProjection[[]any](rule["identity_fields"])
	original := ownedProjection[[]any](member["identity"])
	choices := make([][]any, len(identities))
	bounded := false
	for index, field := range identities {
		choices[index] = []any{original[index]}
		value, ok := fields[ownedProjection[string](field)].(map[string]any)
		if !ok || value[termKind] != termDomain {
			continue
		}
		domain := ownedProjection[map[string]any](value[termDomain])
		if domain[termKind] != termEnum {
			return nil, invalidRealization()
		}
		choices[index] = ownedProjection[[]any](domain[termValues])
		bounded = true
	}
	if !bounded {
		return nil, nil
	}
	return choices, nil
}
