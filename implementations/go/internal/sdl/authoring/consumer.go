package authoring

import (
	"encoding/json"
	"math/big"
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/concept"
)

// The published selection-policy output bound also caps finite populations.
const maxSelectionOutputBound = 1_000_000

// ConceptSubjects projects the existing native declaration index.
func (d *Document) ConceptSubjects() ([]concept.Subject, error) {
	if !d.Validated() {
		return nil, semanticInvalid()
	}
	identity, err := d.CanonicalDigest()
	if err != nil {
		return nil, err
	}
	return conceptSubjects(d, identity), nil
}

// ValidateExperimentSelectionAgainstFamily admits intent without selecting a trial.
func (p *Parser) ValidateExperimentSelectionAgainstFamily(spec binding.ExperimentAuthoringInputV1, family *Document) (binding.ExperimentAuthoringInputV1, error) {
	if family == nil || !family.Validated() || family.contract != expandedContract {
		return binding.ExperimentAuthoringInputV1{}, selectionInvalid()
	}
	raw, err := json.Marshal(spec)
	if err != nil || p.models.CheckPortable("experiment-authoring-input-v1", raw, modelLimits(raw)) != nil {
		return binding.ExperimentAuthoringInputV1{}, selectionInvalid()
	}
	var copied binding.ExperimentAuthoringInputV1
	if json.Unmarshal(raw, &copied) != nil {
		return binding.ExperimentAuthoringInputV1{}, selectionInvalid()
	}
	var intent familySelectionIntent
	if json.Unmarshal(raw, &intent) != nil {
		return binding.ExperimentAuthoringInputV1{}, selectionInvalid()
	}
	if len(intent.RunPlan.Policies) == 0 && intent.Factorial.Profile != "factorial-treatments-v1" {
		return copied, nil
	}
	if !intent.matchesFamily(text(family.semantic.root[nameField])) {
		return binding.ExperimentAuthoringInputV1{}, selectionInvalid()
	}
	points := make(map[string]semanticVariation, len(family.semantic.variations))
	for _, point := range family.semantic.variations {
		points[point.name] = point
	}
	for _, rawPolicy := range intent.RunPlan.Policies {
		if !selectionPolicyAdmitted(rawPolicy, points) {
			return binding.ExperimentAuthoringInputV1{}, selectionInvalid()
		}
	}

	return copied, nil
}

type familySelectionIntent struct {
	Intended struct {
		Kind string `json:"ref_kind"`
		ID   string `json:"ref_id"`
	} `json:"intended_scenario_ref"`
	RunPlan struct {
		Policies map[string]json.RawMessage `json:"selection_policies"`
	} `json:"run_plan"`
	Factorial struct {
		Profile string `json:"profile"`
	} `json:"factorial_design"`
	Bindings struct {
		Descriptors []struct {
			Target struct {
				Family string `json:"scenario_family_id"`
			} `json:"target"`
		} `json:"descriptors"`
	} `json:"binding_descriptors"`
}
type familySelectionPolicy struct {
	Kind     string                     `json:"kind"`
	Point    string                     `json:"point_ref"`
	Bound    int                        `json:"output_bound"`
	Outcome  recordedOutcome            `json:"outcome"`
	Outcomes map[string]recordedOutcome `json:"outcomes"`
}

func (intent familySelectionIntent) matchesFamily(name string) bool {
	if intent.Intended.Kind != "scenario" || intent.Intended.ID != name {
		return false
	}
	for _, descriptor := range intent.Bindings.Descriptors {
		if descriptor.Target.Family != "" && descriptor.Target.Family != intent.Intended.ID {
			return false
		}
	}

	return true
}

func selectionPolicyAdmitted(raw json.RawMessage, points map[string]semanticVariation) bool {
	var policy familySelectionPolicy
	if json.Unmarshal(raw, &policy) != nil {
		return false
	}
	if policy.Kind == "product" {
		return true
	}
	point, exists := points[policy.Point]
	if !exists {
		return false
	}
	switch policy.Kind {
	case "fixed":
		return point.admitsOutcome(policy.Outcome)
	case "stratified":
		for _, outcome := range policy.Outcomes {
			if !point.admitsOutcome(outcome) {
				return false
			}
		}
		return true
	case "enumerate", "sample":
		population, ok := variationPopulation(point)
		return ok && population >= 1 && population <= maxSelectionOutputBound && (policy.Kind != "enumerate" || policy.Bound == population)
	default:
		return false
	}
}

func variationPopulation(point semanticVariation) (int, bool) {
	switch point.Kind {
	case variationParameterKind, termLogicalTiming:
		if values, finite := point.Domain.finite(); finite {
			return len(values), true
		}
		if point.Domain.Kind == variationNumericKind && point.Domain.Numeric == integerType {
			lo, hi := point.Domain.integers()
			n := new(big.Int).Add(new(big.Int).Sub(hi, lo), big.NewInt(1))
			if n.IsInt64() && n.Int64() > 0 && n.Int64() <= maxSelectionOutputBound {
				return int(n.Int64()), true
			}
		}
	case termGovernedReference:
		return len(point.Domain.Allowed), true
	case variationAlternativeKind:
		return len(point.Alternatives), true
	}
	return 0, false
}

