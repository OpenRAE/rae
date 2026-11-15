package trial

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func validateInputPins(request Request, input compilationInputs, experimentJSON []byte) error {
	refs := input.refs
	familyDigest, err := sdl.CanonicalDigest(request.Family)
	if err != nil {
		return err
	}
	if refs.Family.ID != input.family.Name || text(refs.Family.Digest) != familyDigest {
		return refuse("scenario-family-ref-mismatch", "/input_refs/scenario_family_ref", "scenario family reference does not match the admitted expanded family")
	}
	experimentDigest, err := hash(json.RawMessage(experimentJSON))
	if err != nil {
		return err
	}
	if refs.Authoring.ID != input.spec.ID || text(refs.Authoring.Version) != input.spec.Version || text(refs.Authoring.Digest) != experimentDigest {
		return refuse("authoring-input-ref-mismatch", "/input_refs/authoring_input_ref", "authoring input reference does not match the admitted experiment")
	}
	task, taskDigest, err := admitTaskPins(input.owner, request.Task)
	if err != nil {
		return err
	}
	if refs.Task.Kind != input.spec.Task.Kind || refs.Task.ID != input.spec.Task.ID || text(refs.Task.Version) != text(input.spec.Task.Version) || refs.Task.ID != task.ID || text(refs.Task.Version) != task.Version || refs.TaskDigest != taskDigest {
		return refuse("task-ref-mismatch", "/input_refs/task_ref", "task reference or digest does not match the admitted task")
	}
	if err = validateBindingPin(input.spec.Bindings, refs.Bindings); err != nil {
		return err
	}
	if refs.Study != nil || refs.Associated != nil {
		return refuse("referenced-input-payload-required", "/input_refs", "optional study or associated-artifact references require their exact typed payloads")
	}
	return validateCapturePins(request, input, task.Protocol.Requirements, task.Protocol.Metrics)
}

type taskInputPins struct {
	ID       string `json:"task_id"`
	Version  string `json:"task_version"`
	Protocol struct {
		Requirements []reference `json:"observation_requirements"`
		Metrics      map[string]struct {
			Requirements []reference `json:"evidence_requirements"`
		} `json:"metric_definitions"`
	} `json:"evaluation_protocol"`
}

func admitTaskPins(owner *admission.Validator, taskValue binding.ExperimentTaskV1) (taskInputPins, string, error) {
	var task taskInputPins
	if admission.CheckTransport(taskValue, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}) != nil {
		return task, "", trialInvalid()
	}
	raw, err := encoded(taskValue)
	if err != nil {
		return task, "", err
	}
	value, err := owner.Validate("experiment-task-v1", raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
	if err != nil {
		return task, "", err
	}
	raw, err = admission.ExperimentProjection(owner, value)
	if err != nil {
		return task, "", err
	}
	if decode(raw, &task) != nil {
		return task, "", trialInvalid()
	}
	taskDigest, err := hash(json.RawMessage(raw))
	if err != nil {
		return task, "", err
	}
	return task, taskDigest, nil
}
func validateBindingPin(descriptors json.RawMessage, ref *reference) error {
	if isNull(descriptors) && ref != nil {
		return refuse("binding-set-ref-unexpected", "/input_refs/binding_descriptor_set_ref", "an unbound experiment must not carry a binding descriptor set reference")
	}
	if !isNull(descriptors) {
		d, err := hash(descriptors)
		if err != nil {
			return err
		}
		if ref == nil || text(ref.Digest) != d {
			return refuse("binding-set-ref-mismatch", "/input_refs/binding_descriptor_set_ref", "binding descriptor set reference does not match the admitted descriptor set")
		}
	}
	return nil
}
func validateCapturePins(request Request, input compilationInputs, requirements []reference, metrics map[string]struct {
	Requirements []reference `json:"evidence_requirements"`
}) error {
	if len(request.CaptureSpecs) != len(input.spec.Capture) {
		return refuse("capture-spec-payload-mismatch", pathCaptureSpecRefs, "capture specification references do not resolve exactly to the supplied payloads")
	}
	pins := map[string]reference{}
	for _, ref := range input.refs.Capture {
		pins[ref.ID] = ref
	}
	if len(pins) != len(request.CaptureSpecs) {
		return refuse("capture-spec-ref-mismatch", pathCaptureSpecRefs, "capture specification digests do not match the admitted payloads")
	}
	wanted := map[string]reference{}
	for _, ref := range input.spec.Capture {
		wanted[ref.ID] = ref
	}
	known := map[string]bool{}
	for _, id := range slices.Sorted(maps.Keys(request.CaptureSpecs)) {
		capture, err := admitCapturePin(input.owner, id, request.CaptureSpecs[id], wanted[id], pins[id])
		if err != nil {
			return err
		}
		if err = retainCaptureRequirements(capture, known); err != nil {
			return err
		}
	}
	for _, metric := range metrics {
		requirements = append(requirements, metric.Requirements...)
	}
	for _, requirement := range requirements {
		if !known[requirement.ID] {
			return refuse("task-capture-requirement-missing", "/task/evaluation_protocol", "task evidence requirements do not resolve to admitted capture requirements")
		}
	}
	return nil
}

