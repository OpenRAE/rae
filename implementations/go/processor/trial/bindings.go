package trial

import (
	"context"
	"encoding/json"
	"maps"
	"slices"
	"sort"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type descriptorTarget struct {
	Plane           string `json:"plane"`
	Family          string `json:"scenario_family_id"`
	Point           string `json:"variation_point_id"`
	Target          string `json:"target_id"`
	Participant     string `json:"participant_address"`
	Name            string `json:"implementation_name"`
	Version         string `json:"implementation_version"`
	ManifestVersion string `json:"manifest_version"`
}
type descriptor struct {
	ID        string           `json:"binding_id"`
	Condition string           `json:"source_condition_id"`
	Target    descriptorTarget `json:"target"`
	Value     selectionOutcome `json:"value"`
}
type admittedDescriptor struct {
	wire descriptor
	raw  json.RawMessage
}
type familyResolver struct{ family sdl.Scenario }

func (r familyResolver) Resolve(family, point, target string) (admission.ScenarioBindingResolution, error) {
	return sdl.ResolveBindingTarget(r.family, family, point, target)
}

func participantAuthorities(request Request, input compilationInputs) (map[ParticipantManifestKey]binding.ParticipantImplementationManifestV1, error) {
	var apparatus apparatusBinding
	if decode(input.apparatusJSON, &apparatus) != nil {
		return nil, trialInvalid()
	}
	result := map[ParticipantManifestKey]binding.ParticipantImplementationManifestV1{}
	for _, ref := range apparatus.Participants {
		key := ParticipantManifestKey{ParticipantAddress: ref.Address, ImplementationName: ref.Name, ImplementationVersion: ref.Version, ManifestVersion: ref.ManifestVersion}
		manifest, present := request.ParticipantManifests[key]
		if !present {
			return nil, refuse("participant-manifest-payload-missing", "/apparatus/participant_manifest_refs", "selected participant manifest reference has no exact concrete payload")
		}
		constructed, err := admitParticipantManifest(input.owner, manifest, ref)
		if err != nil {
			return nil, err
		}
		result[key] = constructed
	}
	return result, nil
}
func admitParticipantManifest(owner *admission.Validator, manifest binding.ParticipantImplementationManifestV1, ref participantManifestReference) (binding.ParticipantImplementationManifestV1, error) {
	if admission.CheckTransport(manifest, trialIngress()) != nil {
		return binding.ParticipantImplementationManifestV1{}, trialInvalid()
	}
	raw, err := encoded(manifest)
	if err != nil {
		return binding.ParticipantImplementationManifestV1{}, err
	}
	raw, err = admission.ManifestModelProjection(owner, "participant-implementation-manifest-v1", raw)
	if err != nil {
		return binding.ParticipantImplementationManifestV1{}, err
	}
	var metadata manifestMetadata
	if decode(raw, &metadata) != nil {
		return binding.ParticipantImplementationManifestV1{}, trialInvalid()
	}
	if metadata.Identity.Name != ref.Name || metadata.Identity.Version != ref.Version || metadata.SchemaVersion != ref.ManifestVersion {
		return binding.ParticipantImplementationManifestV1{}, refuse("participant-manifest-identity-mismatch", "/apparatus/participant_manifest_refs", "selected participant manifest identity does not match its concrete payload")
	}
	d, err := hash(json.RawMessage(raw))
	if err != nil {
		return binding.ParticipantImplementationManifestV1{}, err
	}
	if ref.ManifestDigest != d {
		return binding.ParticipantImplementationManifestV1{}, refuse("participant-manifest-digest-mismatch", "/apparatus/participant_manifest_refs", "selected participant manifest digest does not match its concrete payload")
	}
	var constructed binding.ParticipantImplementationManifestV1
	if decode(raw, &constructed) != nil {
		return binding.ParticipantImplementationManifestV1{}, trialInvalid()
	}
	return constructed, nil
}
func admittedDescriptors(request Request, input compilationInputs) ([]admittedDescriptor, error) {
	if isNull(input.spec.Bindings) {
		return []admittedDescriptor{}, nil
	}
	var original binding.ExperimentBindingDescriptorsV1
	if decode(input.spec.Bindings, &original) != nil {
		return nil, trialInvalid()
	}
	selected := input.manifests
	admitted, err := admission.ValidateExperimentBindingTargets(input.owner, original, familyResolver{request.Family}, input.participants, selected)
	if err != nil {
		return nil, refuse("binding-target-rejected", "/binding_descriptors", "a binding descriptor target failed authoritative admission")
	}
	raw, err := encoded(admitted)
	if err != nil {
		return nil, err
	}
	var document struct {
		Descriptors []json.RawMessage `json:"descriptors"`
	}
	if decode(raw, &document) != nil {
		return nil, trialInvalid()
	}
	result := make([]admittedDescriptor, len(document.Descriptors))
	for index, raw := range document.Descriptors {
		result[index].raw = raw
		if decode(raw, &result[index].wire) != nil {
			return nil, trialInvalid()
		}
	}
	sort.Slice(result, func(i, j int) bool { return result[i].wire.ID < result[j].wire.ID })
	return result, nil
}
func descriptorMatches(request Request, d descriptor, s selectionRecord) bool {
	if d.Target.Point != s.Point || d.Value.Kind != "literal" {
		return false
	}
	value := s.Outcome.Value
	if s.Outcome.Kind == "reference" {
		value, _ = encoded(s.Outcome.ReferenceID)
	}
	if s.Outcome.Kind == "member" {
		raw, err := sdl.DocumentBytes(request.Family)
		if err != nil {
			return false
		}
		var family struct {
			Points map[string]struct {
				Alternatives map[string]struct {
					Reference string `json:"reference"`
				} `json:"alternatives"`
			} `json:"variation_points"`
		}
		if decode(raw, &family) != nil {
			return false
		}
		value, _ = encoded(family.Points[s.Point].Alternatives[s.Outcome.MemberID].Reference)
	}
	// Both are strict scalar declarations; preserve integer/number identity.
	var left, right any
	if decode(d.Value.Value, &left) != nil || decode(value, &right) != nil {
		return false
	}
	return scalarKind(left) == scalarKind(right) && sameJSON(d.Value.Value, value)
}
func scalarKind(input any) string {
	switch value := input.(type) {
	case json.Number:
		if strings.ContainsAny(value.String(), ".eE") {
			return "number"
		}
		return "integer"
	case bool:
		return "boolean"
	case string:
		return "string"
	default:
		return "null"
	}
}

type entryBindingCollector struct {
	selected []admittedDescriptor
	records  []json.RawMessage
	seen     map[string]bool
}

func (b *entryBindingCollector) append(item admittedDescriptor) error {
	if b.seen[item.wire.ID] {
		return refuse("binding-duplicate", "/binding_descriptors", "an admitted binding descriptor is selected more than once")
	}
	raw, err := encoded(struct {
		Descriptor json.RawMessage `json:"descriptor"`
		Origin     string          `json:"origin"`
	}{item.raw, originSelection})
	if err != nil {
		return err
	}
	b.seen[item.wire.ID] = true
	b.records = append(b.records, raw)
	b.selected = append(b.selected, item)
	return nil
}
func (b *entryBindingCollector) selection(request Request, input compilationInputs, c coordinate, selection selectionRecord) error {
	ids := slices.Clone(input.spec.RunPlan.Policies[selection.Policy].DescriptorRefs)
	slices.Sort(ids)
	for _, id := range ids {
		for _, item := range input.descriptors {
			if item.wire.ID != id || item.wire.Condition != text(c.ConditionID) {
				continue
			}
			if !descriptorMatches(request, item.wire, selection) {
				return refuse("binding-selection-mismatch", "/binding_descriptors/"+id, "a binding descriptor does not equal its selected variation outcome")
			}
			if err := b.append(item); err != nil {
				return err
			}
		}
	}
	return nil
}
func entryBindings(request Request, input compilationInputs, c coordinate, row selectionRow) ([]json.RawMessage, []admittedDescriptor, error) {
	if !isNull(input.spec.Factorial) {
		return factorialEntryBindings(request, input, c, row)
	}
	collector := entryBindingCollector{selected: []admittedDescriptor{}, records: []json.RawMessage{}, seen: map[string]bool{}}
	for _, selection := range row.selections {
		if err := collector.selection(request, input, c, selection); err != nil {
			return nil, nil, err
		}
	}
	for _, item := range input.descriptors {
		if item.wire.Target.Plane != planeParticipant || item.wire.Condition != text(c.ConditionID) {
			continue
		}
		if err := collector.append(item); err != nil {
			return nil, nil, err
		}
	}
	if len(collector.records) > request.Limits.MaxBindingsPerEntry {
		return nil, nil, refuse("binding-limit-exceeded", "/binding_descriptors", "entry bindings exceed the compilation limit")
	}
	return collector.records, collector.selected, nil
}
func entryConfigurations(ctx context.Context, request Request, input compilationInputs, selected sdl.InstantiatedScenario, bindings []admittedDescriptor) ([]json.RawMessage, error) {
	grouped, err := configurationOverrides(input, bindings)
	if err != nil {
		return nil, err
	}
	if len(grouped) > request.Limits.MaxBindingsPerEntry {
		return nil, refuse("participant-configuration-limit-exceeded", "/binding_descriptors", "participant configuration count exceeds the compilation limit")
	}
	result := []json.RawMessage{}
	keys := slices.SortedFunc(maps.Keys(grouped), func(a, b ParticipantManifestKey) int {
		return strings.Compare(a.ParticipantAddress+"\x00"+a.ImplementationName+"\x00"+a.ImplementationVersion+"\x00"+a.ManifestVersion, b.ParticipantAddress+"\x00"+b.ImplementationName+"\x00"+b.ImplementationVersion+"\x00"+b.ManifestVersion)
	})
	for _, key := range keys {
		raw, realizeErr := realizeEntryConfiguration(ctx, request, input, selected, key, grouped[key])
		if realizeErr != nil {
			return nil, realizeErr
		}
		result = append(result, raw)
	}
	return result, nil
}
func realizeEntryConfiguration(ctx context.Context, request Request, input compilationInputs, selected sdl.InstantiatedScenario, key ParticipantManifestKey, overrides []admission.ConfigurationOverride) (json.RawMessage, error) {
	manifest, present := input.participants[key]
	if !present {
		return nil, trialInvalid()
	}
	raw, err := encoded(manifest)
	if err != nil {
		return nil, err
	}
	validatorKey, contextValidator, err := entryConfigurationContext(ctx, request, selected, raw)
	if err != nil {
		return nil, err
	}
	digest, err := hash(json.RawMessage(raw))
	if err != nil {
		return nil, err
	}
	configuration, err := admission.RealizeParticipantConfiguration(ctx, admission.ParticipantConfigurationRequest{ParticipantAddress: key.ParticipantAddress, Manifest: manifest, ManifestRef: key.ImplementationName, ManifestDigest: digest, Overrides: overrides, Validator: request.ParticipantConfigurationValidators[validatorKey], ControlContext: contextValidator})
	if err != nil {
		if category, known := fault.CategoryOf(err); known && category == fault.InvalidInput {
			return nil, refuse("participant-configuration-rejected", "/binding_descriptors", "participant complete configuration failed owner validation")
		}
		return nil, err
	}
	raw, err = encoded(configuration)
	if err != nil {
		return nil, err
	}
	return raw, nil
}

//nolint:ireturn // Return the installed control-context interface without granting authority.
func entryConfigurationContext(ctx context.Context, request Request, selected sdl.InstantiatedScenario, raw []byte) (ConfigurationValidatorKey, admission.ParticipantControlContextValidator, error) {
	var err error
	var metadata struct {
		Registry struct {
			Owner struct {
				ID      string `json:"validator_id"`
				Version string `json:"validator_version"`
			} `json:"owner"`
			Targets map[string]struct {
				Context json.RawMessage `json:"control_context"`
			} `json:"targets"`
		} `json:"configuration_registry"`
	}
	if decode(raw, &metadata) != nil {
		return ConfigurationValidatorKey{}, nil, trialInvalid()
	}
	validatorKey := ConfigurationValidatorKey{metadata.Registry.Owner.ID, metadata.Registry.Owner.Version}
	contextValidator := request.ParticipantControlContextValidators[validatorKey]
	for _, target := range metadata.Registry.Targets {
		if !isNull(target.Context) {
			factory := request.ParticipantControlContextFactories[validatorKey]
			if factory == nil {
				return ConfigurationValidatorKey{}, nil, refuse("participant-configuration-rejected", "/binding_descriptors", "participant complete configuration failed owner validation")
			}
			contextValidator, err = configurationContextForScenario(ctx, factory, selected)
			if err != nil {
				return ConfigurationValidatorKey{}, nil, err
			}
			break
		}
	}
	return validatorKey, contextValidator, nil
}
func configurationOverrides(input compilationInputs, bindings []admittedDescriptor) (map[ParticipantManifestKey][]admission.ConfigurationOverride, error) {
	grouped := factorialDefaultConfigurations(input)
	for _, item := range bindings {
		target := item.wire.Target
		if target.Plane != planeParticipant {
			continue
		}
		key := ParticipantManifestKey{ParticipantAddress: target.Participant, ImplementationName: target.Name, ImplementationVersion: target.Version, ManifestVersion: target.ManifestVersion}
		var value struct {
			Kind      string `json:"kind"`
			Literal   any    `json:"value"`
			Reference string `json:"reference_id"`
		}
		if decode(item.wire.rawValue(), &value) != nil {
			return nil, trialInvalid()
		}
		grouped[key] = append(grouped[key], admission.ConfigurationOverride{TargetID: target.Target, Value: admission.BindingValue{Kind: value.Kind, Literal: value.Literal, ReferenceID: value.Reference}})
	}
	return grouped, nil
}
func (d descriptor) rawValue() json.RawMessage { raw, _ := encoded(d.Value); return raw }
