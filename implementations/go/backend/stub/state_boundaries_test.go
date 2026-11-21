package stub

import (
	"context"
	"encoding/json"
	"maps"
	"math/big"
	"os"
	"slices"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func TestParticipantBatchResetCommitsTogether(t *testing.T) {
	role, err := NewParticipantRuntime()
	if err != nil {
		t.Fatal(err)
	}
	p, ok := role.(*participant)
	if !ok {
		t.Fatal("unexpected participant implementation")
	}
	ctx := context.Background()
	snapshot := binding.RuntimeSnapshotV1{}
	requests := []runtimecontract.EpisodeResetRequest{{ParticipantAddress: "participant.behavior.a"}, {ParticipantAddress: "participant.behavior.b"}}
	for _, request := range requests {
		result, initializeErr := p.Initialize(ctx, runtimecontract.EpisodeInitializeRequest{ParticipantAddress: request.ParticipantAddress}, snapshot)
		if initializeErr != nil || !result.Success {
			t.Fatal(result, initializeErr)
		}
		snapshot = result.Snapshot
	}
	result, err := p.ResetMany(ctx, requests, snapshot)
	if err != nil || !result.Success || !slices.Equal(result.ChangedAddresses, []string{"participant.behavior.a", "participant.behavior.b"}) {
		t.Fatal(result, err)
	}
	for _, address := range result.ChangedAddresses {
		if p.results[address]["episode_id"] != address+"-episode-2" || len(p.history[address]) != 4 {
			t.Fatal("batch did not commit matching state/history", p.results, p.history)
		}
	}
	checkResetBatchRefusals(t, p, result.Snapshot, requests)
}

func checkResetBatchRefusals(t *testing.T, p *participant, snapshot binding.RuntimeSnapshotV1, requests []runtimecontract.EpisodeResetRequest) {
	t.Helper()
	ctx := context.Background()
	noop, err := p.ResetMany(ctx, nil, snapshot)
	if err != nil || !noop.Success || len(noop.ChangedAddresses) != 0 {
		t.Fatal(noop, err)
	}
	duplicate, err := p.ResetMany(ctx, []runtimecontract.EpisodeResetRequest{requests[0], requests[0]}, snapshot)
	if err != nil || duplicate.Success || len(duplicate.Diagnostics) != 1 {
		t.Fatal("duplicate batch accepted", err)
	}
	if _, limitErr := p.ResetMany(ctx, make([]runtimecontract.EpisodeResetRequest, value.Runtime().MaxMembers+1), snapshot); limitErr == nil {
		t.Fatal("oversized reset accepted")
	}
	if _, contextErr := p.ResetMany(nil, requests, snapshot); contextErr == nil { //nolint:staticcheck // Nil context is deliberate invalid input.
		t.Fatal("nil context accepted")
	}
	status, err := p.Status(ctx)
	if err != nil || status["participants"] != 2 || status["running"] != 2 {
		t.Fatal("participant status disagrees with committed batch", status, err)
	}
}

func TestParticipantGenerationFenceAndNativeOutcome(t *testing.T) {
	raw, err := os.ReadFile("../../../../contracts/fixtures/participant-runtime/participant-execution-service-state-v1/valid/running-ready.json")
	if err != nil {
		t.Fatal(err)
	}
	var service map[string]any
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.UseNumber()
	if decodeErr := decoder.Decode(&service); decodeErr != nil {
		t.Fatal(decodeErr)
	}
	scope, generation := "execution-scopes/red-operator-v1", int64(5)
	input := runtimecontract.ParticipantActionInput{ParticipantAddress: "participant.behavior.agent", ExecutionScopeRef: &scope, ExecutionGeneration: &generation}
	for _, test := range []struct {
		name    string
		change  func(map[string]any)
		want    string
		invalid bool
	}{
		{"ready", func(map[string]any) {}, "", false},
		{"stale", func(v map[string]any) { v["observed_generation"] = json.Number("4") }, "execution generation changed", false},
		{"not-accepting", func(v map[string]any) { v["accepting_new_work"] = false }, "execution service is not accepting work", false},
		{"malformed", func(v map[string]any) { delete(v, "generation") }, "", true},
	} {
		t.Run(test.name, func(t *testing.T) {
			candidate := maps.Clone(service)
			test.change(candidate)
			reason, refusalErr := generationRefusal(input, map[string]any{"participant_execution_services": map[string]any{scope: candidate}})
			if (refusalErr != nil) != test.invalid || reason != test.want {
				t.Fatal(reason, err)
			}
		})
	}
	if reason, missingErr := generationRefusal(input, nil); missingErr != nil || reason != "execution-service state is missing" {
		t.Fatal(reason, missingErr)
	}
	checkNativeActionPreconditions(t, input)
}

func checkNativeActionPreconditions(t *testing.T, input runtimecontract.ParticipantActionInput) {
	t.Helper()
	p := &participant{component: newComponent("participant_episode", nil)}
	state, _, err := runningEpisode(episodeCommand{action: termInitialize, address: input.ParticipantAddress}, nil, map[string]*big.Int{}, "2026-01-02T03:04:05Z")
	if err != nil {
		t.Fatal(err)
	}
	snapshot := map[string]any{"participant_episode_results": map[string]any{input.ParticipantAddress: state}}
	refusal, refused, err := actionPrecondition(input, snapshot, binding.RuntimeSnapshotV1{})
	if err != nil || !refused || refusal.Diagnostics[0].Code != "runtime.participant-execution-stale-work" {
		t.Fatal(refusal, err)
	}
	input.ExecutionScopeRef, input.ExecutionGeneration = nil, nil
	input.RequiresTerminalOutcome = true
	refusal, refused, err = actionPrecondition(input, snapshot, binding.RuntimeSnapshotV1{})
	if err != nil || !refused || refusal.Diagnostics[0].Code != "runtime.participant-autonomous-native-outcome-missing" {
		t.Fatal(refusal, err)
	}
	checkNativeOutcomes(t, input, snapshot, state)
	if _, err := p.AdmitAction(context.Background(), nil, binding.RuntimeSnapshotV1{}); err == nil {
		t.Fatal("foreign action accepted")
	}
}

func checkNativeOutcomes(t *testing.T, input runtimecontract.ParticipantActionInput, snapshot, state map[string]any) {
	t.Helper()
	owner, err := schemas()
	if err != nil {
		t.Fatal(err)
	}
	for _, status := range []string{"accepted", "succeeded"} {
		input.ActionResult = nativeOutcome(t, owner, input.ParticipantAddress, text(state, termEpisodeID), status)
		_, refused, outcomeErr := actionPrecondition(input, snapshot, binding.RuntimeSnapshotV1{})
		if outcomeErr != nil || refused != (status == "accepted") {
			t.Fatal("terminal outcome fence", status, refused, outcomeErr)
		}
	}
	input.ActionResult = nativeOutcome(t, owner, input.ParticipantAddress, "different-episode", "succeeded")
	if _, refused, episodeErr := actionPrecondition(input, snapshot, binding.RuntimeSnapshotV1{}); episodeErr != nil || !refused {
		t.Fatal("wrong episode accepted", episodeErr)
	}
	for _, predecessor := range []map[string]any{nil, {"participant_episode_results": map[string]any{input.ParticipantAddress: map[string]any{"private": "sentinel"}}}} {
		if _, refused, predecessorErr := actionPrecondition(input, predecessor, binding.RuntimeSnapshotV1{}); predecessorErr != nil || !refused {
			t.Fatal("missing/corrupt episode accepted", predecessorErr)
		}
	}
	terminated, _, err := terminatedEpisode(episodeCommand{}, state, "2026-01-02T03:04:06Z")
	if err != nil {
		t.Fatal(err)
	}
	snapshot["participant_episode_results"] = map[string]any{input.ParticipantAddress: terminated}
	if _, refused, err := actionPrecondition(input, snapshot, binding.RuntimeSnapshotV1{}); err != nil || !refused {
		t.Fatal("terminated episode accepted", err)
	}
}

func nativeOutcome(t *testing.T, owner *admission.Validator, address, episode, status string) admission.Fragment { //nolint:ireturn // Tests exercise the sealed fragment boundary.
	t.Helper()
	fragment, err := admission.AdmitFragment(owner, admission.ParticipantActionResult, map[string]any{"status": status, "participant_address": address, "episode_id": episode, "action_instance_id": "action-1", "action_contract_address": "participant.action-contract.scan", "observation_point": "observed"}, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	return fragment
}

func TestGraphDeleteReadbackAndCancellation(t *testing.T) {
	c := newComponent("orchestration", nil)
	c.order = []string{"orchestration.script.z"}
	entries := map[string]any{"orchestration.script.z": map[string]any{"domain": "orchestration"}, "orchestration.script.a": map[string]any{"domain": "orchestration"}}
	if got := c.orderedEntries(entries); !slices.Equal(got, []string{"orchestration.script.z", "orchestration.script.a"}) {
		t.Fatal(got)
	}
	snapshot := map[string]any{"entries": entries, "orchestration_results": map[string]any{"orchestration.script.z": map[string]any{"status": "bound"}}, "orchestration_history": map[string]any{"orchestration.script.z": []any{map[string]any{"status": "bound"}}}}
	operations := []any{map[string]any{"action": "delete", "address": "orchestration.script.z"}, map[string]any{"action": "unchanged", "address": "orchestration.script.a"}}
	changed, running := c.foldOperations(map[string]any{"operations": operations}, snapshot, "2026-01-02T03:04:05Z")
	if !running || !slices.Equal(changed, []string{"orchestration.script.z"}) || len(object(snapshot, "orchestration_results")) != 0 || len(object(snapshot, "orchestration_history")) != 0 {
		t.Fatal("delete failed to clear retained graph state", snapshot)
	}
	if got := foldEntryOrder(slices.Clone(c.order), operations); len(got) != 0 {
		t.Fatal("deleted entry retained in stop order", got)
	}
	c.history["orchestration.script.a"] = []map[string]any{{"status": "bound"}}
	history, err := c.History(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	history["orchestration.script.a"][0]["status"] = "tampered"
	if c.history["orchestration.script.a"][0]["status"] != "bound" {
		t.Fatal("history readback aliases retained state")
	}
	status, err := c.Status(context.Background())
	if err != nil || status["running"] != false {
		t.Fatal(status, err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	for _, read := range []func() error{
		func() error { _, err := c.Status(ctx); return err },
		func() error { _, err := c.Results(ctx); return err },
		func() error { _, err := c.History(ctx); return err },
		func() error { _, err := c.Stop(ctx, binding.RuntimeSnapshotV1{}); return err },
		func() error {
			_, err := c.start(ctx, binding.OrchestrationPlanV1{}, "orchestration-plan-v1", binding.RuntimeSnapshotV1{})
			return err
		},
	} {
		if read() == nil {
			t.Fatal("cancelled graph operation succeeded")
		}
	}
	if _, err := NewEvaluator(); err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff([]string{"orchestration.script.z"}, c.order); diff != "" {
		t.Fatal("cancelled calls changed retained ordering", diff)
	}
}

func TestObservationReuseRejectsOutOfDomainAndMalformedInputs(t *testing.T) {
	envelope := map[string]any{"digest": "digest", "configuration": map[string]any{"configuration_digest": "configuration"}}
	prior := map[string]any{"field_path": "nodes.web.realization.compute-substrate", "envelope_digest": "digest", "configuration_digest": "configuration", "verification_scope": "presence", "observation_strength": "guest-observed", "observed_value": "selected"}
	for _, descriptor := range []map[string]any{
		{"kind": "exact", "value": "selected"},
		{"kind": "governed-reference", "allowed_refs": []any{"other", "selected"}},
		{"kind": "enum", "values": []any{"other", "selected"}},
	} {
		constraint := map[string]any{"field_path": prior["field_path"], "value_domain": descriptor}
		if !reusableDisclosure(prior, constraint, envelope) {
			t.Fatal("matching observation refused", descriptor)
		}
		outside := maps.Clone(prior)
		outside["observed_value"] = "outside"
		if reusableDisclosure(outside, constraint, envelope) {
			t.Fatal("out-of-domain evidence retained", descriptor)
		}
	}
	for _, snapshot := range []map[string]any{
		{"realization_observations": []any{true}},
		{"realization_observations": []any{map[string]any{"private": "sentinel"}}},
	} {
		if _, _, err := priorDisclosures(snapshot); err == nil {
			t.Fatal("malformed disclosure accepted")
		}
		if _, err := retainedObservations(nil, snapshot, envelope); err == nil {
			t.Fatal("malformed prior observation accepted")
		}
	}
	for _, plan := range []map[string]any{
		{"observation_demands": true},
		{"operations": []any{true}},
		{"realization_constraints": []any{true}},
	} {
		if _, err := retainedObservations(plan, nil, envelope); err == nil {
			t.Fatal("malformed observation plan accepted", plan)
		}
	}
}

func TestParticipantActionEventsPreserveExplicitOutcomeAndReferences(t *testing.T) {
	owner, err := schemas()
	if err != nil {
		t.Fatal(err)
	}
	selection, err := admission.AdmitFragment(owner, admission.RealizationValue, map[string]any{"implementation_identity": map[string]any{"name": "test", "version": "1"}}, ingress.Limits{MaxBytes: 4096, MaxDepth: 16})
	if err != nil {
		t.Fatal(err)
	}
	temporal, err := admission.AdmitFragment(owner, admission.ParticipantTemporalContext, map[string]any{"temporal_contract_id": "temporal", "time_domain": "simulation_time", "clock_authority": "runtime", "event_points": []any{"observed"}, "observation_point": "observed"}, ingress.Limits{MaxBytes: 4096, MaxDepth: 16})
	if err != nil {
		t.Fatal(err)
	}
	scope, generation, post := "scope", int64(5), "sha256:"+strings.Repeat("a", 64)
	input := runtimecontract.ParticipantActionInput{ParticipantAddress: "participant.behavior.agent", ImplementationSelection: selection, ExecutionScopeRef: &scope, ExecutionGeneration: &generation, PostStateDigest: &post, VisibleRefs: []string{"visible"}, DisclosedRefs: []string{"disclosed"}, EvidenceRefs: []string{"evidence"}, TemporalContexts: []admission.Fragment{temporal}}
	input.ActionResult = nativeOutcome(t, owner, input.ParticipantAddress, "episode", "succeeded")
	events := participantActionEvents(input, "episode", "2026-01-02T03:04:05Z")
	if len(events) != 3 {
		t.Fatal(events)
	}
	for _, event := range events {
		row, ok := event.(map[string]any)
		if !ok || len(array(row["temporal_contexts"])) != 1 {
			t.Fatal("temporal context omitted", event)
		}
	}
	observed, ok := events[2].(map[string]any)
	if !ok || observed["post_state_digest"] != post || object(observed, "action_result")["status"] != "succeeded" || len(object(observed, "details")) != 3 {
		t.Fatal("explicit outcome or disclosures omitted", observed)
	}
}

func TestStubBoundaryRefusalsLeaveRetainedStateUntouched(t *testing.T) {
	ctx := context.Background()
	c := newComponent("orchestration", nil)
	if _, err := c.start(ctx, true, "orchestration-plan-v1", binding.RuntimeSnapshotV1{}); err == nil {
		t.Fatal("non-object plan accepted")
	}
	if _, err := transportObject(make(chan int)); err == nil {
		t.Fatal("foreign transport accepted")
	}
	if _, err := snapshotResult(map[string]any{"entries": true}); err == nil {
		t.Fatal("invalid snapshot accepted")
	}
	if _, err := snapshotResult(map[string]any{"private": make(chan int)}); err == nil {
		t.Fatal("foreign snapshot accepted")
	}
	var destination map[string]any
	if err := copyJSON(make(chan int), &destination); err == nil {
		t.Fatal("foreign JSON input accepted")
	}
	if err := copyJSON(true, &destination); err == nil {
		t.Fatal("non-object decoded into object")
	}
	p := &participant{component: newComponent("participant_episode", nil)}
	if _, err := p.Initialize(nil, runtimecontract.EpisodeInitializeRequest{}, binding.RuntimeSnapshotV1{}); err == nil { //nolint:staticcheck // Nil context is deliberate invalid input.
		t.Fatal("nil lifecycle context accepted")
	}
	if _, err := p.AdmitAction(nil, nil, binding.RuntimeSnapshotV1{}); err == nil { //nolint:staticcheck // Nil context is deliberate invalid input.
		t.Fatal("nil action context accepted")
	}
	if _, _, err := terminatedEpisode(episodeCommand{reason: "invalid"}, nil, "now"); err == nil {
		t.Fatal("invalid terminal reason accepted")
	}
	for _, sequence := range []any{true, json.Number("1.5")} {
		if _, _, err := runningEpisode(episodeCommand{address: "participant.behavior.agent"}, map[string]any{"sequence_number": sequence}, map[string]*big.Int{}, "now"); err == nil {
			t.Fatal("invalid sequence accepted")
		}
	}
	if len(c.history) != 0 || len(c.results) != 0 || c.running {
		t.Fatal("refused input changed retained state")
	}
}

func TestParticipantLifecycleRefusalsAndExplicitEpisode(t *testing.T) {
	p := &participant{component: newComponent("participant_episode", nil), counters: map[string]*big.Int{}}
	ctx := context.Background()
	if result, err := p.Initialize(ctx, runtimecontract.EpisodeInitializeRequest{}, binding.RuntimeSnapshotV1{}); err != nil || result.Success {
		t.Fatal("empty participant accepted", err)
	}
	id := "operator-selected"
	initialized, err := p.Initialize(ctx, runtimecontract.EpisodeInitializeRequest{ParticipantAddress: "participant.behavior.agent", EpisodeID: &id}, binding.RuntimeSnapshotV1{})
	if err != nil || !initialized.Success || p.results["participant.behavior.agent"]["episode_id"] != id {
		t.Fatal(initialized, err)
	}
	if result, restartErr := p.Restart(ctx, runtimecontract.EpisodeRestartRequest{ParticipantAddress: "participant.behavior.agent"}, initialized.Snapshot); restartErr != nil || result.Success {
		t.Fatal("running episode restarted", restartErr)
	}
	terminated, err := p.Terminate(ctx, runtimecontract.EpisodeTerminateRequest{ParticipantAddress: "participant.behavior.agent"}, initialized.Snapshot)
	if err != nil || !terminated.Success {
		t.Fatal(terminated, err)
	}
	if result, terminateErr := p.Terminate(ctx, runtimecontract.EpisodeTerminateRequest{ParticipantAddress: "participant.behavior.agent"}, terminated.Snapshot); terminateErr != nil || result.Success {
		t.Fatal("terminal episode terminated again", terminateErr)
	}
	status, err := p.Status(ctx)
	if err != nil || status["running"] != 0 {
		t.Fatal(status, err)
	}
	cancelled, cancel := context.WithCancel(ctx)
	cancel()
	if _, err := p.Status(cancelled); err == nil {
		t.Fatal("cancelled status succeeded")
	}
}

func TestProvisionerValidationCancellationAndDeletion(t *testing.T) {
	p := &provisioner{}
	ctx := context.Background()
	findings, err := p.Validate(ctx, binding.ProvisioningPlanV1{})
	if err != nil || len(findings) != 0 {
		t.Fatal(findings, err)
	}
	cancelled, cancel := context.WithCancel(ctx)
	cancel()
	if _, err := p.Validate(cancelled, binding.ProvisioningPlanV1{}); err == nil {
		t.Fatal("cancelled validation succeeded")
	}
	snapshot := map[string]any{"entries": map[string]any{"provision.node.vm": map[string]any{"status": "applied"}, "other": map[string]any{"status": "retained"}}}
	changed := foldProvisioning(map[string]any{"operations": []any{map[string]any{"action": "delete", "address": "provision.node.vm"}}}, snapshot)
	if !slices.Equal(changed, []string{"provision.node.vm"}) || len(object(snapshot, "entries")) != 1 || object(object(snapshot, "entries"), "other")["status"] != "retained" {
		t.Fatal("delete changed unrelated inventory", snapshot)
	}
	if _, err := NewProvisionerWithConfiguration(Configuration{Envelope: &binding.RealizationEnvelopeV1{}}); err == nil {
		t.Fatal("invalid configured envelope accepted")
	}
}
