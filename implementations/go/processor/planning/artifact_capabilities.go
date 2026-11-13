package planning

import (
	"bytes"
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

func enumStrings[T ~string](input []T) []string {
	result := make([]string, len(input))
	for i, item := range input {
		result[i] = string(item)
	}
	return result
}

func artifactCapabilityDiagnostics(resources []processor.Resource, kinds []json.RawMessage, modes, scopes []string) []diagnostic.Diagnostic {
	allowed := map[string]bool{}
	for _, kind := range kinds {
		canonical, err := canonjson.JCS(kind)
		if err != nil {
			panic("planning: invalid admitted artifact capability")
		}
		allowed[string(canonical)] = true
	}
	result := []diagnostic.Diagnostic{}
	for _, resource := range resources {
		if resource.Artifact == nil {
			panic("planning: compiled artifact has no native facts")
		}
		code, message := artifactCapabilityGap(resource.Artifact, allowed, modes, scopes)

		if code != "" {
			result = append(result, planDiagnostic("provisioner."+code, termProvisioning, resource.Address, message))
		}
	}
	return result
}

func artifactCapabilityGap(facts *processor.ArtifactFacts, allowed map[string]bool, modes, scopes []string) (string, string) {
	kind := rawProjection(facts.Kind)
	if facts.GeneratorBinding != nil {
		kind = rawProjection(fieldValue(facts.GeneratorBinding.Coordinate))
	}
	canonical, err := canonjson.JCS(kind)
	if err != nil || bytes.Equal(canonical, []byte(termNull)) {
		panic("planning: invalid compiled artifact identity")
	}
	unsupportedModes := []string{}
	for _, mode := range facts.DeliveryModes {
		if !slices.Contains(modes, mode) {
			unsupportedModes = append(unsupportedModes, mode)
		}
	}
	slices.Sort(unsupportedModes)
	code, message := "", ""
	switch {
	case !allowed[string(canonical)]:
		code, message = "unsupported-generated-artifact-kind", "Provisioner does not support the selected generated artifact kind."
	case len(unsupportedModes) > 0:
		code, message = "unsupported-generated-artifact-delivery-mode", "Provisioner does not support generated artifact delivery mode '"+unsupportedModes[0]+"'."
	case facts.Kind == "random_value" && facts.RegenerationScope != "" && !slices.Contains(scopes, facts.RegenerationScope):
		code, message = "unsupported-regeneration-scope", "Provisioner does not support regeneration scope '"+facts.RegenerationScope+"'."
	}
	return code, message
}
