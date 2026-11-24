package planning_test

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func changeManifest(t *testing.T, apply func(map[string]any)) binding.BackendManifestV2 {
	t.Helper()
	raw, err := json.Marshal(manifest(t))
	if err != nil {
		t.Fatal(err)
	}
	var record map[string]any
	if checkErr := json.Unmarshal(raw, &record); checkErr != nil {
		t.Fatal(checkErr)
	}
	apply(record)
	raw, err = json.Marshal(record)
	if err != nil {
		t.Fatal(err)
	}
	var result binding.BackendManifestV2
	if err := json.Unmarshal(raw, &result); err != nil {
		t.Fatal(err)
	}
	return result
}
func TestManifestCapabilityChecksRetainResourceOrder(t *testing.T) {
	compiled := compile(t, "name: example\nnodes:\n  lan: {type: switch}\n  server: {type: compute, os: linux, architecture: amd64}\ninfrastructure:\n  lan: {}\n  server: {}\n")
	target := changeManifest(t, func(record map[string]any) {
		provisioner := requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])
		provisioner["supported_node_types"] = []any{"switch"}
		provisioner["supported_os_families"] = []any{"windows"}
		provisioner["supported_node_architectures"] = []any{}
		provisioner["max_total_nodes"] = 1
	})
	result, err := planning.PlanWithManifest(compiled, target, planning.Options{})
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"provisioner.unsupported-node-type", "provisioner.unsupported-os-family", "provisioner.unsupported-operating-system", "provisioner.unsupported-node-architecture", "provisioner.max-total-nodes-exceeded"}
	filtered := result.Diagnostics[:0]
	for _, d := range result.Diagnostics {
		if d.Domain == "provisioning" {
			filtered = append(filtered, d)
		}
	}
	result.Diagnostics = filtered
	if len(result.Diagnostics) != len(want) {
		t.Fatalf("diagnostics=%+v", result.Diagnostics)
	}
	for i, code := range want {
		if result.Diagnostics[i].Code != code {
			t.Fatalf("diagnostic %d=%+v", i, result.Diagnostics[i])
		}
	}
	if result.Plan.Valid() {
		t.Fatal("unsupported target accepted")
	}
}
func TestCoupledOperatingSystemRowsCannotBeCrossCombined(t *testing.T) {
	compiled := compile(t, "name: example\nnodes:\n  server: {type: compute, os: linux, os_distribution: ubuntu, os_version: '24.04'}\n")
	for _, supported := range []bool{false, true} {
		target := changeManifest(t, func(record map[string]any) {
			provisioner := requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])
			version := "22.04"
			if supported {
				version = "24.04"
			}
			provisioner["operating_systems"] = []any{map[string]any{"family": "linux", "distribution": "ubuntu", "versions": []any{version}}, map[string]any{"family": "linux", "distribution": "debian", "versions": []any{"24.04"}}}
		})
		result, err := planning.PlanWithManifest(compiled, target, planning.Options{})
		if err != nil {
			t.Fatal(err)
		}
		found := false
		for _, d := range result.Diagnostics {
			if d.Code == "provisioner.unsupported-operating-system" {
				found = true
			}
		}
		if found == supported {
			t.Fatalf("supported=%v diagnostics=%+v", supported, result.Diagnostics)
		}
	}
}

func TestTimeModelRequiresDeclaredTargetCapability(t *testing.T) {
	compiled := compile(t, `name: example
time_domains:
  scenario: {kind: simulated, epoch: scenario_start, tick_period_seconds: {numerator: 1, denominator: 1}, description: scenario}
`)
	result, err := planning.PlanWithManifest(compiled, manifest(t), planning.Options{})
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, d := range result.Diagnostics {
		if d.Code == "time.unsupported-capability" && d.Address == "time.model" {
			found = true
		}
	}
	if !found {
		t.Fatalf("time capability gap omitted: %+v", result.Diagnostics)
	}
}

func TestPlacementCapabilityChecksUseNativeResourceKinds(t *testing.T) {
	compiled := compile(t, `name: example
nodes:
  server: {type: compute}
content:
  page: {type: file, target: server, path: /srv/page}
accounts:
  user: {node: server, username: example}
`)
	target := changeManifest(t, func(record map[string]any) {
		caps := requireType[map[string]any](t, requireType[map[string]any](t, record["capabilities"])["provisioner"])
		caps["supports_accounts"] = false
		caps["supported_account_features"] = []any{}
		caps["supported_content_types"] = []any{}
	})
	result, err := planning.PlanWithManifest(compiled, target, planning.Options{})
	if err != nil {
		t.Fatal(err)
	}
	found := []string{}
	for _, d := range result.Diagnostics {
		if d.Domain == "provisioning" {
			found = append(found, d.Code)
		}
	}
	if len(found) != 2 || found[0] != "provisioner.unsupported-content-type" || found[1] != "provisioner.accounts-unsupported" {
		t.Fatalf("placement checks=%v", found)
	}
}
