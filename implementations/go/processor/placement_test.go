package processor_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestCompileGeneratedConsumersCarryIdentityAndRefresh(t *testing.T) {
	scenario, err := sdl.Parse([]byte(`name: generated
nodes:
  server: {type: compute}
generated_artifacts:
  token:
    generator: random_value
    lifecycle: reuse_valid
    regeneration_scope: per_run
    random_value: {alphabet: hex_lower, length: 32}
    provenance: test/token
    outputs: [{name: token, path: token.txt, sensitivity: secret}]
    consumers: [{node: server, mount_destination: /srv/token, access_mode: read_only, selected_outputs: [token]}]
content:
  message: {type: file, target: server, path: message.txt, destination: /tmp/message}
`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	result, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	var artifact, content processor.Resource
	for _, resource := range result.Model().View().Resources {
		if resource.Kind == "generated-artifact" {
			artifact = resource
		}
		if resource.Kind == "content-placement" {
			content = resource
		}
	}
	if artifact.Artifact == nil || artifact.Artifact.Kind != "random_value" || artifact.RegenerationScope != "per_run" || len(artifact.Artifact.Consumers) != 1 || artifact.Artifact.Consumers[0].TargetAddress != "provision.node.server" {
		t.Fatalf("artifact facts = %#v", artifact)
	}
	if content.ContentType != "file" || content.TargetAddress != "provision.node.server" || len(content.OrderingDependencies) != 1 {
		t.Fatalf("content facts = %#v", content)
	}
	artifact.Artifact.Consumers[0].TargetAddress = "changed"
	for _, resource := range result.Model().View().Resources {
		if resource.Kind == "generated-artifact" && resource.Artifact.Consumers[0].TargetAddress != "provision.node.server" {
			t.Fatal("artifact facts retained caller mutation")
		}
	}
}
