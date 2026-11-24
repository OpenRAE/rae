package trial

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestCompilerReconstructionRefusesIncompleteCarriersAndUnownedAuthority(t *testing.T) {
	request := compilerRequest(t, referenceCompilations(t)[0].Request)
	input, err := prepareInputs(request)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name  string
		check func() error
	}{
		{"family-payload", func() error { r := request; r.Family = nil; _, err := input.authoredInputs(r); return err }},
		{"envelope-handle", func() error {
			r := request
			r.RealizationEnvelope = validation.Value{}
			return input.realizationEnvelope(r)
		}},
		{"authority-profile", func() error { r := request; r.ExecutionAuthority = nil; return input.authorityFragments(r) }},
		{"family-pins", func() error { r := request; r.Family = nil; return validateInputPins(r, input, nil) }},
		{"authoring-bytes", func() error { return validateInputPins(request, input, []byte(`{`)) }},
		{"task-carrier", func() error { _, _, err := admitTaskPins(input.owner, binding.ExperimentTaskV1{}); return err }},
		{"capture-carrier", func() error {
			_, err := admitCapturePin(input.owner, "capture", binding.ExperimentCaptureSpecV1{}, reference{}, reference{})
			return err
		}},
		{"participant-carrier", func() error {
			_, err := admitParticipantManifest(input.owner, binding.ParticipantImplementationManifestV1{}, participantManifestReference{})
			return err
		}},
		{"apparatus-members", func() error {
			in := input
			in.apparatusJSON = json.RawMessage(`{`)
			_, err := selectedApparatus(request, in)
			return err
		}},
		{"participant-members", func() error {
			in := input
			in.apparatusJSON = json.RawMessage(`{`)
			_, err := participantAuthorities(request, in)
			return err
		}},
		{"missing-apparatus", func() error { return admitApparatusEnvelope(request, apparatusBinding{}, apparatusSelection{}) }},
		{"missing-envelope", func() error {
			r := request
			r.RealizationEnvelope = validation.Value{}
			return admitApparatusEnvelope(r, apparatusBinding{}, apparatusSelection{backends: map[ApparatusManifestKey]binding.BackendManifestV2{{}: {}}})
		}},
		{"instantiation-owner", func() error { _, _, err := instantiationFamily(reference{}, nil); return err }},
		{"instantiation-pin", func() error { _, _, err := instantiationFamily(reference{}, request.Family); return err }},
		{"plan-carrier", func() error {
			_, err := InstantiateEntry(binding.AdmittedTrialPlanV1{}, "entry", request.Family)
			return err
		}},
		{"schedule-handle", func() error { _, err := PlanBatchScheduleValue(validation.Value{}); return err }},
		{"coordinate-profile", func() error { _, err := RealizationAssignmentKey(nil); return err }},
		{"coordinate-carrier", func() error { _, err := assignmentKey([]byte(`{"unexpected":1}`)); return err }},
		{"capture-relation-bytes", func() error {
			in := input
			in.spec.RunPlan.EvidenceRelations = []json.RawMessage{json.RawMessage(`{`)}
			_, err := captureInputs(request, in)
			return err
		}},
		{"capture-relation-authority", func() error {
			in := input
			in.spec.RunPlan.EvidenceRelations = []json.RawMessage{json.RawMessage(`{}`)}
			_, err := captureInputs(request, in)
			return err
		}},
		{"processor-reference-content", func() error {
			_, err := processorReference(input.owner, "run", "provisioning", "provisioning-plan-v1", json.RawMessage(`{`))
			return err
		}},
		{"mixed-carrier", func() error { _, _, err := mixedBinding(input.owner, nil); return err }},
		{"trial-control-carrier", func() error {
			return admitTrialControls(binding.BackendManifestV2{}, executionControls{}, cleanupTemplate{})
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := test.check(); err == nil {
				t.Fatal("incomplete or unowned compiler input admitted")
			}
		})
	}
}
func TestCompilerSelectedManifestsCannotSubstituteIdentityDigestOrDuplicateAuthority(t *testing.T) {
	request := compilerRequest(t, referenceCompilations(t)[5].Request)
	input, err := prepareInputs(request)
	if err != nil {
		t.Fatal(err)
	}
	var apparatus apparatusBinding
	if decode(input.apparatusJSON, &apparatus) != nil || len(apparatus.Manifests) == 0 || len(apparatus.Participants) == 0 {
		t.Fatal("manifest fixture")
	}
	for _, field := range []string{"missing", "identity", "digest", "duplicate"} {
		t.Run("apparatus-"+field, func(t *testing.T) { checkSelectedApparatusBoundary(t, request, input, apparatus.Manifests[0], field) })
	}
	selected := apparatus.Participants[0]
	key := ParticipantManifestKey{ParticipantAddress: selected.Address, ImplementationName: selected.Name, ImplementationVersion: selected.Version, ManifestVersion: selected.ManifestVersion}
	for _, field := range []string{"identity", "digest"} {
		ref := selected
		if field == "identity" {
			ref.Name = "foreign"
		} else {
			ref.ManifestDigest = "sha256:foreign"
		}
		if _, err := admitParticipantManifest(input.owner, request.ParticipantManifests[key], ref); err == nil {
			t.Fatal("participant authority substitution admitted", field)
		}
	}
}
func TestEntryRefusalsKeepDeterministicDiagnosticsAndOwnerErrors(t *testing.T) {
	failures := entryFailures{}
	if err := failures.add(trialInvalid(), coordinate{}); err != nil {
		t.Fatal(err)
	}
	result := failures.result()
	if result == nil || result.Error() != "entry-invalid" {
		t.Fatal("closed construction refusal lost", result)
	}
	if got := (&captureAdmissionError{}).Error(); got != "trial-capture-admission-failed" {
		t.Fatal("capture error leaked detail", got)
	}
	for _, test := range []struct {
		left, right compilationRefusalError
		want        int
	}{
		{compilationRefusalError{address: "a"}, compilationRefusalError{address: "b"}, -1},
		{compilationRefusalError{address: "a", code: "b"}, compilationRefusalError{address: "a", code: "a"}, 1},
	} {
		if got := failureOrder(&test.left, &test.right); got != test.want {
			t.Fatal("diagnostic order changed", got)
		}
	}
}

func checkSelectedApparatusBoundary(t *testing.T, request Request, input compilationInputs, ref reference, field string) {
	t.Helper()
	r := request
	key, keyErr := apparatusReferenceKey(ref)
	if keyErr != nil {
		t.Fatal(keyErr)
	}
	foreign := "foreign"
	switch field {
	case "missing":
		r.ApparatusManifests = nil
	case "identity":
		ref.ID = foreign
	case "digest":
		ref.Digest = &foreign
	case "duplicate":
		if _, err := loadApparatusSelection(r, input, []reference{ref, ref}); err == nil {
			t.Fatal("duplicate concrete authority admitted")
		}
		return
	}
	if _, err := resolveApparatusReference(r, input, key, ref, "missing selected manifest"); err == nil {
		t.Fatal("selected manifest substitution admitted")
	}
}
