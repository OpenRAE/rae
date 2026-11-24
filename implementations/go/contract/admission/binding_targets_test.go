package admission

import (
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type bindingTargetVector struct {
	Name        string          `json:"name"`
	Descriptors json.RawMessage `json:"descriptors"`
	Resolution  *struct {
		CanonicalTargetID string    `json:"canonical_target_id"`
		ValueType         string    `json:"value_type"`
		AllowedValueKinds []string  `json:"allowed_value_kinds"`
		Sensitivity       string    `json:"sensitivity"`
		Owner             ownerWire `json:"owner"`
	} `json:"resolution"`
	Participants []struct {
		Key      [4]string       `json:"key"`
		Manifest json.RawMessage `json:"manifest"`
	} `json:"participants"`
	Apparatus []struct {
		Key      [4]string       `json:"key"`
		Kind     string          `json:"kind"`
		Manifest json.RawMessage `json:"manifest"`
	} `json:"apparatus"`
	Result json.RawMessage `json:"result"`
}

// tableResolver resolves only the one recorded reference target.
type tableResolver struct {
	key        [3]string
	resolution *ScenarioBindingResolution
}

func (r tableResolver) Resolve(family, point, target string) (ScenarioBindingResolution, error) {
	if r.resolution == nil || [3]string{family, point, target} != r.key {
		return ScenarioBindingResolution{}, errors.New("unknown scenario variation target")
	}
	return *r.resolution, nil
}

func decodeJSON(t *testing.T, data []byte, target any) {
	t.Helper()
	if err := json.Unmarshal(data, target); err != nil {
		t.Fatalf("json.Unmarshal(%T) error = %v", target, err)
	}
}

func jsonValue(t *testing.T, data []byte) any {
	t.Helper()
	var value any
	decodeJSON(t, data, &value)
	return value
}

func vectorResolver(c bindingTargetVector) tableResolver {
	resolver := tableResolver{key: [3]string{"family.techvault", "variation.worker-count", "variables.worker_count"}}
	if r := c.Resolution; r != nil {
		resolver.resolution = &ScenarioBindingResolution{CanonicalTargetID: r.CanonicalTargetID, ValueType: r.ValueType, AllowedValueKinds: r.AllowedValueKinds, Sensitivity: r.Sensitivity, Owner: BindingOwner(r.Owner)}
	}
	return resolver
}

func vectorParticipants(t *testing.T, c bindingTargetVector) map[ParticipantManifestKey]binding.ParticipantImplementationManifestV1 {
	t.Helper()
	participants := map[ParticipantManifestKey]binding.ParticipantImplementationManifestV1{}
	for _, p := range c.Participants {
		var manifest binding.ParticipantImplementationManifestV1
		decodeJSON(t, p.Manifest, &manifest)
		participants[ParticipantManifestKey{p.Key[0], p.Key[1], p.Key[2], p.Key[3]}] = manifest
	}
	return participants
}

func vectorApparatus(t *testing.T, c bindingTargetVector) map[ApparatusManifestKey]ApparatusManifest {
	t.Helper()
	apparatus := map[ApparatusManifestKey]ApparatusManifest{}
	for _, a := range c.Apparatus {
		manifest := ApparatusManifest{}
		if a.Kind == componentProcessor {
			manifest.Processor = &binding.ProcessorManifestV2{}
			decodeJSON(t, a.Manifest, manifest.Processor)
		} else {
			manifest.Backend = &binding.BackendManifestV2{}
			decodeJSON(t, a.Manifest, manifest.Backend)
		}
		apparatus[ApparatusManifestKey{a.Key[0], a.Key[1], a.Key[2], a.Key[3]}] = manifest
	}
	return apparatus
}

func readBindingTargetVectors(t *testing.T) []bindingTargetVector {
	t.Helper()
	data, err := os.ReadFile("testdata/binding-target-vectors.json")
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	var recording struct {
		Cases []bindingTargetVector `json:"cases"`
	}
	decodeJSON(t, data, &recording)
	if len(recording.Cases) != 25 {
		t.Fatalf("len(cases) = %d, want the 25 recorded reference cases", len(recording.Cases))
	}
	return recording.Cases
}

func checkBindingTargetCase(t *testing.T, c bindingTargetVector) {
	t.Helper()
	var descriptors binding.ExperimentBindingDescriptorsV1
	decodeJSON(t, c.Descriptors, &descriptors)
	got, err := ValidateExperimentBindingTargets(boundTestOwner(t), descriptors, vectorResolver(c), vectorParticipants(t, c), vectorApparatus(t, c))
	if string(c.Result) == "null" {
		if refused, ok := errors.AsType[*fault.Error](err); !ok || refused.Category() != fault.InvalidInput || refused.Code() != "experiment-binding-target-invalid" {
			t.Fatalf("ValidateExperimentBindingTargets() error = %v, want InvalidInput experiment-binding-target-invalid", err)
		}
		return
	}
	if err != nil {
		t.Fatalf("ValidateExperimentBindingTargets() error = %v", err)
	}
	encoded, err := json.Marshal(got)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}
	if diff := cmp.Diff(jsonValue(t, c.Result), jsonValue(t, encoded)); diff != "" {
		t.Errorf("ValidateExperimentBindingTargets() mismatch (-want +got):\n%s", diff)
	}
}

