package authoring

import (
	"maps"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// AdmitProspectiveContent checks the common content constructor and full
// semantics without admitting an authored, instantiated or materialized phase.
func (p *Parser) AdmitProspectiveContent(data []byte) (*Document, error) {
	document, local, err := p.constructCommonContent(data)
	if err != nil {
		return nil, err
	}
	if containsVariable(document.compositionValue) {
		return nil, invalid()
	}
	admitted, _, err := local.Validate(document)
	if err != nil {
		return nil, err
	}
	projection := semanticValueProjection{queries: admitted.semantic.scopes, limits: value.Runtime()}
	frame := semanticValueFrame{data: admitted.semantic.root, schema: local.schemas[expandedContract], pointer: "#"}
	if err = value.ValidateProjected(frame, value.Runtime(), projection.project); err != nil {
		return nil, err
	}
	return admitted, nil
}

func (p *Parser) constructCommonContent(data []byte) (*Document, *Parser, error) {
	if p == nil || p.models == nil {
		return nil, nil, invalid()
	}
	options := p.options("prospective-content", "reject")
	options.KeyScope = dataScope
	// This is a common-content value, not an authored source root. The
	// selected concrete field schemas below own all declaration identities.
	options.BasePointer = "/prospective-content"
	parsed, err := source.Decode(data, options)
	if err != nil {
		return nil, nil, err
	}
	input := object(parsed.Value())
	if input == nil {
		return nil, nil, invalid()
	}
	local := p.prospectiveParser()
	root := local.schemas[expandedContract]
	queries := newScopeQueries(local, expandedContract, input)
	fill := importDefaultWalk{queries: queries, remaining: compositionJSONWork(p.limits)}
	full, err := fill.value(input, root, "#")
	if err != nil {
		return nil, nil, err
	}
	walk := normalizer{parser: local, id: expandedContract, workingLimit: compositionJSONWork(p.limits)}
	normalized, err := walk.walk(root, "#", full, nil, scalarPolicy{}, parsed.View())
	if err != nil {
		return nil, nil, err
	}
	if err = local.checkProspectiveFields(normalized); err != nil {
		return nil, nil, err
	}
	model, err := encode(normalized, compositionJSONWork(p.limits), false)
	if err != nil {
		return nil, nil, err
	}
	serialized, err := encode(normalized, compositionJSONWork(p.limits), true)
	if err != nil {
		return nil, nil, err
	}
	document := &Document{source: parsed, sourceName: "prospective-content", contract: expandedContract, data: serialized, modelData: model, compositionValue: input}
	return document, local, nil
}

// Only the root property view changes. All declaration types, constructors,
// field layouts and validators keep their existing native owners.
func (p *Parser) prospectiveParser() *Parser {
	local := *p
	local.schemas = maps.Clone(p.schemas)
	root := maps.Clone(p.schemas[expandedContract])
	fields := maps.Clone(object(root["properties"]))
	for _, field := range []string{variablesSection, variationPointsField, "expansion_provenance"} {
		delete(fields, field)
	}
	root["properties"] = fields
	local.schemas[expandedContract] = root
	return &local
}

func (p *Parser) checkProspectiveFields(normalized any) error {
	// The existing concrete construction view supplies the common field
	// schemas with qualified declaration keys. Selecting a field grants no
	// provenance, document phase or semantic authority.
	for field, input := range object(normalized) {
		raw, err := encode(input, compositionJSONWork(p.limits), false)
		if err != nil {
			return err
		}
		pointer := "#/properties/" + jsonpointer.EscapeToken(field)
		if err = p.models.CheckSDLConstruction(instantiatedContract, pointer, raw, modelLimits(raw)); err != nil {
			return err
		}
	}
	return nil
}
