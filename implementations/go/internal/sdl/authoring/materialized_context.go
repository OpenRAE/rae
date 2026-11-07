package authoring

import (
	"maps"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

type controlAssetPin struct {
	id, version, digest string
	value               map[string]any
}

func (c materializedChecks) controlContext() error {
	assets, err := c.controlAssets()
	if err != nil {
		return err
	}
	roles := c.participantRoles()
	claimed := map[[2]string]bool{}
	for name, raw := range object(c.value[agentsSection]) {
		if err = c.contextSelections(object(raw), map[string]bool{name: true}, assets, roles, claimed); err != nil {
			return err
		}
	}
	for _, raw := range object(c.value[behaviorSection]) {
		spec := object(raw)
		if err = c.contextSelections(spec, selectedParticipants(spec, object(c.value[agentsSection]), roles), assets, roles, claimed); err != nil {
			return err
		}
	}
	return nil
}
func (c materializedChecks) controlAssets() (map[string]controlAssetPin, error) {
	result, versions := map[string]controlAssetPin{}, map[[2]string]string{}
	for name, raw := range object(c.value[controlAssetsSection]) {
		asset := object(raw)
		normalized, err := c.descriptorDefaults(asset, "ParticipantControlContextAssetModel")
		if err != nil {
			return nil, err
		}
		content, err := c.descriptorDefaults(object(asset["content"]), "ExperimentArtifactRefModel")
		if err != nil {
			return nil, err
		}
		normalized["content"] = content
		encoded, err := encode(normalized, jsonWorkingLimit(c.parser.limits.MaxComposedBytes, c.parser.limits.MaxComposedNodes), false)
		if err != nil {
			return nil, err
		}
		canonical, err := canonjson.JCS(encoded)
		if err != nil {
			return nil, err
		}
		pin := controlAssetPin{id: text(asset["asset_id"]), version: text(asset["asset_version"]), digest: digest.SHA256(canonical), value: asset}
		key := [2]string{pin.id, pin.version}
		if previous, present := versions[key]; present && previous != pin.digest {
			return nil, semanticInvalid()
		}
		versions[key] = pin.digest
		result[name] = pin
	}
	return result, nil
}
func (c materializedChecks) descriptorDefaults(value map[string]any, definition string) (map[string]any, error) {
	pointer := "#/$defs/" + definition
	schema := object(object(c.parser.schemas[materializedContract]["$defs"])[definition])
	result := maps.Clone(value)
	for field, raw := range object(schema["properties"]) {
		if _, present := result[field]; present {
			continue
		}
		fallback, found, err := c.scopes.defaultValue(pointer, field, object(raw))
		if err != nil {
			return nil, err
		}
		if found {
			result[field] = fallback
		}
	}
	return result, nil
}
func (c materializedChecks) contextSelections(owner map[string]any, participants map[string]bool, assets map[string]controlAssetPin, roles map[string]string, claimed map[[2]string]bool) error {
	for participant := range participants {
		for slot, raw := range object(owner[controlContextField]) {
			key := [2]string{participant, slot}
			if claimed[key] {
				return semanticInvalid()
			}
			claimed[key] = true
			binding := object(raw)
			if variable(binding[declarationRefField]) {
				continue
			}
			if err := c.contextSelection(binding, participant, roles[participant], assets); err != nil {
				return err
			}
		}
	}
	return nil
}
func (c materializedChecks) contextSelection(binding map[string]any, participant, role string, assets map[string]controlAssetPin) error {
	ref := text(binding[declarationRefField])
	candidates := c.index.aliases[ref]
	if len(candidates) != 1 {
		return semanticInvalid()
	}
	name := ""
	for address, candidate := range candidates {
		if candidate.kind != controlAssetsSection {
			return semanticInvalid()
		}
		name = address[len(controlAssetsSection)+1:]
	}
	asset, present := assets[name]
	expected := object(binding["asset_ref"])
	if !present || expected["asset_id"] != asset.id || expected["asset_version"] != asset.version || expected["asset_digest"] != asset.digest {
		return semanticInvalid()
	}
	if !stringSet(array(asset.value["participant_addresses"]))["agents."+participant] && !stringSet(array(asset.value["role_refs"]))[role] && !variable(role) {
		return semanticInvalid()
	}
	return nil
}
