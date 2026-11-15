package admission

import (
	"strings"
	"time"

	"github.com/OpenRAE/rae/implementations/go/internal/base/timestamp"
)

func evidenceRecordBinding(task, run any, source evidenceRequirement, record any) error {
	spec, requirement := source.spec, source.requirement
	ref := map[string]any{fieldRefKind: termCaptureSpec, fieldRefID: at(spec, "capture_spec_id"), fieldRefVersion: at(spec, "spec_version")}
	if !referenceSatisfies(ref, at(record, "capture_spec_ref")) || !equal(at(record, "capture_requirement_ref"), at(requirement, "requirement_id")) || !matchingFields(record, requirement, "output_contract") || !equal(at(record, "evidence_kind"), at(requirement, "capture_kind")) {
		return invalid()
	}
	if err := evidenceExecutionIdentity(task, run, record); err != nil {
		return err
	}
	if err := evidenceWindow(run, spec, requirement, record); err != nil {
		return err
	}
	if err := evidenceDisclosure(requirement, record); err != nil {
		return err
	}
	return evidenceSource(run, requirement, record)
}
func evidenceExecutionIdentity(task, run, record any) error {
	ref := map[string]any{fieldRefKind: kindRun, fieldRefID: at(run, termRunID), fieldRefVersion: at(run, "run_version")}
	if !referenceSatisfies(ref, at(record, "run_ref")) {
		return invalid()
	}
	if taskRef := at(record, "task_ref"); taskRef != nil && (!equal(at(taskRef, fieldRefID), at(task, "task_id")) || !equal(at(taskRef, fieldRefVersion), at(task, "task_version"))) {
		return invalid()
	}
	apparatus := at(run, "apparatus_context")
	ref = map[string]any{fieldRefKind: "apparatus-context", fieldRefID: at(apparatus, "apparatus_context_id"), fieldRefVersion: at(apparatus, "context_version")}
	return require(at(record, "apparatus_context_ref") == nil || referenceSatisfies(ref, at(record, "apparatus_context_ref")))
}
func evidenceWindow(run, spec, requirement, record any) error {
	id := stringAt(record, "capture_window_ref")
	if !set(at(requirement, "window_refs"))[id] {
		return invalid()
	}
	var window any
	count := 0
	for _, candidate := range array(at(spec, "capture_windows")) {
		if stringAt(candidate, "window_id") == id {
			window = candidate
			count++
		}
	}
	if count != 1 {
		return invalid()
	}
	start, end, err := evidenceWindowBounds(run, window)
	if err != nil {
		return err
	}
	captured, err := timestamp.ParseRFC3339("captured_at", stringAt(record, "captured_at"))
	if err != nil {
		return invalid()
	}
	return require((start == nil || !captured.Instant().Before(*start)) && (end == nil || !captured.Instant().After(*end)))
}
func evidenceWindowBounds(run, window any) (*time.Time, *time.Time, error) {
	start, err := evidenceTime(window, "starts_at")
	if err != nil {
		return nil, nil, err
	}
	end, err := evidenceTime(window, "ends_at")
	if err != nil {
		return nil, nil, err
	}
	kind := stringAt(window, "window_kind")
	if kind == "run" || kind == "task" {
		return evidenceRunWindow(run, start, end)
	}
	if kind == "interval" && (start == nil || end == nil) || start == nil && end == nil {
		return nil, nil, invalid()
	}
	return start, end, nil
}
func evidenceRunWindow(run any, start, end *time.Time) (*time.Time, *time.Time, error) {
	runStart, err := evidenceTime(run, "started_at")
	if err != nil || runStart == nil {
		return nil, nil, invalid()
	}
	runEnd, err := evidenceTime(run, "ended_at")
	if err != nil || runEnd == nil {
		return nil, nil, invalid()
	}
	if start == nil || start.Before(*runStart) {
		start = runStart
	}
	if end == nil || end.After(*runEnd) {
		end = runEnd
	}
	return start, end, nil
}

func evidenceTime(root any, field string) (*time.Time, error) {
	if at(root, field) == nil {
		return nil, nil //nolint:nilnil // Absence is a valid unbounded window endpoint.
	}
	value, err := timestamp.ParseRFC3339(field, stringAt(root, field))
	if err != nil {
		return nil, invalid()
	}
	instant := value.Instant()
	return &instant, nil
}
func evidenceDisclosure(requirement, record any) error {
	if !matchingFields(requirement, record, "sensitivity", "redaction_policy") {
		return invalid()
	}
	if at(requirement, "redaction_policy") != nil {
		return invalid()
	}
	expected := postureNone
	if stringAt(requirement, "sensitivity") == "redacted" {
		expected = "redacted"
	}
	return require(stringAt(record, "redaction_state") == expected && (stringAt(record, "redaction_state") != postureNone || at(record, "raw_content", "loss_disclosure") == nil))
}
func evidenceSource(run, requirement, record any) error {
	required := at(requirement, "channel_ref")
	sourceMatches := false
	for _, source := range array(at(record, "source_refs")) {
		if matchingFields(source, required, fieldRefKind, fieldRefID) && (at(required, fieldRefVersion) == nil || equal(at(source, fieldRefVersion), at(required, fieldRefVersion))) {
			sourceMatches = true
			break
		}
	}
	if !sourceMatches {
		return invalid()
	}
	for _, channel := range array(at(run, "apparatus_context", "measurement_channels")) {
		if !referenceSatisfies(channel, required) {
			continue
		}
		for _, source := range array(at(record, "source_refs")) {
			if referenceSatisfies(channel, source) {
				return nil
			}
		}
	}
	return invalid()
}
func evidenceArtifact(run, record any) (any, error) {
	raw := at(record, "raw_content")
	ref := at(raw, "artifact_ref")
	candidates := []any{}
	for _, artifact := range array(at(run, "evidence_artifacts")) {
		if ref != nil {
			if equal(at(artifact, termArtifactID), at(ref, termArtifactID)) {
				candidates = append(candidates, artifact)
			}
			continue
		}
		if at(raw, "content_uri") != nil && at(raw, "content_checksum") != nil && equal(at(artifact, "uri"), at(raw, "content_uri")) && equal(at(artifact, "checksum", "algorithm"), at(raw, "content_checksum", "algorithm")) && strings.EqualFold(stringAt(artifact, "checksum", termValue), stringAt(raw, "content_checksum", termValue)) {
			candidates = append(candidates, artifact)
		}
	}
	if len(candidates) != 1 || ref != nil && !equal(ref, candidates[0]) {
		return nil, invalid()
	}
	return candidates[0], nil
}
