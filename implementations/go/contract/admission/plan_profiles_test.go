package admission

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func profileAuthorityFixture(t *testing.T) (binding.PlanRealizationProfilesV1, binding.DomainProfileResolutionContextV1, map[string]any) {
	t.Helper()
	raw, err := os.ReadFile("../../../../contracts/fixtures/plans/plan-realization-profiles-v1/valid/resource-label-authority.json")
	if err != nil {
		t.Fatal(err)
	}
	var authority binding.PlanRealizationProfilesV1
	if json.Unmarshal(raw, &authority) != nil {
		t.Fatal("fixture")
	}
	var input map[string]any
	if json.Unmarshal(raw, &input) != nil {
		t.Fatal("fixture")
	}
	definition := requireType[map[string]any](t, requireType[map[string]any](t, requireType[[]any](t, input["definitions"])[0])["definition"])
	contextInput := map[string]any{
		"definitions":          input["definitions"],
		"namespace_admissions": []any{map[string]any{"namespace": "com.example.private", "authority": "urn:example:profiles", "trust_decision_id": "trust"}},
		"support_declarations": []any{map[string]any{
			"coordinate": definition["coordinate"], "semantic_contract": definition["semantic_contract"],
			"operations":                []string{"comparison", "execution", "semantic-validation", "structural-validation"},
			"supported_schema_dialects": []string{"https://json-schema.org/draft/2020-12/schema"},
			"supported_schema_keywords": []string{"$id", "$schema", "additionalProperties", "properties", "required", "type"},
		}},
	}
	raw = requireJSON(t, contextInput)
	var context binding.DomainProfileResolutionContextV1
	if err := json.Unmarshal(raw, &context); err != nil {
		t.Fatal(err)
	}
	return authority, context, input
}

func TestPlanProfilesKeepPinnedAuthorityAndIndependentSupport(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	authority, context, source := profileAuthorityFixture(t)
	valid, err := CheckPlanProfileAuthority(owner, authority, context)
	if err != nil || !valid {
		t.Fatalf("authority=%v %v", valid, err)
	}
	digest, err := DomainProfileContextDigest(owner, context)
	if err != nil || len(digest) != 71 {
		t.Fatalf("digest=%s %v", digest, err)
	}
	selection := requireType[map[string]any](t, requireType[[]any](t, source["bindings"])[0])
	requireType[map[string]any](t, selection["provenance"])["basis"] = "backend-selected"
	selection["value"] = map[string]any{"name": "green"}
	selectedBytes := requireJSON(t, selection)
	var selected binding.DomainProfileBindingV1
	if checkErr := json.Unmarshal(selectedBytes, &selected); checkErr != nil {
		t.Fatal(checkErr)
	}
	valid, err = CheckPlanProfileSelection(owner, authority, []binding.DomainProfileBindingV1{selected}, context)
	if err != nil || !valid {
		t.Fatalf("bounded backend selection=%v %v", valid, err)
	}
	selection["value"] = map[string]any{"name": "outside"}
	selectedBytes = requireJSON(t, selection)
	requireNoError(t, json.Unmarshal(selectedBytes, &selected))
	valid, err = CheckPlanProfileSelection(owner, authority, []binding.DomainProfileBindingV1{selected}, context)
	if err != nil || valid {
		t.Fatalf("out-of-authority selection=%v %v", valid, err)
	}
	context.SupportDeclarations = zeroField(context.SupportDeclarations)
	valid, err = CheckPlanProfileAuthority(owner, authority, context)
	if err != nil || valid {
		t.Fatalf("missing support admitted=%v %v", valid, err)
	}
}

func zeroField[T any](binding.Field[T]) binding.Field[T] { return binding.Field[T]{} }

func TestAuthoredProfileAuthorityKeepsExactSelection(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	authority, context, input := profileAuthorityFixture(t)
	raw := requireJSON(t, input["bindings"])
	var authored []binding.DomainProfileBindingV1
	if checkErr := json.Unmarshal(raw, &authored); checkErr != nil {
		t.Fatal(checkErr)
	}
	if _, checkErr := ResolvePlanProfileAuthority(owner, authored, nil, nil); checkErr == nil {
		t.Fatal("authored profile without target context admitted")
	}
	resolved, err := ResolvePlanProfileAuthority(owner, authored, nil, &context)
	if err != nil || resolved == nil {
		t.Fatalf("authored authority=%v %v", resolved, err)
	}
	valid, err := CheckPlanProfileAuthority(owner, *resolved, context)
	if err != nil || !valid {
		t.Fatalf("authored authority invalid=%v %v", valid, err)
	}
	if _, err := ResolvePlanProfileAuthority(owner, authored, &authority, &context); err == nil {
		t.Fatal("wider supplied constraint replaced exact authored selection")
	}
	if _, err := ResolvePlanProfileAuthority(owner, authored, resolved, &context); err != nil {
		t.Fatalf("same authored source refused: %v", err)
	}
	missing := context
	requireNoError(t, missing.Definitions.UnmarshalJSON([]byte(`[]`)))
	if _, err := ResolvePlanProfileAuthority(owner, authored, nil, &missing); err == nil {
		t.Fatal("authored authority with no pinned definition admitted")
	}
}

func TestProfileContextKeepsNativeScalarLimit(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	_, context, _ := profileAuthorityFixture(t)
	raw := requireJSON(t, context)
	var input map[string]any
	requireNoError(t, json.Unmarshal(raw, &input))
	requireType[map[string]any](t, requireType[[]any](t, input["namespace_admissions"])[0])["authority"] = "urn:example:" + strings.Repeat("x", 4097)
	raw = requireJSON(t, input)
	requireNoError(t, json.Unmarshal(raw, &context))
	if _, err := DomainProfileContextDigest(owner, context); err == nil {
		t.Fatal("profile scalar limit was widened")
	}
}

func TestAuthoredProfileConstraintsKeepNativeTreeOrder(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	_, context, input := profileAuthorityFixture(t)
	first := requireType[map[string]any](t, requireType[[]any](t, input["bindings"])[0])
	first["binding_id"] = "alpha"
	one := requireJSON(t, first)
	first["binding_id"] = "zeta"
	two := requireJSON(t, first)
	var roots []binding.DomainProfileBindingV1
	if json.Unmarshal(append(append(append([]byte{'['}, one...), ','), append(two, ']')...), &roots) != nil {
		t.Fatal("binding roots")
	}
	resolved, err := ResolvePlanProfileAuthority(owner, roots, nil, &context)
	if err != nil {
		t.Fatal(err)
	}
	constraints, _ := resolved.Constraints.Value()
	path, _ := constraints[0].BindingPath.Value()
	if len(path) != 1 || path[0] != "zeta" {
		t.Fatalf("native tree order=%v", path)
	}
}
