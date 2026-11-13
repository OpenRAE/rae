package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

func profileBoundaryCopy(t *testing.T, input any) map[string]any {
	t.Helper()
	var output map[string]any
	requireNoError(t, json.Unmarshal(requireJSON(t, input), &output))
	return output
}

func TestPlanProfileNodesKeepOwnerProvenanceAndSourceCommitment(t *testing.T) {
	owner := boundTestOwner(t)
	_, _, input := profileAuthorityFixture(t)
	tree, err := planProfileTree(array(input["bindings"]))
	requireNoError(t, err)
	var root planProfileNode
	for _, node := range tree {
		root = node
		break
	}
	constraint := requireType[map[string]any](t, array(input["constraints"])[0])
	if !owner.planProfileNodeValid(root, tree, constraint) {
		t.Fatal("published profile authority refused")
	}
	for _, field := range []string{"owning_contract_id", "concept_family", "lifecycle_phase", "use", "canonical_address"} {
		t.Run(field, func(t *testing.T) {
			node := root
			node.data = profileBoundaryCopy(t, root.data)
			requireType[map[string]any](t, node.data["owner"])[field] = "different"
			if owner.planProfileNodeValid(node, tree, constraint) {
				t.Fatalf("changed profile owner %q accepted", field)
			}
		})
	}
	node := root
	node.data = profileBoundaryCopy(t, root.data)
	requireType[map[string]any](t, node.data["provenance"])["basis"] = "backend-selected"
	if owner.planProfileNodeValid(node, tree, constraint) {
		t.Fatal("backend provenance became authored authority")
	}
	node.data = profileBoundaryCopy(t, root.data)
	node.data["value"] = func() {}
	if owner.planProfileNodeValid(node, tree, constraint) {
		t.Fatal("non-JSON selected value accepted")
	}
	changed := profileBoundaryCopy(t, constraint)
	requireType[map[string]any](t, changed["document"])["semantic_profile"] = "different/v1"
	if owner.planProfileNodeValid(root, tree, changed) {
		t.Fatal("constraint changed its pinned definition")
	}
	changed = profileBoundaryCopy(t, constraint)
	changed["source_binding"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
	if owner.planProfileNodeValid(root, tree, changed) {
		t.Fatal("changed source commitment accepted")
	}
}

func TestNestedProfileNodesCannotChangeTheirParentResource(t *testing.T) {
	owner := boundTestOwner(t)
	_, _, input := profileAuthorityFixture(t)
	tree, err := planProfileTree(array(input["bindings"]))
	requireNoError(t, err)
	var root planProfileNode
	for _, node := range tree {
		root = node
		break
	}
	constraint := array(input["constraints"])[0]
	child := root
	child.path = []string{root.path[0], "child"}
	if owner.planProfileNodeValid(child, nil, constraint) {
		t.Fatal("nested binding with no parent accepted")
	}
	parent := root
	parent.data = profileBoundaryCopy(t, root.data)
	requireType[map[string]any](t, parent.data["owner"])["canonical_address"] = "#/resources/provision.node.other"
	tree[jsonpointer.FromTokens(root.path)] = parent
	if owner.planProfileNodeValid(child, tree, constraint) {
		t.Fatal("child profile borrowed another resource's parent")
	}
}

func TestPlanProfileAuthorityRejectsMissingAndChangedPinnedInputs(t *testing.T) {
	owner := boundTestOwner(t)
	_, context, original := profileAuthorityFixture(t)
	for _, field := range []string{"bindings", "constraints", "definitions"} {
		t.Run(field, func(t *testing.T) {
			input := profileBoundaryCopy(t, original)
			input[field] = []any{}
			var changed binding.PlanRealizationProfilesV1
			requireNoError(t, json.Unmarshal(requireJSON(t, input), &changed))
			admitted, err := CheckPlanProfileAuthority(owner, changed, context)
			if err == nil && admitted {
				t.Fatalf("authority without its %s accepted", field)
			}
		})
	}
	input := profileBoundaryCopy(t, original)
	constraints := requireType[[]any](t, input["constraints"])
	requireType[map[string]any](t, constraints[0])["source_binding"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
	var changed binding.PlanRealizationProfilesV1
	requireNoError(t, json.Unmarshal(requireJSON(t, input), &changed))
	if admitted, err := CheckPlanProfileAuthority(owner, changed, context); err == nil && admitted {
		t.Fatal("changed source commitment granted profile authority")
	}
}
