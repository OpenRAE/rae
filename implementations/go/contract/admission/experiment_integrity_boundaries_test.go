package admission

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"slices"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestExperimentBinaryCoercionMatchesEveryReferenceModel(t *testing.T) {
	var reference struct{ Fields map[string][]string }
	readFullReferenceJSON(t, "testdata/experiment-binary-fields-reference.json", &reference)
	if len(reference.Fields) != 62 {
		t.Fatal("incomplete constructor coercion inventory")
	}
	for model, fields := range reference.Fields {
		t.Run(model, func(t *testing.T) {
			if actual := experimentBinaryFields(model); !slices.Equal(actual, fields) {
				t.Fatalf("binary text leaves = %v, want %v", actual, fields)
			}
		})
	}
	if fields := experimentBinaryFields("StrictStringModel"); len(fields) != 0 {
		t.Fatal("undeclared binary coercion admitted")
	}
}

func TestExperimentYAMLScalarAndContainerRefusalsMatchReference(t *testing.T) {
	var reference struct {
		Cases               []experimentYAMLReferenceCase
		ConstructorFailures []struct{ Name, Text, SourceException string } `json:"constructor_failures"`
	}
	readFullReferenceJSON(t, "testdata/experiment-yaml-scalars-reference.json", &reference)
	if len(reference.Cases) != 73 || len(reference.ConstructorFailures) != 1 {
		t.Fatal("scalar refusal inventory changed", len(reference.Cases))
	}
	for _, test := range reference.Cases {
		t.Run(test.Name, func(t *testing.T) { checkExperimentYAMLReference(t, test) })
	}
	for _, test := range reference.ConstructorFailures {
		t.Run(test.Name, func(t *testing.T) {
			if _, err := ParseExperiment([]byte(test.Text), nil); err == nil {
				t.Fatal("constructor failure was admitted")
			}
		})
	}
}

func TestExperimentTaskPinsAreCheckedAtAuthoringIngress(t *testing.T) {
	owner := boundTestOwner(t)
	structural := schemaOnlyTestOwner(t, owner)
	var documents struct{ Cases []experimentYAMLReferenceCase }
	readFullReferenceJSON(t, "testdata/experiment-yaml-reference.json", &documents)
	var evidence struct {
		Cases []experimentEvidenceReferenceCase
	}
	readFullReferenceJSON(t, "testdata/experiment-evidence-reference.json", &evidence)
	for _, test := range []struct {
		name, field, replacement string
		valid                    bool
	}{{"exact", "", "", true}, {"different-task", "task_id", "foreign-task", false}, {"different-version", "task_version", "foreign-version", false}} {
		t.Run(test.name, func(t *testing.T) {
			document := object(decodeRuleObject(t, string(evidence.Cases[0].Task)))
			if test.field != "" {
				document[test.field] = test.replacement
			}
			raw, err := json.Marshal(document)
			if err != nil {
				t.Fatal(err)
			}
			task, err := structural.Validate(termExperimentTaskV1, raw, experimentProjectionLimits(), nil)
			if err != nil {
				t.Fatal(err)
			}
			_, err = ParseExperiment([]byte(documents.Cases[0].Text), &task)
			if (err == nil) != test.valid {
				t.Fatalf("task pin admission = %v, want %v", err, test.valid)
			}
		})
	}
	wrong := validation.Value{}
	if _, err := ParseExperiment([]byte(documents.Cases[0].Text), &wrong); err == nil {
		t.Fatal("unowned task admitted")
	}
}

func TestParticipantSelectionMustBindEveryRealizedAuthorityPin(t *testing.T) {
	result, err := RealizeParticipantConfiguration(context.Background(), configurationRequestFixture(t))
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	view := object(decodeRuleObject(t, string(raw)))
	owner := boundTestOwner(t)
	var reference struct {
		Cases []experimentEvidenceReferenceCase
	}
	readFullReferenceJSON(t, "testdata/experiment-evidence-reference.json", &reference)
	baseline := array(at(decodeRuleObject(t, string(reference.Cases[0].Run)), "participant_implementation_provenance", "participant_implementations"))[0]
	for _, field := range []string{"", "participant_address", "implementation_identity", "manifest_ref", "manifest_digest", "configuration_digest"} {
		t.Run("pin-"+field, func(t *testing.T) {
			checkParticipantSelectionBoundary(t, view, baseline, field, owner, result)
		})
	}
	if ValidateParticipantConfigurationSelection(nil, result) == nil {
		t.Fatal("unowned selection admitted")
	}
	if ValidateParticipantConfigurationSelection(nil, binding.ParticipantConfigurationResultV1{}) == nil {
		t.Fatal("empty result admitted")
	}
}

type stalledEvidenceReader struct{}

func (stalledEvidenceReader) Read([]byte) (int, error) { return 0, nil }

type failedEvidenceReader struct{}

func (failedEvidenceReader) Read([]byte) (int, error) { return 0, errors.New("private reader detail") }

func TestEvidenceReadersRequireExactBoundedContentAndProgress(t *testing.T) {
	for _, test := range []struct {
		name      string
		reader    io.Reader
		size      int
		algorithm string
		valid     bool
	}{
		{"exact", strings.NewReader("abc"), 3, "sha256", true},
		{"empty", bytes.NewReader(nil), 0, "sha256", true},
		{"short", strings.NewReader("ab"), 3, "sha256", false},
		{"long", strings.NewReader("abcd"), 3, "sha256", false},
		{"no-progress", stalledEvidenceReader{}, 1, "sha256", false},
		{"reader-error", failedEvidenceReader{}, 1, "sha256", false},
		{"unknown-algorithm", strings.NewReader("abc"), 3, "foreign", false},
	} {
		t.Run(test.name, func(t *testing.T) {
			data, checksum, err := readEvidence(test.reader, test.size, test.algorithm)
			if (err == nil) != test.valid {
				t.Fatalf("content admission = %v, want %v", err, test.valid)
			}
			if test.valid && (len(data) != test.size || checksum == "") {
				t.Fatal("admitted content lost its size or checksum")
			}
			if err != nil && strings.Contains(err.Error(), "private") {
				t.Fatal("reader detail escaped")
			}
		})
	}
}

