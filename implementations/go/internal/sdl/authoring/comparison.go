package authoring

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type comparisonSubject struct {
	Family        string   `json:"Family"`
	Name          string   `json:"Name"`
	ModelType     string   `json:"ModelType"`
	PresentFields []string `json:"PresentFields"`
	Semantic      any      `json:"Semantic"`
}
type comparisonProjection struct {
	Name            string              `json:"Name"`
	Version         string              `json:"Version"`
	CanonicalDigest string              `json:"CanonicalDigest"`
	Structural      any                 `json:"Structural"`
	Semantic        any                 `json:"Semantic"`
	Subjects        []comparisonSubject `json:"Subjects"`
	Imports         []any               `json:"Imports"`
}

// ComparisonProjection derives the reference comparison facts from the
// original native authored constructor, retaining its presence and model types.
func (p *Parser) ComparisonProjection(document *Document, version string) ([]byte, error) {
	if p == nil || document == nil || document.source == nil || document.contract != authoringContract || version != "1" && version != "2" {
		return nil, invalid()
	}
	input, err := ingress.Parse(document.data, modelLimits(document.data), ingress.Object)
	if err != nil {
		return nil, err
	}
	present := object(input)
	c := composition{parser: p}
	full, err := c.bindingPayload(present, document.semanticOrder())
	if err != nil {
		return nil, err
	}
	selected := full
	if version == "2" {
		selected = present
	}
	queries := newScopeQueries(p, authoringContract, selected)
	editorial := modelEditorialNative
	if version == "1" {
		editorial = modelEditorialAll
	}
	walk := comparisonWalk{modelProjection: &modelProjection{queries: queries, editorial: editorial, modelNames: version == "1", remaining: value.Plan().MaxNodes}}
	root := p.schemas[authoringContract]
	semantics, err := walk.project(selected, root, "#", 0)
	if err != nil {
		return nil, err
	}
	result := comparisonProjection{Name: text(full[nameField]), Version: text(full["version"]), Structural: comparisonStructure(full), Semantic: comparisonRootSemantics(object(semantics), version), Subjects: []comparisonSubject{}, Imports: []any{}}
	result.Imports = append(result.Imports, array(full[importsField])...)
	result.Subjects, err = walk.subjects(selected, root)
	if err != nil {
		return nil, err
	}
	canonicalProjection := modelProjection{queries: newScopeQueries(p, authoringContract, full), modelNames: true, remaining: value.Plan().MaxNodes}
	canonical, err := canonicalProjection.project(full, root, "#", 0)
	if err != nil {
		return nil, err
	}
	if version == "2" {
		canonical = map[string]any{"profile": "raes-canonical-sdl/v2", "scenario": present}
	}
	rawCanonical, err := json.Marshal(canonical)
	if err != nil {
		return nil, err
	}
	encoded, err := canonjson.JCS(rawCanonical)
	if err != nil {
		return nil, err
	}
	result.CanonicalDigest = digest.SHA256(encoded)
	if err := value.ValidateProjected(result, value.Plan(), comparisonBudgetValue); err != nil {
		return nil, err
	}
	return json.Marshal(result)
}

func comparisonDeclarationFields() []string {
	return slices.DeleteFunc(declarationSections(), func(field string) bool { return field == controlAssetsSection })
}
func comparisonStructure(full map[string]any) map[string]any {
	declarations := map[string]any{}
	for _, field := range comparisonDeclarationFields() {
		declarations[field] = append([]string{}, slices.Sorted(maps.Keys(object(full[field])))...)
	}
	namespaces := []string{}
	for _, item := range array(full[importsField]) {
		namespaces = append(namespaces, text(object(item)[namespaceField]))
	}
	slices.Sort(namespaces)
	return map[string]any{"declarations": declarations, "forwarding_agent_count": len(array(full[forwardingSection])), "has_module_descriptor": full["module"] != nil, "import_namespaces": namespaces, "has_realization_designation": full["realization"] != nil}
}
func comparisonRootSemantics(input map[string]any, version string) map[string]any {
	fields := append(comparisonDeclarationFields(), nameField, "version", forwardingSection, "module", importsField, "realization")
	if version == "2" {
		fields = append(fields, "semantic_revision")
	}
	result := map[string]any{}
	for _, field := range fields {
		if v, exists := input[field]; exists {
			result[field] = v
		}
	}
	return result
}

type comparisonWalk struct{ *modelProjection }

func (w *comparisonWalk) subjects(input, root map[string]any) ([]comparisonSubject, error) {
	result := []comparisonSubject{}
	// A field that is itself a model is not a dictionary declaration family.
	for _, family := range w.queries.w.parser.layoutFor(authoringContract, "#").Fields {
		members, ok := input[family].(map[string]any)
		if !ok {
			continue
		}
		schema, err := w.queries.w.propertySchema(root, family)
		if err != nil {
			return nil, err
		}
		pointer := schemaPropertyPointer(root, "#", family)
		schema, pointer = w.queries.schema(schema, pointer, members)
		if owner := w.queries.w.parser.layoutFor(authoringContract, pointer); owner.ModelType != "" {
			continue
		}
		for _, name := range slices.Sorted(maps.Keys(members)) {
			subject, err := w.subject(family, name, members[name], schema, pointer)
			if err != nil {
				return nil, err
			}
			result = append(result, subject)
		}
	}
	return result, nil
}
func (w *comparisonWalk) subject(family, name string, input any, schema map[string]any, pointer string) (comparisonSubject, error) {
	child, err := w.queries.w.propertySchema(schema, name)
	if err != nil {
		return comparisonSubject{}, err
	}
	pointer = schemaPropertyPointer(schema, pointer, name)
	child, pointer = w.queries.schema(child, pointer, input)
	owner := w.queries.w.parser.layoutFor(authoringContract, pointer)
	modelType := owner.ModelType
	if modelType == "" {
		modelType = "dict"
	}
	fields := []string{}
	for field := range object(input) {
		fields = append(fields, modelFieldName(owner, field))
	}
	slices.Sort(fields)
	semantic, err := w.project(input, child, pointer, 0)
	return comparisonSubject{Family: family, Name: name, ModelType: modelType, PresentFields: fields, Semantic: semantic}, err
}

// Only private projection records reach this shallow adapter. The shared
// walker charges the complete result before any aggregate encoding or copy.
func comparisonBudgetValue(input any) (any, error) {
	switch data := input.(type) {
	case comparisonProjection:
		return map[string]any{"Name": data.Name, "Version": data.Version, "CanonicalDigest": data.CanonicalDigest, "Structural": data.Structural, "Semantic": data.Semantic, "Subjects": data.Subjects, "Imports": data.Imports}, nil
	case comparisonSubject:
		return map[string]any{"Family": data.Family, "Name": data.Name, "ModelType": data.ModelType, "PresentFields": data.PresentFields, "Semantic": data.Semantic}, nil
	case []comparisonSubject:
		if len(data) > value.Plan().MaxMembers {
			return nil, value.ErrLimit
		}
		output := make([]any, len(data))
		for i, subject := range data {
			output[i] = subject
		}
		return output, nil
	case []string:
		if len(data) > value.Plan().MaxMembers {
			return nil, value.ErrLimit
		}
		output := make([]any, len(data))
		for i, field := range data {
			output[i] = field
		}
		return output, nil
	default:
		return input, nil
	}
}