// ArtifactSources returns only Source models selected by the admitted schema.
// Arbitrary data objects cannot introduce a source by naming one of its fields.
func (d *Document) ArtifactSources() (map[string]json.RawMessage, error) {
	if !d.Validated() {
		return nil, semanticInvalid()
	}
	query := newScopeQueries(d.semantic.scopes.w.parser, d.contract, d.semantic.root)
	walk := artifactSourceWalk{document: d, queries: query, output: map[string]json.RawMessage{}}
	if err := walk.visit(d.semantic.root, query.w.parser.schemas[d.contract], "#", nil); err != nil {
		return nil, err
	}
	return walk.output, nil
}

type artifactSourceWalk struct {
	document *Document
	queries  *scopeQueries
	output   map[string]json.RawMessage
}

func (w *artifactSourceWalk) visit(value any, schema map[string]any, pointer string, trail []string) error {
	schema, pointer = w.queries.schema(schema, pointer, value)
	if schema == nil {
		return nil
	}
	if pointer == termSourceDefinition {
		return w.record(value, trail)
	}
	switch entry := value.(type) {
	case map[string]any:
		return w.mapping(entry, schema, pointer, trail)
	case []any:
		for index, item := range entry {
			if err := w.visit(item, object(schema["items"]), pointer+"/items", appendPath(trail, strconv.Itoa(index))); err != nil {
				return err
			}
		}
	}
	return nil
}
func (w *artifactSourceWalk) record(input any, trail []string) error {
	source := object(input)
	if source["artifact_requirement"] == nil {
		return nil
	}
	raw, err := json.Marshal(source)
	if err != nil {
		return err
	}
	w.output[jsonpointer.FromTokens(trail)] = raw
	return nil
}
func schemaPropertyPointer(schema map[string]any, pointer, name string) string {
	if _, known := object(schema["properties"])[name]; known {
		return pointer + "/properties/" + jsonpointer.EscapeToken(name)
	}
	return pointer + "/additionalProperties"
}
func (w *artifactSourceWalk) mapping(entry, schema map[string]any, pointer string, trail []string) error {
	for _, name := range orderedKeys(entry, w.document.semantic.index.order[jsonpointer.FromTokens(trail)]) {
		child, err := w.queries.w.propertySchema(schema, name)
		if err != nil {
			continue
		}
		if err := w.visit(entry[name], child, schemaPropertyPointer(schema, pointer, name), appendPath(trail, name)); err != nil {
			return err
		}
	}
	return nil
}

// ObservationScopes shares native declaration resolution and private scope queries.
func (d *Document) ObservationScopes(pointers, references []string, profiles []admission.RealizationCollectionProfile) (map[string]string, error) {
	if !d.Validated() || len(pointers) > 4096 || len(references) > 4096 || len(pointers) > 4096-len(references) {
		return nil, semanticInvalid()
	}
	query := newScopeQueries(d.semantic.scopes.w.parser, d.contract, d.semantic.root)
	query.profiles = slices.Clone(profiles)
	output := map[string]string{}
	for _, pointer := range pointers {
		scope, err := query.resolve(pointer)
		if err != nil {
			return nil, err
		}
		output[pointer] = scope
	}
	for _, reference := range references {
		tokens, err := d.observationReferenceTokens(reference)
		if err != nil {
			return nil, err
		}
		tokens = query.observationCollectionTokens(tokens)
		scope, err := query.resolve(jsonpointer.FromTokens(tokens))
		if err != nil {
			return nil, err
		}
		output[reference] = scope
	}

	return output, nil
}

func (d *Document) observationReferenceTokens(reference string) ([]string, error) {
	if len(reference) > 4096 {
		return nil, semanticInvalid()
	}
	resolved := d.semantic.referenceResult(reference, []semanticPurpose{referenceObservation})
	if len(resolved.domain) != 1 || len(resolved.eligible) != 1 {
		return nil, semanticInvalid()
	}
	tokens := d.semantic.index.declarations[resolved.domain[0]].tokens
	if len(tokens) == 0 {
		return nil, semanticInvalid()
	}
	return tokens, nil
}
func (q *scopeQueries) observationCollectionTokens(tokens []string) []string {
	if len(tokens) <= 2 {
		return tokens
	}
	index, err := strconv.Atoi(tokens[len(tokens)-2])
	if err != nil || index < 0 {
		return tokens
	}
	fieldPointer := jsonpointer.FromTokens(tokens[:len(tokens)-2])
	for _, profile := range q.profiles {
		if profile.FieldPointer == fieldPointer {
			return tokens[:len(tokens)-1]
		}
	}
	q.profiles = append(q.profiles, admission.RealizationCollectionProfile{FieldPointer: fieldPointer, CollectionKind: "sdl-declaration", IdentityFields: []string{tokens[len(tokens)-1]}, Closure: admission.RealizationClosure{Posture: "closed", Universe: "sdl-declarations/v1", Profile: "recursive-realization-constraint/v1"}})
	return tokens[:len(tokens)-1]
}
