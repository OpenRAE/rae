package planning_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestPlanProfilesNeedPinnedIndependentTargetContext(t *testing.T) {
	raw, err := os.ReadFile("../../../../contracts/fixtures/plans/plan-realization-profiles-v1/valid/resource-label-authority.json")
	requireNoError(t, err)
	var authority binding.PlanRealizationProfilesV1
	requireNoError(t, json.Unmarshal(raw, &authority))
	scenario, err := sdl.Parse([]byte("name: example\nnodes: {host: {type: compute}}\n"), sdl.DefaultParseOptions())
	requireNoError(t, err)
	compiled, err := processor.CompileWithOptions(scenario, processor.CompileOptions{ProfileAuthority: &authority})
	requireNoError(t, err)
	result, err := planning.PlanWithManifest(compiled, manifest(t), planning.Options{})
	requireNoError(t, err)
	found := false
	for _, d := range result.Diagnostics {
		found = found || d.Code == "realization.profile-unsupported"
	}
	if !found || result.Plan.Valid() {
		t.Fatalf("profile authority accepted without independent context: %+v", result.Diagnostics)
	}
	limited := changeManifest(t, func(record map[string]any) {
		requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])["supported_node_types"] = []any{"switch"}
	})
	ordered, err := planning.PlanWithManifest(compiled, limited, planning.Options{})
	if err != nil || len(ordered.Diagnostics) < 2 || ordered.Diagnostics[0].Code != "realization.profile-unsupported" {
		t.Fatalf("profile refusal order=%+v %v", ordered.Diagnostics, err)
	}
	var input map[string]any
	requireNoError(t, json.Unmarshal(raw, &input))
	definition := requireType[map[string]any](t, requireType[map[string]any](t, requireType[[]any](t, input["definitions"])[0])["definition"])
	contextRaw := requireJSON(t, map[string]any{
		"definitions":          input["definitions"],
		"namespace_admissions": []any{map[string]any{"namespace": "com.example.private", "authority": "urn:example:profiles", "trust_decision_id": "trust"}},
		"support_declarations": []any{map[string]any{"coordinate": definition["coordinate"], "semantic_contract": definition["semantic_contract"], "operations": []string{"comparison", "execution", "semantic-validation", "structural-validation"}, "supported_schema_dialects": []string{"https://json-schema.org/draft/2020-12/schema"}, "supported_schema_keywords": []string{"$id", "$schema", "additionalProperties", "properties", "required", "type"}}},
	})
	var context binding.DomainProfileResolutionContextV1
	requireNoError(t, json.Unmarshal(contextRaw, &context))
	owner, err := admission.New()
	requireNoError(t, err)
	digest, err := admission.DomainProfileContextDigest(owner, context)
	requireNoError(t, err)
	target := changeManifest(t, func(record map[string]any) {
		record["domain_profile_context_digest"] = digest
		record["supported_contract_versions"] = append(requireType[[]any](t, record["supported_contract_versions"]), "plan-realization-profiles-v1", "backend-realization-preparation-v1")
	})
	supported, err := planning.PlanWithManifest(compiled, target, planning.Options{ProfileContext: &context})
	if err != nil || !supported.Plan.Valid() {
		t.Fatalf("supported profile: %+v %v", supported.Diagnostics, err)
	}
	ops := field(supported.Plan.Provisioning().Operations)
	if len(ops) != 1 || len(field(ops[0].ProfileBindings)) != 1 || len(field(supported.Plan.Provisioning().ProfileAuthority)) == 0 {
		t.Fatal("profile authority or selected binding dropped")
	}
	snapshot, err := planning.AssumedSnapshot(supported.Plan)
	requireNoError(t, err)
	entries := field(snapshot.Entries)
	var entry map[string]any
	if json.Unmarshal(entries["provision.node.host"], &entry) != nil {
		t.Fatal("snapshot")
	}
	selected := requireType[map[string]any](t, requireType[[]any](t, entry["profile_bindings"])[0])
	selected["value"] = map[string]any{"name": "green"}
	requireType[map[string]any](t, selected["provenance"])["basis"] = "backend-selected"
	entries["provision.node.host"] = requireJSON(t, entry)
	retained, err := planning.PlanWithManifest(compiled, target, planning.Options{ProfileContext: &context, Snapshot: &snapshot})
	if err != nil || !retained.Plan.Valid() {
		t.Fatalf("retention: %+v %v", retained.Diagnostics, err)
	}
	ops = field(retained.Plan.Provisioning().Operations)
	if field(ops[0].Action) != "unchanged" {
		t.Fatal("admitted backend selection was not retained")
	}
}
