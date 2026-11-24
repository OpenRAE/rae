package experiment

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type failingBoundaryArchive struct {
	Archive

	stage   string
	reached bool
}

func (a *failingBoundaryArchive) fail(stage string) error {
	if a.stage == stage {
		a.reached = true
		return errors.New("private archive refusal")
	}
	return nil
}
func (a *failingBoundaryArchive) BuildRun(ctx context.Context, source RecordSource) (binding.ExperimentRunV1, error) {
	if err := a.fail("build"); err != nil {
		return binding.ExperimentRunV1{}, err
	}
	return a.Archive.BuildRun(ctx, source)
}
func (a *failingBoundaryArchive) WriteSources(ctx context.Context, source RecordSource) error {
	if err := a.fail("sources"); err != nil {
		return err
	}
	return a.Archive.WriteSources(ctx, source)
}
func (a *failingBoundaryArchive) WriteRun(ctx context.Context, run binding.ExperimentRunV1) error {
	if err := a.fail("write-run"); err != nil {
		return err
	}
	return a.Archive.WriteRun(ctx, run)
}
func (a *failingBoundaryArchive) ReadRun(ctx context.Context, id, version string) (binding.ExperimentRunV1, error) {
	if err := a.fail("read-run"); err != nil {
		return binding.ExperimentRunV1{}, err
	}
	return a.Archive.ReadRun(ctx, id, version)
}
func (a *failingBoundaryArchive) WriteStudy(ctx context.Context, study binding.ExperimentStudyV1) error {
	if err := a.fail("write-study"); err != nil {
		return err
	}
	return a.Archive.WriteStudy(ctx, study)
}
func (a *failingBoundaryArchive) ReadStudy(ctx context.Context, id, version string) (binding.ExperimentStudyV1, error) {
	if err := a.fail("read-study"); err != nil {
		return binding.ExperimentStudyV1{}, err
	}
	return a.Archive.ReadStudy(ctx, id, version)
}
func checkArchiveBoundaryFailure(t *testing.T, archive *failingBoundaryArchive, err error) {
	t.Helper()
	category, known := fault.CategoryOf(err)
	if !archive.reached || !known || category != fault.Operational || strings.Contains(err.Error(), "private") {
		t.Fatal("archive failure lost or disclosed", archive.reached, err)
	}
}
func TestRuntimeArchiveOutagesRetainFrozenCandidatesForRecovery(t *testing.T) {
	ref := scienceReference(t)
	for _, stage := range []string{"sources", "write-run", "read-run", "write-study", "read-study"} {
		t.Run(stage, func(t *testing.T) { checkArchiveOutageRecovery(t, ref, stage) })
	}
}
func checkArchiveOutageRecovery(t *testing.T, ref scientificReference, stage string) {
	t.Helper()
	c, journal := scienceRuntime(t, ref)
	reader, _ := scienceReader(t, ref)
	actual := &studyArchive{testArchive: &testArchive{runs: map[string]binding.ExperimentRunV1{}}}
	archive := &failingBoundaryArchive{Archive: actual, stage: stage}
	options := RecordOptions{Evidence: reader, Study: &ref.Definition, Archive: archive}
	_, err := c.Records(t.Context(), c.options.Identity, options)
	checkArchiveBoundaryFailure(t, archive, err)
	if len(pendingPublications(journal.records, c.id)) == 0 {
		t.Fatal("outage discarded frozen candidates")
	}
	archive.stage = ""
	if _, err := c.Records(t.Context(), c.options.Identity, options); err != nil {
		t.Fatal("frozen publication did not recover", err)
	}
	_, published := publicationCounts(journal.records)
	if published < 2 {
		t.Fatal("recovery lost run or study publication")
	}
}
func TestRuntimeReplacementArchiveBuildFailureKeepsParentActive(t *testing.T) {
	f := prepareReplacementRuntime(t, false)
	archive := &failingBoundaryArchive{Archive: f.archive, stage: "build"}
	f.c.options.Archive = archive
	_, err := f.c.Advance(t.Context(), f.options.Identity)
	checkArchiveBoundaryFailure(t, archive, err)
	if f.host.retireCalls != 0 {
		t.Fatal("parent retired after archive failure")
	}
	if len(pendingPublications(f.journal.records, f.c.id)) != 0 {
		t.Fatal("failed archive produced publication")
	}
}

type outageBoundaryJournal struct {
	*testJournal

	loads   int
	failAt  int
	reached bool
}

func (j *outageBoundaryJournal) Load(ctx context.Context) ([]Decision, error) {
	j.loads++
	if j.loads == j.failAt {
		j.reached = true
		return nil, errors.New("private load failure")
	}
	return j.testJournal.Load(ctx)
}
func TestRuntimeProgressRecoversJournalReadOutagesWithoutRepeatingStarts(t *testing.T) {
	journal := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, journal))
	initial := append([]Decision{}, journal.records...)
	for failAt := 1; failAt <= 7; failAt++ {
		checkJournalReadOutage(t, c, initial, failAt)
	}
}
func checkJournalReadOutage(t *testing.T, c *coordinator, initial []Decision, failAt int) {
	t.Helper()
	for _, timer := range c.deadlines {
		timer.timer.Stop()
	}
	c.deadlines = map[string]*attemptDeadline{}
	journal := &outageBoundaryJournal{testJournal: &testJournal{records: append([]Decision{}, initial...)}, failAt: failAt}
	c.options.Journal = journal
	c.options.Host = terminalHost{testHost: &testHost{ceased: true}, evidence: fixtureEvidence(t)}
	var failure error
	for range 5 {
		if _, failure = c.Advance(t.Context(), c.options.Identity); failure != nil {
			break
		}
	}
	if !journal.reached {
		t.Fatal("journal outage position was not exercised", failAt, journal.loads)
	}
	category, known := fault.CategoryOf(failure)
	if !known || category != fault.Operational || strings.Contains(failure.Error(), "private") {
		t.Fatal("read outage lost or disclosed", failAt, failure)
	}
	for range 5 {
		if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
			t.Fatal("read outage did not recover", failAt, err)
		}
	}
	for _, slot := range c.slotSnapshot() {
		if len(slotAttempts(journal.records, c.id, slot.entry.PlanEntryID)) != 1 {
			t.Fatal("outage repeated experiment start", failAt)
		}
	}
}
