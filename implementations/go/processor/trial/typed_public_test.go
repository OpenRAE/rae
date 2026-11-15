package trial

import (
	"encoding/json"
	"maps"
	"testing"
)

func TestTypedPublicExamplesPreservePlansAndRealization(t *testing.T) {
	raw, err := readCompressedReference("testdata/typed-public-reference.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []referenceCompilation `json:"cases"`
	}
	if json.Unmarshal(raw, &fixture) != nil {
		t.Fatal("fixture")
	}
	for _, reference := range fixture.Cases {
		t.Run(reference.Name, func(t *testing.T) { checkTypedPublicReference(t, reference) })
	}
}
func checkTypedPublicReference(t *testing.T, reference referenceCompilation) {
	t.Helper()
	request := typedCompilerRequest(t, reference)
	compiled, err := Compile(request)
	if err != nil || compiled.Plan == nil {
		t.Fatal("public compilation", err, compiled.Diagnostics)
	}
	raw, err := encoded(compiled.Plan)
	if err != nil || !sameJSON(raw, reference.Plan) {
		t.Fatal("public source plan differs", err)
	}
	plan, err := Readmit(t.Context(), *compiled.Plan, request)
	if err != nil {
		t.Fatal(err)
	}
	inputs := RealizationInputs{Plan: plan, Family: request.Family, Experiment: request.Experiment, Task: request.Task, CaptureSpecs: request.CaptureSpecs, ApparatusManifests: request.ApparatusManifests, ParticipantManifests: request.ParticipantManifests, RealizationEnvelope: request.RealizationEnvelope, BackendKey: ApparatusManifestKey{ComponentKind: componentBackend, ComponentName: "backend-a", ComponentVersion: "1", ManifestVersion: "backend-manifest/v2"}}
	realized, err := RealizeEntry(inputs, reference.Instantiation.EntryID, RealizationOptions{})
	if err != nil {
		t.Fatal(err)
	}
	refs := make([]any, len(realized.ProcessorPlanRefs))
	for index, ref := range realized.ProcessorPlanRefs {
		refs[index] = ref.Document()
	}
	actual, err := encoded(map[string]any{"snapshot_digest": realized.SnapshotDigest, "provisioning": realized.ProvisioningPlan, "orchestration": realized.OrchestrationPlan, "evaluation": realized.EvaluationPlan, "processor_plan_refs": refs})
	if err != nil || !sameJSON(actual, reference.Realization) {
		t.Fatal("public processor realization differs", err)
	}
	inputs.ParticipantManifests = maps.Clone(inputs.ParticipantManifests)
	substitutePublicManifest(t, inputs)
	if _, err = RealizeEntry(inputs, reference.Instantiation.EntryID, RealizationOptions{}); err == nil {
		t.Fatal("changed participant manifest bypassed realization pin")
	}
}
func substitutePublicManifest(t *testing.T, inputs RealizationInputs) {
	t.Helper()
	for key, manifest := range inputs.ParticipantManifests {
		raw, err := encoded(manifest)
		if err != nil {
			t.Fatal(err)
		}
		var view map[string]any
		if decode(raw, &view) != nil {
			t.Fatal("manifest fixture")
		}
		registry, ok := view["configuration_registry"].(map[string]any)
		if !ok {
			t.Fatal("registry fixture")
		}
		targets, ok := registry["targets"].(map[string]any)
		if !ok {
			t.Fatal("target fixture")
		}
		model, ok := targets["policy.model"].(map[string]any)
		if !ok {
			t.Fatal("model fixture")
		}
		model["aliases"] = []string{"substituted-alias"}
		raw, err = encoded(view)
		if err != nil || decode(raw, &manifest) != nil {
			t.Fatal("mutated manifest fixture", err)
		}
		inputs.ParticipantManifests[key] = manifest
		return
	}
	t.Fatal("participant manifest missing")
}
