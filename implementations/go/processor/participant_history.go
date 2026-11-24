package processor

import (
	"encoding/json"
	"fmt"
	"math/big"
	"slices"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"
)

const participantHistoryLocator = "runtime.snapshot.participant-behavior-history"

type participantHistoryAnalysis struct {
	model      *runtimeModel
	events     []participantHistoryEvent
	findings   []diagnostic.Diagnostic
	violations *participantViolations
	episodes   participantEpisodeHistories
}

func newParticipantHistoryAnalysis(model *runtimeModel) *participantHistoryAnalysis {
	return &participantHistoryAnalysis{model: model, events: []participantHistoryEvent{}, findings: []diagnostic.Diagnostic{}, violations: newParticipantViolations()}
}
func participantEventLocator(index int) string {
	return fmt.Sprintf("%s[%d]", participantHistoryLocator, index)
}
func (analysis *participantHistoryAnalysis) add(pointer, message string) {
	analysis.violations.add(message)
	if analysis.violations.err == nil {
		analysis.findings = append(analysis.findings, participantFinding("participant.behavior-history-violation", "", pointer, message))
	}
}
func (analysis *participantHistoryAnalysis) collect(pointer string, start int) {
	for _, message := range analysis.violations.messages[start:] {
		analysis.findings = append(analysis.findings, participantFinding("participant.behavior-history-violation", "", pointer, message))
	}
}
func (analysis *participantHistoryAnalysis) normalize(raw []json.RawMessage, participant string, scoped bool) {
	for index, input := range raw {
		if !analysis.violations.work.spend(1) {
			analysis.violations.err = participantContractInput()
			return
		}
		pointer := participantEventLocator(index)
		if !participantHistoryMapping(input) {
			analysis.add(pointer, "participant behavior history event must be a mapping")
			continue
		}
		event, err := parseParticipantHistoryEvent(input)
		if err != nil {
			analysis.add(pointer, "participant behavior history event is invalid")
			continue
		}
		if participant != "" && event.Participant != participant {
			analysis.add(pointer, fmt.Sprintf("participant behavior history event outer key %s does not match inner participant_address %s", pyrepr.Quote(participant), pyrepr.Quote(event.Participant)))
			continue
		}
		if scoped {
			analysis.addressViolations(event, pointer)
		}
		analysis.events = append(analysis.events, event)
	}
}
func (analysis *participantHistoryAnalysis) addressViolations(event participantHistoryEvent, pointer string) {
	if _, present := analysis.model.participants.actions[participantText(event.Action)]; !present {
		analysis.add(pointer, "participant behavior event references unknown action_contract_address "+participantOptionalRepr(event.Action))
	}
	if event.Boundary != nil {
		if _, present := analysis.model.participants.boundaries[*event.Boundary]; !present {
			analysis.add(pointer, "participant behavior event references unknown observation_boundary_address "+pyrepr.Quote(*event.Boundary))
		}
	}
}
func (analysis *participantHistoryAnalysis) structureViolations() {
	for index, event := range analysis.events {
		if event.details.present && event.Type != termObservationEmitted {
			analysis.add(participantEventLocator(index), "participant behavior details are only allowed on observation_emitted events")
		}
		if len(event.details.unsupported) > 0 {
			analysis.add(participantEventLocator(index), "observation details may only contain visible_refs, disclosed_refs, evidence_refs; unsupported fields: "+strings.Join(event.details.unsupported, ", "))
		}
	}
	groups := map[string][]participantHistoryEvent{}
	order := []string{}
	for _, event := range analysis.events {
		if _, present := groups[event.Instance]; !present {
			order = append(order, event.Instance)
		}
		groups[event.Instance] = append(groups[event.Instance], event)
	}
	for _, instance := range order {
		if message := participantActionInstanceViolation(groups[instance]); message != "" {
			analysis.add(instance, message)
		}
	}
	analysis.jointViolations()
}
func participantActionInstanceViolation(events []participantHistoryEvent) string {
	attempts := 0
	observations := []participantHistoryEvent{}
	transitions := []participantHistoryEvent{}
	for _, event := range events {
		switch event.Type {
		case termActionAttempted:
			attempts++
		case termStateTransitionRecorded:
			transitions = append(transitions, event)
		case termObservationEmitted:
			if event.terminal() {
				observations = append(observations, event)
			}
		}
	}
	switch {
	case attempts > 1:
		return "participant action instance may only have one action_attempted event"
	case attempts == 0:
		return "participant behavior events require a matching action_attempted event"
	case len(observations) != 1:
		return "participant action instance requires exactly one terminal observation or orphaned-action observation"
	}
	if participantText(observations[0].Status) == "orphaned_action" {
		return ""
	}
	if len(transitions) != 1 {
		return "participant action instance requires exactly one state transition"
	}
	if !participantOptionalEqual(observations[0].Digest, transitions[0].Digest) {
		return "terminal observation post_state_digest must match the state transition post_state_digest"
	}
	return ""
}
func (analysis *participantHistoryAnalysis) jointViolations() {
	groups := map[string]map[string][]string{}
	for _, event := range analysis.events {
		if event.Type != termActionAttempted || event.Joint == nil || event.Order == nil {
			continue
		}
		if groups[*event.Joint] == nil {
			groups[*event.Joint] = map[string][]string{}
		}
		order := string(*event.Order)
		groups[*event.Joint][order] = append(groups[*event.Joint][order], event.Participant+"/"+event.Instance)
	}
	for _, joint := range sortedParticipantKeys(groups) {
		orders := sortedParticipantKeys(groups[joint])
		slices.SortFunc(orders, func(left, right string) int {
			l, _ := new(big.Int).SetString(left, 10)
			r, _ := new(big.Int).SetString(right, 10)
			return l.Cmp(r)
		})
		for _, order := range orders {
			instances := groups[joint][order]
			if len(instances) < 2 {
				continue
			}
			slices.Sort(instances)
			analysis.add("joint-action-set."+joint, "joint action set realized_order "+order+" is assigned to multiple action_attempted events: "+strings.Join(instances, ", "))
		}
	}
}
func sortedParticipantKeys[T any](values map[string]T) []string {
	result := make([]string, 0, len(values))
	for key := range values {
		result = append(result, key)
	}
	slices.Sort(result)
	return result
}
func (analysis *participantHistoryAnalysis) contractViolations() {
	for index, event := range analysis.events {
		if !event.terminal() {
			continue
		}
		action, present := analysis.model.participants.actions[participantText(event.Action)]
		if !present || len(action.PreconditionClasses)+len(action.EffectClasses)+len(action.FailureClasses) == 0 {
			continue
		}
		pointer := participantEventLocator(index)
		if event.Result == nil {
			analysis.add(pointer, "terminal observation must carry SEM-211 action_result for "+participantText(event.Action))
			continue
		}
		start := len(analysis.violations.messages)
		event.Result.contractViolations(action, participantText(event.Action), analysis.violations)
		analysis.collect(pointer, start)
	}
	analysis.temporalViolations()
	analysis.outcomeContractViolations()
}
func (analysis *participantHistoryAnalysis) outcomeContractViolations() {
	for index, event := range analysis.events {
		if event.Type != termObservationEmitted {
			continue
		}
		for _, record := range event.Outcomes {
			rule, present := analysis.model.participants.outcomes[record.Rule]
			if !present {
				analysis.add(participantEventLocator(index), fmt.Sprintf("outcome interpretation %s references unknown rule_address %s", pyrepr.Quote(record.ID), pyrepr.Quote(record.Rule)))
				continue
			}
			start := len(analysis.violations.messages)
			record.contractViolations(rule, record.Rule, analysis.violations)
			analysis.collect(participantEventLocator(index), start)
		}
	}
}
func (analysis *participantHistoryAnalysis) result() ([]diagnostic.Diagnostic, error) {
	if analysis.violations.err != nil {
		return nil, analysis.violations.err
	}
	return analysis.findings, nil
}

