package authoring

import "github.com/OpenRAE/rae/implementations/go/sdl/module"

func versionSpec(requested string) (module.VersionRequirement, error) {
	result, err := module.ParseVersionRequirement(requested)
	if err != nil {
		return result, invalid()
	}
	return result, nil
}
