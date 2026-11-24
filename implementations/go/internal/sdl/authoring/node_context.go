package authoring

import "github.com/OpenRAE/rae/implementations/go/contract/diagnostic"

// ValidateNodeRealizationContext constructs a bounded partial context and
// checks the existing native node references without admitting author intent.
func (p *Parser) ValidateNodeRealizationContext(data []byte) ([]diagnostic.Diagnostic, error) {
	if p == nil || p.models == nil {
		return nil, invalid()
	}
	document, local, err := p.constructCommonContent(data)
	if err != nil {
		return nil, err
	}
	allowed := map[string]bool{nameField: true, nodesSection: true, infrastructureField: true, "generated_artifacts": true, "persistent_volumes": true, "accounts": true, contentField: true}
	for field := range document.compositionValue {
		if !allowed[field] {
			return nil, invalid()
		}
	}
	model, err := local.newSemanticModel(document)
	if err != nil {
		return nil, err
	}
	collector := newSemanticCollector(document)
	for _, node := range model.nodes {
		checkNodePlatform(&collector, node)
	}
	model.checkInfrastructure(&collector)
	model.checkRuntimeConfiguration(&collector)
	model.checkStatefulResources(&collector)
	if err := model.checkVariables(&collector); err != nil {
		return nil, err
	}
	return append([]diagnostic.Diagnostic{}, collector.errors...), nil
}
