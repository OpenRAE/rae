package authoring

import (
	"encoding/json"
	"fmt"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

// ExplicitnessRecord describes authored intent without carrying its value or
// granting realization, execution, or observation authority.
type ExplicitnessRecord struct {
	Path           string   `json:"path"`
	Classification string   `json:"classification"`
	Provenance     string   `json:"provenance"`
	Reason         string   `json:"reason"`
	Variables      []string `json:"variables"`
}

// Explicitness returns independent metadata copies for an admitted document.
// A constructed or zero document has no admitted classification records.
func (d *Document) Explicitness() map[string]ExplicitnessRecord {
	result := map[string]ExplicitnessRecord{}
	if !d.Validated() || d.semantic.intent == nil {
		return result
	}
	for path, record := range d.semantic.intent.records {
		record.Variables = slices.Clone(record.Variables)
		result[path] = record
	}
	return result
}

type semanticIntentFrame struct {
	data               any
	schema             map[string]any
	pointer, path      string
	tokens             []string
	policy             scalarPolicy
	variableDefinition bool
}
type semanticIntentVisitor struct {
	model      *semanticModel
	records    map[string]ExplicitnessRecord
	errors     []string
	references []semanticString
}

func (m *semanticModel) loadIntent() error {
	if m.intent != nil {
		return nil
	}
	visitor := &semanticIntentVisitor{model: m, records: map[string]ExplicitnessRecord{}}
	root := semanticIntentFrame{data: m.root, schema: m.parser.schemas[m.document.contract], pointer: "#"}
	if _, err := visitor.visit(root); err != nil {
		return err
	}
	m.intent = visitor
	return nil
}

//nolint:nilnil // The root has no classification record; absence is a successful walk.
func (v *semanticIntentVisitor) visit(frame semanticIntentFrame) (*ExplicitnessRecord, error) {
	frame.schema, frame.pointer = v.model.scopes.schema(frame.schema, frame.pointer, frame.data)
	switch data := frame.data.(type) {
	case map[string]any:
		return v.mapping(frame, data)
	case []any:
		if !frame.policy.ExplicitnessAtomic {
			return v.sequence(frame, data)
		}
	}
	if frame.path == "" {
		return nil, nil
	} // Root models have no classification record.
	return v.scalar(frame), nil
}
func (v *semanticIntentVisitor) mapping(frame semanticIntentFrame, data map[string]any) (*ExplicitnessRecord, error) {
	presentation, model := v.model.parser.lookupLayout(v.model.document.contract, frame.pointer)
	keys := v.model.keys(frame.tokens...)
	if model {
		keys = intentSuppliedFields(presentation, data)
	}
	exactExtension, err := intentExactExtension(frame)
	if err != nil {
		return nil, err
	}
	var children []ExplicitnessRecord
	for _, field := range keys {
		child, err := v.childFrame(frame, presentation, field, data[field])
		if err != nil {
			return nil, err
		}
		record, err := v.visit(child)
		if err != nil {
			return nil, err
		}
		if record != nil {
			if exactExtension && field == "record_type" && len(record.Variables) == 0 {
				record.Classification = exactTerm
				record.Reason = "owning model supplies exact extension identity"
				v.records[record.Path] = *record
			}
			children = append(children, *record)
		}
	}
	return v.container(frame.path, children), nil
}
func intentSuppliedFields(presentation layout, data map[string]any) []string {
	var keys []string
	for _, field := range presentation.Fields {
		if _, supplied := data[field]; supplied {
			keys = append(keys, field)
		}
	}
	return keys
}

func (v *semanticIntentVisitor) childFrame(frame semanticIntentFrame, presentation layout, field string, data any) (semanticIntentFrame, error) {
	name := field
	if modelName, known := presentation.ModelNames[field]; known {
		name = modelName
	}
	path := name
	if frame.path != "" {
		path = frame.path + "." + name
	}
	schema, err := v.model.scopes.w.propertySchema(frame.schema, field)
	if err != nil {
		return semanticIntentFrame{}, fault.New(fault.Operational, "sdl-explicitness-model", nil)
	}
	policy, known := presentation.Scalar[field]
	if !known {
		policy = childPolicy(frame.policy.Values)
	}
	childPointer := frame.pointer + "/additionalProperties"
	if _, declared := object(frame.schema["properties"])[field]; declared {
		childPointer = frame.pointer + "/properties/" + jsonpointer.EscapeToken(field)
	}
	child := semanticIntentFrame{data: data, schema: schema, pointer: childPointer, path: path, tokens: appendPath(frame.tokens, field), policy: policy, variableDefinition: frame.variableDefinition || len(frame.tokens) == 0 && field == variablesSection}
	return child, nil
}

func (v *semanticIntentVisitor) sequence(frame semanticIntentFrame, data []any) (*ExplicitnessRecord, error) {
	children := make([]ExplicitnessRecord, 0, len(data))
	for i, item := range data {
		child := semanticIntentFrame{data: item, schema: object(frame.schema["items"]), pointer: frame.pointer + "/items", path: frame.path + "[" + strconv.Itoa(i) + "]", tokens: appendPath(frame.tokens, strconv.Itoa(i)), policy: childPolicy(frame.policy.Items), variableDefinition: frame.variableDefinition}
		record, err := v.visit(child)
		if err != nil {
			return nil, err
		}
		if record != nil {
			children = append(children, *record)
		}
	}
	return v.container(frame.path, children), nil
}
func (v *semanticIntentVisitor) container(path string, children []ExplicitnessRecord) *ExplicitnessRecord {
	if path == "" {
		return nil
	}
	record := ExplicitnessRecord{Path: path, Classification: exactTerm, Provenance: "author-declared", Reason: "authored empty structure", Variables: []string{}}
	if len(children) > 0 {
		record.Reason = "derived from child declarations"
	}
	variables := map[string]bool{}
	for _, child := range children {
		if intentRank(child.Classification) < intentRank(record.Classification) {
			record.Classification = child.Classification
		}
		for _, name := range child.Variables {
			variables[name] = true
		}
	}
	for name := range variables {
		record.Variables = append(record.Variables, name)
	}
	slices.Sort(record.Variables)
	v.records[path] = record
	return &record
}
func intentRank(classification string) int {
	switch classification {
	case openTerm:
		return 0
	case "constrained":
		return 1
	default:
		return 2
	}
}
func (v *semanticIntentVisitor) scalar(frame semanticIntentFrame) *ExplicitnessRecord {
	record := ExplicitnessRecord{Path: frame.path, Classification: exactTerm, Provenance: "author-declared", Reason: "authored concrete value", Variables: []string{}}
	if text, ok := frame.data.(string); ok {
		record.Variables = append(record.Variables, semanticVariableNames(text)...)
		v.references = append(v.references, semanticString{frame.path, text, frame.variableDefinition})
		if len(record.Variables) > 0 {
			record.Classification = "constrained"
			record.Reason = v.variableReason(frame.path, record.Variables)
		} else if slices.Contains(frame.policy.ExplicitnessEnums, text) {
			record.Classification = openTerm
			record.Reason = "open taxonomy sentinel"
		}
	}
	v.records[frame.path] = record
	return &record
}
func (v *semanticIntentVisitor) variableReason(path string, names []string) string {
	var parts, missing []string
	for _, name := range names {
		variable, known := v.model.variationVariables[name]
		switch {
		case !known:
			parts = append(parts, name+": undefined")
			missing = append(missing, name)
		case len(variable.Allowed) > 0:
			parts = append(parts, name+": allowed_values")
		default:
			parts = append(parts, name+": type "+variable.Type)
		}
	}
	if len(missing) > 0 {
		v.errors = append(v.errors, fmt.Sprintf("Cannot classify explicitness for '%s': undefined variable(s) %s", path, strings.Join(missing, ", ")))
	}
	return strings.Join(parts, "; ")
}
func intentExactExtension(frame semanticIntentFrame) (bool, error) {
	if frame.pointer != "#/$defs/DnsResourceRecordSet" {
		return false, nil
	}
	// This is the reference's single exact-extension hook. It consumes only
	// the declared DNS type-code field through a closed typed projection.
	var rrset struct {
		TypeCode semanticInteger `json:"type_code"`
	}
	data, err := json.Marshal(frame.data)
	if err != nil || json.Unmarshal(data, &rrset) != nil {
		return false, fault.New(fault.Operational, "sdl-explicitness-model", nil)
	}
	return rrset.TypeCode.integer != nil, nil
}
