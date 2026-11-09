package authoring

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

type semanticControlPin struct {
	ID      string `json:"asset_id"`
	Version string `json:"asset_version"`
	Digest  string `json:"asset_digest"`
}
type semanticControlAsset struct {
	ID           string   `json:"asset_id"`
	Version      string   `json:"asset_version"`
	Participants []string `json:"participant_addresses"`
	Roles        []string `json:"role_refs"`
	pin          semanticControlPin
	canonical    bool
}
type semanticControlSelection struct {
	slot      string
	Reference string             `json:"declaration_ref"`
	Pin       semanticControlPin `json:"asset_ref"`
}
type semanticControlOwner struct {
	owner    semanticOwner
	bindings []semanticControlSelection
}

func (m *semanticModel) controlFacts() error {
	m.controlAssets = map[string]semanticControlAsset{}
	values := fieldValue(m.transport.ControlContextAssets)
	for _, name := range m.keys(controlAssetsSection) {
		var asset semanticControlAsset
		if err := json.Unmarshal(values[name], &asset); err != nil {
			return invalid()
		}
		encoded, err := m.controlAssetProjection(values[name])
		if err != nil {
			return err
		}
		canonical, canonicalErr := canonjson.JCS(encoded)
		asset.canonical = canonicalErr == nil
		asset.pin = semanticControlPin{ID: asset.ID, Version: asset.Version}
		if asset.canonical {
			asset.pin.Digest = digest.SHA256(canonical)
		}
		m.controlAssets[name] = asset
	}
	for _, name := range m.keys(agentsSection) {
		if err := m.controlOwnerFacts(semanticOwner{agentsSection, name}, fieldValue(fieldValue(m.transport.Agents)[name].ControlContext)); err != nil {
			return err
		}
	}
	for _, name := range m.keys(behaviorSection) {
		if err := m.controlOwnerFacts(semanticOwner{behaviorSection, name}, fieldValue(fieldValue(m.transport.BehaviorSpecifications)[name].ControlContext)); err != nil {
			return err
		}
	}
	return nil
}
func (m *semanticModel) controlOwnerFacts(owner semanticOwner, values map[string]json.RawMessage) error {
	row := semanticControlOwner{owner: owner}
	for _, slot := range m.keys(owner.section, owner.name, controlContextField) {
		binding := semanticControlSelection{slot: slot}
		if err := json.Unmarshal(values[slot], &binding); err != nil {
			return invalid()
		}
		row.bindings = append(row.bindings, binding)
	}
	if len(row.bindings) != 0 {
		m.controlOwners = append(m.controlOwners, row)
	}
	return nil
}
func (m *semanticModel) controlAssetProjection(raw json.RawMessage) ([]byte, error) {
	// Defaults are applied only to a private descriptor projection for its pin.
	// Reference predicates below use closed typed facts, never this transport map.
	value, err := ingress.Parse(raw, modelLimits(raw), ingress.Object)
	if err != nil {
		return nil, err
	}
	asset, err := m.scopes.descriptorDefaults(object(value), "ParticipantControlContextAssetModel")
	if err != nil {
		return nil, err
	}
	content, err := m.scopes.descriptorDefaults(object(asset[contentField]), "ExperimentArtifactRefModel")
	if err != nil {
		return nil, err
	}
	refs := array(content["satisfies_refs"])
	for i, ref := range refs {
		normalized, defaultErr := m.scopes.descriptorDefaults(object(ref), "ExperimentEvidenceSatisfactionReferenceModel")
		if defaultErr != nil {
			return nil, defaultErr
		}
		refs[i] = normalized
	}
	content["satisfies_refs"] = refs
	asset[contentField] = content
	return encode(asset, jsonWorkingLimit(m.parser.limits.MaxComposedBytes, m.parser.limits.MaxComposedNodes), false)
}

type semanticControlCheck struct {
	model     *semanticModel
	collector *semanticCollector
	seen      map[string]bool
	claimed   map[[2]string]bool
}

func (s *semanticControlCheck) report(message string) {
	if !s.seen[message] {
		s.seen[message] = true
		s.collector.report(semanticOwner{}, message)
	}
}
func (m *semanticModel) checkControlContext(c *semanticCollector) {
	check := semanticControlCheck{m, c, map[string]bool{}, map[[2]string]bool{}}
	check.descriptors()
	behaviors := map[string]semanticBehavior{}
	for _, row := range m.behaviors {
		behaviors[row.name] = row
	}
	for _, owner := range m.controlOwners {
		participants := []string{owner.owner.name}
		if owner.owner.section == behaviorSection {
			row := behaviors[owner.owner.name]
			participants = m.selectParticipants(row.participants, row.roles)
		}
		for _, name := range participants {
			for _, binding := range owner.bindings {
				check.selection(name, binding)
			}
		}
	}
}
func (s *semanticControlCheck) descriptors() {
	versions := map[[2]string]semanticControlPin{}
	for _, name := range s.model.keys(controlAssetsSection) {
		asset := s.model.controlAssets[name]
		if !asset.canonical {
			s.report("control-context.descriptor-not-canonical")
			continue
		}
		key := [2]string{asset.ID, asset.Version}
		if previous, known := versions[key]; known && previous != asset.pin {
			s.report("control-context.descriptor-conflict")
		}
		versions[key] = asset.pin
	}
}
func (s *semanticControlCheck) selection(participant string, binding semanticControlSelection) {
	key := [2]string{participant, binding.slot}
	if s.claimed[key] {
		s.report("control-context.selection-conflict")
	}
	s.claimed[key] = true
	if variable(binding.Reference) {
		return
	}
	if message := s.referenceIssue(participant, binding); message != "" {
		s.report(message)
	}
}
func (s *semanticControlCheck) referenceIssue(participant string, binding semanticControlSelection) string {
	candidates := s.model.index.aliases[binding.Reference]
	if len(candidates) == 0 {
		return "control-context.reference-missing"
	}
	if len(candidates) > 1 {
		return "control-context.reference-ambiguous"
	}
	for _, candidate := range candidates {
		if candidate.kind != controlAssetsSection {
			return "control-context.reference-incompatible"
		}
		asset := s.model.controlAssets[candidate.tokens[1]]
		return s.assetIssue(participant, binding, asset)
	}
	return ""
}
func (s *semanticControlCheck) assetIssue(participant string, binding semanticControlSelection, asset semanticControlAsset) string {
	if !asset.canonical {
		return "control-context.descriptor-not-canonical"
	}
	if binding.Pin != asset.pin {
		return "control-context.reference-stale"
	}
	if !s.model.definitions[agentsSection][participant] {
		return "control-context.participant-missing"
	}
	role := s.model.roles[participant]
	if !slices.Contains(asset.Participants, agentsSection+"."+participant) && !slices.Contains(asset.Roles, role) && !variable(role) {
		return "control-context.scope-incompatible"
	}
	return ""
}
