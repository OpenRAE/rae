package authoring

import (
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type treatmentDescriptor struct {
	Target struct {
		Family string `json:"scenario_family_id"`
		Point  string `json:"variation_point_id"`
		ID     string `json:"target_id"`
	} `json:"target"`
	FamilyDigest string `json:"scenario_family_digest"`
	Owner        struct {
		Contract         string `json:"contract_id"`
		Version          string `json:"contract_version"`
		Validator        string `json:"validator_id"`
		ValidatorVersion string `json:"validator_version"`
	} `json:"owner"`
	Outcome recordedOutcome `json:"outcome"`
}

// ValidateTreatment checks one exact typed selection against its native SDL owner.
func (p *Parser) ValidateTreatment(document *Document, data []byte) error {
	if document == nil || !document.Validated() || document.contract != expandedContract {
		return selectionInvalid()
	}
	if p.models.CheckModelFragment("experiment-authoring-input-v1", "#/$defs/ExperimentScenarioSelectionDescriptorModel", data, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return selectionInvalid()
	}
	var treatment treatmentDescriptor
	if json.Unmarshal(data, &treatment) != nil {
		return selectionInvalid()
	}
	digest, err := document.CanonicalDigest()
	if err != nil {
		return err
	}
	if treatment.Target.Family != text(document.semantic.root[nameField]) || treatment.FamilyDigest != digest || treatment.Owner.Contract != "sdl-authoring-input-v1" || treatment.Owner.Version != "1" || treatment.Owner.Validator != "raes-selected-scenario" || treatment.Owner.ValidatorVersion != "1" {
		return selectionInvalid()
	}
	for _, point := range document.semantic.variations {
		if point.name != treatment.Target.Point {
			continue
		}
		target, err := document.semantic.trialTarget(point)
		if err != nil {
			return err
		}
		if treatment.Target.ID != target || !point.admitsOutcome(treatment.Outcome) {
			return selectionInvalid()
		}
		return nil
	}
	return selectionInvalid()
}
func (m *semanticModel) trialTarget(point semanticVariation) (string, error) {
	if point.Target.Kind == termVariable {
		return variablesSection + "." + point.Target.Variable, nil
	}
	if point.Target.Slot == slotDetectionRuleSources {
		var selected declaration
		count := 0
		for _, entry := range m.index.aliases[point.Target.Owner] {
			if entry.kind == termNetworkDetectionEngines && len(entry.tokens) == 6 {
				selected = entry
				count++
			}
		}
		if count != 1 {
			return "", selectionInvalid()
		}
		record, present := provenancePointer(m.root, jsonpointer.FromTokens(selected.tokens[:len(selected.tokens)-1]))
		if !present {
			return "", selectionInvalid()
		}
		id := text(object(record)["network_detection_engine_id"])
		return nodesSection + "." + selected.node + ".runtime.network_detection_engines." + id + ".rule_sources", nil
	}
	section, _, _ := strings.Cut(point.Target.Slot, ".")
	owner, err := m.selectedOwner(point.Target.Owner, section)
	if err != nil {
		return "", err
	}
	return section + "." + owner + "." + selectionField(point.Target.Slot), nil
}
