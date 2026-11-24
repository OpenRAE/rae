package planning_test

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func TestAcceptedDescendantsRequireLifecycleDisposition(t *testing.T) {
	baseline := compile(t, "name: example\nnodes: {host: {type: compute}, worker: {type: compute}}\n")
	initial, err := planning.PlanWithManifest(baseline, manifest(t), planning.Options{})
	requireNoError(t, err)
	snapshot, err := planning.AssumedSnapshot(initial.Plan)
	requireNoError(t, err)
	archiveRaw, err := os.ReadFile("../../../../contracts/fixtures/experiment-core/materialization-archive-record-v1/valid/reference.json")
	requireNoError(t, err)
	var archive map[string]any
	requireNoError(t, json.Unmarshal(archiveRaw, &archive))
	digest := "sha256:" + strings.Repeat("a", 64)
	archive["inventory"] = map[string]any{"contract_id": "backend-runtime-descendants-v1", "run_id": "run-1", "attempt_id": "attempt-1", "source_digest": digest, "target_scope": "target:example", "scope": "/nodes", "sequence": 1, "complete": true, "descendants": []any{map[string]any{"address": "provision.node.worker", "parent_address": "provision.node.host", "source_address": "provision.node.host", "native_identity_digest": digest, "creation": map[string]any{"run_id": "run-1", "operation_id": "operation-1", "attempt_id": "attempt-1", "evidence_digest": digest}}}}
	raw, err := json.Marshal([]any{archive})
	requireNoError(t, err)
	if err := snapshot.MaterializationAttestations.UnmarshalJSON(raw); err != nil {
		t.Fatal(err)
	}
	for _, open := range []bool{false, true} {
		source := "name: example\nnodes: {host: {type: compute}}\n"
		if open {
			source += "realization: {default: closed, scopes: [{field_pointer: /nodes, posture: open}, {field_pointer: /nodes/host, posture: closed}]}\n"
		}
		candidate := compile(t, source)
		result, err := planning.PlanWithManifest(candidate, manifest(t), planning.Options{Snapshot: &snapshot})
		requireNoError(t, err)
		checkDescendantDisposition(t, result, open)
	}
}

func checkDescendantDisposition(t *testing.T, result planning.Result, open bool) {
	t.Helper()
	if preparedOperationDeletes(result.Plan, "provision.node.worker") {
		t.Fatal("authored omission deleted an accepted descendant")
	}
	if result.Plan.Valid() != open {
		t.Fatalf("open=%v diagnostics=%+v", open, result.Diagnostics)
	}
	if !open {
		if len(result.Diagnostics) != 1 || result.Diagnostics[0].Code != "realization.descendant-collection-conflict" {
			t.Fatalf("closed collection refusal=%+v", result.Diagnostics)
		}
	}
}
