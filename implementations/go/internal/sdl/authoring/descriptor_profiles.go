package authoring

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

// DescriptorProfiles returns the existing semantic owner's admitted bindings
// in host and declaration order. It does not confer target support.
func (d *Document) DescriptorProfiles() ([]binding.DomainProfileBindingV1, error) {
	if d == nil || !d.Validated() {
		return nil, semanticInvalid()
	}
	result := make([]binding.DomainProfileBindingV1, 0, len(d.semantic.descriptors))
	for _, row := range d.semantic.descriptors {
		var copied binding.DomainProfileBindingV1
		if !descriptorOwned(row) || json.Unmarshal(row.raw, &copied) != nil {
			return nil, semanticInvalid()
		}
		result = append(result, copied)
	}
	return result, nil
}
