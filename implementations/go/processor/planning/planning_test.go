package planning_test

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func compile(t *testing.T, raw string) processor.Compilation {
	t.Helper()
	scenario, err := sdl.Parse([]byte(raw), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	result, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	return result
}
func manifest(t *testing.T) binding.BackendManifestV2 {
	t.Helper()
	raw, err := os.ReadFile("../../../../contracts/fixtures/backend-manifest/backend-manifest-v2/valid/stub.json")
	if err != nil {
		t.Fatal(err)
	}
	var result binding.BackendManifestV2
	if err := json.Unmarshal(raw, &result); err != nil {
		t.Fatal(err)
	}
	return result
}

//nolint:ireturn // Each generated instantiation returns its concrete transport type without a runtime interface.
func field[T any](input binding.Field[T]) T { result, _ := input.Value(); return result }

const basicScenario = "name: example\nnodes:\n  lan: {type: switch}\n  server: {type: compute}\ninfrastructure:\n  lan: {}\n  server: {links: [lan]}\n"

func TestPlanOrdersDependenciesAndOwnsProjections(t *testing.T) {
	compiled := compile(t, basicScenario)
	result, err := planning.PlanWithManifest(compiled, manifest(t), planning.Options{})
	if err != nil {
		t.Fatal(err)
	}
	if !result.Plan.Valid() {
		t.Fatalf("invalid basic plan: %+v", result.Diagnostics)
	}
	ops := field(result.Plan.Provisioning().Operations)
	if len(ops) != 2 || field(ops[0].Address) != "provision.network.lan" || field(ops[1].Address) != "provision.node.server" || field(ops[1].Action) != "create" {
		t.Fatalf("operations=%+v", ops)
	}
	field(ops[0].Payload)["changed"] = json.RawMessage(`true`)
	got := field(result.Plan.Provisioning().Operations)
	if _, present := field(got[0].Payload)["changed"]; present {
		t.Fatal("caller changed owned plan")
	}
	snapshot, err := planning.AssumedSnapshot(result.Plan)
	if err != nil {
		t.Fatal(err)
	}
	entries := field(snapshot.Entries)
	if len(entries) != 2 {
		t.Fatalf("snapshot entries=%d", len(entries))
	}
	var entry struct {
		Status string `json:"status"`
	}
	if json.Unmarshal(entries["provision.node.server"], &entry) != nil || entry.Status != "planned-state-projection" {
		t.Fatalf("snapshot status=%s", entry.Status)
	}
	replanned, err := planning.PlanWithManifest(compiled, manifest(t), planning.Options{Snapshot: &snapshot})
	if err != nil {
		t.Fatal(err)
	}
	for _, operation := range field(replanned.Plan.Provisioning().Operations) {
		if field(operation.Action) != "unchanged" {
			t.Fatalf("same model changed: %+v", operation)
		}
	}
	if _, err := planning.AssumedSnapshot(replanned.Plan); err == nil {
		t.Fatal("nonempty-base projection accepted")
	}
}

func TestReconcileRefreshesDependentsAndDeletesInReverseOrder(t *testing.T) {
	baseline := compile(t, basicScenario)
	candidate := compile(t, strings.Replace(basicScenario, "lan: {type: switch}", "lan: {type: switch, description: changed}", 1))
	result, err := planning.Reconcile(baseline, candidate, manifest(t), planning.Options{})
	if err != nil {
		t.Fatal(err)
	}
	if result.Actions == nil || result.Actions.Update != 2 || result.Actions.Unchanged != 0 {
		t.Fatalf("refresh actions=%+v", result.Actions)
	}
	empty := compile(t, "name: empty\n")
	removed, err := planning.Reconcile(baseline, empty, manifest(t), planning.Options{})
	if err != nil {
		t.Fatal(err)
	}
	ops := field(removed.Candidate.Plan.Provisioning().Operations)
	if removed.Actions == nil || removed.Actions.Delete != 2 || len(ops) != 2 || field(ops[0].Address) != "provision.node.server" || field(ops[1].Address) != "provision.network.lan" {
		t.Fatalf("delete order=%+v", ops)
	}
}

func TestRejectedBaselineHasNoCandidateActionReport(t *testing.T) {
	baseline := compile(t, "name: cycle\nnodes:\n  a: {type: compute}\n  b: {type: compute}\ninfrastructure:\n  a: {dependencies: [b]}\n  b: {dependencies: [a]}\n")
	result, err := planning.Reconcile(baseline, nil, manifest(t), planning.Options{})
	if err != nil {
		t.Fatal(err)
	}
	if result.Baseline.Plan.Valid() || result.Candidate.Plan != nil || result.Actions != nil {
		t.Fatal("rejected baseline acquired a candidate action report")
	}
	if _, err := planning.AssumedSnapshot(result.Baseline.Plan); err == nil {
		t.Fatal("invalid plan acquired assumed state")
	}
}

type replacedPlan struct{ planning.ExecutionPlan }

func (replacedPlan) Valid() bool { panic("foreign plan called") }
func TestPlannerRefusesForeignOwners(t *testing.T) {
	if _, err := planning.AssumedSnapshot(replacedPlan{}); err == nil {
		t.Fatal("foreign plan accepted")
	}
	if _, err := planning.PlanWithManifest(nil, manifest(t), planning.Options{}); err == nil {
		t.Fatal("foreign compilation accepted")
	}
}