// ParticipantBehaviorHistoryViolations checks bounded history against one compiled native owner.
func ParticipantBehaviorHistoryViolations(model RuntimeModel, participantAddress string, history, episodeHistory admission.Fragment) ([]diagnostic.Diagnostic, error) {
	owned, err := nativeRuntimeModel(model)
	if err != nil {
		return nil, err
	}
	if len(participantAddress) > 1<<20 || !utf8.ValidString(participantAddress) {
		return nil, participantContractInput()
	}
	var raw []json.RawMessage
	if checkErr := participantFragmentDecode(history, admission.RealizationValue, &raw); checkErr != nil {
		return nil, checkErr
	}
	if raw == nil {
		return nil, participantContractInput()
	}
	analysis := newParticipantHistoryAnalysis(owned)
	analysis.episodes, err = parseParticipantEpisodeHistories(episodeHistory)
	if err != nil {
		return nil, err
	}
	analysis.normalize(raw, participantAddress, true)
	if len(analysis.findings) > 0 || analysis.violations.err != nil {
		return analysis.result()
	}
	for _, check := range []func(){analysis.structureViolations, analysis.outcomeGroundingViolations, analysis.contractViolations, analysis.anchorViolations, analysis.visibilityViolations} {
		if analysis.violations.err != nil {
			return analysis.result()
		}
		check()
	}
	return analysis.result()
}

// ParticipantJointActionViolations checks realized order across valid participant histories.
func ParticipantJointActionViolations(histories admission.Fragment) ([]diagnostic.Diagnostic, error) {
	var raw map[string]json.RawMessage
	if err := participantFragmentDecode(histories, admission.RealizationValue, &raw); err != nil {
		return nil, err
	}
	if raw == nil {
		return nil, participantContractInput()
	}
	analysis := newParticipantHistoryAnalysis(nil)
	for _, key := range sortedParticipantKeys(raw) {
		var entries []json.RawMessage
		if participantDecode(raw[key], &entries) != nil || entries == nil {
			continue
		}
		group := newParticipantHistoryAnalysis(nil)
		group.normalize(entries, "", false)
		if !analysis.violations.work.spend(len(entries)) {
			return nil, participantContractInput()
		}
		if len(group.findings) > 0 || group.violations.err != nil {
			continue
		}
		analysis.events = append(analysis.events, group.events...)
	}
	analysis.jointViolations()
	return analysis.result()
}
