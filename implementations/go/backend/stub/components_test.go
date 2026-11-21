package stub_test

import (
	"context"
	"encoding/json"
	"os"
	"testing"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/backend/stub"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestProvisionerPreservesDomainsAndUnchangedWrites(t *testing.T) {
	producer, err := stub.NewProvisioner()
	if err != nil {
		t.Fatal(err)
	}
	var plan binding.ProvisioningPlanV1
	var snapshot binding.RuntimeSnapshotV1
	if json.Unmarshal([]byte(`{"operations":[{"action":"create","address":"provision.node.vm","resource_type":"node","payload":{"secret_ref":"secret:logical"}},{"action":"unchanged","address":"provision.node.base","resource_type":"node","payload":{}}],"diagnostics":[],"realization_constraints":[],"realization_authority":[],"observation_demands":[]}`), &plan) != nil || json.Unmarshal([]byte(`{"entries":{},"metadata":{"keep":true}}`), &snapshot) != nil {
		t.Fatal("fixture")
	}
	result, err := producer.Apply(context.Background(), plan, snapshot)
	if err != nil || !result.Success {
		t.Fatal(result, err)
	}
	if len(result.ChangedAddresses) != 1 || result.ChangedAddresses[0] != "provision.node.vm" {
		t.Fatal(result.ChangedAddresses)
	}
	entries, _ := result.Snapshot.Entries.Value()
	var entry struct {
		Status string `json:"status"`
	}
	if json.Unmarshal(entries["provision.node.base"], &entry) != nil {
		t.Fatal("entry")
	}
	unchanged := entry.Status
	if unchanged != "unchanged" {
		t.Fatal("unchanged operation was skipped")
	}
	original, _ := snapshot.Entries.Value()
	if len(original) != 0 {
		t.Fatal("predecessor mutated")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := producer.Apply(ctx, plan, snapshot); err == nil {
		t.Fatal("cancelled call applied")
	}
}

func TestOrchestratorFixedClockAndReadbackIsolation(t *testing.T) {
	fixed := time.Date(2026, 1, 2, 3, 4, 5, 123000000, time.UTC)
	producer, err := stub.NewOrchestratorWithConfiguration(stub.Configuration{Clock: func() time.Time { return fixed }})
	if err != nil {
		t.Fatal(err)
	}
	var plan binding.OrchestrationPlanV1
	var snapshot binding.RuntimeSnapshotV1
	if json.Unmarshal([]byte(`{"operations":[{"action":"create","address":"orchestration.workflow.demo","resource_type":"workflow","payload":{"result_contract":{"observable_steps":{"one":{}}},"execution_contract":{"start_step":"one"}}}],"diagnostics":[],"startup_order":["orchestration.workflow.demo"]}`), &plan) != nil || json.Unmarshal([]byte(`{"entries":{}}`), &snapshot) != nil {
		t.Fatal("fixture")
	}
	result, err := producer.Start(context.Background(), plan, snapshot)
	if err != nil || !result.Success {
		t.Fatal(err)
	}
	results, err := producer.Results(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if results["orchestration.workflow.demo"]["started_at"] != "2026-01-02T03:04:05.123000Z" {
		t.Fatal(results)
	}
	results["orchestration.workflow.demo"]["workflow_status"] = "corrupt"
	again, err := producer.Results(context.Background())
	if err != nil || again["orchestration.workflow.demo"]["workflow_status"] != "running" {
		t.Fatal("retained state alias")
	}
	stopped, err := producer.Stop(context.Background(), result.Snapshot)
	if err != nil || len(stopped.ChangedAddresses) != 1 {
		t.Fatal(stopped, err)
	}
}

func TestProvisionerAdmitsEnvelopeAndRefusesIdentitySwap(t *testing.T) {
	envelope, identity := provisionerEnvelopeFixture(t)
	producer, err := stub.NewProvisionerWithConfiguration(stub.Configuration{Envelope: &envelope})
	if err != nil {
		t.Fatal(err)
	}
	planDocument := map[string]any{"operations": []any{map[string]any{"action": "create", "address": "provision.node.web", "resource_type": "node", "payload": map[string]any{}}}, "diagnostics": []any{}, "realization_constraints": []any{map[string]any{"address": "provision.node.web", "field_path": "nodes.web.realization.compute-substrate", "concern": "compute-substrate", "posture": "open", "governing_scope": "#/nodes/web", "provenance": "author-declared"}}, "realization_authority": []any{}, "observation_demands": []any{}}
	var plan binding.ProvisioningPlanV1
	if json.Unmarshal(marshalTest(t, planDocument), &plan) != nil {
		t.Fatal("plan")
	}
	refused, err := producer.Apply(context.Background(), plan, binding.RuntimeSnapshotV1{})
	if err != nil || refused.Success || len(refused.Diagnostics) != 1 {
		t.Fatal("missing identity not refused", err)
	}
	planDocument["operation_id"] = "operation:test"
	planDocument["realization_envelope"] = identity
	if json.Unmarshal(marshalTest(t, planDocument), &plan) != nil {
		t.Fatal("bound plan")
	}
	// Mutation after construction cannot change the selected apparatus.
	if envelope.Digest.UnmarshalJSON([]byte(`"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"`)) != nil {
		t.Fatal("digest")
	}
	applied, err := producer.Apply(context.Background(), plan, binding.RuntimeSnapshotV1{})
	if err != nil || !applied.Success {
		t.Fatal("bound apply", err)
	}
	if len(applied.OperationalRealizationObservations) != 0 {
		t.Fatal("stub manufactured independent evidence")
	}
	identity["digest"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	if json.Unmarshal(marshalTest(t, planDocument), &plan) != nil {
		t.Fatal("swapped plan")
	}
	swapped, err := producer.Apply(context.Background(), plan, applied.Snapshot)
	if err != nil || swapped.Success {
		t.Fatal("identity swap accepted", err)
	}
	if diff := cmp.Diff(marshalTest(t, applied.Snapshot), marshalTest(t, swapped.Snapshot)); diff != "" {
		t.Fatal("refusal changed predecessor", diff)
	}
}

func TestStopKeepsTheEstablishedOperationOrder(t *testing.T) {
	producer, err := stub.NewOrchestrator()
	if err != nil {
		t.Fatal(err)
	}
	var plan binding.OrchestrationPlanV1
	if json.Unmarshal([]byte(`{"operations":[{"action":"create","address":"orchestration.script.z","resource_type":"script","payload":{}},{"action":"create","address":"orchestration.script.a","resource_type":"script","payload":{}}],"startup_order":[],"diagnostics":[]}`), &plan) != nil {
		t.Fatal("plan")
	}
	started, err := producer.Start(context.Background(), plan, binding.RuntimeSnapshotV1{})
	if err != nil {
		t.Fatal(err)
	}
	stopped, err := producer.Stop(context.Background(), started.Snapshot)
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff([]string{"orchestration.script.z", "orchestration.script.a"}, stopped.ChangedAddresses); diff != "" {
		t.Fatal(diff)
	}
}

func provisionerEnvelopeFixture(t *testing.T) (binding.RealizationEnvelopeV1, map[string]any) {
	t.Helper()
	raw, err := os.ReadFile("../../../../contracts/realization-envelopes/reference-emulation/in-process-v1.json")
	if err != nil {
		t.Fatal(err)
	}
	var envelope binding.RealizationEnvelopeV1
	if json.Unmarshal(raw, &envelope) != nil {
		t.Fatal("envelope")
	}

	var document map[string]any
	if json.Unmarshal(raw, &document) != nil {
		t.Fatal("document")
	}
	configuration, ok := document["configuration"].(map[string]any)
	if !ok {
		t.Fatal("configuration")
	}
	identity := map[string]any{"contract_id": document["contract_id"], "schema_version": document["schema_version"], "envelope_id": document["id"], "digest": document["digest"], "configuration_digest": configuration["configuration_digest"]}
	return envelope, identity
}
