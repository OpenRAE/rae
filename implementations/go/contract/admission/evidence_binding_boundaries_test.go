package admission

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestEvidenceRecordPinsEveryExecutionAndCaptureAuthority(t *testing.T) {
	var reference struct {
		Cases []experimentEvidenceReferenceCase
	}
	readFullReferenceJSON(t, "testdata/experiment-evidence-reference.json", &reference)
	ref := reference.Cases[0]
	for _, test := range []struct {
		name, target, field string
		value               any
	}{
		{"exact", "", "", nil},
		{"capture-spec", "capture", "capture_spec_id", "foreign"},
		{"requirement", "requirement", "requirement_id", "foreign"},
		{"contract", "record", "output_contract", "foreign"},
		{"kind", "record", "evidence_kind", "foreign"},
		{"run", "run-ref", "ref_id", "foreign"},
		{"run-version", "run-ref", "ref_version", "foreign"},
		{"task", "task-ref", "ref_id", "foreign"},
		{"task-version", "task-ref", "ref_version", "foreign"},
		{"apparatus", "apparatus-ref", "ref_id", "foreign"},
		{"apparatus-version", "apparatus-ref", "ref_version", "foreign"},
		{"window", "record", "capture_window_ref", "foreign"},
		{"invalid-time", "record", "captured_at", "invalid"},
		{"before-window", "record", "captured_at", "1900-01-01T00:00:00Z"},
		{"after-window", "record", "captured_at", "9999-01-01T00:00:00Z"},
		{"sensitivity", "record", "sensitivity", "redacted"},
		{"redaction", "record", "redaction_state", "redacted"},
		{"sources", "record", "source_refs", []any{}},
		{"installed-channel", "apparatus", "measurement_channels", []any{}},
	} {
		t.Run(test.name, func(t *testing.T) {
			task := decodeRuleObject(t, string(ref.Task))
			run := decodeRuleObject(t, string(ref.Run))
			capture := decodeRuleObject(t, string(ref.Capture))
			record := decodeRuleObject(t, string(ref.Record))
			if at(record, "apparatus_context_ref") == nil {
				object(record)["apparatus_context_ref"] = map[string]any{"ref_kind": "apparatus-context", "ref_id": at(run, "apparatus_context", "apparatus_context_id"), "ref_version": at(run, "apparatus_context", "context_version")}
			}
			requirement := at(capture, "capture_requirements", stringAt(record, "capture_requirement_ref"))
			targets := map[string]any{"capture": capture, "record": record, "requirement": requirement, "run-ref": at(record, "run_ref"), "task-ref": at(record, "task_ref"), "apparatus-ref": at(record, "apparatus_context_ref"), "apparatus": at(run, "apparatus_context")}
			if test.target != "" {
				target := object(targets[test.target])
				if target == nil {
					t.Fatal("missing authority fixture", test.target)
				}
				target[test.field] = test.value
			}
			err := evidenceRecordBinding(task, run, evidenceRequirement{capture, requirement}, record)
			if (err == nil) != (test.name == "exact") {
				t.Fatalf("evidence authority admission = %v", err)
			}
		})
	}
}

func TestEvidenceWindowsRequireKnownTimesWithinTheRun(t *testing.T) {
	run := map[string]any{"started_at": "2026-11-15T10:00:00Z", "ended_at": "2026-11-15T11:00:00Z"}
	for _, test := range []struct {
		name   string
		window map[string]any
		valid  bool
	}{
		{"run", map[string]any{"window_kind": "run"}, true},
		{"bounded-run", map[string]any{"window_kind": "run", "starts_at": "2026-11-15T09:00:00Z", "ends_at": "2026-11-15T12:00:00Z"}, true},
		{"interval", map[string]any{"window_kind": "interval", "starts_at": "2026-11-15T10:15:00Z", "ends_at": "2026-11-15T10:30:00Z"}, true},
		{"missing-interval-end", map[string]any{"window_kind": "interval", "starts_at": "2026-11-15T10:15:00Z"}, false},
		{"unbounded-event", map[string]any{"window_kind": "event"}, false},
		{"invalid-start", map[string]any{"window_kind": "run", "starts_at": "invalid"}, false},
		{"invalid-end", map[string]any{"window_kind": "run", "ends_at": "invalid"}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			start, end, err := evidenceWindowBounds(run, test.window)
			if (err == nil) != test.valid {
				t.Fatal("window admission", err)
			}
			if test.valid && (start == nil || end == nil || start.After(*end)) {
				t.Fatal("valid window lost its bounds")
			}
		})
	}
	for _, field := range []string{"started_at", "ended_at"} {
		broken := map[string]any{"started_at": run["started_at"], "ended_at": run["ended_at"]}
		delete(broken, field)
		if _, _, err := evidenceWindowBounds(broken, map[string]any{"window_kind": "run"}); err == nil {
			t.Fatal("missing run endpoint admitted", field)
		}
		broken[field] = "invalid"
		if _, _, err := evidenceWindowBounds(broken, map[string]any{"window_kind": "task"}); err == nil {
			t.Fatal("invalid run endpoint admitted", field)
		}
	}
}