func TestBindingTargetsResolveThroughOwners(t *testing.T) {
	for _, c := range readBindingTargetVectors(t) {
		t.Run(c.Name, func(t *testing.T) { checkBindingTargetCase(t, c) })
	}
}

func TestBindingTargetsRefuseInvalidInputs(t *testing.T) {
	both := ApparatusManifest{Processor: &binding.ProcessorManifestV2{}, Backend: &binding.BackendManifestV2{}}
	for name, call := range map[string]func() error{
		"no validator": func() error {
			_, err := ValidateExperimentBindingTargets(nil, binding.ExperimentBindingDescriptorsV1{}, nil, nil, nil)
			return err
		},
		"empty descriptors": func() error {
			_, err := ValidateExperimentBindingTargets(boundTestOwner(t), binding.ExperimentBindingDescriptorsV1{}, nil, nil, nil)
			return err
		},
	} {
		err := call()
		if refused, ok := errors.AsType[*fault.Error](err); !ok || refused.Code() != "experiment-binding-input-invalid" {
			t.Errorf("%s: error = %v, want InvalidInput experiment-binding-input-invalid", name, err)
		}
	}
	if (both.Processor == nil) == (both.Backend == nil) {
		descriptor := descriptorWire{Target: targetWire{Plane: planeApparatus, ComponentKind: "processor"}}
		_, err := boundTestOwner(t).resolveApparatusTarget(descriptor, map[ApparatusManifestKey]ApparatusManifest{{ComponentKind: "processor"}: both})
		if err == nil {
			t.Errorf("resolveApparatusTarget(two manifests) error = nil, want refusal")
		}
	}
	if _, err := resolveScenarioTarget(descriptorWire{}, nil); err == nil {
		t.Errorf("resolveScenarioTarget(nil resolver) error = nil, want refusal")
	}
	for name, r := range map[string]ScenarioBindingResolution{
		"empty target": {ValueType: "string", Sensitivity: "public", Owner: BindingOwner{"a", "b", "c", "d"}},
		"empty owner":  {CanonicalTargetID: "x", ValueType: "string", Sensitivity: "public"},
		"bad type":     {CanonicalTargetID: "x", ValueType: "text", Sensitivity: "public", Owner: BindingOwner{"a", "b", "c", "d"}},
		"bad level":    {CanonicalTargetID: "x", ValueType: "string", Sensitivity: "top", Owner: BindingOwner{"a", "b", "c", "d"}},
		"bad kind":     {CanonicalTargetID: "x", ValueType: "string", Sensitivity: "public", AllowedValueKinds: []string{"locator"}, Owner: BindingOwner{"a", "b", "c", "d"}},
	} {
		if validScenarioResolution(r) {
			t.Errorf("%s: validScenarioResolution() = true, want false", name)
		}
	}
}
