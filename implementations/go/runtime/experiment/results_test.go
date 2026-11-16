package experiment

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type resultHost struct {
	terminalHost

	receipt  map[string]any
	snapshot binding.RuntimeSnapshotV1
}

func (h *resultHost) Observe(ctx context.Context, trial Trial) (Observation, error) {
	o, err := h.terminalHost.Observe(ctx, trial)
	o.Snapshot = h.snapshot
	return o, err
}
func (h *resultHost) Records(_ context.Context, trial Trial) (RecordSource, error) {
	view, err := transportView(h.receipt)
	if err != nil {
		return RecordSource{}, err
	}
	id := "operation:" + trial.ExecutionAttemptID
	view["operation_id"] = id
	object(view["context"])["run_scope"] = "run:" + trial.RunID
	object(view["context"])["actor_id"] = trial.Identity.ActorID
	object(view["context"])["authorization_scope"] = trial.Identity.AuthorizationScope
	var selected, unselected binding.OperationReceiptV1
	if convert(view, &selected) != nil {
		return RecordSource{}, integrity()
	}
	view["operation_id"] = "unselected:" + trial.ExecutionAttemptID
	if convert(view, &unselected) != nil {
		return RecordSource{}, integrity()
	}
	return RecordSource{OperationRefs: map[string][]string{trial.ExecutionAttemptID: {id}}, OperationReceipts: []binding.OperationReceiptV1{selected, unselected}}, nil
}
func resultFixture(t *testing.T) *resultHost {
	t.Helper()
	h := &resultHost{testHost: &testHost{ceased: true}, evidence: fixtureEvidence(t)}
	for path, target := range map[string]any{"../../../../contracts/fixtures/control-plane/operation-receipt-v1/valid/accepted.json": &h.receipt, "../../../../contracts/fixtures/snapshots/runtime-snapshot-v1/valid/reference.json": &h.snapshot} {
		raw, err := os.ReadFile(path) //nolint:gosec // The loop uses only the two literal repository fixture paths above.
		if err != nil {
			t.Fatal(err)
		}
		if json.Unmarshal(raw, target) != nil {
			t.Fatal("fixture")
		}
	}
	return h
}
func TestRuntimeResultsRetainAttemptReceiptsSnapshotAndEvidenceRoles(t *testing.T) {
	h := resultFixture(t)
	c := runtimeCoordinator(t, newRuntime(t, h, &testJournal{}))
	for range 2 {
		if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
			t.Fatal(err)
		}
	}
	results, err := c.Results(t.Context(), c.options.Identity)
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 || len(results[0].OperationReceipts) != 1 || len(results[0].Evidence) != 1 || len(results[0].CleanupEvidence) == 0 {
		t.Fatal("terminal result lost or merged independent facts")
	}
	if !same(results[0].Snapshot, h.snapshot) {
		t.Fatal("execution snapshot lost")
	}
	entries, ok := results[0].Snapshot.Entries.Value()
	if !ok {
		t.Fatal("fixture entries")
	}
	clear(entries)
	again, err := c.Results(t.Context(), c.options.Identity)
	if err != nil {
		t.Fatal(err)
	}
	if !same(again[0].Snapshot, h.snapshot) {
		t.Fatal("caller mutated retained snapshot")
	}
}
func TestRuntimeEveryPublicOperationEnforcesActorAndScopes(t *testing.T) {
	h := &testHost{}
	c := runtimeCoordinator(t, newRuntime(t, h, &testJournal{}))
	for _, identity := range []Identity{{ActorID: "other", AuthorizationScope: []string{"run"}}, {ActorID: "actor", AuthorizationScope: []string{"other"}}} {
		for _, call := range []func() error{func() error { _, err := c.Advance(t.Context(), identity); return err }, func() error { return c.Cancel(t.Context(), identity) }, func() error { _, err := c.Results(t.Context(), identity); return err }, func() error { _, err := c.Records(t.Context(), identity, RecordOptions{}); return err }} {
			if call() == nil {
				t.Fatal("unauthorized operation admitted")
			}
		}
	}
}
func TestRuntimeForeignOwnerFailureOmitsPrivateMessages(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{fail: true}, &testJournal{}))
	_, err := c.Advance(t.Context(), c.options.Identity)
	if err == nil || strings.Contains(err.Error(), "secret-owner-message") {
		t.Fatal("unsafe foreign failure", err)
	}
}

func TestRuntimeTerminalHandoffRejectsOversizedSnapshotBeforeCompletion(t *testing.T) {
	h := resultFixture(t)
	view, err := transportView(h.snapshot)
	if err != nil {
		t.Fatal(err)
	}
	view["metadata"] = map[string]any{"oversized": strings.Repeat("a", (1<<20)+1)}
	if err = convert(view, &h.snapshot); err != nil {
		t.Fatal(err)
	}
	j := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, h, j))
	if _, err = c.Advance(t.Context(), c.options.Identity); err != nil {
		t.Fatal(err)
	}
	if _, err = c.Advance(t.Context(), c.options.Identity); err == nil {
		t.Fatal("oversized trial result completed")
	}
	attempt := slotAttempts(j.records, c.id, c.slots[0].entry.PlanEntryID)[0]
	if findAttemptDecision(j.records, terminalSchema, text(attempt, termExecutionAttemptID)) != nil {
		t.Fatal("invalid handoff retained as completed")
	}
}
