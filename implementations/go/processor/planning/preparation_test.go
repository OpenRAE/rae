package planning_test

import (
	"encoding/json"
	"io/fs"
	"os"
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func TestPreparationManifestCommitmentKeepsReferenceNormalization(t *testing.T) {
	checkManifestCommitments(t, "autonomous-support.json")
	checkManifestCommitments(t, "autonomous-v3-support.json")
}
func checkManifestCommitments(t *testing.T, path string) {
	t.Helper()
	raw, err := fs.ReadFile(os.DirFS("../testdata"), path)
	requireNoError(t, err)
	var cases []struct {
		Name     string                    `json:"name"`
		Manifest binding.BackendManifestV2 `json:"manifest"`
		Digest   string                    `json:"manifest_digest"`
	}
	requireNoError(t, json.Unmarshal(raw, &cases))
	owner, err := admission.New()
	requireNoError(t, err)
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			normalized, err := admission.NormalizeBackendManifest(owner, test.Manifest)
			requireNoError(t, err)
			canonical, err := canonjson.JCS(requireJSON(t, normalized))
			requireNoError(t, err)
			if got := digest.SHA256(canonical); got != test.Digest {
				t.Fatalf("manifest commitment %s want %s", got, test.Digest)
			}
		})
	}
}

func TestNegotiatedOpenNodeCollectionRetainsExistingMembers(t *testing.T) {
	baseline := compile(t, "name: example\nnodes: {host: {type: compute}, worker: {type: compute}}\n")
	initial, err := planning.PlanWithManifest(baseline, manifest(t), planning.Options{})
	requireNoError(t, err)
	snapshot, err := planning.AssumedSnapshot(initial.Plan)
	requireNoError(t, err)
	target := changeManifest(t, func(record map[string]any) {
		versions := requireType[[]any](t, record["supported_contract_versions"])
		record["supported_contract_versions"] = append(versions, "backend-realization-preparation-v1")
	})
	for _, open := range []bool{false, true} {
		t.Run(map[bool]string{false: "closed", true: "open"}[open], func(t *testing.T) {
			source := "name: example\nnodes: {host: {type: compute}}\n"
			if open {
				source += "realization: {default: closed, scopes: [{field_pointer: /nodes, posture: open}, {field_pointer: /nodes/host, posture: closed}]}\n"
			}
			result, err := planning.PlanWithManifest(compile(t, source), target, planning.Options{Snapshot: &snapshot})
			requireNoError(t, err)
			if !result.Plan.Valid() {
				t.Fatalf("node collection diagnostics=%+v", result.Diagnostics)
			}
			checkPreparedAuthority(t, result.Plan)
			removed := preparedOperationDeletes(result.Plan, "provision.node.worker")
			if removed == open {
				t.Fatalf("open=%v removed=%v", open, removed)
			}
		})
	}
	if slices.Contains(field(manifest(t).SupportedContractVersions), "backend-realization-preparation-v1") {
		t.Fatal("fixture unexpectedly negotiates preparation")
	}
}

func checkPreparedAuthority(t *testing.T, plan planning.ExecutionPlan) {
	t.Helper()
	var authority struct {
		Contract   string          `json:"contract_id"`
		Digest     string          `json:"manifest_digest"`
		Collection json.RawMessage `json:"node_collection"`
	}
	requireNoError(t, json.Unmarshal(field(plan.Provisioning().Preparation), &authority))
	if authority.Contract != "backend-realization-preparation-v1" || authority.Digest == "" || len(authority.Collection) == 0 {
		t.Fatal("missing negotiated preparation authority")
	}
}

func preparedOperationDeletes(plan planning.ExecutionPlan, address string) bool {
	for _, operation := range field(plan.Provisioning().Operations) {
		if field(operation.Address) == address {
			return field(operation.Action) == "delete"
		}
	}
	return false
}
