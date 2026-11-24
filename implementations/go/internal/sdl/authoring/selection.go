package authoring

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
)

type recordedOutcome struct {
	Kind      string          `json:"kind"`
	Value     json.RawMessage `json:"value"`
	Member    string          `json:"member_id"`
	Members   []string        `json:"member_ids"`
	Reference string          `json:"reference_id"`
}

func selectionInvalid() error { return fault.New(fault.InvalidInput, "sdl-selection-invalid", nil) }

// Select applies complete recorded outcomes against one unchanged admitted family.
// It grants no random generation, host access, or execution permission.
func (p *Parser) Select(document *Document, outcomes []byte, trial []byte) (*Document, error) {
	if document == nil || !document.Validated() {
		return nil, selectionInvalid()
	}
	trialValue, err := p.selectionTrial(trial)
	if err != nil {
		return nil, err
	}
	family, err := p.AdmitFamily(document)
	if err != nil {
		return nil, err
	}
	model := family.semantic
	recorded, err := p.selectionOutcomes(outcomes, model)
	if err != nil {
		return nil, err
	}
	if !model.selectionRelations(recorded) {
		return nil, selectionInvalid()
	}
	input := model.document
	value, err := p.modelValue(input)
	if err != nil {
		return nil, err
	}
	c := composition{parser: p}
	original, err := c.bindingPayload(value, model.order)
	if err != nil {
		return nil, err
	}
	writes, parameters, structural, err := model.selectionWrites(original, recorded)
	if err != nil {
		return nil, err
	}
	payload, err := c.bindingPayload(value, model.order)
	if err != nil {
		return nil, err
	}
	if err = applySelectionWrites(original, payload, writes, structural); err != nil {
		return nil, err
	}
	selected, err := p.rebuildFamily(payload, input)
	if err != nil {
		return nil, selectionInvalid()
	}
	result, err := p.instantiate(selected, parameters, "", trialValue)
	if err != nil {
		return nil, selectionInvalid()
	}
	return result, nil
}

func applySelectionWrites(original, payload map[string]any, writes []selectedWrite, structural bool) error {
	for _, write := range writes {
		if err := applySelectedWrite(payload, write); err != nil {
			return err
		}
	}
	payload[variationPointsField] = map[string]any{}
	if structural {
		reconcileSelectedProvenance(original, payload)
	}
	return nil
}
func (p *Parser) selectionTrial(raw []byte) (any, error) {
	if len(raw) == 0 {
		return nil, nil //nolint:nilnil // Null represents valid absence in this operation contract.
	}
	value, err := ingress.Parse(raw, ingress.Limits{MaxBytes: int(p.limits.MaxInputBytes), MaxDepth: p.limits.MaxDepth}, ingress.Object)
	if err != nil {
		return nil, err
	}
	if err = p.models.CheckModelFragment(instantiatedContract, "#/$defs/TrialInstantiationProvenance", raw, modelLimits(raw)); err != nil {
		return nil, err
	}
	return value, nil
}

func (p *Parser) selectionOutcomes(raw []byte, model *semanticModel) (map[string]recordedOutcome, error) {
	value, err := ingress.Parse(raw, ingress.Limits{MaxBytes: int(p.limits.MaxInputBytes), MaxDepth: p.limits.MaxDepth}, ingress.Object)
	if err != nil {
		return nil, err
	}
	if len(object(value)) != len(model.variations) {
		return nil, selectionInvalid()
	}
	result := make(map[string]recordedOutcome, len(model.variations))
	for _, point := range model.variations {
		member, exists := object(value)[point.name]
		if !exists {
			return nil, selectionInvalid()
		}
		encoded, err := json.Marshal(member)
		if err != nil {
			return nil, err
		}
		var outcome recordedOutcome
		if json.Unmarshal(encoded, &outcome) != nil {
			return nil, selectionInvalid()
		}
		definition := outcomeDefinition(outcome.Kind)
		if definition == "" || p.models.CheckModelFragment("experiment-authoring-input-v1", "#/$defs/"+definition, encoded, modelLimits(encoded)) != nil {
			return nil, selectionInvalid()
		}
		if !point.admitsOutcome(outcome) {
			return nil, selectionInvalid()
		}
		result[point.name] = outcome
	}
	return result, nil
}

