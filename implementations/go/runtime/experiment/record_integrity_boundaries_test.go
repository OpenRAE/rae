package experiment

import (
	"encoding/json"
	"fmt"
	"maps"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestRetainedEvidenceRejectsConflictingVersionsAndCrossAttemptMixing(t *testing.T) {
	template := fixtureEvidence(t)
	proof, err := trialEvidence(template, "run:one", "evidence:one")
	if err != nil {
		t.Fatal(err)
	}
	changed := maps.Clone(template)
	changed["captured_at"] = "2026-11-15T10:00:00Z"
	other, err := trialEvidence(changed, "run:one", "evidence:one")
	if err != nil {
		t.Fatal(err)
	}
	makeObservation := func(attempt string, evidence binding.ExperimentEvidenceRecordV1) Decision {
		d, err := makeDecision(observationSchema, map[string]any{termExecutionAttemptID: attempt, "observation": map[string]any{"kind": termCapture, "complete": true, termEvidence: []binding.ExperimentEvidenceRecordV1{evidence}}})
		if err != nil {
			t.Fatal(err)
		}
		return d
	}
	first := makeObservation("attempt:one", proof)
	foreign := makeObservation("attempt:two", proof)
	for _, test := range []struct {
		name    string
		records []Decision
		attempt string
		count   int
		valid   bool
	}{
		{"one", []Decision{first}, "attempt:one", 1, true},
		{"idempotent", []Decision{first, first}, "attempt:one", 1, true},
		{"foreign-attempt", []Decision{first, foreign}, "attempt:one", 1, true},
		{"all-attempts", []Decision{first, foreign}, "", 1, true},
		{"conflicting-version", []Decision{first, makeObservation("attempt:one", other)}, "attempt:one", 0, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			records, err := observedEvidence(test.records, test.attempt)
			if (err == nil) != test.valid || test.valid && len(records) != test.count {
				t.Fatal("retained evidence identity", err, len(records))
			}
		})
	}
	if _, err := recordTraceability(RecordSource{Observations: []Decision{first}}, RunMetadata{Traceability: json.RawMessage(`{`)}, map[string]any{}); err == nil {
		t.Fatal("malformed traceability admitted")
	}
	if _, err := recordTraceability(RecordSource{Observations: []Decision{first}}, RunMetadata{Traceability: json.RawMessage(`{"evidence_record_refs":[{"ref_id":"foreign","ref_version":"1"}]}`)}, map[string]any{}); err == nil {
		t.Fatal("traceability invented evidence")
	}
	if _, err := recordTraceability(RecordSource{Observations: []Decision{first, makeObservation("attempt:one", other)}}, RunMetadata{}, map[string]any{}); err == nil {
		t.Fatal("conflicting proof entered traceability")
	}
}

func TestRuntimeBindingsReportOnlyObservedParticipantConfigurations(t *testing.T) {
	entry := map[string]any{"participant_configurations": []any{map[string]any{"participant_address": "p", "configuration_digest": "digest:p"}}, "selections": []any{map[string]any{"treatment": map[string]any{"selection_id": "s"}}}, "bindings": []any{
		map[string]any{"descriptor": map[string]any{"binding_id": "scenario", "target": map[string]any{"plane": "scenario"}}, "origin": "selection"},
		map[string]any{"descriptor": map[string]any{"binding_id": "participant", "target": map[string]any{"plane": "participant-implementation", "participant_address": "p"}}, "origin": "selection"},
		map[string]any{"descriptor": map[string]any{"binding_id": "apparatus", "target": map[string]any{"plane": "apparatus"}}, "origin": "selection"},
	}}
	if values := realizedSelections(entry); len(values) != 1 || text(values[0], "selection_id") != "s" {
		t.Fatal("record discarded realized treatment")
	}
	for _, observed := range []bool{false, true} {
		latest := map[string]any{}
		expected := 1
		if observed {
			latest["configuration_status"] = "observed"
			expected = 2
		}
		bindings := realizedBindings(entry, latest)
		if len(bindings) != expected {
			t.Fatal("unobserved participant configuration became a realized binding", len(bindings), expected)
		}
		if observed && text(bindings[1], "configuration_digest") != "digest:p" {
			t.Fatal("realized configuration digest changed")
		}
	}
	payload := map[string]any{"realized_bindings": []any{map[string]any{"descriptor": map[string]any{"binding_id": "automatic"}}}}
	if err := mergeRecordBindings(payload, []json.RawMessage{json.RawMessage(`{"descriptor":{"binding_id":"automatic"}}`)}); err == nil {
		t.Fatal("metadata replaced automatic binding")
	}
	if err := mergeRecordBindings(payload, []json.RawMessage{json.RawMessage(`{`)}); err == nil {
		t.Fatal("malformed metadata binding admitted")
	}
	if err := mergeRecordBindings(payload, []json.RawMessage{json.RawMessage(`{"descriptor":{"binding_id":"additional"}}`)}); err != nil || len(array(payload["realized_bindings"])) != 2 {
		t.Fatal("independent binding lost", err)
	}
}