type captureInputPins struct {
	ID           string                     `json:"capture_spec_id"`
	Version      string                     `json:"spec_version"`
	Requirements map[string]json.RawMessage `json:"capture_requirements"`
}

func admitCapturePin(owner *admission.Validator, id string, spec binding.ExperimentCaptureSpecV1, ref, pin reference) (captureInputPins, error) {
	var capture captureInputPins
	if admission.CheckTransport(spec, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}) != nil {
		return capture, trialInvalid()
	}
	raw, err := encoded(spec)
	if err != nil {
		return capture, err
	}
	value, err := owner.Validate("experiment-capture-spec-v1", raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
	if err != nil {
		return capture, err
	}
	raw, err = admission.ExperimentProjection(owner, value)
	if err != nil {
		return capture, err
	}
	if decode(raw, &capture) != nil {
		return capture, trialInvalid()
	}
	if ref.ID != id || capture.ID != id || text(ref.Version) != capture.Version {
		return capture, refuse("capture-spec-payload-mismatch", pathCaptureSpecRefs, "capture specification references do not resolve exactly to the supplied payloads")
	}
	d, err := hash(json.RawMessage(raw))
	if err != nil {
		return capture, err
	}
	if text(pin.Version) != capture.Version || text(pin.Digest) != d {
		return capture, refuse("capture-spec-ref-mismatch", pathCaptureSpecRefs, "capture specification digests do not match the admitted payloads")
	}
	return capture, nil
}

type apparatusBinding struct {
	Manifests    []reference                    `json:"manifest_refs"`
	Envelope     json.RawMessage                `json:"realization_envelope"`
	Capabilities []string                       `json:"capability_refs"`
	Participants []participantManifestReference `json:"participant_manifest_refs"`
}
type participantManifestReference struct {
	Address         string `json:"participant_address"`
	Name            string `json:"implementation_name"`
	Version         string `json:"implementation_version"`
	ManifestVersion string `json:"manifest_version"`
	ManifestDigest  string `json:"manifest_digest"`
	ManifestRef     string `json:"manifest_ref"`
}
type manifestMetadata struct {
	SchemaVersion string `json:"schema_version"`
	Identity      struct {
		Name    string `json:"name"`
		Version string `json:"version"`
	} `json:"identity"`
	Envelope      json.RawMessage `json:"realization_envelope"`
	Contracts     []string        `json:"supported_contract_versions"`
	Compatibility struct {
		Processors []string `json:"processors"`
		Backends   []string `json:"backends"`
	} `json:"compatibility"`
	Capabilities struct {
		SDL      []string `json:"supported_sdl_versions"`
		Features []string `json:"supported_features"`
	} `json:"capabilities"`
}

func sameJSON(a, b json.RawMessage) bool {
	left, e1 := canonical(a)
	right, e2 := canonical(b)
	return e1 == nil && e2 == nil && string(left) == string(right)
}
func admitApparatusManifest(owner *admission.Validator, key ApparatusManifestKey, manifest admission.ApparatusManifest) ([]byte, manifestMetadata, *binding.BackendManifestV2, error) {
	var metadata manifestMetadata
	if (manifest.Backend == nil) == (manifest.Processor == nil) {
		return nil, metadata, nil, trialInvalid()
	}
	var payload any
	contract := "processor-manifest-v2"
	if key.ComponentKind == componentBackend {
		if manifest.Backend == nil {
			return nil, metadata, nil, trialInvalid()
		}
		payload = manifest.Backend
		contract = "backend-manifest-v2"
	} else {
		if manifest.Processor == nil {
			return nil, metadata, nil, trialInvalid()
		}
		payload = manifest.Processor
	}
	if err := admission.CheckTransport(payload, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}); err != nil {
		return nil, metadata, nil, err
	}
	raw, err := encoded(payload)
	if err != nil {
		return nil, metadata, nil, err
	}
	raw, err = admission.ManifestModelProjection(owner, contract, raw)
	if err != nil {
		return nil, metadata, nil, err
	}
	if decode(raw, &metadata) != nil {
		return nil, metadata, nil, trialInvalid()
	}
	var backend *binding.BackendManifestV2
	if manifest.Backend != nil {
		var constructed binding.BackendManifestV2
		if decode(raw, &constructed) != nil {
			return nil, metadata, nil, trialInvalid()
		}
		backend = &constructed
	}
	return raw, metadata, backend, nil
}

func retainCaptureRequirements(capture captureInputPins, known map[string]bool) error {
	for requirement := range capture.Requirements {
		if known[requirement] {
			return refuse("capture-requirement-ambiguous", pathCaptureSpecRefs, "capture requirement identities must be unique across admitted capture specifications")
		}
		known[requirement] = true
	}
	return nil
}
