package stub_test

import (
	"context"
	"encoding/json"
	"os"
	"testing"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/backend"
	"github.com/OpenRAE/rae/implementations/go/backend/stub"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
)

func TestParticipantLifecycleMatchesPythonReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/participant-lifecycle-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []lifecycleReference
	if json.Unmarshal(raw, &cases) != nil || len(cases) != 6 {
		t.Fatal("fixture")
	}
	producer, err := stub.NewParticipantRuntimeWithConfiguration(stub.Configuration{Clock: func() time.Time { return time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC) }})
	if err != nil {
		t.Fatal(err)
	}
	var snapshot binding.RuntimeSnapshotV1
	if json.Unmarshal([]byte(`{"entries":{}}`), &snapshot) != nil {
		t.Fatal("snapshot")
	}
	for _, test := range cases {
		result, err := applyReferenceLifecycle(producer, test.Action, snapshot)

		if err != nil {
			t.Fatal(err)
		}
		checkLifecycleReference(t, result, test)

		snapshot = result.Snapshot
	}
}

func TestParticipantAtomicResetRollsBackCountersAndState(t *testing.T) {
	producer, err := stub.NewParticipantRuntime()
	if err != nil {
		t.Fatal(err)
	}
	resetter, ok := producer.(backend.CoordinatedParticipantResetRuntime)
	if !ok {
		t.Fatal("atomic reset not implemented")
	}
	var snapshot binding.RuntimeSnapshotV1
	if json.Unmarshal([]byte(`{"entries":{}}`), &snapshot) != nil {
		t.Fatal("fixture")
	}
	initialized, err := producer.Initialize(context.Background(), runtimecontract.EpisodeInitializeRequest{ParticipantAddress: "participant.behavior.a"}, snapshot)
	if err != nil || !initialized.Success {
		t.Fatal(err)
	}
	failed, err := resetter.ResetMany(context.Background(), []runtimecontract.EpisodeResetRequest{{ParticipantAddress: "participant.behavior.a", Reason: "test"}, {ParticipantAddress: "participant.behavior.missing", Reason: "test"}}, initialized.Snapshot)
	if err != nil || failed.Success {
		t.Fatal("partial batch committed", err)
	}
	originalJSON := marshalTest(t, initialized.Snapshot)
	failedJSON := marshalTest(t, failed.Snapshot)
	if string(originalJSON) != string(failedJSON) {
		t.Fatal("snapshot changed on failed batch")
	}
	next, err := producer.Reset(context.Background(), runtimecontract.EpisodeResetRequest{ParticipantAddress: "participant.behavior.a", Reason: "test"}, initialized.Snapshot)
	if err != nil || !next.Success {
		t.Fatal(err)
	}
	raw := marshalTest(t, next.Snapshot)
	var result struct {
		States map[string]struct {
			EpisodeID string `json:"episode_id"`
		} `json:"participant_episode_results"`
	}
	if json.Unmarshal(raw, &result) != nil || result.States["participant.behavior.a"].EpisodeID != "participant.behavior.a-episode-2" {
		t.Fatal("failed batch spent the episode counter")
	}
}

