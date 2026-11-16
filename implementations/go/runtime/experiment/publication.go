package experiment

import (
	"context"
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func versionKey(kind string, subject any) string {
	raw, err := canonical([]any{at(subject, kind+"_id"), at(subject, kind+"_version")})
	if err != nil {
		return ""
	}
	return kind + ":" + string(raw)
}
func retainVersion(versions map[string]any, kind string, subject any) error {
	key := versionKey(kind, subject)
	if key == "" {
		return integrity()
	}
	if prior, ok := versions[key]; ok && !same(prior, subject) {
		return integrity()
	}
	versions[key] = subject
	return nil
}
func retainedVersions(records []Decision, id string) (map[string]any, error) {
	versions := map[string]any{}
	for _, record := range records {
		m := decisionMap(record)
		if text(m, termExperimentID) != id {
			continue
		}
		subjects := decisionSubjects(record.SchemaVersion(), m)
		for kind, items := range subjects {
			for _, subject := range items {
				if err := retainVersion(versions, kind, subject); err != nil {
					return nil, err
				}
			}
		}
	}
	return versions, nil
}
func decisionSubjects(schema string, m map[string]any) map[string][]any {
	subjects := map[string][]any{}
	switch schema {
	case candidateSchema, archiveSchema:
		subjects[termRun] = []any{m[termRun]}
	case replacementSchema:
		subjects[termRun] = []any{m["parent_run"], m["superseded_run"]}
	case publicationSchema:
		if m[termRun] != nil {
			subjects[termRun] = []any{m[termRun]}
		}
		if m[termStudy] != nil {
			subjects[termStudy] = []any{m[termStudy]}
		}
	}
	return subjects
}

type recordPublication struct {
	coordinator *coordinator
	versions    map[string]any
	byVersion   map[string]map[string]any
}

func (p *recordPublication) addRun(run binding.ExperimentRunV1, status string, failures []string) error {
	view, err := transportView(run)
	if err != nil {
		return err
	}
	if err = retainVersion(p.versions, termRun, view); err != nil {
		return err
	}
	p.byVersion[versionKey(termRun, view)] = map[string]any{termExperimentID: p.coordinator.id, termRun: view, "validation_status": status, "failure_codes": nonNilStrings(failures)}
	return nil
}
func (p *recordPublication) currentRun(bundle RecordBundle, index int) error {
	run, checked := bundle.Runs[index], bundle.ValidationRecords[index]
	view, err := transportView(run)
	if err != nil {
		return err
	}
	checkedView, err := transportView(checked)
	if err != nil {
		return err
	}
	id := text(view, termRunID)
	if err = p.addRun(checked, bundle.ValidationByRun[id], bundle.ValidationFailures[id]); err != nil {
		return err
	}
	status, failures := bundle.ValidationByRun[id], bundle.ValidationFailures[id]
	if versionKey(termRun, view) != versionKey(termRun, checkedView) {
		status, failures = termNotPerformed, nil
	}
	return p.addRun(run, status, failures)
}
func (p *recordPublication) freeze(ctx context.Context, bundle RecordBundle) error {
	if len(bundle.Runs) != len(bundle.ValidationRecords) {
		return integrity()
	}
	for _, run := range bundle.RetainedHistory {
		if err := p.addRun(run, termNotPerformed, nil); err != nil {
			return err
		}
	}
	for index := range bundle.Runs {
		if err := p.currentRun(bundle, index); err != nil {
			return err
		}
	}
	for _, key := range slices.Sorted(maps.Keys(p.byVersion)) {
		if _, err := p.coordinator.claim(ctx, publicationSchema, p.byVersion[key]); err != nil {
			return err
		}
	}
	if bundle.Study != nil {
		return p.freezeStudy(ctx, bundle)
	}
	return nil
}
func (p *recordPublication) freezeStudy(ctx context.Context, bundle RecordBundle) error {
	view, err := transportView(bundle.Study)
	if err != nil {
		return err
	}
	if err = retainVersion(p.versions, termStudy, view); err != nil {
		return err
	}
	failures := []string{}
	if bundle.StudyValidation != termPassed {
		failures = []string{"study-validation-failed"}
	}
	_, err = p.coordinator.claim(ctx, publicationSchema, map[string]any{termExperimentID: p.coordinator.id, termStudy: view, "validation_status": bundle.StudyValidation, "failure_codes": failures})
	return err
}
func (c *coordinator) publishRecords(ctx context.Context, bundle RecordBundle, archive Archive, records []Decision) error {
	versions, err := retainedVersions(records, c.id)
	if err != nil {
		return err
	}
	publication := recordPublication{coordinator: c, versions: versions, byVersion: map[string]map[string]any{}}
	if err = publication.freeze(ctx, bundle); err != nil {
		return err
	}
	for _, source := range bundle.Sources {
		_, err = ownerCall(ctx, c, "store", c.options.StoreBudget, func(work context.Context) (struct{}, error) {
			detached, copyErr := detachSource(source)
			if copyErr != nil {
				return struct{}{}, copyErr
			}
			return struct{}{}, archive.WriteSources(work, detached)
		})
		if err != nil {
			return err
		}
	}
	return c.replayPublications(ctx, archive)
}
func (c *coordinator) replayPublications(ctx context.Context, archive Archive) error {
	retained, err := c.load(ctx)
	if err != nil {
		return err
	}
	pending := pendingPublications(retained, c.id)
	for _, candidate := range pending {
		if err = c.writeAndRead(ctx, archive, candidate); err != nil {
			return err
		}
		candidate["state"] = "published"
		if _, err = c.claim(ctx, publicationSchema, candidate); err != nil {
			return err
		}
	}
	return nil
}
func pendingPublications(records []Decision, id string) []map[string]any {
	pending := []map[string]any{}
	for _, d := range records {
		m := decisionMap(d)
		if d.SchemaVersion() == publicationSchema && text(m, termExperimentID) == id && text(m, "state") == termCandidate {
			pending = append(pending, m)
		}
	}
	slices.SortStableFunc(pending, func(a, b map[string]any) int {
		if a[termStudy] == nil && b[termStudy] != nil {
			return -1
		}
		if a[termStudy] != nil && b[termStudy] == nil {
			return 1
		}
		return 0
	})
	return pending
}
func (c *coordinator) writeAndRead(ctx context.Context, archive Archive, candidate map[string]any) error {
	_, err := ownerCall(ctx, c, "store", c.options.StoreBudget, func(work context.Context) (struct{}, error) {
		kind, subject := termRun, candidate[termRun]
		if subject == nil {
			kind, subject = termStudy, candidate[termStudy]
		}
		owner, ownerErr := experimentOwner()
		if ownerErr != nil {
			return struct{}{}, ownerErr
		}
		observed, readErr := archiveRoundTrip(work, archive, kind, subject)
		if readErr != nil {
			return struct{}{}, readErr
		}
		if admission.CheckTransport(observed, runtimeIngress()) != nil {
			return struct{}{}, integrity()
		}
		raw, encodeErr := json.Marshal(observed)
		if encodeErr != nil {
			return struct{}{}, integrity()
		}
		projected, projectErr := admission.ExperimentModelProjection(owner, "experiment-"+kind+"-v1", raw)
		if projectErr != nil || !same(subject, json.RawMessage(projected)) {
			return struct{}{}, integrity()
		}
		return struct{}{}, nil
	})
	return err
}

func archiveRoundTrip(ctx context.Context, archive Archive, kind string, subject any) (any, error) {
	var observed any
	if kind == termRun {
		var run binding.ExperimentRunV1
		if convert(subject, &run) != nil {
			return nil, integrity()
		}
		if writeErr := archive.WriteRun(ctx, run); writeErr != nil {
			return nil, writeErr
		}
		read, readErr := archive.ReadRun(ctx, text(subject, termRunID), text(subject, "run_version"))
		if readErr != nil {
			return nil, readErr
		}
		return read, nil
	}

	var study binding.ExperimentStudyV1
	if convert(subject, &study) != nil {
		return nil, integrity()
	}
	if writeErr := archive.WriteStudy(ctx, study); writeErr != nil {
		return nil, writeErr
	}
	read, readErr := archive.ReadStudy(ctx, text(subject, "study_id"), text(subject, "study_version"))
	if readErr != nil {
		return nil, readErr
	}
	observed = read

	return observed, nil
}
