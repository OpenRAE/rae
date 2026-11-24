package processor

import (
	"encoding/json"
	"slices"
	"strings"
)

type generatedValueSource struct {
	GeneratedArtifact string `json:"generated_artifact"`
	Output            string `json:"output"`
}
type generatedNodeConsumer struct {
	Node                string `json:"node"`
	TargetAddress       string `json:"target_address"`
	DeliveryMode        string `json:"delivery_mode"`
	Output              string `json:"output"`
	EnvironmentVariable string `json:"environment_variable,omitempty"`
	EnvironmentFile     string `json:"environment_file,omitempty"`
}
type generatedContentConsumer struct {
	Content       string `json:"content"`
	TargetAddress string `json:"target_address"`
	DeliveryMode  string `json:"delivery_mode"`
	Output        string `json:"output"`
}
type statefulMountConsumer struct {
	Node             string    `json:"node"`
	MountDestination string    `json:"mount_destination"`
	AccessMode       string    `json:"access_mode"`
	SelectedOutputs  *[]string `json:"selected_outputs,omitempty"`
	TargetAddress    string    `json:"target_address"`
	DeliveryMode     string    `json:"delivery_mode,omitempty"`
}
type generatedConsumerIndex struct {
	environment     map[string][]generatedNodeConsumer
	content         map[string][]generatedContentConsumer
	classifications map[[3]string]string
}

func (state *compilerState) generatedConsumerIndex() generatedConsumerIndex {
	result := generatedConsumerIndex{environment: map[string][]generatedNodeConsumer{}, content: map[string][]generatedContentConsumer{}, classifications: map[[3]string]string{}}
	nodes := fieldValue(state.input.model.Nodes)
	for _, name := range orderedNames(nodes, state.names(termNodes)) {
		result.addEnvironmentConsumers(state, name)
		if state.err != nil {
			return result
		}
	}
	content := fieldValue(state.input.model.Content)
	for _, name := range orderedNames(content, state.names(termContent)) {
		var source *generatedValueSource
		if raw := fieldValue(content[name].TextFrom); len(raw) > 0 {
			if err := json.Unmarshal(raw, &source); err != nil {
				state.err = invalidCompiled()
				return result
			}
		}
		if source != nil {
			artifact := state.sectionName(source.GeneratedArtifact, termGeneratedArtifacts)
			result.content[artifact] = append(result.content[artifact], generatedContentConsumer{name, state.address(termProvision, termContent, name), "content_text", source.Output})
		}
	}
	return result
}
func (index *generatedConsumerIndex) addEnvironmentConsumers(state *compilerState, name string) {
	var runtime struct {
		Environment []struct {
			Name                string                `json:"name"`
			ValueClassification string                `json:"value_classification"`
			ValueFrom           *generatedValueSource `json:"value_from"`
		} `json:"environment"`
		EnvironmentFiles []struct {
			Name      string               `json:"name"`
			ValueFrom generatedValueSource `json:"value_from"`
		} `json:"environment_files"`
	}
	if raw := fieldValue(fieldValue(state.input.model.Nodes)[name].Runtime); len(raw) > 0 {
		if err := json.Unmarshal(raw, &runtime); err != nil {
			state.err = invalidCompiled()
			return
		}
	}
	for _, variable := range runtime.Environment {
		if variable.ValueFrom == nil {
			continue
		}
		artifact := state.sectionName(variable.ValueFrom.GeneratedArtifact, termGeneratedArtifacts)
		index.environment[artifact] = append(index.environment[artifact], generatedNodeConsumer{Node: name, TargetAddress: state.address(termProvision, termNode, name), DeliveryMode: "environment", Output: variable.ValueFrom.Output, EnvironmentVariable: variable.Name})
		index.classifications[[3]string{artifact, name, variable.Name}] = variable.ValueClassification
	}
	for _, file := range runtime.EnvironmentFiles {
		artifact := state.sectionName(file.ValueFrom.GeneratedArtifact, termGeneratedArtifacts)
		index.environment[artifact] = append(index.environment[artifact], generatedNodeConsumer{Node: name, TargetAddress: state.address(termProvision, termNode, name), DeliveryMode: "env_file", Output: file.ValueFrom.Output, EnvironmentFile: file.Name})
	}
}

func (state *compilerState) statefulDependency(ref string) string {
	artifacts := fieldValue(state.input.model.GeneratedArtifacts)
	volumes := fieldValue(state.input.model.PersistentVolumes)
	if name, qualified := strings.CutPrefix(ref, "generated_artifacts."); qualified {
		if _, exists := artifacts[name]; exists {
			return state.address(termProvision, termGeneratedArtifact, name)
		}
	}
	if name, qualified := strings.CutPrefix(ref, "persistent_volumes."); qualified {
		if _, exists := volumes[name]; exists {
			return state.address(termProvision, termPersistentVolume, name)
		}
	}
	_, artifact := artifacts[ref]
	_, volume := volumes[ref]
	if artifact != volume {
		kind := termPersistentVolume
		if artifact {
			kind = termGeneratedArtifact
		}
		return state.address(termProvision, kind, ref)
	}
	state.err = invalidCompiled()
	return ""
}
func (state *compilerState) statefulDependencies(refs []string) []string {
	result := make([]string, 0, len(refs))
	for _, ref := range refs {
		result = append(result, state.statefulDependency(ref))
	}
	return result
}

