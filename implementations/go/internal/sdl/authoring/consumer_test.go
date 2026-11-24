package authoring

import (
	"bytes"
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestConsumerFamilySelectionPreservesContextAndDomain(t *testing.T) {
	parser := operationParser(t)
	document := operationDocument(t, parser, `name: family-example
variables:
  host: {type: string, default: first}
variation_points:
  payload-host:
    kind: parameter
    target: {kind: variable, variable: host}
    domain: {kind: enum, values: [first, second]}
`)
	family, err := parser.AdmitFamily(document)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile("../../../../../contracts/fixtures/experiment-core/experiment-authoring-input-v1/valid/sample-selection.json")
	if err != nil {
		t.Fatal(err)
	}
	var spec binding.ExperimentAuthoringInputV1
	if err := json.Unmarshal(raw, &spec); err != nil {
		t.Fatal(err)
	}
	if _, err := parser.ValidateExperimentSelectionAgainstFamily(spec, family); err != nil {
		t.Fatalf("valid sample policy refused: %v", err)
	}
	for _, changed := range []string{
		strings.Replace(string(raw), "family-example", "other-family", 1),
		strings.Replace(string(raw), "payload-host", "missing-point", 1),
	} {
		if err := json.Unmarshal([]byte(changed), &spec); err != nil {
			t.Fatal(err)
		}
		if _, err := parser.ValidateExperimentSelectionAgainstFamily(spec, family); err == nil {
			t.Fatal("family selection admitted a changed family or missing point")
		}
	}
	if _, err := parser.ValidateExperimentSelectionAgainstFamily(spec, document); err == nil {
		t.Fatal("selection admitted an unexpanded constructed document")
	}
}

func TestConsumerInstantiationPreservesDeclarationOrder(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	document, err := parser.Decode(Request{Source: []byte("name: ordered\nnodes:\n  z: {type: compute}\n  a: {type: compute}\n")})
	if err != nil {
		t.Fatal(err)
	}
	instance, err := parser.Instantiate(document, nil, "")
	if err != nil {
		t.Fatal(err)
	}
	var value struct {
		Nodes json.RawMessage `json:"nodes"`
	}
	if err := json.Unmarshal(instance.ModelJSON(), &value); err != nil {
		t.Fatal(err)
	}
	if bytes.Index(value.Nodes, []byte(`"z":`)) > bytes.Index(value.Nodes, []byte(`"a":`)) {
		t.Fatal("instantiation reordered authored nodes")
	}
}

func TestConsumerInstantiationKeepsAbsentOutputSelection(t *testing.T) {
	parser := operationParser(t)
	document := operationDocument(t, parser, `name: generated
nodes:
  server: {type: compute}
generated_artifacts:
  settings:
    generator: rendered_config
    lifecycle: reuse_valid
    provenance: config/settings.yaml
    outputs: [{name: config, path: config.txt, sensitivity: public}]
    consumers: [{node: server, mount_destination: /config, access_mode: read_only}]
`)
	instance, err := parser.Instantiate(document, nil, "")
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(instance.JSON(), []byte(`"selected_outputs":[]`)) {
		t.Fatal("binding published an empty output selection")
	}
}

func TestConcernConstructionDoesNotRequireSiblingReferences(t *testing.T) {
	parser := operationParser(t)
	value, err := parser.NormalizeConcern("nodes", []string{"runtime", "software_components"}, []byte(`[{"component_id":"component","name":"library","component_type":"library","repository_refs":["repo"]}]`))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(value, []byte(`"repository_refs":["repo"]`)) {
		t.Fatal("isolated concern lost its declared reference")
	}
}
