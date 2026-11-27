package trial

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type referenceRequest struct {
	Family     json.RawMessage          `json:"family"`
	Experiment json.RawMessage          `json:"experiment"`
	Task       binding.ExperimentTaskV1 `json:"task"`
	InputRefs  json.RawMessage          `json:"input_refs"`
	Apparatus  json.RawMessage          `json:"apparatus"`
	Envelope   json.RawMessage          `json:"realization_envelope"`
	Authority  json.RawMessage          `json:"execution_authority"`
	Manifests  []struct {
		Key      []string        `json:"key"`
		Manifest json.RawMessage `json:"manifest"`
	} `json:"apparatus_manifests"`
	Participants []struct {
		Key      []string                                    `json:"key"`
		Manifest binding.ParticipantImplementationManifestV1 `json:"manifest"`
	} `json:"participant_manifests"`
	CaptureSpecs map[string]binding.ExperimentCaptureSpecV1 `json:"capture_specs"`
}
type referenceCompilation struct {
	Realization   json.RawMessage  `json:"realization"`
	Name          string           `json:"name"`
	Request       referenceRequest `json:"request"`
	Plan          json.RawMessage  `json:"plan"`
	Instantiation struct {
		EntryID    string          `json:"entry_id"`
		Digest     string          `json:"snapshot_digest"`
		Provenance json.RawMessage `json:"provenance"`
	} `json:"instantiation"`
}

func TestInstantiationMatchesIndependentSnapshotsAndLineage(t *testing.T) {
	for _, reference := range referenceCompilations(t) {
		t.Run(reference.Name, func(t *testing.T) { checkInstantiationReference(t, reference) })
	}
}

func referenceCompilations(t *testing.T) []referenceCompilation {
	t.Helper()
	raw, err := readCompressedReference("testdata/compiler-reference.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Cases []referenceCompilation `json:"cases"`
	}
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("invalid compiler reference")
	}
	if len(reference.Cases) != 10 {
		t.Fatal("compiler reference inventory changed")
	}
	return reference.Cases
}

func compilerRequest(t *testing.T, input referenceRequest) Request {
	t.Helper()
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	family, err := sdl.Parse(input.Family, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	family, err = sdl.AdmitFamily(family)
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}
	experiment, err := owner.Validate("experiment-authoring-input-v1", input.Experiment, limits, nil)
	if err != nil {
		t.Fatal(err)
	}
	envelope, err := owner.Validate("realization-envelope-v1", input.Envelope, limits, nil)
	if err != nil {
		t.Fatal(err)
	}
	request := Request{Family: family, Experiment: experiment, Task: input.Task, RealizationEnvelope: envelope, CaptureSpecs: input.CaptureSpecs, Limits: DefaultLimits(), MixedCompositionLimits: DefaultMixedCompositionLimits(), ApparatusManifests: map[ApparatusManifestKey]admission.ApparatusManifest{}}
	for _, item := range []struct {
		Raw     json.RawMessage
		Profile admission.FragmentProfile
		Target  *admission.Fragment
	}{{input.InputRefs, admission.TrialInputRefs, &request.InputRefs}, {input.Apparatus, admission.TrialApparatus, &request.Apparatus}, {input.Authority, admission.TrialExecutionAuthority, &request.ExecutionAuthority}} {
		var value any
		decoder := json.NewDecoder(bytes.NewReader(item.Raw))
		decoder.UseNumber()
		if decoder.Decode(&value) != nil {
			t.Fatal("invalid owner fragment")
		}
		fragment, err := admission.AdmitFragment(owner, item.Profile, value, limits)
		if err != nil {
			t.Fatal(err)
		}
		*item.Target = fragment
	}
	request.ApparatusManifests = compilerManifestFixture(t, input)
	request.ParticipantManifests = map[ParticipantManifestKey]binding.ParticipantImplementationManifestV1{}
	for _, item := range input.Participants {
		request.ParticipantManifests[ParticipantManifestKey{ParticipantAddress: item.Key[0], ImplementationName: item.Key[1], ImplementationVersion: item.Key[2], ManifestVersion: item.Key[3]}] = item.Manifest
	}
	return request
}

func TestCompilerMatchesIndependentPlansAndDraws(t *testing.T) {
	for _, reference := range referenceCompilations(t) {
		t.Run(reference.Name, func(t *testing.T) { checkCompilerPlanReference(t, reference) })
	}
}

