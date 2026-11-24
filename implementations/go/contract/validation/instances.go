package validation

import (
	"net/url"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// SchemaInstance describes an applicable published schema at an original input
// path. Check callbacks must not mutate or retain Root or Value.
type SchemaInstance struct {
	ContractID, SchemaPointer, Path, Discriminator string
	Root, Value                                    any
}

// CheckInstances schema-checks bounded input, then visits its applicable schema
// instances for family-owned model conditions. Callback errors are redacted.
// This method grants no semantic admission.
func (v *Validator) CheckInstances(id string, data []byte, limits ingress.Limits, check func(SchemaInstance) error) error {
	root, err := v.parse(id, data, limits)
	if err != nil {
		return err
	}
	if check == nil {
		return failure(fault.Operational, "contract-model-check-required")
	}
	entry := v.contracts[id]
	return walkSchemaBound(visit{entry.schema, root, ""}, entry.walkBound(len(data)), func(current visit) error {
		return entry.visitInstance(id, current, root, check)
	})
}

// visitInstance passes one schema instance to the check. The instance names
// the discriminator property of its schema, if the schema has one.
func (c contract) visitInstance(id string, current visit, root any, check func(SchemaInstance) error) error {
	location, err := url.Parse(current.schema.Location)
	if err != nil {
		return failure(fault.Operational, codeContractSchemaInvalid)
	}
	var discriminator string
	if raw, ok := atDefaultPath(c.raw, location.Fragment); ok {
		if schema, ok := raw.(map[string]any); ok {
			if tag, ok := schema["discriminator"].(map[string]any); ok {
				discriminator, _ = tag["propertyName"].(string)
			}
		}
	}
	if err := check(SchemaInstance{id, "#" + location.Fragment, current.path, discriminator, root, current.value}); err != nil {
		return failure(fault.InvalidInput, "contract-model-mismatch")
	}
	return nil
}
