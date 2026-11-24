package authoring

import (
	"testing"

	"github.com/google/go-cmp/cmp"
)

func rewriteBoundarySymbols() importSymbols {
	return importSymbols{nodesSection: {"host": "lib.host"}, agentsSection: {"agent": "lib.agent"}, workflowsSection: {"flow": "lib.flow"}, generatedArtifactsField: {"token": "lib.token", "shared": "lib.artifact"}, persistentVolumesField: {"disk": "lib.disk", "shared": "lib.volume"}, contentField: {"tool": "lib.tool"}, controlAssetsSection: {"policy": "lib.policy"}}
}

func TestProfileAddressRewriteKeepsCompiledResourceAndControllerOwnership(t *testing.T) {
	symbols := rewriteBoundarySymbols()
	symbols[identityDomainsField] = map[string]string{"domain": "lib.domain"}
	for _, test := range []struct{ before, after string }{
		{"#/resources/provision.node.host", "#/resources/provision.node.lib.host"},
		{"#/resources/provision.content.tool", "#/resources/provision.content.lib.tool"},
		{"#/resources/provision.generated-artifact.token", "#/resources/provision.generated-artifact.lib.token"},
		{"#/resources/provision.persistent-volume.disk", "#/resources/provision.persistent-volume.lib.disk"},
		{"#/resources/provision.node.other", "#/resources/provision.node.other"},
		{"#/resources/provision.domain-controller.domain.host", "#/resources/provision.domain-controller.lib.domain.lib.host"},
		{"#/resources/provision.domain-controller.domain.other", "#/resources/provision.domain-controller.domain.other"},
		{"#/resources/provision.domain-controller.other.host", "#/resources/provision.domain-controller.other.host"},
		{"#/resources/evaluation.proposition.host", "#/resources/evaluation.proposition.host"},
	} {
		if got := rewriteCompiledProfileAddress(test.before, symbols); got != test.after {
			t.Fatalf("profile owner rewrite=%q, want %q", got, test.after)
		}
	}
}

func TestTransformationExportsRenameAndRemoveOnlyTheSelectedDeclaration(t *testing.T) {
	for _, remove := range []bool{false, true} {
		payload := map[string]any{"module": map[string]any{"exports": map[string]any{"nodes": []any{"host", "other"}, "accounts": []any{"host"}}}}
		rewriteTransformationExports(payload, "nodes", "host", "renamed", remove)
		want := []any{"renamed", "other"}
		if remove {
			want = []any{"other"}
		}
		exports := object(object(payload["module"])["exports"])
		if diff := cmp.Diff(want, exports["nodes"]); diff != "" {
			t.Fatal(diff)
		}
		if diff := cmp.Diff([]any{"host"}, exports["accounts"]); diff != "" {
			t.Fatal("renaming one declaration changed another family: " + diff)
		}
	}
}

func TestReferenceRewriteKeepsQualifiedScopeAndRejectsAmbiguousState(t *testing.T) {
	symbols := rewriteBoundarySymbols()
	for _, test := range []struct {
		domain, before, after string
		refuse                bool
	}{
		{"!stateful", "token", "lib.token", false}, {"!stateful", "disk", "lib.disk", false}, {"!stateful", "shared", "", true},
		{"!stateful", "generated_artifacts.shared", "generated_artifacts.lib.artifact", false}, {"!stateful", "persistent_volumes.shared", "persistent_volumes.lib.volume", false}, {"!stateful", "absent", "absent", false},
		{"!controller", "self", "self", false}, {"!controller", "agent", "lib.agent", false}, {"!workflow-step", "flow.step", "lib.flow.step", false}, {"!workflow-step", "flow", "flow", false},
		{"!node-service", "nodes.host.services.http", "nodes.lib.host.services.http", false}, {"!node-service", "nodes.other.services.http", "nodes.other.services.http", false},
		{"!control-asset", "policy", "lib.policy", false}, {"!tool", "tool", "lib.tool", false}, {"=nodes", "nodes.host", "nodes.lib.host", false}, {"=nodes", "nodes.absent", "nodes.absent", false},
		{"!stateful", "${choice}", "${choice}", false}, {"!stateful", "", "", false},
	} {
		t.Run(test.domain+"/"+test.before, func(t *testing.T) {
			got, err := rewriteReference(test.before, symbols, test.domain)
			if (err != nil) != test.refuse || got != test.after {
				t.Fatalf("rewrite=%q/%v, want %q/refused=%t", got, err, test.after, test.refuse)
			}
		})
	}
}

func TestReferenceRewriteTraversesOwnedListsAndRefusesKeyCollisions(t *testing.T) {
	symbols := rewriteBoundarySymbols()
	input := map[string]any{"refs": []any{"token", "disk"}, "description": "token"}
	got, err := rewritePath(input, []string{"refs", "*"}, symbols, "!stateful")
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]any{"refs": []any{"lib.token", "lib.disk"}, "description": "token"}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Fatal(diff)
	}
	if _, err := rewriteReferenceValue([]any{"shared"}, symbols, "!stateful"); err == nil {
		t.Fatal("ambiguous nested stateful reference accepted")
	}
	symbols[nodesSection]["second"] = "lib.host"
	if err := rewriteMappingKeys(map[string]any{"host": true, "second": false}, symbols, nodesSection); err == nil {
		t.Fatal("two declarations merged under one rewritten key")
	}
	if got, err := rewritePath(7, []string{"*"}, symbols, nodesSection); err != nil || got != 7 {
		t.Fatal("non-reference scalar was changed")
	}
}

func TestStructuredReferencesRewriteOnlyTheirDeclaredOwnerLayer(t *testing.T) {
	symbols := rewriteBoundarySymbols()
	symbols["deployment_tenants"] = map[string]string{"tenant": "lib.tenant"}
	symbols[actionsSection] = map[string]string{"action": "lib.action"}
	symbols[objectivesSection] = map[string]string{"goal": "lib.goal"}
	for _, test := range []struct{ domain, field, kind, before, after string }{
		{"!budget-owner", "kind", "participant", "agents.agent", "agents.lib.agent"},
		{"!budget-owner", "kind", "deployment_tenant", "deployment_tenants.tenant", "deployment_tenants.lib.tenant"},
		{"!budget-owner", "kind", "shared_service", "nodes.host.services.http", "nodes.lib.host.services.http"},
		{"!budget-owner", "kind", "future", "agent", "agent"},
		{"!outcome-source", "source_layer", "participant_action_outcome", "action", "lib.action"},
		{"!outcome-target", "target_layer", "objective_result", "goal", "lib.goal"},
		{"!outcome-target", "target_layer", "workflow_result", "flow", "lib.flow"},
		{"!outcome-target", "target_layer", "future", "goal", "goal"},
	} {
		t.Run(test.domain+"/"+test.kind, func(t *testing.T) {
			input := map[string]any{test.field: test.kind, "ref": test.before, "description": test.before}
			_, err := rewriteReferenceValue(input, symbols, test.domain)
			if err != nil || input["ref"] != test.after || input["description"] != test.before {
				t.Fatalf("structured reference crossed layers: %+v %v", input, err)
			}
		})
	}
}
