package processor

import (
	"encoding/json"
	"math"
	"math/big"
	"slices"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

type participantArgumentRules struct {
	Name                       string `json:"name"`
	ValueType                  string `json:"value_type"`
	Cardinality                string `json:"cardinality"`
	Normalization              string `json:"normalization"`
	Omission                   string `json:"omission"`
	NormalizationDisclosureRef string `json:"normalization_disclosure_ref"`
	OmissionDisclosureRef      string `json:"omission_disclosure_ref"`
	DefaultDisclosureRef       string `json:"default_disclosure_ref"`
	LossDisclosureRef          string `json:"loss_disclosure_ref"`
	Minimum, Maximum           *json.Number
	MinLength                  *json.Number `json:"min_length"`
	MaxLength                  *json.Number `json:"max_length"`
	MinItems                   *json.Number `json:"min_items"`
	MaxItems                   *json.Number `json:"max_items"`
	UniqueItems                bool         `json:"unique_items"`
}
type participantArgument struct {
	participantArgumentRules

	HasDefault    bool
	Default       participantArgumentValue
	AllowedValues []Scalar
}
type participantArgumentValue struct {
	Scalar Scalar
	Items  []Scalar
	Many   bool
}

func compileParticipantArgument(raw json.RawMessage) (participantArgument, error) {
	var wire struct {
		participantArgumentRules

		Default       json.RawMessage   `json:"default"`
		AllowedValues []json.RawMessage `json:"allowed_values"`
	}
	if err := participantDecode(raw, &wire); err != nil {
		return participantArgument{}, err
	}
	result := participantArgument{participantArgumentRules: wire.participantArgumentRules, AllowedValues: []Scalar{}}
	if len(wire.Default) > 0 && string(wire.Default) != termNull {
		var err error
		result.Default, err = participantArgumentLiteral(wire.Default)
		if err != nil {
			return participantArgument{}, err
		}
		result.HasDefault = true
	}
	for _, raw := range wire.AllowedValues {
		scalar, err := compiledScalar(raw)
		if err != nil {
			return participantArgument{}, err
		}
		result.AllowedValues = append(result.AllowedValues, scalar)
	}
	return result, nil
}
func participantArgumentLiteral(raw json.RawMessage) (participantArgumentValue, error) {
	if len(raw) > 0 && raw[0] == '[' {
		var values []json.RawMessage
		if err := participantDecode(raw, &values); err != nil {
			return participantArgumentValue{}, err
		}
		result := participantArgumentValue{Items: []Scalar{}, Many: true}
		for _, item := range values {
			scalar, err := compiledScalar(item)
			if err != nil {
				return participantArgumentValue{}, err
			}
			result.Items = append(result.Items, scalar)
		}
		return result, nil
	}
	scalar, err := compiledScalar(raw)
	return participantArgumentValue{Scalar: scalar}, err
}
func (literal participantArgumentValue) document() any {
	if !literal.Many {
		return literal.Scalar.Value()
	}
	result := make([]any, len(literal.Items))
	for index, scalar := range literal.Items {
		result[index] = scalar.Value()
	}
	return result
}
func participantNumber(value json.Number) (*big.Rat, bool) {
	if strings.ContainsAny(string(value), ".eE") {
		f, err := strconv.ParseFloat(string(value), 64)
		if err != nil || math.IsInf(f, 0) || math.IsNaN(f) {
			return nil, false
		}
		return new(big.Rat).SetFloat64(f), true
	}
	r, ok := new(big.Rat).SetString(string(value))
	return r, ok
}
func participantScalarEqual(left, right Scalar) bool {
	if left.kind != right.kind {
		return false
	}
	if l, ok := left.value.(json.Number); ok {
		r, rok := right.value.(json.Number)
		if !rok {
			return false
		}
		lv, lok := participantNumber(l)
		rv, valid := participantNumber(r)
		return lok && valid && lv.Cmp(rv) == 0
	}
	return left.value == right.value
}
func participantScalarKey(input Scalar) string {
	if number, ok := input.value.(json.Number); ok {
		if rational, valid := participantNumber(number); valid {
			return input.kind + ":" + rational.RatString()
		}
	}
	return input.kind + ":" + string(rawJSON(input.value))
}
func participantBound(count int, bound *json.Number, minimum bool) bool {
	if bound == nil {
		return true
	}
	r, ok := participantNumber(*bound)
	if !ok {
		return false
	}
	comparison := new(big.Rat).SetInt64(int64(count)).Cmp(r)
	return minimum && comparison >= 0 || !minimum && comparison <= 0
}
func (definition participantArgument) normalizeScalar(input Scalar, work *participantWork) (Scalar, error) {
	if !work.spend(1+len(definition.AllowedValues)) || !definition.acceptsType(input) {
		return Scalar{}, participantArgumentInput()
	}
	result := input
	switch definition.Normalization {
	case "identity":
	case "trim":
		text, ok := input.value.(string)
		if !ok {
			return Scalar{}, participantArgumentInput()
		}
		result.value = strings.TrimFunc(text, func(r rune) bool { return unicode.IsSpace(r) || r >= 0x1c && r <= 0x1f })
	default:
		return Scalar{}, participantArgumentInput()
	}
	if !definition.scalarDomainAdmits(result) {
		return Scalar{}, participantArgumentInput()
	}
	return result, nil
}
func (definition participantArgument) acceptsType(input Scalar) bool {
	switch definition.ValueType {
	case termScalarString, "reference":
		return input.kind == termScalarString
	case termScalarInteger:
		return input.kind == termScalarInteger
	case termScalarBoolean:
		return input.kind == termScalarBoolean
	case "number":
		n, ok := input.value.(json.Number)
		if !ok {
			return false
		}
		f, err := strconv.ParseFloat(string(n), 64)
		return err == nil && !math.IsInf(f, 0) && !math.IsNaN(f)
	default:
		return false
	}
}
func (definition participantArgument) scalarDomainAdmits(input Scalar) bool {
	if text, ok := input.value.(string); ok {
		length := utf8.RuneCountInString(text)
		if !participantBound(length, definition.MinLength, true) || !participantBound(length, definition.MaxLength, false) {
			return false
		}
	}
	if n, ok := input.value.(json.Number); ok {
		if !definition.numberAdmits(n) {
			return false
		}
	}
	return len(definition.AllowedValues) == 0 || slices.ContainsFunc(definition.AllowedValues, func(allowed Scalar) bool { return participantScalarEqual(input, allowed) })
}
func (definition participantArgument) numberAdmits(input json.Number) bool {
	actual, valid := participantNumber(input)
	if !valid {
		return false
	}
	for _, bound := range []struct {
		value   *json.Number
		minimum bool
	}{{definition.Minimum, true}, {definition.Maximum, false}} {
		if bound.value == nil {
			continue
		}
		limit, valid := participantNumber(*bound.value)
		if !valid {
			return false
		}
		cmp := actual.Cmp(limit)
		if bound.minimum && cmp < 0 || !bound.minimum && cmp > 0 {
			return false
		}
	}
	return true
}
func (definition participantArgument) normalize(input participantArgumentValue, work *participantWork) (participantArgumentValue, error) {
	if definition.Cardinality == "one" {
		if input.Many {
			return participantArgumentValue{}, participantArgumentInput()
		}
		scalar, err := definition.normalizeScalar(input.Scalar, work)
		return participantArgumentValue{Scalar: scalar}, err
	}
	if definition.Cardinality != "many" || !input.Many || !participantBound(len(input.Items), definition.MinItems, true) || !participantBound(len(input.Items), definition.MaxItems, false) {
		return participantArgumentValue{}, participantArgumentInput()
	}
	result := participantArgumentValue{Many: true, Items: []Scalar{}}
	seen := map[string]bool{}
	for _, item := range input.Items {
		scalar, err := definition.normalizeScalar(item, work)
		if err != nil {
			return participantArgumentValue{}, err
		}
		key := participantScalarKey(scalar)
		if definition.UniqueItems && seen[key] {
			return participantArgumentValue{}, participantArgumentInput()
		}
		seen[key] = true
		result.Items = append(result.Items, scalar)
	}
	return result, nil
}

type participantArgumentResolution struct {
	ActionContractAddress       string   `json:"action_contract_address"`
	ArgumentShapeRef            string   `json:"argument_shape_ref"`
	ProposalRef                 string   `json:"proposal_ref"`
	NormalizedArguments         [][2]any `json:"normalized_arguments"`
	DefaultedArgumentNames      []string `json:"defaulted_argument_names"`
	OmittedArgumentNames        []string `json:"omitted_argument_names"`
	NormalizationDisclosureRefs []string `json:"normalization_disclosure_refs"`
	OmissionDisclosureRefs      []string `json:"omission_disclosure_refs"`
	DefaultDisclosureRefs       []string `json:"default_disclosure_refs"`
	LossDisclosureRefs          []string `json:"loss_disclosure_refs"`
}

func (resolution *participantArgumentResolution) resolve(definition participantArgument, input map[string]json.RawMessage, work *participantWork) error {
	resolution.NormalizationDisclosureRefs = append(resolution.NormalizationDisclosureRefs, definition.NormalizationDisclosureRef)
	resolution.OmissionDisclosureRefs = append(resolution.OmissionDisclosureRefs, definition.OmissionDisclosureRef)
	resolution.LossDisclosureRefs = append(resolution.LossDisclosureRefs, definition.LossDisclosureRef)
	literal := definition.Default
	if raw, present := input[definition.Name]; present {
		var err error
		literal, err = participantArgumentLiteral(raw)
		if err != nil {
			return participantArgumentInput()
		}
	} else {
		switch definition.Omission {
		case "omit":
			resolution.OmittedArgumentNames = append(resolution.OmittedArgumentNames, definition.Name)
			return nil
		case "use_default":
			if !definition.HasDefault || definition.DefaultDisclosureRef == "" {
				return participantArgumentInput()
			}
			resolution.DefaultedArgumentNames = append(resolution.DefaultedArgumentNames, definition.Name)
			resolution.DefaultDisclosureRefs = append(resolution.DefaultDisclosureRefs, definition.DefaultDisclosureRef)
		default:
			return participantArgumentInput()
		}
	}
	normalized, err := definition.normalize(literal, work)
	if err != nil {
		return err
	}
	resolution.NormalizedArguments = append(resolution.NormalizedArguments, [2]any{definition.Name, normalized.document()})
	return nil
}

// ResolveParticipantActionArguments resolves concrete values through one compiled shape.
//
//nolint:ireturn // The reviewed API returns the existing sealed normalized carrier.
func ResolveParticipantActionArguments(model RuntimeModel, actionContractAddress, argumentShapeRef, proposalRef string, proposed admission.Fragment) (admission.Fragment, error) {
	owned, err := nativeRuntimeModel(model)
	if err != nil {
		return nil, err
	}
	action, ok := owned.participants.actions[actionContractAddress]
	if !ok || action.ArgumentShapeRef == "" || action.ArgumentShapeRef != argumentShapeRef || proposalRef == "" || len(proposalRef) > 1<<20 || !utf8.ValidString(proposalRef) {
		return nil, participantArgumentInput()
	}
	var input map[string]json.RawMessage
	if checkErr := participantFragmentDecode(proposed, admission.RealizationValue, &input); checkErr != nil {
		return nil, checkErr
	}
	if input == nil || len(input) > 4096 {
		return nil, participantArgumentInput()
	}
	names := map[string]bool{}
	for _, definition := range action.arguments {
		names[definition.Name] = true
	}
	for name := range input {
		if !names[name] {
			return nil, participantArgumentInput()
		}
	}
	result := participantArgumentResolution{ActionContractAddress: actionContractAddress, ArgumentShapeRef: argumentShapeRef, ProposalRef: proposalRef, NormalizedArguments: [][2]any{}, DefaultedArgumentNames: []string{}, OmittedArgumentNames: []string{}, NormalizationDisclosureRefs: []string{}, OmissionDisclosureRefs: []string{}, DefaultDisclosureRefs: []string{}, LossDisclosureRefs: []string{}}
	work := participantWork{remaining: participantRelationWork}
	for _, definition := range action.arguments {
		if checkErr := result.resolve(definition, input, &work); checkErr != nil {
			return nil, checkErr
		}
	}
	result.NormalizationDisclosureRefs = dedupe(result.NormalizationDisclosureRefs)
	result.OmissionDisclosureRefs = dedupe(result.OmissionDisclosureRefs)
	result.DefaultDisclosureRefs = dedupe(result.DefaultDisclosureRefs)
	result.LossDisclosureRefs = dedupe(result.LossDisclosureRefs)
	owner, err := processorAdmissionOwner()
	if err != nil {
		return nil, err
	}
	return admission.AdmitFragment(owner, admission.ValidatedActionSelection, decodeProjection(rawJSON(result)), participantRelationLimits())
}