func outcomeDefinition(kind string) string {
	switch kind {
	case termLiteral:
		return "LiteralBindingValueModel"
	case termMember:
		return "ExperimentSelectionMemberOutcomeModel"
	case termReference:
		return "ExperimentSelectionReferenceOutcomeModel"
	case termSubset:
		return "ExperimentSelectionSubsetOutcomeModel"
	case termOrder:
		return "ExperimentSelectionOrderOutcomeModel"
	default:
		return ""
	}
}
func (p semanticVariation) admitsOutcome(outcome recordedOutcome) bool {
	switch p.Kind {
	case variationParameterKind, termLogicalTiming:
		return outcome.Kind == termLiteral && p.Domain.contains(variationScalar(outcome.Value))
	case termGovernedReference:
		return outcome.Kind == termReference && slices.Contains(p.Domain.Allowed, outcome.Reference)
	case variationAlternativeKind:
		_, exists := p.Alternatives[outcome.Member]
		return outcome.Kind == termMember && exists
	case termSubset, termOrder:
		return p.admitsCollectionOutcome(outcome)
	default:
		return false
	}
}
func (p semanticVariation) admitsCollectionOutcome(outcome recordedOutcome) bool {
	if outcome.Kind != p.Kind {
		return false
	}
	selected := map[string]int{}
	for index, member := range outcome.Members {
		if _, exists := p.Members[member]; !exists {
			return false
		}
		if _, duplicate := selected[member]; duplicate {
			return false
		}
		selected[member] = index
	}
	if p.Kind == termOrder {
		return p.admitsOrder(selected)
	}
	maximum := len(p.Members)
	if p.Maximum != nil {
		maximum = *p.Maximum
	}
	return len(selected) >= p.Minimum && len(selected) <= maximum
}
func (p semanticVariation) admitsOrder(positions map[string]int) bool {
	if len(positions) != len(p.Members) {
		return false
	}
	for _, edge := range p.Precedence {
		if positions[edge.Before] >= positions[edge.After] {
			return false
		}
	}
	for member, position := range p.FixedPositions {
		if positions[member] != position {
			return false
		}
	}
	return true
}
func (d semanticVariationDomain) contains(value any) bool {
	if values, finite := d.finite(); finite {
		return concreteAllowed(value, values)
	}
	if d.Kind != variationNumericKind {
		return false
	}
	kind := domain.Number
	if d.Numeric == integerType {
		kind = domain.Integer
	}
	descriptor := domain.Interval{Type: kind, Lower: d.Lower, Upper: d.Upper, LowerClosed: d.LowerClosed == nil || *d.LowerClosed, UpperClosed: d.UpperClosed == nil || *d.UpperClosed}
	member, err := domain.In(value, descriptor)
	return err == nil && member
}
func (m *semanticModel) selectionRelations(outcomes map[string]recordedOutcome) bool {
	selected := map[string]map[string]bool{}
	for point, outcome := range outcomes {
		selected[point] = map[string]bool{}
		if outcome.Kind == termMember {
			selected[point][outcome.Member] = true
		}
		for _, member := range outcome.Members {
			selected[point][member] = true
		}
	}
	for _, point := range m.variations {
		members := point.Members
		if point.Kind == variationAlternativeKind {
			members = point.Alternatives
		}
		for _, name := range slices.Sorted(maps.Keys(selected[point.name])) {
			member := members[name]
			if !m.selectedMemberRelations(selected, member) {
				return false
			}
		}
	}
	return true
}
func (m *semanticModel) selectedMemberRelations(selected map[string]map[string]bool, member semanticVariationMember) bool {
	for _, relation := range member.Requires {
		if !m.selectionRelation(selected, relation, true) {
			return false
		}
	}
	for _, relation := range member.Excludes {
		if !m.selectionRelation(selected, relation, false) {
			return false
		}
	}
	return true
}
func (m *semanticModel) selectionRelation(selected map[string]map[string]bool, relation semanticSelectionRelation, required bool) bool {
	points := m.variationMatches(relation.Point)
	if len(points) != 1 {
		return false
	}
	for _, member := range relation.Members {
		if selected[m.variations[points[0]].name][member] != required {
			return false
		}
	}
	return true
}

func (m *semanticModel) selectedOwner(reference, section string) (string, error) {
	owner, valid := m.structuralOwner(reference, section)
	if !valid {
		return "", selectionInvalid()
	}
	return owner, nil
}
func selectionField(slot string) string { _, field, _ := strings.Cut(slot, "."); return field }
