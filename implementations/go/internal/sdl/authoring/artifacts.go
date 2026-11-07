package authoring

import "regexp"

var extensionMechanism = regexp.MustCompile(`^x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*$`)

func artifactModel(model string, value map[string]any) error {
	switch model {
	case "ArtifactConstraint":
		if !uniqueStrings(array(value["allowed_values"])) {
			return invalid()
		}
	case "ArtifactMechanismProfile":
		return mechanismModel(text(value["mechanism"]))
	case "ArtifactRequirement":
		return artifactRequirement(value)
	case "Source":
		requirement := object(value["artifact_requirement"])
		if requirement["explicitness"] == exactTerm {
			identity := object(requirement["exact_artifact"])
			version, present := value["version"]
			if !present {
				version = "*"
			}
			if value["name"] != identity["artifact_id"] || version != identity["version"] {
				return invalid()
			}
		}
	}
	return nil
}
func mechanismModel(mechanism string) error {
	switch mechanism {
	case "exact-artifact", "backend-owned-artifact", "published-candidate", "dynamic-composition", "materialization-specification":
		return nil
	default:
		if !extensionMechanism.MatchString(mechanism) {
			return invalid()
		}
		return nil
	}
}
func artifactRequirement(value map[string]any) error {
	for section, identity := range map[string]string{
		"constraints": "constraint_id", "candidates": "candidate_id",
		"locked_inputs": "input_id", "materialization_specifications": "specification_id",
	} {
		seen := map[string]bool{}
		for _, raw := range array(value[section]) {
			name := text(object(raw)[identity])
			if seen[name] {
				return invalid()
			}
			seen[name] = true
		}
	}
	if err := artifactRoutes(array(value["permitted_routes"])); err != nil {
		return err
	}
	return artifactInputs(value)
}
func artifactRoutes(routes []any) error {
	seen := map[[5]string]bool{}
	for _, raw := range routes {
		route := object(raw)
		mechanism := object(route["mechanism"])
		identity := [5]string{text(mechanism["mechanism"]), text(mechanism["profile"]), text(mechanism["version"]), text(route["acquisition"]), text(route["timing"])}
		if seen[identity] {
			return invalid()
		}
		seen[identity] = true
	}
	return nil
}
func artifactInputs(value map[string]any) error {
	declared := map[string]bool{}
	for _, raw := range array(value["locked_inputs"]) {
		declared[text(object(raw)["input_id"])] = true
	}
	for _, raw := range array(value["materialization_specifications"]) {
		for _, reference := range array(object(raw)["locked_input_ids"]) {
			if !declared[text(reference)] {
				return invalid()
			}
		}
	}
	return nil
}
