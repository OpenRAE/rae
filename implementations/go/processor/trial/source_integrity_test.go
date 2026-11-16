package trial

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type mixedSourceBoundaryCase struct{ name, code string }

func TestLinkedMixedSourceBindsSealedTupleInputsAndSelection(t *testing.T) {
	ref := referenceCompilations(t)[0]
	request := compilerRequest(t, ref.Request)
	input, err := prepareInputs(request)
	if err != nil {
		t.Fatal(err)
	}
	var plan trialPlan
	var carrier binding.AdmittedTrialPlanV1
	if decode(ref.Plan, &plan) != nil || decode(ref.Plan, &carrier) != nil {
		t.Fatal("source plan fixture")
	}
	entry := plan.Entries[ref.Instantiation.EntryID]
	pin := mixedSource{PlanID: plan.ID, PlanDigest: plan.Digest, EntryID: entry.ID, EntryDigest: entry.Digest, RunID: entry.RunID}
	outcomes := map[string]selectionOutcome{}
	for _, record := range entry.Selections {
		outcomes[record.Point] = record.Outcome
	}
	fragment, err := fragmentDocument(input.owner, outcomes)
	if err != nil {
		t.Fatal(err)
	}
	selected, err := sdl.Select(request.Family, fragment, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []mixedSourceBoundaryCase{
		{"exact", ""}, {"missing-plan", "composition-source-plan-unresolved"},
		{"unsealed-plan", "composition-source-plan-invalid"},
		{"entry-id", "composition-source-trial-mismatch"}, {"plan-digest", "composition-source-trial-mismatch"},
		{"entry-digest", "composition-source-trial-mismatch"}, {"run-id", "composition-source-trial-mismatch"},
		{"authoring-input", "composition-source-input-mismatch"}, {"task-input", "composition-source-input-mismatch"},
		{"task-digest", "composition-source-input-mismatch"}, {"family-input", "composition-source-input-mismatch"},
	} {
		t.Run(test.name, func(t *testing.T) {
			checkLinkedMixedSourceBoundary(t, request, input, pin, carrier, selected, test)
		})
	}
}

func TestCompilationInputReferencesRequireExactAdmittedPayloads(t *testing.T) {
	ref := referenceCompilations(t)[0]
	request := compilerRequest(t, ref.Request)
	input, err := prepareInputs(request)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := admission.ExperimentProjection(input.owner, request.Experiment)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct{ name, code string }{
		{"family-id", "scenario-family-ref-mismatch"}, {"family-digest", "scenario-family-ref-mismatch"},
		{"authoring-id", "authoring-input-ref-mismatch"}, {"authoring-version", "authoring-input-ref-mismatch"},
		{"authoring-digest", "authoring-input-ref-mismatch"}, {"task-id", "task-ref-mismatch"},
		{"task-digest", "task-ref-mismatch"}, {"study-without-payload", "referenced-input-payload-required"},
		{"association-without-payload", "referenced-input-payload-required"},
	} {
		t.Run(test.name, func(t *testing.T) {
			in := input
			foreign := "foreign"
			switch test.name {
			case "family-id":
				in.refs.Family.ID = foreign
			case "family-digest":
				in.refs.Family.Digest = &foreign
			case "authoring-id":
				in.refs.Authoring.ID = foreign
			case "authoring-version":
				in.refs.Authoring.Version = &foreign
			case "authoring-digest":
				in.refs.Authoring.Digest = &foreign
			case "task-id":
				in.refs.Task.ID = foreign
			case "task-digest":
				in.refs.TaskDigest = foreign
			case "study-without-payload":
				in.refs.Study = &reference{ID: foreign}
			case "association-without-payload":
				in.refs.Associated = &reference{ID: foreign}
			}
			err := validateInputPins(request, in, raw)
			var refusal *compilationRefusalError
			if !errors.As(err, &refusal) || refusal.code != test.code {
				t.Fatalf("input reference refusal = %v, want %s", err, test.code)
			}
		})
	}
}

func TestRealizationRefusesMissingOwnersAndEntryAuthority(t *testing.T) {
	ref := referenceCompilations(t)[6]
	request := compilerRequest(t, ref.Request)
	var plan binding.AdmittedTrialPlanV1
	if json.Unmarshal(ref.Plan, &plan) != nil {
		t.Fatal("plan fixture")
	}
	baseline := RealizationInputs{Plan: plan, Family: request.Family, Experiment: request.Experiment, Task: request.Task, RealizationEnvelope: request.RealizationEnvelope, CaptureSpecs: request.CaptureSpecs, ApparatusManifests: request.ApparatusManifests, BackendKey: ApparatusManifestKey{ComponentKind: componentBackend, ComponentName: "backend-a", ComponentVersion: "1", ManifestVersion: "backend-manifest/v2"}}
	for _, field := range []string{"plan", "entry", "family", "experiment", "task", "envelope", "backend", "manifests"} {
		t.Run(field, func(t *testing.T) {
			input, entry := baseline, ref.Instantiation.EntryID
			switch field {
			case "plan":
				input.Plan = binding.AdmittedTrialPlanV1{}
			case "entry":
				entry = "foreign-entry"
			case "family":
				input.Family = nil
			case "experiment":
				input.Experiment = validation.Value{}
			case "task":
				input.Task = binding.ExperimentTaskV1{}
			case "envelope":
				input.RealizationEnvelope = validation.Value{}
			case "backend":
				input.BackendKey = ApparatusManifestKey{}
			case "manifests":
				input.ApparatusManifests = nil
			}
			if _, err := RealizeEntry(input, entry, RealizationOptions{}); err == nil {
				t.Fatal("missing realization authority admitted")
			}
		})
	}
	if _, err := InstantiateEntry(plan, "foreign-entry", request.Family); err == nil {
		t.Fatal("foreign entry instantiated")
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if _, err := Readmit(ctx, plan, request); !errors.Is(err, context.Canceled) {
		t.Fatal("readmission lost cancellation", err)
	}
	request.Experiment = validation.Value{}
	if _, err := Readmit(t.Context(), plan, request); err == nil {
		t.Fatal("readmission accepted missing original inputs")
	}
}

func TestCleanupSupportRequiresDeclaredActionsProbesAndReuse(t *testing.T) {
	for _, test := range []struct {
		name string
		want bool
	}{{"exact", true}, {"missing", false}, {"action", false}, {"residual", false}, {"probe", false}, {"reuse", false}} {
		t.Run(test.name, func(t *testing.T) {
			cleanup := &cleanupSupport{Actions: []string{"release"}, Methods: []string{"probe"}, Residual: true, Reusable: true}
			var requirements cleanupRequirements
			requirements.CleanState.Mode = termDeclaredReusable
			requirements.CleanState.Probes = []string{"probe:state"}
			if decode([]byte(`{"resource":{"action_kind":"release","requirement":"required","verification_probe_refs":["probe:resource"]}}`), &requirements.Obligations) != nil {
				t.Fatal("cleanup obligation fixture")
			}
			switch test.name {
			case "missing":
				cleanup = nil
			case "action":
				cleanup.Actions = nil
			case "residual":
				cleanup.Residual = false
			case "probe":
				cleanup.Methods = nil
			case "reuse":
				cleanup.Reusable = false
			}
			if err := admitCleanupSupport(cleanup, requirements); (err == nil) != test.want {
				t.Fatalf("cleanup support = %v, want %v", err, test.want)
			}
		})
	}
}

func TestReplacementCoordinatesMatchRecordedChildAllocation(t *testing.T) {
	var reference struct {
		Request referenceRequest `json:"request"`
		Cases   []struct {
			Expected replacementWire `json:"expected"`
		} `json:"cases"`
	}
	readTrialBoundaryJSON(t, "testdata/replacement-reference.json.gz", &reference)
	request := compilerRequest(t, reference.Request)
	input, err := prepareInputs(request)
	if err != nil {
		t.Fatal(err)
	}
	for _, index := range []int{0, 1} {
		checkRecordedReplacementCoordinate(t, request, input, reference.Cases[index].Expected)
	}
}
func checkRecordedReplacementCoordinate(t *testing.T, request Request, input compilationInputs, child replacementWire) {
	t.Helper()
	if child.Plan == nil {
		t.Fatal("missing recorded child")
	}
	raw, encodeErr := encoded(child.Plan)
	if encodeErr != nil {
		t.Fatal(encodeErr)
	}
	var plan trialPlan
	if decode(raw, &plan) != nil {
		t.Fatal("child plan fixture")
	}
	coordinates, coordinateErr := authoringCoordinates(input.spec, request.Limits, plan)
	if coordinateErr != nil || len(coordinates) != 1 {
		t.Fatal("replacement coordinate reconstruction", coordinateErr)
	}
	for _, entry := range plan.Entries {
		left, _ := encoded(coordinates[0])
		right, _ := encoded(entry.Coordinate)
		if !sameJSON(left, right) {
			t.Fatal("replacement reused the wrong logical coordinate")
		}
	}
	plan.ReplacementOrigin = json.RawMessage(`{"root_plan_id":"foreign","root_entry_id":"foreign"}`)
	if _, err := authoringCoordinates(input.spec, request.Limits, plan); err == nil {
		t.Fatal("foreign replacement origin admitted")
	}
	plan.ReplacementOrigin = json.RawMessage(`{`)
	if _, err := authoringCoordinates(input.spec, request.Limits, plan); err == nil {
		t.Fatal("malformed replacement origin admitted")
	}
}

func readTrialBoundaryJSON(t *testing.T, name string, target any) {
	t.Helper()
	raw, err := readCompressedReference(name)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, target); err != nil {
		t.Fatal(err)
	}
}

func TestTypedEffectEquivalenceRejectsMalformedOrUnresolvedContent(t *testing.T) {
	for _, test := range []struct {
		name  string
		check func() error
	}{
		{"assets", func() error { _, err := typedParticipantEffects(nil, json.RawMessage(`[]`)); return err }},
		{"configuration", func() error {
			_, err := typedParticipantEffects([]json.RawMessage{json.RawMessage(`{`)}, json.RawMessage(`{}`))
			return err
		}},
		{"value", func() error { _, err := typedConfigurationEffect(json.RawMessage(`{`), nil); return err }},
		{"selection", func() error {
			_, err := typedConfigurationEffect(json.RawMessage(`{"control_context_selection":[]}`), nil)
			return err
		}},
		{"missing-context", func() error {
			_, err := typedConfigurationEffect(json.RawMessage(`{"control_context_selection":{"slot_id":"prompt","declaration_ref":"control_context_assets.missing"}}`), nil)
			return err
		}},
		{"context-value", func() error {
			_, err := typedConfigurationEffect(json.RawMessage(`{"control_context_selection":{"slot_id":"prompt","declaration_ref":"control_context_assets.asset"}}`), map[string]json.RawMessage{"asset": json.RawMessage(`[]`)})
			return err
		}},
		{"participant-value", func() error {
			_, err := typedParticipantEffects([]json.RawMessage{json.RawMessage(`{"participant_address":"p","configuration":{"values":[{"control_context_selection":[]}]}}`)}, json.RawMessage(`{}`))
			return err
		}},
		{"provenance", func() error { _, err := operativeProvenance(json.RawMessage(`{`)); return err }},
		{"binding", func() error { _, err := bindingEffects([]json.RawMessage{json.RawMessage(`{`)}, true); return err }},
		{"binding-target", func() error {
			_, err := bindingEffects([]json.RawMessage{json.RawMessage(`{"descriptor":{"target":[]}}`)}, true)
			return err
		}},
		{"scalar-configuration", func() error { _, err := scalarParticipantEffects([]json.RawMessage{json.RawMessage(`{`)}); return err }},
		{"canonical-rows", func() error { _, err := canonicalRows([]json.RawMessage{json.RawMessage(`{`)}); return err }},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := test.check(); err == nil {
				t.Fatal("malformed operative content contributed a treatment signature")
			}
		})
	}
}

