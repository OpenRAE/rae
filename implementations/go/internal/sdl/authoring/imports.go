package authoring

import "encoding/json"

func (p *Parser) checkImports(document *Document, request Request) error {
	var value map[string]any
	if err := json.Unmarshal(document.data, &value); err != nil {
		return err
	}
	if len(array(value["imports"])) == 0 {
		return nil
	}
	return invalid()
}
