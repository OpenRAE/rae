package admission

import "regexp"

var sdlMechanismExtension = regexp.MustCompile(`^x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*\z`)

func sdlArtifactProfile(v any) error {
	mechanism := stringAt(v, "mechanism")
	switch mechanism {
	case "exact-artifact", "backend-owned-artifact", "published-candidate", "dynamic-composition", termMaterializationSpecification:
		return nil
	default:
		return require(sdlMechanismExtension.MatchString(mechanism))
	}
}