func TestTrialRealizationUsesExistingProcessorPlans(t *testing.T) {
	ref := referenceCompilations(t)[6]
	request := compilerRequest(t, ref.Request)
	var plan binding.AdmittedTrialPlanV1
	if json.Unmarshal(ref.Plan, &plan) != nil {
		t.Fatal("invalid plan fixture")
	}
	inputs := RealizationInputs{Plan: plan, Family: request.Family, Experiment: request.Experiment, Task: request.Task, CaptureSpecs: request.CaptureSpecs, ApparatusManifests: request.ApparatusManifests, RealizationEnvelope: request.RealizationEnvelope, BackendKey: ApparatusManifestKey{ComponentKind: componentBackend, ComponentName: "backend-a", ComponentVersion: "1", ManifestVersion: "backend-manifest/v2"}}
	realized, err := RealizeEntry(inputs, ref.Instantiation.EntryID, RealizationOptions{})
	if err != nil {
		t.Fatal(err)
	}
	refs := []any{}
	for _, ref := range realized.ProcessorPlanRefs {
		refs = append(refs, ref.Document())
	}
	actual, err := encoded(struct {
		Digest        string                      `json:"snapshot_digest"`
		Provisioning  binding.ProvisioningPlanV1  `json:"provisioning"`
		Orchestration binding.OrchestrationPlanV1 `json:"orchestration"`
		Evaluation    binding.EvaluationPlanV1    `json:"evaluation"`
		Refs          []any                       `json:"processor_plan_refs"`
	}{realized.SnapshotDigest, realized.ProvisioningPlan, realized.OrchestrationPlan, realized.EvaluationPlan, refs})
	if err != nil {
		t.Fatal(err)
	}
	if !sameJSON(actual, ref.Realization) {
		var a, b any
		_ = json.Unmarshal(actual, &a)
		_ = json.Unmarshal(ref.Realization, &b)
		t.Fatal(cmp.Diff(a, b))
	}
}

func TestFactorialProjectionCanReenterTheNativeFamilyOwner(t *testing.T) {
	ref := referenceCompilations(t)[7]
	request := compilerRequest(t, ref.Request)
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	raw, err := admission.ExperimentProjection(owner, request.Experiment)
	if err != nil {
		t.Fatal(err)
	}
	if err := owner.CheckPortable("experiment-authoring-input-v1", raw, trialIngress()); err != nil {
		t.Fatal("projected authoring input refused:", err)
	}
}

func checkInstantiationReference(t *testing.T, reference referenceCompilation) {
	t.Helper()

	request := compilerRequest(t, reference.Request)
	var plan binding.AdmittedTrialPlanV1
	if json.Unmarshal(reference.Plan, &plan) != nil {
		t.Fatal("bad plan reference")
	}
	instance, err := InstantiateEntry(plan, reference.Instantiation.EntryID, request.Family)
	if err != nil {
		t.Fatal(err)
	}
	digest, err := sdl.CanonicalDigest(instance)
	if err != nil {
		t.Fatal(err)
	}
	if digest != reference.Instantiation.Digest {
		t.Fatal("instantiated snapshot digest differs:", digest, reference.Instantiation.Digest)
	}
	if _, err := InstantiateEntry(plan, "missing", request.Family); err == nil {
		t.Fatal("missing entry admitted")
	}
}

func checkCompilerPlanReference(t *testing.T, reference referenceCompilation) {
	t.Helper()

	result, err := Compile(compilerRequest(t, reference.Request))
	if err != nil {
		t.Fatal(err)
	}
	if result.Plan == nil {
		t.Fatal("compilation refused:", result.Diagnostics)
	}
	actual, err := json.Marshal(result.Plan)
	if err != nil {
		t.Fatal(err)
	}
	actual, err = canonjson.JCS(actual)
	if err != nil {
		t.Fatal(err)
	}
	expected, err := canonjson.JCS(reference.Plan)
	if err != nil {
		t.Fatal(err)
	}
	if string(actual) != string(expected) {
		var a, b any
		_ = json.Unmarshal(actual, &a)
		_ = json.Unmarshal(expected, &b)
		t.Fatal(cmp.Diff(a, b))
	}
}

func compilerManifestFixture(t *testing.T, input referenceRequest) map[ApparatusManifestKey]admission.ApparatusManifest {
	t.Helper()
	result := map[ApparatusManifestKey]admission.ApparatusManifest{}
	for _, item := range input.Manifests {
		key := ApparatusManifestKey{ComponentKind: item.Key[0], ComponentName: item.Key[1], ComponentVersion: item.Key[2], ManifestVersion: item.Key[3]}
		if key.ComponentKind == componentProcessor {
			var manifest binding.ProcessorManifestV2
			if json.Unmarshal(item.Manifest, &manifest) != nil {
				t.Fatal("invalid processor fixture")
			}
			result[key] = admission.ApparatusManifest{Processor: &manifest}
			continue
		}
		var manifest binding.BackendManifestV2
		if json.Unmarshal(item.Manifest, &manifest) != nil {
			t.Fatal("invalid backend fixture")
		}
		result[key] = admission.ApparatusManifest{Backend: &manifest}
	}
	return result
}
