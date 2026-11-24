package processor

import (
	"encoding/json"
	"fmt"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"
)

type participantEpisodeHistory struct {
	Type        string      `json:"event_type"`
	Participant string      `json:"participant_address"`
	Episode     string      `json:"episode_id"`
	Timestamp   string      `json:"timestamp"`
	Sequence    json.Number `json:"sequence_number"`
	Reason      *string     `json:"terminal_reason"`
	Control     *string     `json:"control_action"`
}
type participantEpisodeKey struct{ participant, episode string }
type participantEpisodeHistories struct {
	statuses map[participantEpisodeKey]map[string]bool
	list     bool
}

func participantEpisodeTerminal(typeName string) string {
	switch typeName {
	case "episode_completed":
		return "completed"
	case "episode_timed_out":
		return "timed_out"
	case "episode_truncated":
		return "truncated"
	case "episode_interrupted":
		return "interrupted"
	default:
		return ""
	}
}
func parseParticipantEpisodeHistories(input admission.Fragment) (participantEpisodeHistories, error) {
	result := participantEpisodeHistories{statuses: map[participantEpisodeKey]map[string]bool{}}
	if input == nil {
		return result, nil
	}
	raw, err := participantFragmentBytes(input, admission.RealizationValue)
	if err != nil {
		return result, err
	}
	groups, isList := participantEpisodeGroups(raw)
	result.list = isList
	owner, err := processorAdmissionOwner()
	if err != nil {
		return result, err
	}
	for _, group := range groups {
		var entries []json.RawMessage
		if participantDecode(group, &entries) != nil {
			continue
		}
		for _, raw := range entries {
			event, valid := participantValidTerminalEpisode(raw, owner)
			if !valid {
				continue
			}
			key := participantEpisodeKey{event.Participant, event.Episode}
			if result.statuses[key] == nil {
				result.statuses[key] = map[string]bool{}
			}
			result.statuses[key][participantEpisodeTerminal(event.Type)] = true
		}
	}
	return result, nil
}
func participantEpisodeGroups(raw []byte) ([]json.RawMessage, bool) {
	if len(raw) > 0 && raw[0] == '[' {
		return []json.RawMessage{raw}, true
	}
	var mapping map[string]json.RawMessage
	valid := participantDecode(raw, &mapping) == nil
	if !valid {
		return nil, false
	}
	result := []json.RawMessage{}
	for _, key := range sortedParticipantKeys(mapping) {
		result = append(result, mapping[key])
	}
	return result, false
}
func participantValidTerminalEpisode(raw json.RawMessage, owner *admission.Validator) (participantEpisodeHistory, bool) {
	var event participantEpisodeHistory
	if owner.CheckModelFragment("runtime-snapshot-v1", "#/$defs/ParticipantEpisodeHistoryEventModel", raw, participantRelationLimits()) != nil || participantDecode(raw, &event) != nil {
		return event, false
	}
	terminal := participantEpisodeTerminal(event.Type)
	valid := terminal != "" && event.Reason != nil && *event.Reason == terminal && event.Control == nil && !strings.ContainsAny(string(event.Sequence), ".eE") && !strings.HasPrefix(string(event.Sequence), "-")
	return event, valid
}
func (episodes participantEpisodeHistories) closes(events []participantHistoryEvent) bool {
	if !episodes.list || len(events) == 0 {
		return false
	}
	for _, event := range events {
		if len(episodes.statuses[participantEpisodeKey{event.Participant, event.Episode}]) == 0 {
			return false
		}
	}
	return true
}
func (event participantHistoryEvent) evidenceRefs() map[string]bool {
	result := map[string]bool{}
	add := func(refs []string) {
		for _, ref := range refs {
			result[ref] = true
		}
	}
	add(event.details.evidence)
	if event.Result != nil {
		add(event.Result.EvidenceRefs)
		for _, record := range event.Result.Preconditions {
			add(record.EvidenceRefs)
		}
		for _, record := range event.Result.Effects {
			add(record.EvidenceRefs)
		}
	}
	for _, edge := range event.Attributions {
		add(edge.Evidence)
	}
	return result
}
func (analysis *participantHistoryAnalysis) outcomeEvidenceGrounding(pointer string, record participantOutcomeRecord, owner string, refs []string, grounded map[string]bool) {
	if owner != "" {
		owner = " " + owner
	}
	for _, ref := range refs {
		if !grounded[ref] {
			analysis.add(pointer, fmt.Sprintf("outcome interpretation %s%s evidence_ref %s is not grounded in event evidence", pyrepr.Quote(record.ID), owner, pyrepr.Quote(ref)))
		}
	}
}
func (analysis *participantHistoryAnalysis) outcomeGroundingViolations() {
	for index, event := range analysis.events {
		if event.Type != termObservationEmitted || len(event.Outcomes) == 0 {
			continue
		}
		pointer := participantEventLocator(index)
		grounded := event.evidenceRefs()
		for _, record := range event.Outcomes {
			analysis.outcomeRecordGrounding(pointer, event, record, grounded)
		}
	}
}
func (analysis *participantHistoryAnalysis) outcomeRecordGrounding(pointer string, event participantHistoryEvent, record participantOutcomeRecord, grounded map[string]bool) {
	analysis.outcomeEvidenceGrounding(pointer, record, "", record.EvidenceRefs, grounded)
	for _, source := range record.Sources {
		analysis.outcomeSourceGrounding(pointer, event, record, source)
		if source.Layer == "evidence_claim" && !grounded[source.Ref] {
			analysis.add(pointer, fmt.Sprintf("outcome interpretation %s evidence_claim source %s ref %s is not grounded in event evidence", pyrepr.Quote(record.ID), pyrepr.Quote(source.ID), pyrepr.Quote(source.Ref)))
		}
		analysis.outcomeEvidenceGrounding(pointer, record, "source "+pyrepr.Quote(source.ID), source.EvidenceRefs, grounded)
	}
	for _, target := range record.Targets {
		analysis.outcomeEvidenceGrounding(pointer, record, "target "+pyrepr.Quote(target.ID), target.EvidenceRefs, grounded)
	}
}
func (analysis *participantHistoryAnalysis) outcomeSourceGrounding(pointer string, event participantHistoryEvent, record participantOutcomeRecord, source participantOutcomeSourceRecord) {
	prefix := fmt.Sprintf("outcome interpretation %s source %s", pyrepr.Quote(record.ID), pyrepr.Quote(source.ID))
	switch source.Layer {
	case "participant_action_outcome":
		if event.Result == nil {
			analysis.add(pointer, prefix+" uses participant_action_outcome without an action_result")
			return
		}
		if source.Ref != event.Result.Action {
			analysis.add(pointer, fmt.Sprintf("%s ref %s does not match action_result action_contract_address %s", prefix, pyrepr.Quote(source.Ref), pyrepr.Quote(event.Result.Action)))
		}
		if source.Observed != event.Result.Status {
			analysis.add(pointer, fmt.Sprintf("%s observed_value %s does not match action_result status %s", prefix, pyrepr.Quote(source.Observed), pyrepr.Quote(event.Result.Status)))
		}
	case "participant_episode_status":
		statuses := analysis.episodes.statuses[participantEpisodeKey{record.Participant, record.Episode}]
		if len(statuses) == 0 {
			analysis.add(pointer, prefix+" participant_episode_status is not grounded by a terminal participant_episode_history event")
			return
		}
		if !statuses[source.Observed] {
			expected := sortedParticipantKeys(statuses)
			for index := range expected {
				expected[index] = pyrepr.Quote(expected[index])
			}
			analysis.add(pointer, fmt.Sprintf("%s observed_value %s does not match participant_episode_history terminal status %s", prefix, pyrepr.Quote(source.Observed), strings.Join(expected, ", ")))
		}
	}
}
func participantTupleRepr(values []string) string {
	quoted := slices.Clone(values)
	for index := range quoted {
		quoted[index] = pyrepr.Quote(quoted[index])
	}
	if len(quoted) == 1 {
		return "(" + quoted[0] + ",)"
	}
	return "(" + strings.Join(quoted, ", ") + ")"
}
func (analysis *participantHistoryAnalysis) temporalViolations() {
	for index, event := range analysis.events {
		if len(event.Temporal) == 0 {
			continue
		}
		pointer := participantEventLocator(index)
		action, present := analysis.model.participants.actions[participantText(event.Action)]
		if !present {
			analysis.add(pointer, "temporal context cannot resolve action contract "+pyrepr.Quote(participantText(event.Action)))
			continue
		}
		declared := map[string]participantTemporalDeclaration{}
		for _, definition := range action.temporal {
			declared[definition.ID] = definition
		}
		for _, context := range event.Temporal {
			definition, present := declared[context.ID]
			if !present {
				analysis.add(pointer, "temporal context references undeclared temporal_contract_id "+pyrepr.Quote(context.ID))
				continue
			}
			analysis.temporalContextViolations(pointer, context, definition, action)
		}
	}
}
func (analysis *participantHistoryAnalysis) temporalContextViolations(pointer string, context participantTemporalContext, definition participantTemporalDeclaration, action participantAction) {
	prefix := "temporal context " + pyrepr.Quote(context.ID)
	for _, field := range []struct{ name, actual, expected string }{{"time_domain", context.Domain, definition.Domain}, {"clock_authority", context.Authority, definition.Authority}} {
		if field.actual != field.expected {
			analysis.add(pointer, fmt.Sprintf("%s %s %s does not match compiled contract %s", prefix, field.name, pyrepr.Quote(field.actual), pyrepr.Quote(field.expected)))
		}
	}
	if !slices.Equal(context.EventPoints, definition.EventPoints) {
		analysis.add(pointer, fmt.Sprintf("%s event_points %s do not match compiled contract %s", prefix, participantTupleRepr(context.EventPoints), participantTupleRepr(definition.EventPoints)))
	}
	for _, ref := range analysis.violations.difference(context.BackendDisclosureRefs, definition.BackendDisclosureRefs) {
		analysis.add(pointer, fmt.Sprintf("%s reports backend_disclosure_ref %s not declared by the temporal contract", prefix, pyrepr.Quote(ref)))
	}
	disclosures := []string{}
	for _, disclosure := range action.BackendTimingDisclosures {
		disclosures = append(disclosures, disclosure.DisclosureID)
	}
	for _, ref := range analysis.violations.difference(context.BackendDisclosureRefs, disclosures) {
		analysis.add(pointer, fmt.Sprintf("%s reports unknown backend_disclosure_ref %s", prefix, pyrepr.Quote(ref)))
	}
	for _, field := range []struct {
		name             string
		actual, expected *string
	}{{"reset_boundary", context.Reset, definition.Reset}, {termReplayBoundary, context.Replay, definition.Replay}} {
		if field.expected != nil && !participantOptionalEqual(field.actual, field.expected) {
			analysis.add(pointer, fmt.Sprintf("%s %s %s does not match compiled contract %s", prefix, field.name, participantOptionalRepr(field.actual), participantOptionalRepr(field.expected)))
		}
	}
}
