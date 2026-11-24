package admission

import (
	"context"
	"encoding/json"
	"math/big"
	"reflect"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func normalizeConfiguration(ctx context.Context, validator ParticipantConfigurationValidator, input ParticipantConfiguration) (result ParticipantConfiguration, err error) {
	defer func() {
		if recover() != nil {
			err = fault.New(fault.Operational, "participant-validator-panic", nil)
		}
	}()
	return validator.ValidateAndNormalize(ctx, copyConfiguration(input))
}
func checkConfigurationContext(ctx context.Context, validator ParticipantControlContextValidator, participant string, selection ControlContextSelection) (err error) {
	defer func() {
		if recover() != nil {
			err = fault.New(fault.Operational, "participant-validator-panic", nil)
		}
	}()
	return validator.ValidateControlContextReference(ctx, participant, selection)
}

// configurationBudget uses the existing exact JSON-size projection before
// invoking an installed normalizer or serializing a complete configuration.
func configurationDocument(configuration ParticipantConfiguration) (map[string]any, error) {
	values := make([]any, len(configuration.Values))
	for index, entry := range configuration.Values {
		binding := map[string]any{"kind": entry.Value.Kind}
		if entry.Value.Kind == kindLiteral {
			literal, err := configurationBudgetScalar(entry.Value.Literal)
			if err != nil {
				return nil, err
			}
			binding[termValue] = literal
		} else {
			binding["reference_id"] = entry.Value.ReferenceID
		}
		projected := map[string]any{"target_id": entry.TargetID, "value_type": entry.ValueType, termOrigin: entry.Origin, termValue: binding}
		if context := entry.ControlContextSelection; context != nil {
			projected["control_context_selection"] = map[string]any{"slot_id": context.SlotID, "declaration_ref": context.DeclarationRef, "asset_ref": map[string]any{"asset_id": context.AssetRef.AssetID, "asset_version": context.AssetRef.AssetVersion, "asset_digest": context.AssetRef.AssetDigest}}
		}
		values[index] = projected
	}
	owner := configuration.Owner
	document := map[string]any{"implementation_identity": map[string]any{"name": configuration.ImplementationIdentity.Name, termVersion: configuration.ImplementationIdentity.Version}, fieldManifestVersion: configuration.ManifestVersion, "owner": map[string]any{termContractID: owner.ContractID, "contract_version": owner.ContractVersion, "validator_id": owner.ValidatorID, "validator_version": owner.ValidatorVersion}, "values": values}
	return document, nil
}

func configurationBudget(configuration ParticipantConfiguration) error {
	document, err := configurationDocument(configuration)
	if err != nil {
		return err
	}
	return configurationTreeBudget(document)
}
func configurationRequestBudget(request ParticipantConfigurationRequest, configuration ParticipantConfiguration) error {
	document, err := configurationDocument(configuration)
	if err != nil {
		return err
	}
	slots := map[string]bool{}
	for _, entry := range configuration.Values {
		if control := entry.ControlContextSelection; control != nil {
			if slots[control.SlotID] {
				return configurationInvalid()
			}
			slots[control.SlotID] = true
		}
	}
	return configurationTreeBudget(map[string]any{"schema_version": "participant-configuration-result/v1", fieldParticipantAddress: request.ParticipantAddress, "manifest_ref": request.ManifestRef, "manifest_digest": request.ManifestDigest, "configuration": document, termConfigurationDigest: "sha256:0000000000000000000000000000000000000000000000000000000000000000"})
}
func configurationTreeBudget(document any) error {
	limits := value.Plan()
	limits.MaxDepth = 64
	limits.MaxScalarBytes = bindingTargetsMaxSize
	limits.MaxTotalScalarBytes = bindingTargetsMaxSize
	limits.MaxDocumentScalarBytes = 0
	projection := transportProjection{limits: limits, bytes: bindingTargetsMaxSize}
	if value.ValidateProjected(transportValue{reflect.ValueOf(document), true}, limits, projection.project) != nil {
		return configurationInvalid()
	}
	return nil
}
func configurationBudgetScalar(input any) (any, error) {
	switch input.(type) {
	case *big.Int:
		limits := value.Plan()
		raw, err := value.Encode(input, limits)
		if err != nil {
			return nil, configurationInvalid()
		}
		return json.Number(raw), nil
	case int, int8, int16, int32, int64, uint, uint8, uint16, uint32, uint64, float32, float64:
		raw, err := json.Marshal(input)
		if err != nil {
			return nil, configurationInvalid()
		}
		return json.Number(raw), nil
	default:
		return input, nil
	}
}

func normalizeCompleteConfiguration(ctx context.Context, validator ParticipantConfigurationValidator, configuration ParticipantConfiguration, registry *registryWire) (ParticipantConfiguration, error) {
	if validator == nil {
		return configuration, nil
	}
	normalized, err := normalizeConfiguration(ctx, validator, configuration)
	if err != nil {
		return ParticipantConfiguration{}, configurationHookError(ctx, err)
	}
	if err = ctx.Err(); err != nil {
		return ParticipantConfiguration{}, err
	}
	if configurationBudget(normalized) != nil || !configurationNormalizationValid(configuration, normalized, registry) {
		return ParticipantConfiguration{}, configurationInvalid()
	}
	return copyConfiguration(normalized), nil
}

// Error traversal is part of the foreign validator's boundary.
func configurationHookCategory(err error) (category fault.Category, known bool) {
	defer func() {
		if recover() != nil {
			category = 0
			known = false
		}
	}()
	return fault.CategoryOf(err)
}
