package authoring

import (
	"maps"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// AdmitFamily derives a separately checked family from a constructed document.
// It performs no file or network reads and cannot admit foreign expanded maps.
func (p *Parser) AdmitFamily(document *Document) (*Document, error) {
	if document == nil || document.source == nil || document.contract != authoringContract && document.contract != expandedContract {
		return nil, invalid()
	}
	if document.expanded != nil {
		document = document.expanded
	}
	if document.contract == expandedContract {
		admitted, _, err := p.Validate(document)
		return admitted, err
	}
	value, err := p.modelValue(document)
	if err != nil {
		return nil, err
	}
	if len(array(value[importsField])) != 0 {
		return nil, importError("source-refused")
	}
	facts, err := newImportFacts(document, value)
	if err != nil {
		return nil, err
	}
	candidate := *document
	candidate.validated, candidate.semantic = false, nil
	c := composition{parser: p, facts: map[string]*importFacts{document.sourceName: facts}, records: map[string][]map[string]any{}}
	if err = c.retainExpanded(&candidate, value, document.sourceName); err != nil {
		return nil, err
	}
	admitted, _, err := p.Validate(candidate.expanded)
	return admitted, err
}

// Only native operations can rebuild an expanded value from this private map.
func (p *Parser) rebuildFamily(payload map[string]any, origin *Document) (*Document, error) {
	content := maps.Clone(payload)
	delete(content, "expansion_provenance")
	c := composition{parser: p}
	if _, err := c.validateBound(content); err != nil {
		return nil, err
	}
	limit := compositionJSONWork(p.limits)
	walk := normalizer{parser: p, id: expandedContract, workingLimit: limit, order: origin.semanticOrder()}
	normalized, err := walk.walk(p.schemas[expandedContract], "#", payload, nil, scalarPolicy{}, source.View{})
	if err != nil {
		return nil, err
	}
	model, err := encode(normalized, limit, false)
	if err != nil {
		return nil, err
	}
	serialized, err := encode(normalized, limit, true)
	if err != nil {
		return nil, err
	}
	candidate := *origin
	candidate.expanded, candidate.semantic, candidate.validated = nil, nil, false
	candidate.contract, candidate.data, candidate.modelData = expandedContract, serialized, model
	admitted, _, err := p.Validate(&candidate)
	return admitted, err
}
