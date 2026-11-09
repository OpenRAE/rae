package sdlrules

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

const (
	contentSection   = "content"
	jsonNull         = "null"
	nodesSection     = "nodes"
	generatedSection = "generated_artifacts"
	volumesSection   = "persistent_volumes"
)

type statefulModel struct {
	input                 binding.SdlAuthoringInputV1
	order                 map[string][]string
	nodes                 []statefulNode
	nodeIndex             map[string]int
	resources             []resource
	generated             map[string]*resource
	volumes               map[string]bool
	content, propositions []artifactBinding
	occupied              map[[2]string]string
	consumed              map[string]bool
	findings              []Finding
}
type statefulNode struct {
	name, os string
	bindings []artifactBinding
	mounts   []string
}
type resource struct {
	owner        Owner
	consumers    []resourceConsumer
	dependencies []string
	outputs      []artifactOutput
}
type resourceConsumer struct{ node, destination string }
type artifactOutput struct{ name, sensitivity, disposition string }
type artifactSource struct {
	Artifact string `json:"generated_artifact"`
	Output   string `json:"output"`
}
type artifactBinding struct {
	owner                      Owner
	label                      string
	source                     artifactSource
	classification             *string
	sensitiveFalse, wrongBasis bool
}
type environmentBinding struct {
	Name           string          `json:"name"`
	Source         *artifactSource `json:"value_from"`
	Classification *string         `json:"value_classification"`
}

//nolint:ireturn // Each call returns its concrete schema-derived field type, without a runtime interface.
func fieldValue[T any](field binding.Field[T]) T { result, _ := field.Value(); return result }
func orderedKeys[T any](values map[string]T, order map[string][]string, tokens ...string) []string {
	if keys, present := order[jsonpointer.FromTokens(tokens)]; present {
		return keys
	}
	keys := make([]string, 0, len(values))
	for name := range values {
		keys = append(keys, name)
	}
	slices.Sort(keys)
	return keys
}
func decodeStateful(data []byte, order map[string][]string) (*statefulModel, error) {
	m := &statefulModel{order: order, nodeIndex: map[string]int{}, generated: map[string]*resource{}, volumes: map[string]bool{}, occupied: map[[2]string]string{}, consumed: map[string]bool{}}
	if json.Unmarshal(data, &m.input) != nil {
		return nil, projectionInvalid()
	}
	for _, load := range []func() error{m.nodeFacts, m.contentFacts, m.propositionFacts} {
		if err := load(); err != nil {
			return nil, err
		}
	}
	m.resourceFacts()
	return m, nil
}
func (m *statefulModel) nodeFacts() error {
	values := fieldValue(m.input.Nodes)
	for _, name := range orderedKeys(values, m.order, nodesSection) {
		value := values[name]
		os, err := textScalar(fieldValue(value.Os))
		if err != nil {
			return err
		}
		row := statefulNode{name: name, os: os}
		if err := row.runtimeFacts(fieldValue(value.Runtime)); err != nil {
			return err
		}
		m.nodeIndex[name] = len(m.nodes)
		m.nodes = append(m.nodes, row)
	}
	return nil
}
func (row *statefulNode) runtimeFacts(raw json.RawMessage) error {
	if len(raw) == 0 || string(raw) == jsonNull {
		return nil
	}
	var runtime struct {
		Environment []environmentBinding `json:"environment"`
		Files       []environmentBinding `json:"environment_files"`
		Mounts      []struct {
			Target string `json:"target"`
		} `json:"mounts"`
	}
	if json.Unmarshal(raw, &runtime) != nil {
		return projectionInvalid()
	}
	for _, env := range runtime.Environment {
		if env.Source == nil {
			continue
		}
		classification := env.Classification
		if classification == nil {
			unknown := "unknown"
			classification = &unknown
		}
		row.bindings = append(row.bindings, artifactBinding{owner: Owner{nodesSection, row.name}, label: "node " + quoted(row.name) + " environment variable " + quoted(env.Name), source: *env.Source, classification: classification})
	}
	for _, file := range runtime.Files {
		if file.Source != nil {
			row.bindings = append(row.bindings, artifactBinding{owner: Owner{nodesSection, row.name}, label: "node " + quoted(row.name) + " environment file " + quoted(file.Name), source: *file.Source})
		}
	}
	for _, mount := range runtime.Mounts {
		row.mounts = append(row.mounts, mount.Target)
	}
	return nil
}
func (m *statefulModel) resourceFacts() {
	generated := fieldValue(m.input.GeneratedArtifacts)
	for _, name := range orderedKeys(generated, m.order, generatedSection) {
		value := generated[name]
		row := resource{owner: Owner{generatedSection, name}, dependencies: append(slices.Clone(fieldValue(value.OrderingDependencies)), fieldValue(value.RefreshDependencies)...)}
		for _, consumer := range fieldValue(value.Consumers) {
			row.consumers = append(row.consumers, resourceConsumer{fieldValue(consumer.Node), fieldValue(consumer.MountDestination)})
		}
		for _, output := range fieldValue(value.Outputs) {
			row.outputs = append(row.outputs, artifactOutput{fieldValue(output.Name), string(fieldValue(output.Sensitivity)), string(fieldValue(output.Disposition))})
		}
		m.resources = append(m.resources, row)
		// Each resource has separate stable storage for generated-output lookup.
		m.generated[name] = &row
	}
	volumes := fieldValue(m.input.PersistentVolumes)
	for _, name := range orderedKeys(volumes, m.order, volumesSection) {
		value := volumes[name]
		row := resource{owner: Owner{volumesSection, name}, dependencies: append(slices.Clone(fieldValue(value.OrderingDependencies)), fieldValue(value.RefreshDependencies)...)}
		for _, consumer := range fieldValue(value.Consumers) {
			row.consumers = append(row.consumers, resourceConsumer{fieldValue(consumer.Node), fieldValue(consumer.MountDestination)})
		}
		m.resources = append(m.resources, row)
		m.volumes[name] = true
	}
}
func (m *statefulModel) contentFacts() error {
	values := fieldValue(m.input.Content)
	for _, name := range orderedKeys(values, m.order, contentSection) {
		value := values[name]
		var source *artifactSource
		if raw := fieldValue(value.TextFrom); len(raw) > 0 && json.Unmarshal(raw, &source) != nil {
			return projectionInvalid()
		}
		if source == nil {
			continue
		}
		sensitivity := fieldValue(value.Sensitive)
		m.content = append(m.content, artifactBinding{owner: Owner{contentSection, name}, label: "content " + quoted(name) + " text_from", source: *source, sensitiveFalse: len(sensitivity) == 0 || string(sensitivity) == "false"})
	}
	return nil
}
func (m *statefulModel) propositionFacts() error {
	values := fieldValue(m.input.Propositions)
	for _, name := range orderedKeys(values, m.order, "propositions") {
		value := values[name]
		var predicate struct {
			Kind   string          `json:"kind"`
			Source *artifactSource `json:"expected_from"`
		}
		if raw := fieldValue(value.Predicate); len(raw) > 0 && json.Unmarshal(raw, &predicate) != nil {
			return projectionInvalid()
		}
		if predicate.Kind != "string" || predicate.Source == nil {
			continue
		}
		m.propositions = append(m.propositions, artifactBinding{owner: Owner{"propositions", name}, label: "proposition " + quoted(name) + " expected_from", source: *predicate.Source, wrongBasis: string(fieldValue(value.Basis)) != "observed_state"})
	}
	return nil
}
