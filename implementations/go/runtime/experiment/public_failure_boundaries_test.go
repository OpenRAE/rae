package experiment

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"
)

type unavailableBoundaryJournal struct{ *testJournal }

func (unavailableBoundaryJournal) Load(context.Context) ([]Decision, error) {
	return nil, errors.New("private journal outage")
}
func TestRuntimePublicReadersAndCancellationRefuseJournalOutages(t *testing.T) {
	journal := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, journal))
	c.options.Journal = unavailableBoundaryJournal{testJournal: journal}
	for _, operation := range []string{"advance", "results", "records", "cancel"} {
		if err := runBoundaryPublicOperation(t, c, operation); err == nil || strings.Contains(err.Error(), "private") {
			t.Fatal("journal outage lost or disclosed", operation, err)
		}
	}
}
func runBoundaryPublicOperation(t *testing.T, c *coordinator, operation string) error {
	t.Helper()
	switch operation {
	case "advance":
		_, err := c.Advance(t.Context(), c.options.Identity)
		return err
	case "results":
		_, err := c.Results(t.Context(), c.options.Identity)
		return err
	case "records":
		_, err := c.Records(t.Context(), c.options.Identity, RecordOptions{})
		return err
	default:
		return c.Cancel(t.Context(), c.options.Identity)
	}
}
func TestRuntimePublicProgressAndReadersKeepAdmissionBudgets(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	c.options.AdmissionBudget = time.Nanosecond
	c.gate <- struct{}{}
	defer func() { <-c.gate }()
	for _, operation := range []string{"advance", "results", "records"} {
		if err := runBoundaryPublicOperation(t, c, operation); err == nil {
			t.Fatal("busy operation ignored admission budget", operation)
		}
	}
}
func TestRuntimeResultsRefuseAnUnavailableRecordOwner(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, terminalHost{testHost: &testHost{ceased: true}, evidence: fixtureEvidence(t)}, &testJournal{}))
	for range 2 {
		if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
			t.Fatal(err)
		}
	}
	c.options.Host = phaseBoundaryHost{Host: c.options.Host, failed: "records"}
	if _, err := c.Results(t.Context(), c.options.Identity); err == nil || strings.Contains(err.Error(), "private") {
		t.Fatal("unconfirmed source became a result", err)
	}
}
func TestRuntimePublicOperationsRefuseAnUnownedReplacementJournalEntry(t *testing.T) {
	f := prepareReplacementRuntime(t, false)
	if _, err := f.c.Advance(t.Context(), f.options.Identity); err != nil {
		t.Fatal(err)
	}
	journal := &testJournal{}
	host := &testHost{}
	c := runtimeCoordinator(t, newRuntime(t, host, journal))
	view := decisionMap(onlyReplacementDecision(t, f.journal.records))
	view[termExperimentID] = c.id
	record, err := makeDecision(replacementSchema, view)
	if err != nil {
		t.Fatal(err)
	}
	journal.records = append(journal.records, record)
	host.events = nil
	for _, operation := range []string{"advance", "results", "records", "cancel"} {
		if err := runBoundaryPublicOperation(t, c, operation); err == nil {
			t.Fatal("unowned replacement was restored", operation)
		}
	}
	if len(host.events) != 0 {
		t.Fatal("corrupt replacement reached an installed phase")
	}
}
