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

func TestOrchestratorRefusesWorkflowsAndKeepsNonWorkflowState(t *testing.T) {
	fixed := time.Date(2026, 1, 2, 3, 4, 5, 123000000, time.UTC)
	producer, err := stub.NewOrchestratorWithConfiguration(stub.Configuration{Clock: func() time.Time { return fixed }})
	if err != nil {
		t.Fatal(err)
	}
	var workflow, script binding.OrchestrationPlanV1
	var snapshot binding.RuntimeSnapshotV1
	if json.Unmarshal([]byte(`{"operations":[{"action":"create","address":"orchestration.workflow.demo","resource_type":"workflow","payload":{}}],"diagnostics":[],"startup_order":["orchestration.workflow.demo"]}`), &workflow) != nil ||
		json.Unmarshal([]byte(`{"operations":[{"action":"create","address":"orchestration.script.demo","resource_type":"script","payload":{}}],"diagnostics":[],"startup_order":["orchestration.script.demo"]}`), &script) != nil ||
		json.Unmarshal([]byte(`{"entries":{}}`), &snapshot) != nil {
		t.Fatal("fixture")
	}
	// Workflow steps run only through runtime dispatch.
	if _, refused := producer.Start(context.Background(), workflow, snapshot); refused == nil {
		t.Fatal("workflow plan started outside runtime dispatch")
	}
	result, err := producer.Start(context.Background(), script, snapshot)
	if err != nil || !result.Success {
		t.Fatal(err)
	}
	entries, _ := result.Snapshot.Entries.Value()
	var entry struct {
		Status string `json:"status"`
	}
	if json.Unmarshal(entries["orchestration.script.demo"], &entry) != nil || entry.Status != "queued" {
		t.Fatal("non-workflow orchestration resource was not installed")
	}
	stopped, err := producer.Stop(context.Background(), result.Snapshot)
	if err != nil || len(stopped.ChangedAddresses) != 1 {
		t.Fatal(stopped, err)
	}
}

// The expected responses come from the reference stub for the same dispatches.
func TestOrchestratorDispatchSimulatesOnlyTheDispatchedStep(t *testing.T) {
	producer, err := stub.NewOrchestrator()
	if err != nil {
		t.Fatal(err)
	}
	base := `"dispatch_id":"dispatch-1","program_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","root_operation_id":"operation:root","invocation_id":"invocation-1","workflow_address":"orchestration.workflow.demo","branch_id":"main","step_name":"one","attempt":1,"predecessor_revision":0`
	for _, test := range []struct{ request, response string }{
		{`{` + base + `,"step_type":"objective"}`, `{"attempt_provenance":null,"dispatch_digest":"sha256:821e99508bb10c855dd4f5189f11825a85e32a7a9a5bd71876f3f074e426da41","dispatch_id":"dispatch-1","observations":{},"outcome":"succeeded","schema_version":"workflow-step-response/v1"}`},
		{`{` + base + `,"step_type":"objective","execution_mode":"objective","objective_address":"objectives.goal","scaffold_refs":["s"],"allowed_action_families":["a"]}`, `{"attempt_provenance":{"allowed_action_families":["a"],"attempt_id":"dispatch-1","execution_mode":"objective","exposed_scaffold_refs":["s"],"objective_address":"objectives.goal","outcome":"failed","procedure_ref":"","step_name":"one"},"dispatch_digest":"sha256:e6e91a4481734710ba237dbb9ce80ac939daa997331230e168f1c7672d9fea89","dispatch_id":"dispatch-1","observations":{},"outcome":"failed","schema_version":"workflow-step-response/v1"}`},
		{`{` + base + `,"step_type":"decision"}`, `{"attempt_provenance":null,"dispatch_digest":"sha256:cf4aa2530a224ec1fd29b676e328e7a46fa74db5fa7596a4e114c99c3aa30e06","dispatch_id":"dispatch-1","observations":{},"outcome":null,"schema_version":"workflow-step-response/v1"}`},
	} {
		var request binding.WorkflowStepDispatchV1
		if json.Unmarshal([]byte(test.request), &request) != nil {
			t.Fatal("dispatch fixture")
		}
		response, err := producer.DispatchStep(context.Background(), request)
		if err != nil {
			t.Fatal(err)
		}
		var got, want any
		if json.Unmarshal(marshalTest(t, response), &got) != nil || json.Unmarshal([]byte(test.response), &want) != nil || !cmp.Equal(got, want) {
			t.Fatalf("dispatch response = %s; want %s", marshalTest(t, response), test.response)
		}
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
