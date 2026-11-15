package experiment

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestRetryReadinessRequiresEveryResetAndCompensationProof(t *testing.T) {
	for _, ref := range retryReferences(t) {
		if ref.Name != "reset" && ref.Name != "compensate" {
			continue
		}
		t.Run(ref.Name, func(t *testing.T) { checkRetryProofBoundary(t, ref) })
	}
}
func checkRetryProofBoundary(t *testing.T, ref runtimeReferenceCompilation) {
	t.Helper()
	host := &retryHost{testHost: &testHost{}, evidence: fixtureEvidence(t)}
	c := runtimeCoordinator(t, newRuntimeWithInputs(t, host, &testJournal{}, runtimeInputFixture(t, ref)))
	slot := c.slotSnapshot()[0]
	start, err := c.startAttempt(t.Context(), slot, 1)
	if err != nil {
		t.Fatal(err)
	}
	trial := slot.request(decisionMap(start))
	phase, err := host.PrepareRetry(t.Context(), trial)
	if err != nil || phase.Observation == nil {
		t.Fatal("retry proof fixture", err)
	}
	for _, field := range []string{"exact", "missing-proof", "failed-proof", "foreign-proof"} {
		t.Run(field, func(t *testing.T) { checkRetryProofMutation(t, slot, trial, *phase.Observation, ref.Name, field) })
	}
}
func checkRetryProofMutation(t *testing.T, slot trialSlot, trial Trial, observation Observation, policy, field string) {
	t.Helper()
	view, err := observationDocument(observation)
	if err != nil {
		t.Fatal(err)
	}
	if policy == "compensate" {
		if field != "exact" {
			view["verified_compensations"] = []any{}
		}
	} else {
		switch field {
		case "missing-proof":
			view["obligation_results"] = map[string]any{}
		case "failed-proof":
			object(at(view, "obligation_results", "reset"))["status"] = termFailed
		case "foreign-proof":
			object(at(view, "obligation_results", "reset"))["evidence_refs"] = []any{"foreign"}
		}
	}
	if err := validateRetry(slot, trial, view); (err == nil) != (field == "exact") {
		t.Fatal("retry readiness proof admission", err)
	}
}

type panicBoundaryCalls struct{}

func (panicBoundaryCalls) Call(context.Context, string, time.Duration, func(context.Context) (any, error)) (any, error) {
	panic("private adapter panic")
}

type malformedCommitmentHost struct{ Host }

func (malformedCommitmentHost) Admit(context.Context, Trial) (string, error) {
	return "unverified", nil
}
func TestRuntimeConstructionContainsAdapterPanicsAndUnverifiedCommitments(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	for _, field := range []string{"adapter", "commitment", "scope", "plan"} {
		options := c.options
		options.Journal = &testJournal{}
		switch field {
		case "adapter":
			options.Calls = panicBoundaryCalls{}
		case "commitment":
			options.Host = malformedCommitmentHost{Host: &testHost{}}
		case "scope":
			options.Identity.AuthorizationScope = []string{""}
		case "plan":
			options.Inputs.Plan = binding.AdmittedTrialPlanV1{}
		}
		if _, err := New(t.Context(), options); err == nil || strings.Contains(err.Error(), "private") {
			t.Fatal("unverified construction admitted or disclosed detail", field, err)
		}
	}
}