func TestRuntimeAttemptRecoveryRejectsIdentityAndDeadlineChanges(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	slot := c.slotSnapshot()[0]
	decision, err := c.startAttempt(t.Context(), slot, 1)
	if err != nil {
		t.Fatal(err)
	}
	baseline := decisionMap(decision)
	for _, test := range []struct {
		field string
		value any
	}{
		{"attempt", json.Number("2")}, {termRunID, "foreign"}, {termExecutionAttemptID, "foreign"},
		{termStartedAt, "invalid"}, {"deadline", "invalid"}, {"deadline", baseline[termStartedAt]},
	} {
		t.Run(test.field+"/"+fmt.Sprint(test.value), func(t *testing.T) {
			changed := maps.Clone(baseline)
			changed[test.field] = test.value
			if err := validateRetainedAttempts(c.id, slot, []map[string]any{changed}); err == nil {
				t.Fatal("changed attempt authority admitted")
			}
		})
	}
	trial := slot.request(baseline)
	for _, field := range []string{termStartedAt, "deadline"} {
		invalid := trial
		if field == termStartedAt {
			invalid.StartedAt = "invalid"
		} else {
			invalid.Deadline = invalid.StartedAt
		}
		if _, err := c.interruption(t.Context(), slot, invalid, nil, false); err == nil {
			t.Fatal("invalid retained deadline admitted", field)
		}
	}
	if outcome := interruptionOutcome(map[string]any{"disposition": "abort"}); outcome != termAborted {
		t.Fatal("abort disposition changed", outcome)
	}
}

func TestRuntimeCleanupAndRetryRequireScopedProofForEveryClaim(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	ref := recordReferences(t).Cases[4]
	source := recordSourceFixture(t, c, ref)
	var slot trialSlot
	for _, s := range c.slotSnapshot() {
		if s.entry.RunID == source.RunID {
			slot = s
		}
	}
	trial := slot.request(decisionMap(source.Attempts[0]))
	phase, err := (terminalHost{testHost: &testHost{}, evidence: fixtureEvidence(t)}).Cleanup(t.Context(), trial, termSucceeded)
	if err != nil || phase.Observation == nil {
		t.Fatal("cleanup proof fixture", err)
	}
	for _, field := range []string{"", "attempt", "receipt-model", "obligation-proof", "clean-proof"} {
		t.Run("cleanup-"+field, func(t *testing.T) {
			checkRuntimeCleanupProofBoundary(t, c, slot, trial, phase, field)
		})
	}
	for _, test := range []struct {
		name    string
		receipt any
		valid   bool
	}{
		{"failed", map[string]any{"cleanup_status": termFailed}, false},
		{"fresh-range", map[string]any{"cleanup_status": termSucceeded, "clean_state_claim": map[string]any{"disposition": "fresh-range-required"}}, false},
		{"undeclared-reuse", map[string]any{"cleanup_status": termSucceeded, "clean_state_claim": map[string]any{"disposition": "declared-reusable"}}, false},
	} {
		if got := reusable(slot, trial, test.receipt); got != test.valid {
			t.Fatal("reuse authority", test.name, got)
		}
	}
	if err := validateRetry(slot, trial, map[string]any{"ready": false}); err != nil {
		t.Fatal("not-ready retry should retain pending state", err)
	}
	if err := validateRetry(slot, trial, map[string]any{"ready": true}); err == nil {
		t.Fatal("ready retry without evidence admitted")
	}
	if err := validateRetry(slot, trial, map[string]any{"ready": false, "obligation_results": map[string]any{"foreign": map[string]any{"obligation_id": "foreign"}}}); err == nil {
		t.Fatal("foreign retry obligation admitted")
	}
}

func checkRuntimeCleanupProofBoundary(t *testing.T, c *coordinator, slot trialSlot, trial Trial, phase Phase, field string) {
	t.Helper()

	m, err := observationDocument(*phase.Observation)
	if err != nil {
		t.Fatal(err)
	}
	receipt := object(m["receipt"])
	switch field {
	case "attempt":
		receipt[termExecutionAttemptID] = "foreign"
	case "receipt-model":
		receipt["cleanup_status"] = "foreign"
	case "obligation-proof":
		for _, result := range object(receipt["obligation_results"]) {
			object(result)["evidence_refs"] = []any{"foreign"}
		}
	case "clean-proof":
		object(receipt["clean_state_claim"])["evidence_refs"] = []any{"foreign"}
	}
	if err := c.validateCleanup(slot, trial, m); (err == nil) != (field == "") {
		t.Fatal("cleanup evidence authority", err)
	}
}
