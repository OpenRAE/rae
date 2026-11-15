package experiment

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/trial"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type runtimeReferenceRequest struct {
	InputRefs          json.RawMessage                            `json:"input_refs"`
	Apparatus          json.RawMessage                            `json:"apparatus"`
	ExecutionAuthority json.RawMessage                            `json:"execution_authority"`
	Family             json.RawMessage                            `json:"family"`
	Experiment         json.RawMessage                            `json:"experiment"`
	Envelope           json.RawMessage                            `json:"realization_envelope"`
	Task               binding.ExperimentTaskV1                   `json:"task"`
	Capture            map[string]binding.ExperimentCaptureSpecV1 `json:"capture_specs"`
	Manifests          []struct {
		Key      []string        `json:"key"`
		Manifest json.RawMessage `json:"manifest"`
	} `json:"apparatus_manifests"`
}
type runtimeReferenceCompilation struct {
	Name    string                      `json:"name"`
	Plan    binding.AdmittedTrialPlanV1 `json:"plan"`
	Request runtimeReferenceRequest     `json:"request"`
}

func runtimeInputs(t *testing.T) trial.RealizationInputs {
	t.Helper()
	raw, err := readCompressedReference("../../processor/trial/testdata/compiler-reference.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []runtimeReferenceCompilation `json:"cases"`
	}
	if json.Unmarshal(raw, &fixture) != nil {
		t.Fatal("bad fixture")
	}
	for _, item := range fixture.Cases {
		if item.Name == "processor-realization" {
			return runtimeInputFixture(t, item)
		}
	}
	t.Fatal("missing case")
	return trial.RealizationInputs{}
}
func runtimeInputFixture(t *testing.T, item runtimeReferenceCompilation) trial.RealizationInputs {
	t.Helper()
	owner, err := experimentOwner()
	if err != nil {
		t.Fatal(err)
	}
	family, err := sdl.Parse(item.Request.Family, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	family, err = sdl.AdmitFamily(family)
	if err != nil {
		t.Fatal(err)
	}
	spec, err := owner.Validate("experiment-authoring-input-v1", item.Request.Experiment, runtimeIngress(), nil)
	if err != nil {
		t.Fatal(err)
	}
	envelope, err := owner.Validate("realization-envelope-v1", item.Request.Envelope, runtimeIngress(), nil)
	if err != nil {
		t.Fatal(err)
	}
	input := trial.RealizationInputs{Plan: item.Plan, Family: family, Experiment: spec, RealizationEnvelope: envelope, Task: item.Request.Task, CaptureSpecs: item.Request.Capture, ApparatusManifests: map[trial.ApparatusManifestKey]admission.ApparatusManifest{}}
	for _, manifest := range item.Request.Manifests {
		key := trial.ApparatusManifestKey{ComponentKind: manifest.Key[0], ComponentName: manifest.Key[1], ComponentVersion: manifest.Key[2], ManifestVersion: manifest.Key[3]}
		input.ApparatusManifests[key] = runtimeManifestFixture(t, key.ComponentKind, manifest.Manifest)
		if key.ComponentKind == termBackend {
			input.BackendKey = key
		}
	}
	return input
}
func runtimeManifestFixture(t *testing.T, kind string, raw json.RawMessage) admission.ApparatusManifest {
	t.Helper()
	if kind == "processor" {
		var dto binding.ProcessorManifestV2
		if json.Unmarshal(raw, &dto) != nil {
			t.Fatal("processor")
		}
		return admission.ApparatusManifest{Processor: &dto}
	}
	var dto binding.BackendManifestV2
	if json.Unmarshal(raw, &dto) != nil {
		t.Fatal(termBackend)
	}
	return admission.ApparatusManifest{Backend: &dto}
}
