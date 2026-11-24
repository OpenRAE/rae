package authoring

import "encoding/json"

// RealizationDesignations copies lexical records from the admitted semantic owner.
// A composed authored document retains expansion separately from its root view.
func (d *Document) RealizationDesignations() (json.RawMessage, error) {
	if !d.Validated() {
		return nil, semanticInvalid()
	}
	root := d.semantic.root
	records := authoredDesignations(root)
	if d.Instantiated() {
		records = array(object(root["instantiation_provenance"])[termRealizationDesignations])
	} else if d.expanded != nil || d.contract == expandedContract {
		records = array(object(root["expansion_provenance"])[termRealizationDesignations])
	}
	if records == nil {
		records = []any{}
	}
	return json.Marshal(records)
}

func authoredDesignations(root map[string]any) []any {
	policy := object(root["realization"])
	if policy == nil {
		return nil
	}
	posture := policy[defaultField]
	if posture == nil {
		posture = termUnspecified
	}
	declaration := map[string]any{namespaceField: []any{}, fieldPointerField: "", "posture": posture}
	return append([]any{declaration}, array(policy[scopesField])...)
}
