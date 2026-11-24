package experiment

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type failingBoundaryJournal struct {
	*testJournal

	schema  string
	reached bool
}

func (j *failingBoundaryJournal) Claim(ctx context.Context, decision Decision) (bool, error) {
	if decision.SchemaVersion() == j.schema {
		j.reached = true
		return false, errors.New("private journal refusal")
	}
	return j.testJournal.Claim(ctx, decision)
}
func checkBoundaryJournalFailure(t *testing.T, j *failingBoundaryJournal, err error) {
	t.Helper()
	category, known := fault.CategoryOf(err)
	if !j.reached || !known || category != fault.Operational || strings.Contains(err.Error(), "private") {
		t.Fatal("journal failure was lost or disclosed", j.reached, err)
	}
	for _, record := range j.records {
		if record.SchemaVersion() == j.schema {
			t.Fatal("failed journal claim retained")
		}
	}
}
func TestRuntimeJournalFailuresCannotConfirmPhasesOrTerminalResults(t *testing.T) {
	initialJournal := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, terminalHost{testHost: &testHost{ceased: true}, evidence: fixtureEvidence(t)}, initialJournal))
	initial := append([]Decision{}, initialJournal.records...)
	for _, schema := range []string{attemptSchema, observationSchema, terminalSchema, cancelSchema, interruptionSchema} {
		t.Run(schema, func(t *testing.T) { checkRuntimeJournalClaimBoundary(t, c, initial, schema) })
	}
	j := &failingBoundaryJournal{testJournal: &testJournal{}, schema: experimentSchema}
	c.options.Journal = j
	_, err := New(t.Context(), c.options)
	checkBoundaryJournalFailure(t, j, err)
}
func checkRuntimeJournalClaimBoundary(t *testing.T, c *coordinator, initial []Decision, schema string) {
	t.Helper()
	for _, timer := range c.deadlines {
		timer.timer.Stop()
	}
	c.deadlines = map[string]*attemptDeadline{}
	j := &failingBoundaryJournal{testJournal: &testJournal{records: append([]Decision{}, initial...)}, schema: schema}
	c.options.Journal = j
	if schema == interruptionSchema {
		if _, err := c.startAttempt(t.Context(), c.slotSnapshot()[0], 1); err != nil {
			t.Fatal(err)
		}
		if err := c.Cancel(t.Context(), c.options.Identity); err != nil {
			t.Fatal(err)
		}
	}
	failure := runJournalBoundaryOperation(t, c, schema)

	checkBoundaryJournalFailure(t, j, failure)
}
func TestRuntimeReplacementJournalFailuresKeepParentOwnership(t *testing.T) {
	for _, schema := range []string{candidateSchema, archiveSchema, replacementSchema} {
		t.Run(schema, func(t *testing.T) {
			f := prepareReplacementRuntime(t, false)
			j := &failingBoundaryJournal{testJournal: f.journal, schema: schema}
			f.c.options.Journal = j
			_, err := f.c.Advance(t.Context(), f.options.Identity)
			checkBoundaryJournalFailure(t, j, err)
			if f.host.retireCalls != 0 {
				t.Fatal("parent retired without durable replacement")
			}
		})
	}
}
func TestRuntimeRecordJournalFailuresKeepPublicationUnconfirmed(t *testing.T) {
	ref := scienceReference(t)
	for _, schema := range []string{studySchema, publicationSchema} {
		t.Run(schema, func(t *testing.T) {
			c, journal := scienceRuntime(t, ref)
			j := &failingBoundaryJournal{testJournal: journal, schema: schema}
			c.options.Journal = j
			reader, _ := scienceReader(t, ref)
			archive := &testArchive{runs: map[string]binding.ExperimentRunV1{}}
			_, err := c.Records(t.Context(), c.options.Identity, RecordOptions{Evidence: reader, Study: &ref.Definition, Archive: archive})
			checkBoundaryJournalFailure(t, j, err)
			if len(archive.events) != 0 {
				t.Fatal("publication preceded durable candidate")
			}
		})
	}
}

func runJournalBoundaryOperation(t *testing.T, c *coordinator, schema string) error {
	t.Helper()
	if schema == cancelSchema {
		return c.Cancel(t.Context(), c.options.Identity)
	}
	for range 6 {
		if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
			return err
		}
	}
	return nil
}

type foreignBoundaryDecision struct {
	Decision

	called *bool
}

func (d foreignBoundaryDecision) JSON() []byte {
	*d.called = true
	panic("private foreign decision method")
}
func TestRuntimeJournalRejectsForeignRecordMethodsBeforeInspection(t *testing.T) {
	journal := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, journal))
	called := false
	journal.records = []Decision{foreignBoundaryDecision{Decision: journal.records[0], called: &called}}
	if _, err := c.load(t.Context()); err == nil || called {
		t.Fatal("foreign decision supplied executable projection behavior", err, called)
	}
}
