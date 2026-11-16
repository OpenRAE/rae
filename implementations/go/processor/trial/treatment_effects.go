package trial

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type typedParticipantEffect struct {
	Address        string            `json:"participant_address"`
	Implementation json.RawMessage   `json:"implementation"`
	Values         []json.RawMessage `json:"values"`
}

func typedFactorialSignature(entry trialEntry, scenario sdl.InstantiatedScenario) (string, error) {
	raw, err := sdl.ModelBytes(scenario)
	if err != nil {
		return "", err
	}
	var model map[string]json.RawMessage
	if decode(raw, &model) != nil {
		return "", trialInvalid()
	}
	provenance, err := operativeProvenance(model["instantiation_provenance"])
	if err != nil {
		return "", err
	}
	delete(model, "instantiation_provenance")
	participants, err := typedParticipantEffects(entry.Configurations, model["control_context_assets"])
	if err != nil {
		return "", err
	}
	apparatus, err := bindingEffects(entry.Bindings, false)
	if err != nil {
		return "", err
	}

	return hash([]any{model, provenance, participants, apparatus})
}
func typedParticipantEffects(configurations []json.RawMessage, rawAssets json.RawMessage) ([]typedParticipantEffect, error) {
	var assets map[string]json.RawMessage
	if decode(rawAssets, &assets) != nil {
		return nil, trialInvalid()
	}
	result := make([]typedParticipantEffect, 0, len(configurations))
	for _, raw := range configurations {
		var configuration struct {
			Address       string `json:"participant_address"`
			Configuration struct {
				Implementation json.RawMessage   `json:"implementation_identity"`
				Values         []json.RawMessage `json:"values"`
			} `json:"configuration"`
		}
		if decode(raw, &configuration) != nil {
			return nil, trialInvalid()
		}
		effect := typedParticipantEffect{configuration.Address, configuration.Configuration.Implementation, []json.RawMessage{}}
		for _, rawValue := range configuration.Configuration.Values {
			value, err := typedConfigurationEffect(rawValue, assets)
			if err != nil {
				return nil, err
			}
			effect.Values = append(effect.Values, value)
		}
		result = append(result, effect)
	}
	slices.SortFunc(result, func(a, b typedParticipantEffect) int { return strings.Compare(a.Address, b.Address) })
	return result, nil
}
func typedConfigurationEffect(raw json.RawMessage, assets map[string]json.RawMessage) (json.RawMessage, error) {
	var value map[string]json.RawMessage
	if decode(raw, &value) != nil {
		return nil, trialInvalid()
	}
	delete(value, "origin")
	if !isNull(value["control_context_selection"]) {
		var selection struct {
			Slot        string `json:"slot_id"`
			Declaration string `json:"declaration_ref"`
		}
		if decode(value["control_context_selection"], &selection) != nil {
			return nil, trialInvalid()
		}
		var asset struct {
			Kind    string `json:"kind"`
			Content struct {
				Checksum json.RawMessage `json:"checksum"`
				Media    string          `json:"media_type"`
				Size     json.RawMessage `json:"size_bytes"`
			} `json:"content"`
			Participants []string `json:"participant_addresses"`
			Roles        []string `json:"role_refs"`
		}
		rawAsset, present := assets[strings.TrimPrefix(selection.Declaration, "control_context_assets.")]
		if !present || decode(rawAsset, &asset) != nil {
			return nil, trialInvalid()
		}
		slices.Sort(asset.Participants)
		slices.Sort(asset.Roles)
		context, err := encoded(struct {
			Slot         string          `json:"slot_id"`
			Kind         string          `json:"kind"`
			Checksum     json.RawMessage `json:"checksum"`
			Media        string          `json:"media_type"`
			Size         json.RawMessage `json:"size_bytes"`
			Participants []string        `json:"participant_addresses"`
			Roles        []string        `json:"role_refs"`
		}{selection.Slot, asset.Kind, asset.Content.Checksum, asset.Content.Media, asset.Content.Size, asset.Participants, asset.Roles})
		if err != nil {
			return nil, err
		}
		delete(value, "value")
		value["control_context_selection"] = context
	}
	return encoded(value)
}
func operativeProvenance(raw json.RawMessage) (json.RawMessage, error) {
	var source struct {
		Capabilities []struct {
			Pointer string            `json:"field_pointer"`
			Allowed []json.RawMessage `json:"allowed_values"`
		} `json:"capability_constraints"`
		Derivations  []json.RawMessage `json:"parameter_derivations"`
		Explicitness []struct {
			Path           string `json:"model_path"`
			Classification string `json:"classification"`
		} `json:"explicitness"`
		Designations []json.RawMessage            `json:"realization_designations"`
		Constraints  []map[string]json.RawMessage `json:"realization_constraints"`
	}
	if decode(raw, &source) != nil {
		return nil, trialInvalid()
	}
	capabilities := []json.RawMessage{}
	for _, constraint := range source.Capabilities {
		allowed, err := canonicalRows(constraint.Allowed)
		if err != nil {
			return nil, err
		}
		effect, err := canonical(struct {
			Pointer string            `json:"field_pointer"`
			Allowed []json.RawMessage `json:"allowed_values"`
		}{constraint.Pointer, allowed})
		if err != nil {
			return nil, err
		}
		capabilities = append(capabilities, effect)
	}
	slices.SortFunc(capabilities, func(a, b json.RawMessage) int { return strings.Compare(string(a), string(b)) })
	constraints := []json.RawMessage{}
	for _, constraint := range source.Constraints {
		delete(constraint, "provenance")
		effect, err := encoded(constraint)
		if err != nil {
			return nil, err
		}
		constraints = append(constraints, effect)
	}
	if source.Derivations == nil {
		source.Derivations = []json.RawMessage{}
	}
	if source.Explicitness == nil {
		source.Explicitness = []struct {
			Path           string `json:"model_path"`
			Classification string `json:"classification"`
		}{}
	}
	if source.Designations == nil {
		source.Designations = []json.RawMessage{}
	}
	return encoded(struct {
		Capabilities []json.RawMessage `json:"capability_constraints"`
		Derivations  []json.RawMessage `json:"parameter_derivations"`
		Explicitness any               `json:"explicitness"`
		Designations []json.RawMessage `json:"realization_designations"`
		Constraints  []json.RawMessage `json:"realization_constraints"`
	}{capabilities, source.Derivations, source.Explicitness, source.Designations, constraints})
}
func canonicalRows(rows []json.RawMessage) ([]json.RawMessage, error) {
	result := make([]json.RawMessage, len(rows))
	for i, raw := range rows {
		value, err := canonical(raw)
		if err != nil {
			return nil, err
		}
		result[i] = value
	}
	slices.SortFunc(result, func(a, b json.RawMessage) int { return strings.Compare(string(a), string(b)) })
	return result, nil
}