func TestEvidenceArtifactLookupRequiresExactUniqueMetadata(t *testing.T) {
	artifact := map[string]any{"artifact_id": "a", "uri": "evidence/a.json", "checksum": map[string]any{"algorithm": "sha256", "value": strings.Repeat("a", 64)}}
	for _, test := range []struct {
		name      string
		artifacts []any
		raw       any
		valid     bool
	}{
		{"exact-reference", []any{artifact}, map[string]any{"artifact_ref": artifact}, true},
		{"exact-locator", []any{artifact}, map[string]any{"content_uri": artifact["uri"], "content_checksum": artifact["checksum"]}, true},
		{"missing", nil, map[string]any{"artifact_ref": artifact}, false},
		{"duplicate", []any{artifact, artifact}, map[string]any{"artifact_ref": artifact}, false},
		{"wrong-metadata", []any{artifact}, map[string]any{"artifact_ref": map[string]any{"artifact_id": "a", "uri": "foreign"}}, false},
		{"wrong-locator", []any{artifact}, map[string]any{"content_uri": "foreign", "content_checksum": artifact["checksum"]}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			_, err := evidenceArtifact(map[string]any{"evidence_artifacts": test.artifacts}, map[string]any{"raw_content": test.raw})
			if (err == nil) != test.valid {
				t.Fatal("artifact identity admission", err)
			}
		})
	}
}

func TestEvidenceRelationAndProducerInputsRetainConcreteAuthority(t *testing.T) {
	owner := boundTestOwner(t)
	structural := schemaOnlyTestOwner(t, owner)
	var reference struct {
		Cases []experimentEvidenceReferenceCase
	}
	readFullReferenceJSON(t, "testdata/experiment-evidence-reference.json", &reference)
	ref := reference.Cases[0]
	capture, err := structural.Validate(contractExperimentCapture, ref.Capture, experimentProjectionLimits(), nil)
	if err != nil {
		t.Fatal(err)
	}
	if err := owner.experimentEvidenceRelations(nil, ExperimentEvidenceInputs{CaptureSpecs: map[string]validation.Value{"capture": capture}}); err != nil {
		t.Fatal("valid concrete capture authority refused", err)
	}
	if err := owner.experimentEvidenceRelations([]any{map[string]any{}}, ExperimentEvidenceInputs{}); err == nil {
		t.Fatal("malformed relation admitted")
	}
	if err := owner.experimentEvidenceRelations(nil, ExperimentEvidenceInputs{CaptureSpecs: map[string]validation.Value{"capture": {}}}); err == nil {
		t.Fatal("unowned capture value admitted")
	}
	for _, valid := range []bool{false, true} {
		producer := map[string]any{"ref_kind": "processor", "ref_id": "p", "ref_version": "1"}
		run := map[string]any{"augmentation_disclosures": []any{map[string]any{"augmented_by_ref": producer}}, "apparatus_context": map[string]any{"components": map[string]any{}}}
		if valid {
			object(at(run, "apparatus_context"))["components"] = map[string]any{"processor": map[string]any{"component_kind": "processor", "identity": map[string]any{"name": "p", "version": "1"}}}
		}
		if err := evidenceAugmentationProducers(run); (err == nil) != valid {
			t.Fatal("augmentation producer authority", err)
		}
	}
	for _, value := range []any{json.Number("-1"), json.Number("1.5"), json.Number("268435457"), "1"} {
		if err := evidenceArtifactBounds(map[string]any{"evidence_artifacts": []any{map[string]any{"size_bytes": value}}}); err == nil {
			t.Fatal("invalid artifact size admitted", value)
		}
	}
}
