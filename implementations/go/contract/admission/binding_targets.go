package admission

import (
	"bytes"
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

// BindingOwner is the exact contract and validator that own a binding target.
type BindingOwner struct{ ContractID, ContractVersion, ValidatorID, ValidatorVersion string }

// ParticipantManifestKey selects one participant implementation manifest.
type ParticipantManifestKey struct{ ParticipantAddress, ImplementationName, ImplementationVersion, ManifestVersion string }

// ApparatusManifestKey selects one apparatus component manifest.
type ApparatusManifestKey struct{ ComponentKind, ComponentName, ComponentVersion, ManifestVersion string }

// ApparatusManifest holds exactly one processor or backend manifest.
type ApparatusManifest struct {
	Processor *binding.ProcessorManifestV2
	Backend   *binding.BackendManifestV2
}

// ScenarioBindingResolution is the canonical SDL target of one scenario
// binding, as the public variation authority returns it.
type ScenarioBindingResolution struct {
	CanonicalTargetID, ValueType, Sensitivity string
	AllowedValueKinds                         []string
	Owner                                     BindingOwner
}

// ScenarioBindingTargetResolver resolves a scenario binding target through
// the SDL variation authority. It returns an error for a target that does
// not resolve.
type ScenarioBindingTargetResolver interface {
	Resolve(scenarioFamilyID, variationPointID, suppliedTargetID string) (ScenarioBindingResolution, error)
}

const (
	contractDescriptors   = termExperimentBindingDescriptorsV1
	contractParticipant   = "participant-implementation-manifest-v1"
	contractProcessor     = "processor-manifest-v2"
	contractBackend       = "backend-manifest-v2"
	kindSecretReference   = "secret-reference"
	kindLiteral           = "literal"
	planeScenario         = "scenario"
	planeParticipant      = "participant-implementation"
	planeApparatus        = "apparatus"
	componentProcessor    = "processor"
	componentBackend      = "backend"
	typeString            = "string"
	typeNumber            = "number"
	bindingTargetsMaxSize = 8 * 1048576
)

func bindingTargetInvalid() error {
	return fault.New(fault.InvalidInput, "experiment-binding-target-invalid", nil)
}
func bindingInputInvalid() error {
	return fault.New(fault.InvalidInput, "experiment-binding-input-invalid", nil)
}

type ownerWire struct {
	ContractID       string `json:"contract_id"`
	ContractVersion  string `json:"contract_version"`
	ValidatorID      string `json:"validator_id"`
	ValidatorVersion string `json:"validator_version"`
}

type targetWire struct {
	Plane              string `json:"plane"`
	ScenarioFamilyID   string `json:"scenario_family_id"`
	VariationPointID   string `json:"variation_point_id"`
	ParticipantAddress string `json:"participant_address"`
	ImplementationName string `json:"implementation_name"`
	ImplementationVer  string `json:"implementation_version"`
	ComponentKind      string `json:"component_kind"`
	ComponentName      string `json:"component_name"`
	ComponentVersion   string `json:"component_version"`
	ManifestVersion    string `json:"manifest_version"`
	TargetID           string `json:"target_id"`
}

type valueWire struct {
	Kind  string `json:"kind"`
	Value any    `json:"value"`
}

type descriptorWire struct {
	Target    targetWire `json:"target"`
	ValueType string     `json:"value_type"`
	Value     valueWire  `json:"value"`
	Owner     ownerWire  `json:"owner"`
}

type declarationWire struct {
	TargetID          string   `json:"target_id"`
	ValueType         string   `json:"value_type"`
	Aliases           []string `json:"aliases"`
	AllowedValueKinds []string `json:"allowed_value_kinds"`
	ControlContext    *struct {
		References map[string]json.RawMessage `json:"references"`
	} `json:"control_context"`
}

type registryWire struct {
	Owner   ownerWire                  `json:"owner"`
	Targets map[string]declarationWire `json:"targets"`
}

type manifestWire struct {
	SchemaVersion string `json:"schema_version"`
	Identity      struct {
		Name    string `json:"name"`
		Version string `json:"version"`
	} `json:"identity"`
	Registry *registryWire `json:"configuration_registry"`
}

// ValidateExperimentBindingTargets resolves every descriptor through exactly
// one plane owner and returns the descriptors with their canonical targets.
// The descriptors and each selected manifest pass their published schema and
// local rules first. A refusal is an InvalidInput fault without the supplied
// values.
func ValidateExperimentBindingTargets(v *Validator, descriptors binding.ExperimentBindingDescriptorsV1, resolver ScenarioBindingTargetResolver, participants map[ParticipantManifestKey]binding.ParticipantImplementationManifestV1, apparatus map[ApparatusManifestKey]ApparatusManifest) (binding.ExperimentBindingDescriptorsV1, error) {
	if v == nil {
		return binding.ExperimentBindingDescriptorsV1{}, bindingInputInvalid()
	}
	data, err := v.checkedJSON(contractDescriptors, descriptors)
	if err != nil {
		return binding.ExperimentBindingDescriptorsV1{}, err
	}
	var document struct {
		Descriptors []json.RawMessage `json:"descriptors"`
	}
	var root map[string]json.RawMessage
	if json.Unmarshal(data, &document) != nil || json.Unmarshal(data, &root) != nil {
		return binding.ExperimentBindingDescriptorsV1{}, bindingInputInvalid()
	}
	admitted := make([]json.RawMessage, 0, len(document.Descriptors))
	for _, raw := range document.Descriptors {
		canonical, err := v.resolveDescriptor(raw, resolver, participants, apparatus)
		if err != nil {
			return binding.ExperimentBindingDescriptorsV1{}, err
		}
		updated, err := withTargetID(raw, canonical)
		if err != nil {
			return binding.ExperimentBindingDescriptorsV1{}, err
		}
		admitted = append(admitted, updated)
	}
	return v.canonicalDescriptors(root, admitted)
}

// checkedJSON checks one transport value against its published schema and
// local rules, as the reference model construction does.
func (e *Validator) checkedJSON(id string, value any) ([]byte, error) {
	data, err := json.Marshal(value)
	if err != nil {
		return nil, bindingInputInvalid()
	}
	limits := ingress.Limits{MaxBytes: bindingTargetsMaxSize, MaxDepth: 64}
	if e.low.CheckLocal(id, data, limits) != nil || e.checkModels(id, data, limits) != nil {
		return nil, bindingInputInvalid()
	}
	return data, nil
}

// canonicalDescriptors checks the rebuilt set, so an alias and its canonical
// target cannot both remain.
func (e *Validator) canonicalDescriptors(root map[string]json.RawMessage, descriptors []json.RawMessage) (binding.ExperimentBindingDescriptorsV1, error) {
	encoded, err := json.Marshal(descriptors)
	if err != nil {
		return binding.ExperimentBindingDescriptorsV1{}, bindingInputInvalid()
	}
	root["descriptors"] = encoded
	data, err := json.Marshal(root)
	if err != nil {
		return binding.ExperimentBindingDescriptorsV1{}, bindingInputInvalid()
	}
	limits := ingress.Limits{MaxBytes: bindingTargetsMaxSize, MaxDepth: 64}
	if e.low.CheckLocal(contractDescriptors, data, limits) != nil || e.checkModels(contractDescriptors, data, limits) != nil {
		return binding.ExperimentBindingDescriptorsV1{}, bindingTargetInvalid()
	}
	var result binding.ExperimentBindingDescriptorsV1
	if json.Unmarshal(data, &result) != nil {
		return binding.ExperimentBindingDescriptorsV1{}, bindingInputInvalid()
	}
	return result, nil
}

func withTargetID(raw json.RawMessage, targetID string) (json.RawMessage, error) {
	var descriptor map[string]json.RawMessage
	var target map[string]json.RawMessage
	if json.Unmarshal(raw, &descriptor) != nil || json.Unmarshal(descriptor["target"], &target) != nil {
		return nil, bindingInputInvalid()
	}
	id, err := json.Marshal(targetID)
	if err != nil {
		return nil, bindingInputInvalid()
	}
	target["target_id"] = id
	encoded, err := json.Marshal(target)
	if err != nil {
		return nil, bindingInputInvalid()
	}
	descriptor["target"] = encoded
	return json.Marshal(descriptor)
}

func (e *Validator) resolveDescriptor(raw json.RawMessage, resolver ScenarioBindingTargetResolver, participants map[ParticipantManifestKey]binding.ParticipantImplementationManifestV1, apparatus map[ApparatusManifestKey]ApparatusManifest) (string, error) {
	var descriptor descriptorWire
	if decodeExact(raw, &descriptor) != nil {
		return "", bindingInputInvalid()
	}
	switch descriptor.Target.Plane {
	case planeScenario:
		return resolveScenarioTarget(descriptor, resolver)
	case planeParticipant:
		return e.resolveParticipantTarget(descriptor, participants)
	case planeApparatus:
		return e.resolveApparatusTarget(descriptor, apparatus)
	}
	return "", bindingInputInvalid()
}

func resolveScenarioTarget(descriptor descriptorWire, resolver ScenarioBindingTargetResolver) (string, error) {
	if resolver == nil {
		return "", bindingTargetInvalid()
	}
	target := descriptor.Target
	resolution, err := resolver.Resolve(target.ScenarioFamilyID, target.VariationPointID, target.TargetID)
	if err != nil || !validScenarioResolution(resolution) {
		return "", bindingTargetInvalid()
	}
	if resolution.ValueType != descriptor.ValueType || resolution.Owner != BindingOwner(descriptor.Owner) || !slices.Contains(resolution.AllowedValueKinds, descriptor.Value.Kind) {
		return "", bindingTargetInvalid()
	}
	if resolution.Sensitivity == sensitivitySecret && descriptor.Value.Kind != kindSecretReference {
		return "", bindingTargetInvalid()
	}
	return resolution.CanonicalTargetID, nil
}

// validScenarioResolution applies the reference resolution model.
func validScenarioResolution(r ScenarioBindingResolution) bool {
	owner := r.Owner
	if r.CanonicalTargetID == "" || owner.ContractID == "" || owner.ContractVersion == "" || owner.ValidatorID == "" || owner.ValidatorVersion == "" {
		return false
	}
	if !slices.Contains([]string{typeString, termInteger, typeNumber, typeBoolean, termNull}, r.ValueType) || !slices.Contains([]string{"public", "internal", "restricted", sensitivitySecret}, r.Sensitivity) {
		return false
	}
	for _, kind := range r.AllowedValueKinds {
		if kind != kindLiteral && kind != kindSecretReference {
			return false
		}
	}
	return true
}

func (e *Validator) resolveParticipantTarget(descriptor descriptorWire, participants map[ParticipantManifestKey]binding.ParticipantImplementationManifestV1) (string, error) {
	target := descriptor.Target
	manifest, found := participants[ParticipantManifestKey{target.ParticipantAddress, target.ImplementationName, target.ImplementationVer, target.ManifestVersion}]
	if !found {
		return "", bindingTargetInvalid()
	}
	wire, err := e.manifestRegistry(contractParticipant, manifest)
	if err != nil {
		return "", err
	}
	if wire.Identity.Name != target.ImplementationName || wire.Identity.Version != target.ImplementationVer || wire.SchemaVersion != target.ManifestVersion {
		return "", bindingTargetInvalid()
	}
	return declaredTarget(descriptor, wire.Registry)
}

func (e *Validator) resolveApparatusTarget(descriptor descriptorWire, apparatus map[ApparatusManifestKey]ApparatusManifest) (string, error) {
	target := descriptor.Target
	selected, found := apparatus[ApparatusManifestKey{target.ComponentKind, target.ComponentName, target.ComponentVersion, target.ManifestVersion}]
	if !found || (selected.Processor == nil) == (selected.Backend == nil) {
		return "", bindingTargetInvalid()
	}
	kind, contract, manifest := componentProcessor, contractProcessor, any(selected.Processor)
	if selected.Backend != nil {
		kind, contract, manifest = componentBackend, contractBackend, selected.Backend
	}
	wire, err := e.manifestRegistry(contract, manifest)
	if err != nil {
		return "", err
	}
	if target.ComponentKind != kind || wire.Identity.Name != target.ComponentName || wire.Identity.Version != target.ComponentVersion || wire.SchemaVersion != target.ManifestVersion {
		return "", bindingTargetInvalid()
	}
	return declaredTarget(descriptor, wire.Registry)
}

func (e *Validator) manifestRegistry(contract string, manifest any) (manifestWire, error) {
	data, err := e.checkedJSON(contract, manifest)
	if err != nil {
		return manifestWire{}, err
	}
	var wire manifestWire
	if json.Unmarshal(data, &wire) != nil {
		return manifestWire{}, bindingInputInvalid()
	}
	return wire, nil
}

// declaredTarget resolves the supplied ID directly or through exactly one
// alias, then checks the owner, the value type and the value domain.
func declaredTarget(descriptor descriptorWire, registry *registryWire) (string, error) {
	if registry == nil {
		return "", bindingTargetInvalid()
	}
	declaration, found := registry.Targets[descriptor.Target.TargetID]
	if !found {
		var matches []declarationWire
		for _, candidate := range registry.Targets {
			if slices.Contains(candidate.Aliases, descriptor.Target.TargetID) {
				matches = append(matches, candidate)
			}
		}
		if len(matches) != 1 {
			return "", bindingTargetInvalid()
		}
		declaration = matches[0]
	}
	if registry.Owner != descriptor.Owner || declaration.ValueType != descriptor.ValueType || !declaredValue(declaration, descriptor.Value) {
		return "", bindingTargetInvalid()
	}
	return declaration.TargetID, nil
}

// declaredValue applies the declaration's control-context domain, permitted
// kinds and exact literal type.
func declaredValue(declaration declarationWire, value valueWire) bool {
	if declaration.ControlContext != nil {
		reference, isText := value.Value.(string)
		if value.Kind != kindLiteral || !isText {
			return false
		}
		if _, known := declaration.ControlContext.References[reference]; !known {
			return false
		}
	}
	if !slices.Contains(declaration.AllowedValueKinds, value.Kind) {
		return false
	}
	if value.Kind == kindLiteral {
		return scalarMatches(value.Value, declaration.ValueType)
	}
	return declaration.ValueType != termNull
}

// decodeExact reads JSON with exact numbers.
func decodeExact(data []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	return decoder.Decode(target)
}