func TestParticipantActionHistoryMatchesPythonReference(t *testing.T) {
	raw, err := os.ReadFile("../../contract/runtime/testdata/participant-binding.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Manifest  binding.ParticipantImplementationManifestV1 `json:"manifest"`
		Selection map[string]any                              `json:"selection"`
	}
	if json.Unmarshal(raw, &fixture) != nil {
		t.Fatal("binding fixture")
	}
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	selection, err := admission.AdmitFragment(owner, admission.ParticipantImplementationSelection, fixture.Selection, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	request, err := runtimecontract.BindParticipantAction(runtimecontract.ParticipantActionInput{ParticipantAddress: "participant.behavior.agent", ActionContractAddress: "participant.action-contract.scan", ObservationBoundaryAddress: "participant.observation-boundary.agent", ActionInstanceID: "action-1", StateTransitionKind: "participant_action_admitted", ImplementationManifest: fixture.Manifest, ImplementationSelection: selection})
	if err != nil {
		t.Fatal(err)
	}
	producer, err := stub.NewParticipantRuntimeWithConfiguration(stub.Configuration{Clock: func() time.Time { return time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC) }})
	if err != nil {
		t.Fatal(err)
	}
	var snapshot binding.RuntimeSnapshotV1
	if json.Unmarshal([]byte(`{"entries":{}}`), &snapshot) != nil {
		t.Fatal("snapshot")
	}
	initialized, err := producer.Initialize(context.Background(), runtimecontract.EpisodeInitializeRequest{ParticipantAddress: "participant.behavior.agent"}, snapshot)
	if err != nil {
		t.Fatal(err)
	}
	result, err := producer.AdmitAction(context.Background(), request, initialized.Snapshot)
	if err != nil || !result.Success {
		t.Fatal(result, err)
	}
	raw = marshalTest(t, result.Snapshot)
	var actual map[string]any
	if json.Unmarshal(raw, &actual) != nil {
		t.Fatal("output")
	}
	raw, err = os.ReadFile("testdata/participant-action-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var expected any
	if json.Unmarshal(raw, &expected) != nil {
		t.Fatal("reference")
	}
	if !cmp.Equal(actual["participant_behavior_history"], expected) {
		t.Fatalf("history differs: %+v", actual["participant_behavior_history"])
	}
}

func applyReferenceLifecycle(producer stub.ParticipantRuntime, action string, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	var result runtimecontract.ApplyResult
	var err error
	switch action {
	case "initialize":
		result, err = producer.Initialize(context.Background(), runtimecontract.EpisodeInitializeRequest{ParticipantAddress: "participant.behavior.agent"}, snapshot)
	case "reset":
		result, err = producer.Reset(context.Background(), runtimecontract.EpisodeResetRequest{ParticipantAddress: "participant.behavior.agent", Reason: "reset by operator"}, snapshot)
	case "restart":
		result, err = producer.Restart(context.Background(), runtimecontract.EpisodeRestartRequest{ParticipantAddress: "participant.behavior.agent", Reason: "restarted by operator"}, snapshot)
	case "terminate":
		result, err = producer.Terminate(context.Background(), runtimecontract.EpisodeTerminateRequest{ParticipantAddress: "participant.behavior.agent", TerminalReason: "completed", Detail: "terminated by operator"}, snapshot)
	}
	return result, err
}

type lifecycleReference struct {
	Action   string   `json:"action"`
	Success  bool     `json:"success"`
	States   any      `json:"states"`
	History  any      `json:"history"`
	Messages []string `json:"messages"`
}

func checkLifecycleReference(t *testing.T, result runtimecontract.ApplyResult, test lifecycleReference) {
	t.Helper()
	if result.Success != test.Success {
		t.Fatal(test.Action, result)
	}
	raw, err := json.Marshal(result.Snapshot)
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]any
	if json.Unmarshal(raw, &decoded) != nil {
		t.Fatal("output")
	}
	if !cmp.Equal(decoded["participant_episode_results"], test.States) || !cmp.Equal(decoded["participant_episode_history"], test.History) {
		t.Fatalf("%s differs: %s", test.Action, raw)
	}
	messages := []string{}
	for _, finding := range result.Diagnostics {
		messages = append(messages, finding.Message)
	}
	if !cmp.Equal(messages, test.Messages) {
		t.Fatalf("%s messages %v want %v", test.Action, messages, test.Messages)
	}
}

func TestParticipantCorruptStateRefusalDoesNotExposePayload(t *testing.T) {
	producer, err := stub.NewParticipantRuntime()
	if err != nil {
		t.Fatal(err)
	}
	var snapshot binding.RuntimeSnapshotV1
	raw := []byte(`{"entries":{},"participant_episode_results":{"participant.behavior.agent":{"untrusted":"private-state-sentinel"}}}`)
	if json.Unmarshal(raw, &snapshot) != nil {
		t.Fatal("fixture")
	}
	result, err := producer.Reset(context.Background(), runtimecontract.EpisodeResetRequest{ParticipantAddress: "participant.behavior.agent"}, snapshot)
	if err != nil || result.Success || len(result.Diagnostics) != 1 {
		t.Fatal("corrupt state not refused", err)
	}
	if result.Diagnostics[0].Message != "current state is invalid" {
		t.Fatal("unsafe refusal", result.Diagnostics[0].Message)
	}
	if diff := cmp.Diff(marshalTest(t, snapshot), marshalTest(t, result.Snapshot)); diff != "" {
		t.Fatal("refusal changed predecessor", diff)
	}
}
