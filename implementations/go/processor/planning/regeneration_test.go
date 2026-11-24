package planning_test

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

const scopedRandomValueSource = `name: example
nodes:
  host: {type: compute}
generated_artifacts:
  flag:
    generator: random_value
    lifecycle: reuse_valid
    provenance: test
    regeneration_scope: per_run
    random_value: {alphabet: hex_lower, length: 32}
    outputs: [{name: flag, path: flag.txt, sensitivity: secret}]
    consumers: [{node: host, mount_destination: /srv/flag, access_mode: read_only, selected_outputs: [flag]}]
`

func TestRandomValuesReconcileAgainstAuthoritativeScope(t *testing.T) {
	compiled := compile(t, scopedRandomValueSource)
	target := changeManifest(t, func(record map[string]any) {
		requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])["supported_generated_artifact_kinds"] = []string{"random_value"}
		requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])["supported_regeneration_scopes"] = []string{"once", "per_run", "per_instantiation"}
	})
	run := "run-1"
	unsupported, err := planning.PlanWithManifest(compiled, manifest(t), planning.Options{Scope: &planning.Scope{RunID: &run}})
	requireNoError(t, err)
	if !hasPlanDiagnostic(unsupported, "provisioner.unsupported-generated-artifact-kind") {
		t.Fatalf("unsupported random-value generator accepted: %+v", unsupported.Diagnostics)
	}
	missing, err := planning.PlanWithManifest(compiled, target, planning.Options{})
	requireNoError(t, err)
	if !hasPlanDiagnostic(missing, "provisioner.missing-regeneration-scope-identity") || missing.Plan.Valid() {
		t.Fatalf("missing run scope accepted: %+v", missing.Diagnostics)
	}
	first, err := planning.PlanWithManifest(compiled, target, planning.Options{Scope: &planning.Scope{RunID: &run}})
	requireNoError(t, err)
	if !first.Plan.Valid() {
		t.Fatalf("first plan: %+v %v", first.Diagnostics, err)
	}
	operations := field(first.Plan.Provisioning().Operations)
	artifactIndex := -1
	for i, operation := range operations {
		if field(operation.Address) == "provision.generated-artifact.flag" {
			artifactIndex = i
		}
	}
	if artifactIndex < 0 {
		t.Fatal("artifact missing")
	}
	var scopeBinding string
	requireNoError(t, json.Unmarshal(field(operations[artifactIndex].Payload)["scope_binding"], &scopeBinding))
	if scopeBinding != "run:run-1" {
		t.Fatalf("scope binding=%q", scopeBinding)
	}
	snapshot, err := planning.AssumedSnapshot(first.Plan)
	requireNoError(t, err)
	for _, value := range []string{"run-1", "run-2"} {
		next, err := planning.PlanWithManifest(compiled, target, planning.Options{Scope: &planning.Scope{RunID: &value}, Snapshot: &snapshot})
		requireNoError(t, err)
		if !next.Plan.Valid() {
			t.Fatalf("next plan: %+v %v", next.Diagnostics, err)
		}
		want := map[string]string{"run-1": "unchanged", "run-2": "update"}[value]
		operations = field(next.Plan.Provisioning().Operations)
		if field(operations[artifactIndex].Action) != want {
			t.Fatalf("run %s action=%s", value, field(operations[artifactIndex].Action))
		}
	}
}

func TestRandomValueOnceAndInstantiationScopesKeepTheirOwnIdentity(t *testing.T) {
	target := changeManifest(t, func(record map[string]any) {
		provisioner := requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])
		provisioner["supported_generated_artifact_kinds"] = []string{"random_value"}
		provisioner["supported_regeneration_scopes"] = []string{"once", "per_run", "per_instantiation"}
	})
	for _, scopeName := range []string{"once", "per_instantiation"} {
		t.Run(scopeName, func(t *testing.T) {
			checkRandomScopeIdentity(t, target, scopeName)
		})
	}
}

func checkRandomScopeIdentity(t *testing.T, target binding.BackendManifestV2, scopeName string) {
	t.Helper()
	compiled := compile(t, strings.ReplaceAll(scopedRandomValueSource, "per_run", scopeName))
	missing, err := planning.PlanWithManifest(compiled, target, planning.Options{})
	requireNoError(t, err)
	if hasPlanDiagnostic(missing, "provisioner.missing-regeneration-scope-identity") != (scopeName == "per_instantiation") {
		t.Fatalf("scope identity requirement: %+v", missing.Diagnostics)
	}
	firstID := "instance-1"
	first, err := planning.PlanWithManifest(compiled, target, planning.Options{Scope: &planning.Scope{InstantiationID: &firstID, RunID: &firstID}})
	requireNoError(t, err)
	if !first.Plan.Valid() {
		t.Fatalf("invalid first scoped plan: %+v", first.Diagnostics)
	}
	snapshot, err := planning.AssumedSnapshot(first.Plan)
	requireNoError(t, err)
	for _, nextID := range []string{"instance-1", "instance-2"} {
		next, err := planning.PlanWithManifest(compiled, target, planning.Options{Snapshot: &snapshot, Scope: &planning.Scope{InstantiationID: &nextID, RunID: &nextID}})
		requireNoError(t, err)
		want := "unchanged"
		if scopeName == "per_instantiation" && nextID != firstID {
			want = "update"
		}
		if !next.Plan.Valid() || randomArtifactAction(t, next.Plan) != want {
			t.Fatalf("scope=%s identity=%s want=%s findings=%+v", scopeName, nextID, want, next.Diagnostics)
		}
	}
}

func randomArtifactAction(t *testing.T, plan planning.ExecutionPlan) string {
	t.Helper()
	for _, operation := range field(plan.Provisioning().Operations) {
		if field(operation.Address) == "provision.generated-artifact.flag" {
			return field(operation.Action)
		}
	}
	t.Fatal("random artifact missing")
	return ""
}

func hasPlanDiagnostic(result planning.Result, code string) bool {
	for _, finding := range result.Diagnostics {
		if finding.Code == code {
			return true
		}
	}
	return false
}
