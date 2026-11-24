package planning_test

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor/planning"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestMaterializationReportingKeepsFullNativeSourceAndScope(t *testing.T) {
	compiled := compile(t, basicScenario)
	target := changeManifest(t, func(record map[string]any) {
		record["supported_contract_versions"] = append(requireType[[]any](t, record["supported_contract_versions"]), "backend-materialization-attestation-v1")
	})
	missing, err := planning.PlanWithManifest(compiled, target, planning.Options{})
	if err != nil {
		t.Fatal(err)
	}
	if missing.Plan.Valid() || len(missing.Diagnostics) != 1 || missing.Diagnostics[0].Code != "materialization.source-context-required" {
		t.Fatalf("missing source scope=%+v", missing.Diagnostics)
	}
	run := "run-1"
	result, err := planning.PlanWithManifest(compiled, target, planning.Options{Scope: &planning.Scope{RunID: &run}})
	if err != nil || !result.Plan.Valid() {
		t.Fatalf("source report plan=%+v %v", result.Diagnostics, err)
	}
	raw := field(result.Plan.Provisioning().MaterializationSource)
	var source struct {
		Snapshot     string `json:"snapshot"`
		Authored     string `json:"authored_digest"`
		Instantiated string `json:"instantiated_digest"`
		Run          string `json:"run_id"`
	}
	if checkErr := json.Unmarshal(raw, &source); checkErr != nil {
		t.Fatal(checkErr)
	}
	digest, err := sdl.CanonicalDigest(compiled.Model().View().Original)
	if err != nil {
		t.Fatal(err)
	}
	if source.Instantiated != digest || source.Authored == "" || source.Run != run || !strings.Contains(source.Snapshot, "instantiation_provenance") {
		t.Fatalf("source identity incomplete: %+v", source)
	}
	unsafeRun := "private unsafe run"
	unsafe, err := planning.PlanWithManifest(compiled, target, planning.Options{Scope: &planning.Scope{RunID: &unsafeRun}})
	if err != nil {
		t.Fatal(err)
	}
	if unsafe.Plan.Valid() || len(unsafe.Diagnostics) != 1 || unsafe.Diagnostics[0].Code != "materialization.source-context-required" || strings.Contains(unsafe.Diagnostics[0].Message, unsafeRun) {
		t.Fatalf("unsafe identity refusal=%+v", unsafe.Diagnostics)
	}
}

func TestInventoryReportingRequiresSelectedTargetScope(t *testing.T) {
	compiled := compile(t, basicScenario)
	target := changeManifest(t, func(record map[string]any) {
		record["supported_contract_versions"] = append(requireType[[]any](t, record["supported_contract_versions"]), "backend-materialization-attestation-v1", "backend-runtime-descendants-v1")
	})
	run := "run-1"
	missing, err := planning.PlanWithManifest(compiled, target, planning.Options{Scope: &planning.Scope{RunID: &run}})
	if err != nil {
		t.Fatal(err)
	}
	if missing.Plan.Valid() || len(missing.Diagnostics) != 1 || missing.Diagnostics[0].Code != "materialization.source-context-required" {
		t.Fatalf("missing target scope: %+v", missing.Diagnostics)
	}
	name := "lab"
	result, err := planning.PlanWithManifest(compiled, target, planning.Options{Scope: &planning.Scope{RunID: &run, TargetName: &name}})
	if err != nil || !result.Plan.Valid() {
		t.Fatalf("scoped source: %+v %v", result.Diagnostics, err)
	}
	var source struct {
		Target string `json:"target_scope"`
	}
	if err := json.Unmarshal(field(result.Plan.Provisioning().MaterializationSource), &source); err != nil {
		t.Fatal(err)
	}
	if source.Target != "target:lab" {
		t.Fatalf("inventory target scope=%q", source.Target)
	}
}

func TestExplicitAugmentationScopeRequiresNegotiatedReporting(t *testing.T) {
	for _, policy := range []string{"", "augmentation_scope: {default: closed}\n", "augmentation_scope: {default: open}\n"} {
		model := compile(t, "name: example\n"+policy+"nodes: {host: {type: compute}}\n")
		result, err := planning.PlanWithManifest(model, manifest(t), planning.Options{})
		requireNoError(t, err)
		if hasPlanDiagnostic(result, "augmentation.scope-unsupported") != (policy != "") {
			t.Fatalf("explicit policy=%q diagnostics=%+v", policy, result.Diagnostics)
		}
	}
}