// statefulWireSpec completes a published payload leaf. No later compiler pass
// decodes the leaf; capability and consumer facts remain native records.
func statefulWireSpec(original json.RawMessage, consumers []statefulMountConsumer, environment []generatedNodeConsumer, content []generatedContentConsumer) json.RawMessage {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(original, &fields); err != nil {
		panic("processor: invalid owned stateful source")
	}
	fields["consumers"] = rawJSON(consumers)
	if environment != nil {
		fields["environment_consumers"] = rawJSON(environment)
	}
	if len(content) > 0 {
		fields["content_consumers"] = rawJSON(content)
	}
	return rawJSON(fields)
}
func (state *compilerState) compileGeneratedArtifacts() {
	artifacts := fieldValue(state.input.model.GeneratedArtifacts)
	index := state.generatedConsumerIndex()
	for _, name := range orderedNames(artifacts, state.names(termGeneratedArtifacts)) {
		artifact := artifacts[name]
		facts := &ArtifactFacts{Kind: rawString(fieldValue(artifact.Generator)), RegenerationScope: rawString(fieldValue(artifact.RegenerationScope)), OutputNames: []string{}, Consumers: []ArtifactConsumer{}, DeliveryModes: []string{}}
		if facts.Kind == "" {
			facts.GeneratorBinding = domainProfileBinding(fieldValue(artifact.Generator))
		}
		for _, output := range fieldValue(artifact.Outputs) {
			facts.OutputNames = append(facts.OutputNames, fieldValue(output.Name))
		}
		consumers := state.generatedMountConsumers(name, facts)
		environment := index.environment[name]
		if environment == nil {
			environment = []generatedNodeConsumer{}
		}
		for _, consumer := range environment {
			facts.Consumers = append(facts.Consumers, ArtifactConsumer{Node: consumer.Node, TargetAddress: consumer.TargetAddress, DeliveryMode: consumer.DeliveryMode, Output: consumer.Output, EnvironmentVariable: consumer.EnvironmentVariable, EnvironmentFile: consumer.EnvironmentFile, Classification: index.classifications[[3]string{name, consumer.Node, consumer.EnvironmentVariable}]})
			facts.DeliveryModes = append(facts.DeliveryModes, consumer.DeliveryMode)
		}
		for _, consumer := range index.content[name] {
			facts.Consumers = append(facts.Consumers, ArtifactConsumer{Content: consumer.Content, TargetAddress: consumer.TargetAddress, DeliveryMode: consumer.DeliveryMode, Output: consumer.Output})
			facts.DeliveryModes = append(facts.DeliveryModes, consumer.DeliveryMode)
		}
		slices.Sort(facts.DeliveryModes)
		facts.DeliveryModes = slices.Compact(facts.DeliveryModes)
		spec := statefulWireSpec(rawJSON(artifact), consumers, environment, index.content[name])
		payload := struct {
			Name string          `json:"name"`
			Spec json.RawMessage `json:"spec"`
		}{name, spec}
		state.model.Resources = append(state.model.Resources, Resource{Address: state.address(termProvision, termGeneratedArtifact, name), Name: name, Domain: termProvisioning, Kind: termGeneratedArtifact, OrderingDependencies: state.statefulDependencies(fieldValue(artifact.OrderingDependencies)), RefreshDependencies: state.statefulDependencies(fieldValue(artifact.RefreshDependencies)), Artifact: facts, RegenerationScope: facts.RegenerationScope, Payload: state.payload(payload)})
	}
}
func (state *compilerState) generatedMountConsumers(name string, facts *ArtifactFacts) []statefulMountConsumer {
	consumers := []statefulMountConsumer{}
	for _, consumer := range fieldValue(fieldValue(state.input.model.GeneratedArtifacts)[name].Consumers) {
		node := state.sectionName(fieldValue(consumer.Node), termNodes)
		outputs := nonNilStrings(fieldValue(consumer.SelectedOutputs))
		var selected *[]string
		if len(outputs) > 0 {
			selected = &outputs
		}
		target := state.address(termProvision, termNode, node)
		consumers = append(consumers, statefulMountConsumer{Node: node, MountDestination: fieldValue(consumer.MountDestination), AccessMode: string(fieldValue(consumer.AccessMode)), SelectedOutputs: selected, TargetAddress: target, DeliveryMode: "mount"})
		facts.Consumers = append(facts.Consumers, ArtifactConsumer{Node: node, TargetAddress: target, DeliveryMode: "mount"})
		facts.DeliveryModes = append(facts.DeliveryModes, "mount")
	}
	return consumers
}

func (state *compilerState) compilePersistentVolumes() {
	volumes := fieldValue(state.input.model.PersistentVolumes)
	for _, name := range orderedNames(volumes, state.names(termPersistentVolumes)) {
		volume := volumes[name]
		consumers := []statefulMountConsumer{}
		for _, consumer := range fieldValue(volume.Consumers) {
			node := state.sectionName(fieldValue(consumer.Node), termNodes)
			consumers = append(consumers, statefulMountConsumer{Node: node, MountDestination: fieldValue(consumer.MountDestination), AccessMode: string(fieldValue(consumer.AccessMode)), TargetAddress: state.address(termProvision, termNode, node)})
		}
		spec := statefulWireSpec(rawJSON(volume), consumers, nil, nil)
		state.model.Resources = append(state.model.Resources, Resource{Address: state.address(termProvision, termPersistentVolume, name), Name: name, Domain: termProvisioning, Kind: termPersistentVolume, OrderingDependencies: state.statefulDependencies(fieldValue(volume.OrderingDependencies)), RefreshDependencies: state.statefulDependencies(fieldValue(volume.RefreshDependencies)), Payload: state.payload(struct {
			Name string          `json:"name"`
			Spec json.RawMessage `json:"spec"`
		}{name, spec})})
	}
}
