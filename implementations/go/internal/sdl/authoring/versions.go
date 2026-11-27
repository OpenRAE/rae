package authoring

import (
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/sdl/module"
)

// Resolved import provenance bounds the requested and the module version to this length.
const maxVersionLength = 256

// versionText refuses a version text that is blank or that resolved import
// provenance cannot record. The field type check owns other values.
func versionText(value any) error {
	version, ok := value.(string)
	if ok && (pythonTrim(version) == "" || utf8.RuneCountInString(version) > maxVersionLength) {
		return invalid()
	}
	return nil
}

func versionSpec(requested string) (module.VersionRequirement, error) {
	result, err := module.ParseVersionRequirement(requested)
	if err != nil {
		return result, invalid()
	}
	return result, nil
}
