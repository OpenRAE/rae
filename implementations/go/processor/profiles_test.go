package processor_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestCompileRetainsAuthoredAccountProfile(t *testing.T) {
	raw, err := os.ReadFile("../../../contracts/fixtures/plans/plan-realization-profiles-v1/valid/resource-label-authority.json")
	if err != nil {
		t.Fatal(err)
	}
	var authority map[string]any
	if checkErr := json.Unmarshal(raw, &authority); checkErr != nil {
		t.Fatal(checkErr)
	}
	selection := requireType[map[string]any](t, requireType[[]any](t, authority["bindings"])[0])
	owner := requireType[map[string]any](t, selection["owner"])
	owner["canonical_address"] = "#/resources/provision.account.admin"
	owner["context"] = "account-materialization"
	source := map[string]any{"name": "example", "nodes": map[string]any{"host": map[string]any{"type": "compute"}}, "accounts": map[string]any{"admin": map[string]any{"username": "admin", "node": "host", "materialization_profile": selection}}}
	raw = requireJSON(t, source)
	scenario, err := sdl.Parse(raw, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, resource := range compiled.Model().View().Resources {
		if resource.Address == "provision.account.admin" {
			if len(resource.SelectedProfiles) != 1 {
				t.Fatalf("selected profiles=%+v", resource.SelectedProfiles)
			}
			return
		}
	}
	t.Fatal("account placement missing")
}

func TestCompileSoftwareRefinementUsesExistingProfileHost(t *testing.T) {
	raw, err := os.ReadFile("../../../contracts/fixtures/plans/plan-realization-profiles-v1/valid/resource-label-authority.json")
	if err != nil {
		t.Fatal(err)
	}
	var authority map[string]any
	if checkErr := json.Unmarshal(raw, &authority); checkErr != nil {
		t.Fatal(checkErr)
	}
	definition := requireType[map[string]any](t, requireType[[]any](t, authority["definitions"])[0])["definition"]
	source := map[string]any{"name": "software", "nodes": map[string]any{"host": map[string]any{"type": "compute", "runtime": map[string]any{"software_components": []any{map[string]any{"component_id": "tool", "name": "tool", "refinements": []any{map[string]any{"refinement_id": "route", "purpose": "acquisition", "definition": definition, "profile_value": map[string]any{"name": "blue"}}}}}}}}}
	raw = requireJSON(t, source)
	scenario, err := sdl.Parse(raw, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	profile := compiled.Model().View().ProfileAuthority
	if profile == nil {
		t.Fatal("authored software profile dropped")
	}
	bindings, _ := profile.Bindings.Value()
	constraints, _ := profile.Constraints.Value()
	if len(bindings) != 1 || len(constraints) != 1 {
		t.Fatalf("software profile cover: %d bindings, %d constraints", len(bindings), len(constraints))
	}
	owner, _ := bindings[0].Owner.Value()
	address, _ := owner.CanonicalAddress.Value()
	context, _ := owner.Context.Value()
	if address != "#/resources/provision.node.host" || context != "artifact-acquisition" {
		t.Fatalf("software profile owner: %s %s", address, context)
	}
	id, _ := bindings[0].BindingId.Value()
	if id != "software-e9fabd55ed0254fe52f8a0baa1c848437abb95044806f2f4043183dab845ccaa" {
		t.Fatalf("software binding identity=%s", id)
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := realization.CompileSoftwareProfiles(instance, profile); err == nil {
		t.Fatal("duplicate software profile binding admitted")
	}
	if _, err := realization.CompileSoftwareProfiles(scenario, nil); err == nil {
		t.Fatal("authored input was treated as a concrete profile selection")
	}
}
