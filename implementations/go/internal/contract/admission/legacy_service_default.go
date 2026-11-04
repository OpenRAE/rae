package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// Content.default_service_materialization_profile preserves this native
// default before union discrimination. It never supplies a profile binding.
func legacyServiceProfileDefault(instance validation.SchemaInstance) bool {
	return instance.Discriminator == "interface_profile" &&
		strings.HasSuffix(instance.SchemaPointer, "/Content/properties/service_materialization/anyOf/0") &&
		strings.HasSuffix(instance.Path, "/service_materialization") &&
		stringAt(instance.Value, termSchemaVersion) != "domain-profile-binding/v1"
}
