package admission

import (
	"context"
	"encoding/json"
	"log/slog"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// ImplementationIdentity names the selected participant implementation.
type ImplementationIdentity struct{ Name, Version string }

// BindingValue is one strict literal scalar or logical secret reference.
type BindingValue struct {
	Kind        string
	Literal     any
	ReferenceID string
}

// ControlContextAssetReference pins one public SDL asset.
type ControlContextAssetReference struct{ AssetID, AssetVersion, AssetDigest string }

// ControlContextSelection binds the exact selected declaration and asset.
type ControlContextSelection struct {
	SlotID, DeclarationRef string
	AssetRef               ControlContextAssetReference
}

// ConfigurationOverride supplies a value for a canonical target or alias.
type ConfigurationOverride struct {
	TargetID string
	Value    BindingValue
}

// RealizedConfigurationValue keeps the value's declared type and origin.
type RealizedConfigurationValue struct {
	TargetID, ValueType, Origin string
	Value                       BindingValue
	ControlContextSelection     *ControlContextSelection
}

// ParticipantConfiguration is complete input to an installed owner validator.
type ParticipantConfiguration struct {
	ImplementationIdentity ImplementationIdentity
	ManifestVersion        string
	Owner                  BindingOwner
	Values                 []RealizedConfigurationValue
}

// ParticipantConfigurationValidator checks and normalizes complete settings.
type ParticipantConfigurationValidator interface {
	ValidateAndNormalize(ctx context.Context, configuration ParticipantConfiguration) (ParticipantConfiguration, error)
}

// ParticipantControlContextValidator checks a pinned concrete-scenario binding.
type ParticipantControlContextValidator interface {
	ValidateControlContextReference(ctx context.Context, participantAddress string, selection ControlContextSelection) error
}

// ParticipantConfigurationRequest supplies acquired authority, never secrets.
type ParticipantConfigurationRequest struct {
	ParticipantAddress, ManifestRef, ManifestDigest string
	Manifest                                        binding.ParticipantImplementationManifestV1
	Overrides                                       []ConfigurationOverride
	Validator                                       ParticipantConfigurationValidator
	ControlContext                                  ParticipantControlContextValidator
}

func configurationInvalid() error {
	return fault.New(fault.InvalidInput, "participant-configuration-invalid", nil)
}

func configurationHookError(ctx context.Context, err error) error {
	if ctx.Err() != nil {
		return ctx.Err()
	}
	if category, known := configurationHookCategory(err); known && category == fault.InvalidInput {
		return configurationInvalid()
	}
	slog.ErrorContext(ctx, "installed participant validator failed", slog.String("failure_class", "foreign"))
	return fault.New(fault.Operational, "participant-validator-failed", nil)
}

// RealizeParticipantConfiguration admits one complete configuration atomically.
// It checks owner normalization without resolving any logical secret reference.
func RealizeParticipantConfiguration(ctx context.Context, request ParticipantConfigurationRequest) (binding.ParticipantConfigurationResultV1, error) {
	if err := ctx.Err(); err != nil {
		return binding.ParticipantConfigurationResultV1{}, err
	}
	owner, err := packagedAdmission()
	if err != nil {
		return binding.ParticipantConfigurationResultV1{}, err
	}
	limits := ingress.Limits{MaxBytes: bindingTargetsMaxSize, MaxDepth: 64}
	if CheckTransport(request.Manifest, limits) != nil {
		return binding.ParticipantConfigurationResultV1{}, configurationInvalid()
	}
	manifest, err := owner.manifestRegistry(contractParticipant, request.Manifest)
	if err != nil || manifest.Registry == nil {
		return binding.ParticipantConfigurationResultV1{}, configurationInvalid()
	}
	if len(request.Overrides) > len(manifest.Registry.Targets) {
		return binding.ParticipantConfigurationResultV1{}, configurationInvalid()
	}
	configuration, err := constructConfiguration(ctx, request, manifest)
	if err != nil {
		return binding.ParticipantConfigurationResultV1{}, err
	}
	if err = configurationRequestBudget(request, configuration); err != nil {
		return binding.ParticipantConfigurationResultV1{}, err
	}
	configuration, err = normalizeCompleteConfiguration(ctx, request.Validator, configuration, manifest.Registry)
	if err != nil {
		return binding.ParticipantConfigurationResultV1{}, err
	}

	if err = configurationRequestBudget(request, configuration); err != nil {
		return binding.ParticipantConfigurationResultV1{}, err
	}
	return configurationResult(owner, request, configuration)
}

func constructConfiguration(ctx context.Context, request ParticipantConfigurationRequest, manifest manifestWire) (ParticipantConfiguration, error) {
	registry := manifest.Registry
	overrides, err := configurationOverrides(request.Overrides, registry)
	if err != nil {
		return ParticipantConfiguration{}, err
	}
	configuration := ParticipantConfiguration{ImplementationIdentity: ImplementationIdentity{manifest.Identity.Name, manifest.Identity.Version}, ManifestVersion: manifest.SchemaVersion, Owner: BindingOwner(registry.Owner), Values: []RealizedConfigurationValue{}}
	keys := make([]string, 0, len(registry.Targets))
	for key := range registry.Targets {
		keys = append(keys, key)
	}
	slices.Sort(keys)
	for _, key := range keys {
		entry, err := realizeConfigurationValue(ctx, request, registry.Targets[key], overrides)
		if err != nil {
			return ParticipantConfiguration{}, err
		}
		configuration.Values = append(configuration.Values, entry)
	}
	return configuration, nil
}

func configurationOverrides(supplied []ConfigurationOverride, registry *registryWire) (map[string]BindingValue, error) {
	overrides := map[string]BindingValue{}
	for _, override := range supplied {
		declaration, ok := configurationDeclaration(registry, override.TargetID)
		if !ok {
			return nil, configurationInvalid()
		}
		if _, exists := overrides[declaration.TargetID]; exists || !configurationValueValid(declaration, override.Value) {
			return nil, configurationInvalid()
		}
		overrides[declaration.TargetID] = override.Value
	}
	return overrides, nil
}

func realizeConfigurationValue(ctx context.Context, request ParticipantConfigurationRequest, declaration declarationWire, overrides map[string]BindingValue) (RealizedConfigurationValue, error) {
	selected, exists := overrides[declaration.TargetID]
	origin := "override"
	if !exists {
		var raw valueWire
		if len(declaration.Default) == 0 || decodeExact(declaration.Default, &raw) != nil {
			return RealizedConfigurationValue{}, configurationInvalid()
		}
		selected = BindingValue{Kind: raw.Kind, Literal: raw.Value}
		origin = "default"
	}
	if !configurationValueValid(declaration, selected) {
		return RealizedConfigurationValue{}, configurationInvalid()
	}
	entry := RealizedConfigurationValue{TargetID: declaration.TargetID, ValueType: declaration.ValueType, Origin: origin, Value: selected}
	selection, err := validateConfigurationControl(ctx, request, declaration, selected)
	if err != nil {
		return RealizedConfigurationValue{}, err
	}
	entry.ControlContextSelection = selection
	return entry, nil
}

func validateConfigurationControl(ctx context.Context, request ParticipantConfigurationRequest, declaration declarationWire, selected BindingValue) (*ControlContextSelection, error) {
	if declaration.ControlContext == nil {
		return nil, nil //nolint:nilnil // Absence is the valid non-control target result.
	}
	if request.ControlContext == nil {
		return nil, configurationInvalid()
	}
	ref, ok := selected.Literal.(string)
	if !ok {
		return nil, configurationInvalid()
	}
	selection, err := configurationControlSelection(declaration, ref)
	if err != nil {
		return nil, err
	}
	if err := checkConfigurationContext(ctx, request.ControlContext, request.ParticipantAddress, selection); err != nil {
		return nil, configurationHookError(ctx, err)
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return &selection, nil
}

func configurationDeclaration(registry *registryWire, name string) (declarationWire, bool) {
	if declaration, ok := registry.Targets[name]; ok {
		return declaration, true
	}
	for _, declaration := range registry.Targets {
		if slices.Contains(declaration.Aliases, name) {
			return declaration, true
		}
	}
	return declarationWire{}, false
}

func configurationValueValid(declaration declarationWire, input BindingValue) bool {
	if input.Kind == kindLiteral {
		if input.ReferenceID != "" {
			return false
		}
		if declaration.ValueType == termInteger && !configurationInteger(input.Literal) {
			return false
		}
		limits := value.Plan()
		limits.MaxScalarBytes = bindingTargetsMaxSize
		limits.MaxTotalScalarBytes = bindingTargetsMaxSize
		limits.MaxDocumentScalarBytes = 0
		raw, err := value.Encode(input.Literal, limits)
		if err != nil {
			return false
		}
		var scalar any
		if decodeExact(raw, &scalar) != nil {
			return false
		}
		return declaredValue(declaration, valueWire{Kind: input.Kind, Value: scalar})
	}
	return input.Kind == kindSecretReference && input.Literal == nil && input.ReferenceID != "" && declaredValue(declaration, valueWire{Kind: input.Kind})
}

func configurationInteger(input any) bool {
	switch n := input.(type) {
	case float32, float64:
		return false
	case json.Number:
		return !strings.ContainsAny(n.String(), ".eE")
	default:
		return true
	}
}

func configurationControlSelection(declaration declarationWire, ref string) (ControlContextSelection, error) {
	var asset struct {
		ID      string `json:"asset_id"`
		Version string `json:"asset_version"`
		Digest  string `json:"asset_digest"`
	}
	if json.Unmarshal(declaration.ControlContext.References[ref], &asset) != nil {
		return ControlContextSelection{}, configurationInvalid()
	}
	return ControlContextSelection{SlotID: declaration.ControlContext.SlotID, DeclarationRef: ref, AssetRef: ControlContextAssetReference{asset.ID, asset.Version, asset.Digest}}, nil
}

func copyConfiguration(input ParticipantConfiguration) ParticipantConfiguration {
	output := input
	output.Values = slices.Clone(input.Values)
	for i := range output.Values {
		if number, ok := output.Values[i].Value.Literal.(*big.Int); ok && number != nil {
			output.Values[i].Value.Literal = new(big.Int).Set(number)
		}
		if selection := input.Values[i].ControlContextSelection; selection != nil {
			copied := *selection
			output.Values[i].ControlContextSelection = &copied
		}
	}
	return output
}

func configurationNormalizationValid(original, normalized ParticipantConfiguration, registry *registryWire) bool {
	if normalized.ImplementationIdentity != original.ImplementationIdentity || normalized.ManifestVersion != original.ManifestVersion || normalized.Owner != original.Owner || len(normalized.Values) != len(original.Values) {
		return false
	}
	for i, entry := range normalized.Values {
		prior := original.Values[i]
		if entry.TargetID != prior.TargetID || entry.Origin != prior.Origin || entry.ValueType != prior.ValueType || entry.Value.Kind != prior.Value.Kind || !configurationValueValid(registry.Targets[entry.TargetID], entry.Value) {
			return false
		}
		if prior.Value.Kind == kindSecretReference && prior.Value.ReferenceID != entry.Value.ReferenceID {
			return false
		}
		if (entry.ControlContextSelection == nil) != (prior.ControlContextSelection == nil) {
			return false
		}
		if prior.ControlContextSelection != nil && (*prior.ControlContextSelection != *entry.ControlContextSelection || prior.Value.Literal != entry.Value.Literal) {
			return false
		}
	}
	return true
}

type configurationValuePayload struct {
	TargetID  string          `json:"target_id"`
	ValueType string          `json:"value_type"`
	Origin    string          `json:"origin"`
	Value     json.RawMessage `json:"value"`
	Control   json.RawMessage `json:"control_context_selection,omitempty"`
}
type configurationPayload struct {
	Identity struct {
		Name    string `json:"name"`
		Version string `json:"version"`
	} `json:"implementation_identity"`
	ManifestVersion string                      `json:"manifest_version"`
	Owner           ownerWire                   `json:"owner"`
	Values          []configurationValuePayload `json:"values"`
}

func configurationWire(configuration ParticipantConfiguration) (configurationPayload, error) {
	payload := configurationPayload{ManifestVersion: configuration.ManifestVersion, Owner: ownerWire(configuration.Owner), Values: []configurationValuePayload{}}
	payload.Identity.Name = configuration.ImplementationIdentity.Name
	payload.Identity.Version = configuration.ImplementationIdentity.Version
	for _, entry := range configuration.Values {
		var raw []byte
		var err error
		if entry.Value.Kind == kindLiteral {
			raw, err = json.Marshal(struct {
				Kind  string `json:"kind"`
				Value any    `json:"value"`
			}{entry.Value.Kind, entry.Value.Literal})
		} else {
			raw, err = json.Marshal(struct {
				Kind      string `json:"kind"`
				Reference string `json:"reference_id"`
			}{entry.Value.Kind, entry.Value.ReferenceID})
		}
		if err != nil {
			return configurationPayload{}, configurationInvalid()
		}
		item := configurationValuePayload{TargetID: entry.TargetID, ValueType: entry.ValueType, Origin: entry.Origin, Value: raw}
		if selection := entry.ControlContextSelection; selection != nil {
			item.Control, err = json.Marshal(struct {
				Slot      string `json:"slot_id"`
				Reference string `json:"declaration_ref"`
				Asset     struct {
					ID      string `json:"asset_id"`
					Version string `json:"asset_version"`
					Digest  string `json:"asset_digest"`
				} `json:"asset_ref"`
			}{Slot: selection.SlotID, Reference: selection.DeclarationRef, Asset: struct {
				ID      string `json:"asset_id"`
				Version string `json:"asset_version"`
				Digest  string `json:"asset_digest"`
			}{selection.AssetRef.AssetID, selection.AssetRef.AssetVersion, selection.AssetRef.AssetDigest}})
			if err != nil {
				return configurationPayload{}, configurationInvalid()
			}
		}
		payload.Values = append(payload.Values, item)
	}
	return payload, nil
}

func configurationResult(owner *Validator, request ParticipantConfigurationRequest, configuration ParticipantConfiguration) (binding.ParticipantConfigurationResultV1, error) {
	payload, err := configurationWire(configuration)
	if err != nil {
		return binding.ParticipantConfigurationResultV1{}, err
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return binding.ParticipantConfigurationResultV1{}, configurationInvalid()
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return binding.ParticipantConfigurationResultV1{}, configurationInvalid()
	}
	result := struct {
		SchemaVersion  string               `json:"schema_version"`
		Address        string               `json:"participant_address"`
		Ref            string               `json:"manifest_ref"`
		ManifestDigest string               `json:"manifest_digest"`
		Configuration  configurationPayload `json:"configuration"`
		Digest         string               `json:"configuration_digest"`
	}{"participant-configuration-result/v1", request.ParticipantAddress, request.ManifestRef, request.ManifestDigest, payload, digest.SHA256(canonical)}
	raw, err = json.Marshal(result)
	if err != nil {
		return binding.ParticipantConfigurationResultV1{}, configurationInvalid()
	}
	if owner.CheckPortable(termParticipantConfigurationResultV1, raw, ingress.Limits{MaxBytes: bindingTargetsMaxSize, MaxDepth: 64}) != nil {
		return binding.ParticipantConfigurationResultV1{}, configurationInvalid()
	}
	var output binding.ParticipantConfigurationResultV1
	if json.Unmarshal(raw, &output) != nil {
		return binding.ParticipantConfigurationResultV1{}, configurationInvalid()
	}
	return output, nil
}

// ValidateParticipantConfigurationSelection verifies all selected authority pins.
func ValidateParticipantConfigurationSelection(selection Fragment, result binding.ParticipantConfigurationResultV1) error {
	if CheckFragment(selection, ParticipantImplementationSelection) != nil || CheckTransport(result, ingress.Limits{MaxBytes: bindingTargetsMaxSize, MaxDepth: 64}) != nil {
		return configurationInvalid()
	}
	owner, err := packagedAdmission()
	if err != nil {
		return err
	}
	raw, err := owner.checkedJSON(termParticipantConfigurationResultV1, result)
	if err != nil {
		return configurationInvalid()
	}
	var output any
	if decodeExact(raw, &output) != nil {
		return configurationInvalid()
	}
	input := selection.Document()
	if !equal(at(input, fieldParticipantAddress), at(output, fieldParticipantAddress)) || !equal(at(input, "implementation_identity"), at(output, "configuration", "implementation_identity")) || !equal(at(input, "manifest_ref"), at(output, "manifest_ref")) || !equal(at(input, "manifest_digest"), at(output, "manifest_digest")) || !equal(at(input, termConfigurationDigest), at(output, termConfigurationDigest)) {
		return configurationInvalid()
	}
	return nil
}
