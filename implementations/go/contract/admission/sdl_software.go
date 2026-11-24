package admission

import (
	"maps"

	"github.com/OpenRAE/rae/implementations/go/internal/base/softwareversion"
)

func sdlVersionAccepts(value string, constraint any) bool {
	if constraint == nil {
		return true
	}
	domain, err := modelVersionDomain(constraint)
	if err != nil {
		return false
	}
	membership := domain.Membership(value)
	return membership != softwareversion.Nonconformant && membership != softwareversion.Unresolved
}
func sdlSamePackage(left, right any) bool {
	complete := func(value any) map[string]any {
		result := maps.Clone(object(value))
		for _, field := range []string{termArchitecture, termSource, "purl"} {
			if _, present := result[field]; !present {
				result[field] = ""
			}
		}
		if _, present := result["repository"]; !present {
			result["repository"] = nil
		}
		return result
	}
	return equal(complete(left), complete(right))
}
func sdlPackageCorrespondence(component, pack any) error {
	for field, target := range map[string]string{"package_manager": "manager", "package_name": termName, "package_version": termVersion} {
		value := stringAt(component, field)
		if value != "" && value != stringAt(pack, target) {
			return invalid()
		}
	}
	if inline := at(component, "package"); inline != nil && !sdlSamePackage(inline, pack) {
		return invalid()
	}
	return require(sdlVersionAccepts(stringAt(pack, termVersion), at(component, "package_version_constraint")))
}
func sdlSoftwareComponent(v any) error {
	if !sdlSymbolField(v, termComponentID) || !nonblankSDLFields(v, termName) || !fieldsUnique(v, "repository_refs") {
		return invalid()
	}
	if !sdlAbsoluteFields(v, true, "manifest_path") || !sdlAbsoluteList(v, "installed_paths") {
		return invalid()
	}
	if !sdlUniqueKey(at(v, "refinements"), "refinement_id", false) {
		return invalid()
	}
	if pack := at(v, "package"); pack != nil {
		if err := sdlPackageCorrespondence(v, pack); err != nil {
			return err
		}
	}
	for _, field := range []string{termVersion, "package_version"} {
		value := stringAt(v, field)
		if value != "" && !sdlVersionAccepts(value, at(v, field+"_constraint")) {
			return invalid()
		}
	}
	return nil
}
func sdlPresenceCompatible(source, target any) bool {
	left := text(defaultMember(source, "presence", "required"))
	right := text(defaultMember(target, "presence", "required"))
	return left == "forbidden" || right != "forbidden" && (left != "required" || right != "optional")
}
func sdlRuntimeConfiguration(v any) error {
	if err := sdlRuntimeKeys(v); err != nil {
		return err
	}
	repositories := map[string]any{}
	for _, repository := range array(at(v, "repository_state", "repositories")) {
		repositories[stringAt(repository, "repository_id")] = repository
	}
	for _, component := range array(at(v, "software_components")) {
		if !sdlComponentRepositories(component, repositories) {
			return invalid()
		}
		pack, err := sdlResolvePackage(component, array(at(v, "packages")))
		if err != nil {
			return err
		}
		if pack != nil {
			if err = sdlPackageCorrespondence(component, pack); err != nil {
				return err
			}
		}
	}
	return nil
}
func sdlComponentRepositories(component any, repositories map[string]any) bool {
	for _, ref := range stringsOf(at(component, "repository_refs")) {
		repository, present := repositories[ref]
		if !present || !sdlPresenceCompatible(component, repository) {
			return false
		}
	}
	return true
}
func sdlResolvePackage(component any, packages []any) (any, error) {
	reference := at(component, "package_ref")
	if reference == nil {
		return at(component, "package"), nil
	}
	var selected any
	for _, pack := range packages {
		if stringAt(pack, "manager") != stringAt(reference, "manager") || stringAt(pack, termName) != stringAt(reference, termName) {
			continue
		}
		if architecture := stringAt(reference, termArchitecture); architecture != "" && architecture != stringAt(pack, termArchitecture) {
			continue
		}
		if selected != nil {
			return nil, invalid()
		}
		selected = pack
	}
	if selected == nil {
		return nil, invalid()
	}
	return selected, nil
}
func sdlRepositoryState(v any) error {
	repositories, trusts := array(at(v, "repositories")), array(at(v, "trust_bindings"))
	if !sdlUniqueKey(repositories, "repository_id", false) || !sdlUniqueKey(trusts, "trust_id", false) {
		return invalid()
	}
	byID := map[string]any{}
	for _, trust := range trusts {
		byID[stringAt(trust, "trust_id")] = trust
	}
	for _, repository := range repositories {
		if at(repository, "trust_ref") == nil {
			continue
		}
		trust, present := byID[stringAt(repository, "trust_ref")]
		if !present || !sdlPresenceCompatible(repository, trust) {
			return invalid()
		}
	}
	return nil
}
func sdlRepositoryRefinements(v any, purpose string) error {
	if !sdlUniqueKey(at(v, "refinements"), "refinement_id", false) {
		return invalid()
	}
	for _, refinement := range array(at(v, "refinements")) {
		if stringAt(refinement, "purpose") != purpose {
			return invalid()
		}
	}
	return nil
}
