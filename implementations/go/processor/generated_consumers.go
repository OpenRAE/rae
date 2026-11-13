package processor

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// GeneratedArtifactConsumers derives requested deliveries from a selected
// portable context. The facts grant no generated-artifact delivery authority;
// callers must compare them with the original admitted grant.
func GeneratedArtifactConsumers(input admission.Fragment) (map[string][]ArtifactConsumer, error) {
	if err := admission.CheckFragment(input, admission.RealizationValue); err != nil {
		return nil, err
	}
	findings, err := sdl.ValidateNodeRealizationContext(input)
	if err != nil {
		return nil, err
	}
	if len(findings) > 0 {
		return nil, invalidCompiled()
	}
	raw, err := json.Marshal(input.Document())
	if err != nil {
		return nil, err
	}
	var model binding.InstantiatedScenarioV1
	if err = json.Unmarshal(raw, &model); err != nil {
		return nil, invalidCompiled()
	}
	order, err := compileFieldOrder(raw)
	if err != nil {
		return nil, err
	}
	state := compilerState{input: compilerInput{model: model, order: order}}
	index := state.generatedConsumerIndex()
	if state.err != nil {
		return nil, state.err
	}
	result := make(map[string][]ArtifactConsumer)
	for _, name := range state.names(termGeneratedArtifacts) {
		entries := []ArtifactConsumer{}
		for _, consumer := range index.environment[name] {
			entries = append(entries, ArtifactConsumer{Node: consumer.Node, TargetAddress: consumer.TargetAddress, DeliveryMode: consumer.DeliveryMode, Output: consumer.Output, EnvironmentVariable: consumer.EnvironmentVariable, EnvironmentFile: consumer.EnvironmentFile, Classification: index.classifications[[3]string{name, consumer.Node, consumer.EnvironmentVariable}]})
		}
		for _, consumer := range index.content[name] {
			entries = append(entries, ArtifactConsumer{Content: consumer.Content, TargetAddress: consumer.TargetAddress, DeliveryMode: consumer.DeliveryMode, Output: consumer.Output})
		}
		result[name] = entries
	}
	return result, nil
}
