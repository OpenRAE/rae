package experiment

import (
	"context"
	"errors"
	"maps"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type testArchive struct {
	runs               map[string]binding.ExperimentRunV1
	events             []string
	loseAck, alterRead bool
}

func (a *testArchive) BuildRun(context.Context, RecordSource) (binding.ExperimentRunV1, error) {
	return binding.ExperimentRunV1{}, errors.New("unused")
}
func (a *testArchive) WriteSources(context.Context, RecordSource) error {
	a.events = append(a.events, "source")
	return nil
}
func (a *testArchive) WriteRun(_ context.Context, run binding.ExperimentRunV1) error {
	view, _ := transportView(run)
	key := versionKey(termRun, view)
	if prior, ok := a.runs[key]; ok && !same(prior, run) {
		return errors.New("version conflict")
	}
	a.runs[key] = run
	a.events = append(a.events, termRun)
	if a.loseAck {
		a.loseAck = false
		return errors.New("secret lost ack")
	}
	return nil
}
func (a *testArchive) ReadRun(_ context.Context, id, version string) (binding.ExperimentRunV1, error) {
	a.events = append(a.events, "read")
	key := versionKey(termRun, map[string]any{termRunID: id, "run_version": version})
	run := a.runs[key]
	if a.alterRead {
		view, _ := transportView(run)
		view["run_version"] = "changed"
		if convert(view, &run) != nil {
			return run, errors.New("fixture")
		}
	}
	return run, nil
}
func (a *testArchive) WriteStudy(context.Context, binding.ExperimentStudyV1) error {
	a.events = append(a.events, termStudy)
	return nil
}
func (a *testArchive) ReadStudy(context.Context, string, string) (binding.ExperimentStudyV1, error) {
	return binding.ExperimentStudyV1{}, errors.New("unused")
}
func TestRuntimePublicationFreezesCandidatesAcrossLostAcknowledgement(t *testing.T) {
	j := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, j))
	ctx := context.Background()
	if _, err := c.Advance(ctx, c.options.Identity); err != nil {
		t.Fatal(err)
	}
	archive := &testArchive{runs: map[string]binding.ExperimentRunV1{}, loseAck: true}
	if _, err := c.Records(ctx, c.options.Identity, RecordOptions{Archive: archive}); err == nil {
		t.Fatal("lost acknowledgement reported as publication")
	}
	candidates, published := publicationCounts(j.records)
	if candidates != 1 || published != 0 {
		t.Fatal("write-ahead candidate missing", candidates, published)
	}
	first := map[string]binding.ExperimentRunV1{}
	maps.Copy(first, archive.runs)
	if _, err := c.Records(ctx, c.options.Identity, RecordOptions{Archive: archive}); err != nil {
		t.Fatal(err)
	}
	_, published = publicationCounts(j.records)
	if published != 1 || !same(first, archive.runs) {
		t.Fatal("retry replaced frozen content")
	}
}
func TestRuntimePublicationRejectsDifferentReadback(t *testing.T) {
	j := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, j))
	ctx := context.Background()
	if _, err := c.Advance(ctx, c.options.Identity); err != nil {
		t.Fatal(err)
	}
	a := &testArchive{runs: map[string]binding.ExperimentRunV1{}, alterRead: true}
	if _, err := c.Records(ctx, c.options.Identity, RecordOptions{Archive: a}); err == nil {
		t.Fatal("different readback published")
	}
	_, published := publicationCounts(j.records)
	if published != 0 {
		t.Fatal("unverified publication claimed")
	}
}
func publicationCounts(records []Decision) (int, int) {
	candidates, published := 0, 0
	for _, d := range records {
		if d.SchemaVersion() != publicationSchema {
			continue
		}
		if text(decisionMap(d), "state") == termCandidate {
			candidates++
		} else {
			published++
		}
	}
	return candidates, published
}