func TestAuthoringReplayRejectsContradictoryProfilesCoordinatesAndBindings(t *testing.T) {
	ref := referenceCompilations(t)[0]
	request := compilerRequest(t, ref.Request)
	input, err := prepareInputs(request)
	if err != nil {
		t.Fatal(err)
	}
	var original trialPlan
	if decode(ref.Plan, &original) != nil {
		t.Fatal("plan fixture")
	}
	for _, test := range []struct {
		name  string
		check func() error
	}{
		{"design-shape", func() error {
			in := input
			in.spec.Factorial = json.RawMessage(`[]`)
			return authoringSelections(request, in, original)
		}},
		{"profile-shape", func() error {
			p := original
			p.Profiles = json.RawMessage(`[]`)
			return authoringSelections(request, input, p)
		}},
		{"unrequested-treatment-profile", func() error {
			p := original
			p.Profiles = json.RawMessage(`{"treatment_profile":"factorial-treatment-v1"}`)
			return authoringSelections(request, input, p)
		}},
		{"foreign-coordinate", func() error {
			p := original
			p.Entries = map[string]trialEntry{"foreign": {Coordinate: coordinate{}}}
			return authoringCoordinateMembership([]coordinate{}, p)
		}},
		{"changed-selection", func() error {
			return checkAuthoringEntries(trialPlan{Entries: map[string]trialEntry{"entry": {Selections: []selectionRecord{{Point: "foreign"}}}}}, map[string][]selectionRecord{}, nil)
		}},
		{"malformed-selection", func() error {
			return checkAuthoringEntries(trialPlan{Entries: map[string]trialEntry{"entry": {Selections: []selectionRecord{{Treatment: json.RawMessage(`{`)}}}}}, map[string][]selectionRecord{}, nil)
		}},
		{"malformed-expected-selection", func() error {
			key, _ := canonical(coordinate{})
			return checkAuthoringEntries(trialPlan{Entries: map[string]trialEntry{"entry": {}}}, map[string][]selectionRecord{string(key): {{Treatment: json.RawMessage(`{`)}}}, nil)
		}},
		{"malformed-binding", func() error {
			return authoringEntryBindings(trialEntry{}, []admittedDescriptor{{raw: json.RawMessage(`{`)}})
		}},
		{"changed-binding", func() error {
			return authoringEntryBindings(trialEntry{Bindings: []json.RawMessage{json.RawMessage(`{"descriptor":{"binding_id":"foreign"}}`)}}, nil)
		}},
		{"malformed-binding-list", func() error {
			return authoringEntryBindings(trialEntry{Bindings: []json.RawMessage{json.RawMessage(`{`)}}, nil)
		}},
		{"malformed-capture-relation", func() error {
			in := input
			in.spec.RunPlan.EvidenceRelations = []json.RawMessage{json.RawMessage(`{`)}
			_, err := captureInputs(request, in)
			return err
		}},
		{"unsupported-plan-payload", func() error {
			_, err := processorReference(input.owner, "run", "provisioning", "provisioning-plan-v1", make(chan int))
			return err
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := test.check(); err == nil {
				t.Fatal("contradictory original inputs admitted")
			}
		})
	}
}