func TestEvidenceLocatorsCannotAcquireFilesystemOrAmbiguousAuthority(t *testing.T) {
	for _, test := range []struct {
		uri   string
		valid bool
	}{
		{"evidence/run.json", true}, {"urn:example:evidence", true},
		{"../run.json", false}, {"run/../evidence.json", false}, {"/run.json", false},
		{"run\\evidence.json", false}, {"file:///run.json", false},
		{"https://example.invalid/run.json#fragment", false}, {"run\n.json", false},
		{"https://user:password@example.invalid/run.json", false},
	} {
		t.Run(test.uri, func(t *testing.T) {
			if err := evidenceLocator(test.uri); (err == nil) != test.valid {
				t.Fatalf("locator admission = %v, want %v", err, test.valid)
			}
		})
	}
}

func TestEvidencePayloadRefusesUnknownContractsAndWrongRepresentations(t *testing.T) {
	owner := boundTestOwner(t)
	for _, test := range []struct{ content, media, contract string }{
		{`{}`, "application/json", "foreign"},
		{`{}`, "application/jsonl", termExperimentEvidenceRecordV1},
		{`[]`, "text/plain", termParticipantBehaviorHistoryEventStreamV1},
		{`{}`, "application/json", termParticipantBehaviorHistoryEventStreamV1},
		{`[]`, "application/json", termExperimentEvidenceRecordV1},
		{`{}`, "application/json", termExperimentEvidenceRecordV1},
		{"{}\n\n{}", "application/jsonl", termParticipantBehaviorHistoryEventStreamV1},
	} {
		t.Run(test.media+"/"+test.contract+"/"+test.content, func(t *testing.T) {
			if _, err := owner.evidenceOutput([]byte(test.content), test.media, test.contract); err == nil {
				t.Fatal("unproved content admitted")
			}
		})
	}
}

func TestEvidenceAcquisitionMapsAreBoundedBeforeReading(t *testing.T) {
	owner := boundTestOwner(t)
	for _, field := range []string{"capture", "record", "reader"} {
		t.Run(field, func(t *testing.T) {
			inputs := ExperimentEvidenceInputs{CaptureSpecs: map[string]validation.Value{}, EvidenceRecords: map[string]validation.Value{}, ArtifactReaders: map[string]io.Reader{}}
			for index := range 1025 {
				key := strings.Repeat("x", index+1)
				switch field {
				case "capture":
					inputs.CaptureSpecs[key] = validation.Value{}
				case "record":
					inputs.EvidenceRecords[key] = validation.Value{}
				case "reader":
					inputs.ArtifactReaders[key] = failedEvidenceReader{}
				}
			}
			if _, err := owner.prepareExperimentEvidence(map[string]any{}, map[string]any{}, inputs); err == nil {
				t.Fatal("unbounded evidence acquisition admitted")
			}
		})
	}
	if err := ValidateExperimentRun(nil, validation.Value{}, validation.Value{}, nil); err == nil {
		t.Fatal("unowned evidence admitted")
	}
	if _, err := ExperimentModelProjection(owner, "foreign", []byte(`{}`)); err == nil {
		t.Fatal("unknown model admitted")
	}
	if _, err := ExperimentModelProjection(owner, termExperimentRunV1, []byte(`[]`)); err == nil {
		t.Fatal("array model admitted")
	}
	if _, err := AdmitFragment(owner, TrialInputRefs, nil, ingress.Limits{MaxBytes: 0}); err == nil {
		t.Fatal("invalid fragment limits admitted")
	}
}

func checkParticipantSelectionBoundary(t *testing.T, view map[string]any, baseline any, field string, owner *Validator, result binding.ParticipantConfigurationResultV1) {
	t.Helper()

	selection := map[string]any{
		"participant_address":     view["participant_address"],
		"implementation_identity": at(view, "configuration", "implementation_identity"),
		"manifest_ref":            view["manifest_ref"], "manifest_digest": view["manifest_digest"],
		"configuration_digest": view["configuration_digest"],
		"configuration_ref":    "configuration:reference", "selected_decision_surface_mode": at(baseline, "selected_decision_surface_mode"),
		"participant_contract_versions": at(baseline, "participant_contract_versions"),
		"exposure_policy":               at(baseline, "exposure_policy"),
	}
	if field == "implementation_identity" {
		selection[field] = map[string]any{"name": "foreign", "version": "1"}
	} else if field != "" {
		selection[field] = "foreign"
		if strings.HasSuffix(field, "digest") {
			selection[field] = "sha256:" + strings.Repeat("0", 64)
		}
	}
	fragment, fragmentErr := AdmitFragment(owner, ParticipantImplementationSelection, selection, experimentProjectionLimits())
	if fragmentErr != nil {
		t.Fatal(fragmentErr)
	}
	err := ValidateParticipantConfigurationSelection(fragment, result)
	if (err == nil) != (field == "") {
		t.Fatalf("authority pin %q admission = %v", field, err)
	}
}