func bindingEffects(bindings []json.RawMessage, includeScenario bool) ([]json.RawMessage, error) {
	effects := []json.RawMessage{}
	for _, raw := range bindings {
		var record struct {
			Descriptor map[string]json.RawMessage `json:"descriptor"`
		}
		if decode(raw, &record) != nil {
			return nil, trialInvalid()
		}
		var target descriptorTarget
		if decode(record.Descriptor["target"], &target) != nil {
			return nil, trialInvalid()
		}
		if target.Plane == planeParticipant || !includeScenario && target.Plane != "apparatus" {
			continue
		}
		for _, key := range []string{"binding_id", "source_factor_id", "source_factor_level_id", "source_condition_id"} {
			delete(record.Descriptor, key)
		}
		effect, err := canonical(record.Descriptor)
		if err != nil {
			return nil, err
		}
		effects = append(effects, effect)
	}
	slices.SortFunc(effects, func(a, b json.RawMessage) int { return strings.Compare(string(a), string(b)) })
	return effects, nil
}

type scalarParticipantEffect struct {
	Address       string                     `json:"participant_address"`
	Configuration map[string]json.RawMessage `json:"configuration"`
}

func scalarParticipantEffects(configurations []json.RawMessage) ([]scalarParticipantEffect, error) {
	effects := make([]scalarParticipantEffect, 0, len(configurations))
	for _, raw := range configurations {
		var configuration scalarParticipantEffect
		if decode(raw, &configuration) != nil {
			return nil, trialInvalid()
		}
		var values []map[string]json.RawMessage
		if decode(configuration.Configuration["values"], &values) != nil {
			return nil, trialInvalid()
		}
		for _, value := range values {
			delete(value, "origin")
		}
		var err error
		configuration.Configuration["values"], err = encoded(values)
		if err != nil {
			return nil, err
		}
		effects = append(effects, configuration)
	}
	slices.SortFunc(effects, func(a, b scalarParticipantEffect) int { return strings.Compare(a.Address, b.Address) })
	return effects, nil
}
