package authoring

import "github.com/OpenRAE/rae/implementations/go/base/fault"

const semanticRefusalCode = "sdl-semantic-invalid"

func semanticInvalid() error { return fault.New(fault.InvalidInput, semanticRefusalCode, nil) }

// The reference always checks materialized semantics, including during format.
// Authored formatting deliberately stops at construction and import checks.
func (p *Parser) checkFormatPhase(document *Document) error {
	if document.contract != materializedContract {
		return nil
	}
	err := p.checkMaterializedFormat(document)
	if category, known := fault.CategoryOf(err); known && category == fault.InvalidInput {
		return fault.New(fault.InvalidInput, semanticRefusalCode, err)
	}
	return err
}
func (p *Parser) checkMaterializedFormat(document *Document) error {
	model, err := p.newSemanticModel(document)
	if err != nil {
		return err
	}
	collector := newSemanticCollector(document)
	if err := model.check(&collector); err != nil {
		return err
	}
	if len(collector.errors) != 0 {
		return &semanticError{findings: collector.errors}
	}
	return nil
}
