package realization

import (
	"encoding/json"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// CompilePreparedNode normalizes one backend-selected node and derives exact
// backend requirements and typed presence through the existing SDL/concern
// owners. It grants no authored scope, deployment, or observation assertion.
//
//nolint:ireturn // The reviewed consumer boundary returns the native value fragment.
func CompilePreparedNode(node admission.Fragment, name, compiledAddress string) (admission.Fragment, []Requirement, map[string][]string, error) {
	if admission.CheckFragment(node, admission.RealizationValue) != nil {
		return nil, nil, nil, invalidRealization()
	}
	original, ok := node.Document().(map[string]any)
	if !ok {
		return nil, nil, nil, invalidRealization()
	}
	normalized, presence, err := normalizePreparedNode(original)
	if err != nil {
		return nil, nil, nil, err
	}
	if identityErr := preparedNodeIdentity(normalized, name, compiledAddress); identityErr != nil {
		return nil, nil, nil, identityErr
	}
	requirements, err := preparedNodeRequirements(normalized, original, name, compiledAddress)
	if err != nil {
		return nil, nil, nil, err
	}
	fragment, err := nativeValueFragment(normalized)
	if err != nil {
		return nil, nil, nil, err
	}
	return fragment, requirements, presence, nil
}
func normalizePreparedNode(original map[string]any) (map[string]any, map[string][]string, error) {
	restored, err := restoreRuntimeMarkers(original)
	if err != nil {
		return nil, nil, err
	}
	fragment, err := nativeValueFragment(restored)
	if err != nil {
		return nil, nil, err
	}
	normalized, presence, err := sdl.NormalizeNodeValue(fragment)
	if err != nil {
		return nil, nil, err
	}
	node, ok := normalized.Document().(map[string]any)
	if !ok {
		return nil, nil, invalidRealization()
	}
	// The native typed shape keeps restored blanks; validated logical markers
	// remain in the caller-owned candidate and augment only typed child presence.
	mergePreparedPresence(original, presence, "")
	return node, presence, nil
}
func preparedNodeIdentity(node map[string]any, name, compiledAddress string) error {
	kind := termNode
	if node[termType] == termSwitch {
		kind = termNetwork
	}
	canonical, err := address.Render("provision", kind, name)
	if err != nil || canonical != compiledAddress {
		return invalidRealization()
	}
	return nil
}
func preparedNodeRequirements(node, original map[string]any, name, compiledAddress string) ([]Requirement, error) {
	requirements := []Requirement{}
	for _, definition := range concernDefinitions {
		requirement, include, err := preparedRuntimeRequirement(definition, node, original, name, compiledAddress)
		if err != nil {
			return nil, err
		}
		if include {
			requirements = append(requirements, requirement)
		}
	}
	artifact, err := preparedArtifactRequirement(node, name, compiledAddress)
	if err != nil {
		return nil, err
	}
	if artifact != nil {
		requirements = append(requirements, *artifact)
	}
	for _, requirement := range requirements {
		if _, err := AdmitRequirement(requirement); err != nil {
			return nil, err
		}
	}
	return requirements, nil
}
func preparedRuntimeRequirement(definition concernDefinition, node, original map[string]any, name, compiledAddress string) (Requirement, bool, error) {
	if definition.section != termNodes || len(definition.authored) == 0 || definition.authored[0] != termRuntime {
		return Requirement{}, false, nil
	}
	value, present := payloadConcern(node, definition.authored)
	if !present || emptyPreparedConcern(value) {
		return Requirement{}, false, nil
	}
	// Close backend-supplied values through the installed observation owner.
	observedValue, provided := payloadConcern(original, definition.authored)
	if !provided {
		observedValue = value
	}
	fragment, err := nativeValueFragment(observedValue)
	if err != nil {
		return Requirement{}, false, err
	}
	if _, err := ProjectConcern(definition.kind, fragment, true, false); err != nil {
		return Requirement{}, false, err
	}
	requirement := exactRequirement(compiledAddress, "nodes."+name+"."+strings.Join(definition.authored, "."), definition.kind, "backend-realized", "")
	if definition.kind == termProcessResourceLimits {
		if err := preparedProcessDemands(&requirement, value); err != nil {
			return Requirement{}, false, err
		}
	}
	return requirement, true, nil
}

func emptyPreparedConcern(value any) bool {
	switch input := value.(type) {
	case nil:
		return true
	case string:
		return input == ""
	case []any:
		return len(input) == 0
	case map[string]any:
		return len(input) == 0
	default:
		return false
	}
}
func preparedProcessDemands(requirement *Requirement, value any) error {
	rows, ok := value.([]any)
	if !ok {
		return invalidRealization()
	}
	for _, row := range rows {
		demand, err := nativeProcessDemand(row)
		if err != nil {
			return err
		}
		requirement.ProcessResourceLimits = append(requirement.ProcessResourceLimits, demand)
	}
	return nil
}
func preparedArtifactRequirement(node map[string]any, name, compiledAddress string) (*Requirement, error) {
	source, ok := node[termSource].(map[string]any)
	if !ok || source["artifact_requirement"] == nil {
		return nil, nil //nolint:nilnil // A selected node can have no source-artifact demand.
	}
	encoded, err := json.Marshal(map[string]any{termSchemaVersion: "artifact-requirement/v1", termSource: source})
	if err != nil {
		return nil, invalidRealization()
	}
	var artifact binding.ArtifactRequirementV1
	if json.Unmarshal(encoded, &artifact) != nil {
		return nil, invalidRealization()
	}
	contract, err := loadArtifactContract(artifact)
	if err != nil {
		return nil, err
	}
	requirement := exactRequirement(compiledAddress, "nodes."+name+".source.artifact_requirement", "source-artifact", "backend-realized", "")
	requirement.Posture = &contract.Posture
	requirement.ArtifactRequirement = &artifact
	return &requirement, nil
}
func mergePreparedPresence(value any, presence map[string][]string, path string) {
	switch input := value.(type) {
	case map[string]any:
		mergePreparedRecordPresence(input, presence, path)

		for key, item := range input {
			child := key
			if path != "" {
				child = path + "." + key
			}
			mergePreparedPresence(item, presence, child)
		}
	case []any:
		for index, item := range input {
			mergePreparedPresence(item, presence, path+"["+strconv.Itoa(index)+"]")
		}
	}
}

func mergePreparedRecordPresence(input map[string]any, presence map[string][]string, path string) {
	if _, typed := presence[path]; typed {
		for key, item := range input {
			if field, marker := strings.CutSuffix(key, "_present"); marker && item == true && !slices.Contains(presence[path], field) {
				presence[path] = append(presence[path], field)
			}
		}
		slices.Sort(presence[path])
	}
}
