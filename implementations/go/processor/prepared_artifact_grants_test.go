package processor

import "testing"

func TestPreparedArtifactsRequireExactEnvironmentAndContentConsumerGrants(t *testing.T) {
	environment := map[string]any{"node": "host", "target_address": "provision.node.host", "delivery_mode": "environment", "output": "token", "environment_variable": "TOKEN"}
	content := map[string]any{"content": "config", "target_address": "provision.content.config", "delivery_mode": "content_text", "output": "text"}
	context := preparedContext{environment: map[string][]generatedNodeConsumer{}, content: map[string][]generatedContentConsumer{}}
	if err := context.artifact("generated", map[string]any{"environment_consumers": []any{environment}, "content_consumers": []any{content}}); err != nil {
		t.Fatal(err)
	}
	derived := map[string][]ArtifactConsumer{"generated": {
		{Node: "host", TargetAddress: "provision.node.host", DeliveryMode: "environment", Output: "token", EnvironmentVariable: "TOKEN"},
		{Content: "config", TargetAddress: "provision.content.config", DeliveryMode: "content_text", Output: "text"},
	}}
	if !context.grantsMatch(derived) {
		t.Fatal("exact native artifact consumers refused")
	}
	context.content["generated"][0].TargetAddress = "provision.content.other"
	if context.grantsMatch(derived) {
		t.Fatal("content grant borrowed another target")
	}
	context.content = nil
	context.environment["generated"][0].EnvironmentVariable = "OTHER"
	if context.grantsMatch(derived) {
		t.Fatal("environment grant changed its bound variable")
	}
}

func TestPreparedArtifactConsumersRefuseMissingMalformedAndAdditionalAuthority(t *testing.T) {
	for _, spec := range []map[string]any{
		{}, {"environment_consumers": true}, {"content_consumers": true},
		{"environment_consumers": []any{true}}, {"content_consumers": []any{true}},
		{"environment_consumers": []any{map[string]any{"node": "host", "target_address": "provision.node.other", "delivery_mode": "environment", "output": "token", "environment_variable": "TOKEN"}}},
		{"content_consumers": []any{map[string]any{"content": "config", "target_address": "provision.content.config", "delivery_mode": "content_text", "output": "text", "extra": true}}},
	} {
		context := preparedContext{environment: map[string][]generatedNodeConsumer{}, content: map[string][]generatedContentConsumer{}}
		if err := context.artifact("generated", spec); err == nil {
			t.Fatal("unbound artifact consumer accepted")
		}
	}
}
