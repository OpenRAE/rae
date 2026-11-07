package admission

import (
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) scalarRules() map[string]definition {
	return map[string]definition{
		"random-stream-profile-transform-keys-match": {check: func(i validation.Invocation) error {
			return require(keyed(at(i.Instance, "transforms"), "transform_id"))
		}},
		"random-stream-address-draw-purpose-governed": {check: e.drawPurpose},
		"participant-random-stream-address-governed":  {check: e.participantDrawAddress},
		"random-stream-draw-record-local-coordinate-matches-address": {check: func(i validation.Invocation) error {
			return require(numericEqual(at(i.Instance, "local_coordinate"), at(i.Instance, "address", "local_coordinate")))
		}},
		"random-stream-draw-record-outcome-matches-exhaustion": {check: func(i validation.Invocation) error {
			return require(boolean(at(i.Instance, "rejection_exhausted")) == (at(i.Instance, messageOutcome) == nil))
		}},
		"unique-sentinel-decision-pointers": {check: uniqueSentinels},
	}
}

func (e *Validator) drawPurpose(i validation.Invocation) error {
	purposes, _ := e.authority.Vocabulary("random-stream-draw-purposes")
	return require(slices.Contains(purposes.Terms, stringAt(i.Instance, "draw_purpose")))
}
func (e *Validator) participantDrawAddress(i validation.Invocation) error {
	if err := e.drawPurpose(i); err != nil {
		return err
	}
	return require(strings.HasPrefix(stringAt(i.Instance, "policy_address"), "participant.autonomous-execution.") && strings.HasPrefix(stringAt(i.Instance, fieldParticipantAddress), "participant.behavior."))
}
func uniqueSentinels(i validation.Invocation) error {
	var pointers []string
	for _, decision := range array(at(i.Instance, "sentinel_decisions")) {
		pointers = append(pointers, stringAt(decision, "pointer"))
	}
	return require(unique(pointers))
}