func checkLinkedMixedSourceBoundary(t *testing.T, request Request, input compilationInputs, pin mixedSource, carrier binding.AdmittedTrialPlanV1, selected sdl.InstantiatedScenario, test mixedSourceBoundaryCase) {
	t.Helper()

	r, in, source := request, input, pin
	r.SourcePlans = map[string]binding.AdmittedTrialPlanV1{pin.PlanID: carrier}
	switch test.name {
	case "missing-plan":
		r.SourcePlans = nil
	case "unsealed-plan":
		r.SourcePlans[pin.PlanID] = binding.AdmittedTrialPlanV1{}
	case "entry-id":
		source.EntryID = "foreign-entry"
	case "plan-digest":
		source.PlanDigest = "sha256:" + strings.Repeat("0", 64)
	case "entry-digest":
		source.EntryDigest = "sha256:" + strings.Repeat("0", 64)
	case "run-id":
		source.RunID = "foreign-run"
	case "authoring-input":
		in.refs.Authoring.ID = "foreign-authoring"
	case "task-input":
		in.refs.Task.ID = "foreign-task"
	case "task-digest":
		in.refs.TaskDigest = "sha256:" + strings.Repeat("0", 64)
	case "family-input":
		in.refs.Family.ID = "foreign-family"
	}
	err := validateMixedSource(r, in, source, selected)
	if test.code == "" {
		if err != nil {
			t.Fatal(err)
		}
		return
	}
	var refusal *compilationRefusalError
	if !errors.As(err, &refusal) || refusal.code != test.code {
		t.Fatalf("linked source refusal = %v, want %s", err, test.code)
	}
}
