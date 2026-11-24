package processor

import (
	"bytes"
	"encoding/json"
	"slices"
	"strings"
)

type participantHistoryDetails struct {
	visible, disclosed, evidence, unsupported, errors []string
	present                                           bool
}
type participantAttributionCandidate struct {
	Kind        string `json:"candidate_kind"`
	Ref         string `json:"ref"`
	Description string `json:"description"`
}
type participantAttributionEdge struct {
	ID          string                          `json:"edge_id"`
	Participant string                          `json:"participant_address"`
	Episode     string                          `json:"episode_id"`
	Point       string                          `json:"observation_point"`
	Cause       participantAttributionCandidate `json:"cause_candidate"`
	Effect      participantAttributionCandidate `json:"effect_candidate"`
	Ordering    struct {
		Kind        string   `json:"basis_kind"`
		Relation    string   `json:"relation_ref"`
		Description string   `json:"description"`
		Refs        []string `json:"ordered_event_refs"`
	} `json:"ordering_basis"`
	EvidenceBasis struct {
		Capture         string   `json:"capture_apparatus"`
		Granularity     string   `json:"granularity"`
		Loss            string   `json:"loss_model"`
		Redaction       string   `json:"redaction_policy"`
		ObserverEffects []string `json:"observer_effects"`
	} `json:"evidence_basis"`
	Support     string   `json:"support_class"`
	Confidence  string   `json:"confidence"`
	Strength    string   `json:"strength"`
	Limitations []string `json:"limitations"`
	Evidence    []string `json:"evidence_refs"`
	Rule        *string  `json:"interpretation_rule_ref"`
}
type participantTemporalContext struct {
	ID                    string   `json:"temporal_contract_id"`
	Domain                string   `json:"time_domain"`
	Authority             string   `json:"clock_authority"`
	EventPoints           []string `json:"event_points"`
	Point                 string   `json:"observation_point"`
	BackendDisclosureRefs []string `json:"backend_disclosure_refs"`
	Reset                 *string  `json:"reset_boundary"`
	Replay                *string  `json:"replay_boundary"`
}
type participantHistoryEvent struct {
	Type           string                       `json:"event_type"`
	Timestamp      string                       `json:"timestamp"`
	Participant    string                       `json:"participant_address"`
	Episode        string                       `json:"episode_id"`
	Instance       string                       `json:"action_instance_id"`
	Action         *string                      `json:"action_contract_address"`
	Boundary       *string                      `json:"observation_boundary_address"`
	Status         *string                      `json:"observation_status"`
	Actor          *string                      `json:"actor_provenance"`
	Transition     *string                      `json:"state_transition_kind"`
	Digest         *string                      `json:"post_state_digest"`
	Joint          *string                      `json:"joint_action_set_id"`
	Order          *json.Number                 `json:"realized_order"`
	Interaction    *string                      `json:"interaction_class"`
	InteractionRef *string                      `json:"interaction_ref"`
	Shared         []string                     `json:"shared_state_refs"`
	Result         *participantActionResult     `json:"action_result"`
	Attributions   []participantAttributionEdge `json:"attribution_edges"`
	Outcomes       []participantOutcomeRecord   `json:"outcome_interpretations"`
	Temporal       []participantTemporalContext `json:"temporal_contexts"`
	details        participantHistoryDetails
}

func participantText(input *string) string {
	if input == nil {
		return ""
	}
	return *input
}
func (event participantHistoryEvent) terminal() bool {
	return event.Type == termObservationEmitted && event.Status != nil && (*event.Status == "terminal" || *event.Status == "orphaned_action")
}
func parseParticipantHistoryEvent(raw json.RawMessage) (participantHistoryEvent, error) {
	var result participantHistoryEvent
	owner, err := processorAdmissionOwner()
	if err != nil {
		return result, err
	}
	var fields map[string]json.RawMessage
	if participantDecode(raw, &fields) != nil {
		return result, participantContractInput()
	}
	fields["details"] = json.RawMessage(`{}`)
	if err := owner.CheckModelFragment("runtime-snapshot-v1", "#/$defs/ParticipantBehaviorHistoryEventModel", rawJSON(fields), participantRelationLimits()); err != nil {
		return result, participantContractInput()
	}
	if err := participantDecode(raw, &result); err != nil {
		return result, err
	}
	var details struct {
		Details map[string]json.RawMessage `json:"details"`
	}
	if err := participantDecode(raw, &details); err != nil {
		return result, err
	}
	result.details = parseParticipantHistoryDetails(details.Details)
	if !result.locallyValid() {
		return result, participantContractInput()
	}
	return result, nil
}
func parseParticipantHistoryDetails(raw map[string]json.RawMessage) participantHistoryDetails {
	result := participantHistoryDetails{visible: []string{}, disclosed: []string{}, evidence: []string{}, unsupported: []string{}, errors: []string{}}
	for name := range raw {
		if !slices.Contains([]string{termVisibleRefs, termDisclosedRefs, "evidence_refs"}, name) {
			result.unsupported = append(result.unsupported, name)
			result.present = true
		}
	}
	slices.Sort(result.unsupported)
	for _, field := range []struct {
		name   string
		target *[]string
	}{{termVisibleRefs, &result.visible}, {termDisclosedRefs, &result.disclosed}, {"evidence_refs", &result.evidence}} {
		parsed, message, present := parseParticipantDetailRefs(raw[field.name], field.name)
		result.present = result.present || present
		if message != "" {
			result.errors = append(result.errors, message)
		} else {
			*field.target = parsed
		}
	}
	return result
}
func parseParticipantDetailRefs(input json.RawMessage, name string) ([]string, string, bool) {
	if len(input) == 0 || string(input) == "[]" {
		return nil, "", false
	}
	prefix := "observation details field '" + name + "'"
	var values []json.RawMessage
	if input[0] != '[' || participantDecode(input, &values) != nil {
		return nil, prefix + " must be a list of strings", true
	}
	parsed := []string{}
	for _, item := range values {
		var text string
		if participantDecode(item, &text) != nil || text == "" {
			return nil, prefix + " must contain only non-empty strings", true
		}
		parsed = append(parsed, text)
	}
	if !participantUniqueStrings(parsed) {
		return nil, prefix + " must not contain duplicate refs", true
	}
	return parsed, "", true
}
func (event participantHistoryEvent) locallyValid() bool {
	if event.Participant == "" || event.Episode == "" || event.Instance == "" || event.Timestamp == "" || event.Action == nil || !strings.HasPrefix(*event.Action, "participant.action-contract.") {
		return false
	}
	if event.Boundary != nil && !strings.HasPrefix(*event.Boundary, "participant.observation-boundary.") {
		return false
	}
	if (event.Joint == nil) != (event.Order == nil) || !participantUniqueStrings(event.Shared) {
		return false
	}
	if event.Order != nil && (strings.ContainsAny(string(*event.Order), ".eE") || strings.HasPrefix(string(*event.Order), "-")) {
		return false
	}
	if !event.interactionValid() || !event.typeFieldsValid() || !event.nestedRecordsValid() {
		return false
	}
	return true
}
func (event participantHistoryEvent) interactionValid() bool {
	if event.Interaction == nil {
		return event.InteractionRef == nil
	}
	if event.Joint == nil {
		return false
	}
	if (*event.Interaction == "coordination" || *event.Interaction == "interference") && event.InteractionRef == nil {
		return false
	}
	return (*event.Interaction != "contention" && *event.Interaction != "shared_state_change") || len(event.Shared) > 0
}
func (event participantHistoryEvent) typeFieldsValid() bool {
	switch event.Type {
	case termActionAttempted:
		return event.Actor != nil && event.Boundary == nil && event.Status == nil && event.Transition == nil && event.Digest == nil && event.Result == nil
	case termStateTransitionRecorded:
		return event.Transition != nil && event.Digest != nil && event.Boundary == nil && event.Status == nil && event.Result == nil
	case termObservationEmitted:
		if event.Boundary == nil || event.Status == nil || event.Transition != nil {
			return false
		}
		return *event.Status != "terminal" || event.Digest != nil
	default:
		return false
	}
}
func (event participantHistoryEvent) nestedRecordsValid() bool {
	if event.Result != nil && (!event.Result.locallyValid() || event.Result.Participant != event.Participant || event.Result.Episode != event.Episode || event.Result.Instance != event.Instance || event.Result.Action != participantText(event.Action) || event.terminal() && event.Result.Status == termAccepted) {
		return false
	}
	return event.outcomeRecordsValid() && event.attributionRecordsValid() && event.temporalRecordsValid()
}
func (event participantHistoryEvent) outcomeRecordsValid() bool {
	ids := []string{}
	for _, record := range event.Outcomes {
		if !record.locallyValid() || event.Type != termObservationEmitted || record.Participant != event.Participant || record.Episode != event.Episode || !event.pointMatches(record.Point) {
			return false
		}
		ids = append(ids, record.ID)
	}
	return participantUniqueStrings(ids)
}
func (event participantHistoryEvent) attributionRecordsValid() bool {
	ids := []string{}
	grounded := event.groundedRefs()
	for _, edge := range event.Attributions {
		if !event.attributionValid(edge, grounded) {
			return false
		}
		ids = append(ids, edge.ID)
	}
	return participantUniqueStrings(ids)
}
func (event participantHistoryEvent) temporalRecordsValid() bool {
	ids := []string{}
	for _, context := range event.Temporal {
		if !participantUniqueStrings(context.EventPoints) || !participantUniqueStrings(context.BackendDisclosureRefs) {
			return false
		}
		ids = append(ids, context.ID)
	}
	return participantUniqueStrings(ids)
}
func (event participantHistoryEvent) pointMatches(point string) bool {
	if event.Result != nil {
		return point == event.Result.Point
	}
	return participantObservationPoint(point, event.Instance)
}
func (event participantHistoryEvent) groundedRefs() map[string]bool {
	result := map[string]bool{event.Instance: true, participantText(event.Action): true, participantText(event.Boundary): true, participantText(event.Digest): true}
	for _, refs := range [][]string{event.details.visible, event.details.disclosed, event.details.evidence} {
		for _, ref := range refs {
			result[ref] = true
		}
	}
	if event.Result == nil {
		return result
	}
	for _, refs := range [][]string{event.Result.Observations, event.Result.EvidenceRefs} {
		for _, ref := range refs {
			result[ref] = true
		}
	}
	for _, item := range event.Result.Preconditions {
		for _, ref := range append(slices.Clone(item.SupportRefs), item.EvidenceRefs...) {
			result[ref] = true
		}
	}
	for _, item := range event.Result.Effects {
		for _, ref := range append(slices.Clone(item.TargetRefs), item.EvidenceRefs...) {
			result[ref] = true
		}
	}
	return result
}
func participantOutcomeCandidate(kind string) bool {
	return slices.Contains([]string{"downstream_outcome", "objective_result", "evaluation_result"}, kind)
}
func (event participantHistoryEvent) attributionValid(edge participantAttributionEdge, grounded map[string]bool) bool {
	if !participantUniqueStrings(edge.Limitations) || !participantUniqueStrings(edge.Evidence) || !participantUniqueStrings(edge.Ordering.Refs) || !participantUniqueStrings(edge.EvidenceBasis.ObserverEffects) {
		return false
	}
	if event.Type != termObservationEmitted || edge.Participant != event.Participant || edge.Episode != event.Episode || !event.pointMatches(edge.Point) {
		return false
	}
	if edge.Ordering.Kind == "timestamp_adjacency" && slices.Contains([]string{"intervention_support", "replay_support", "counterfactual_support", "ablation_support", "structural_causal_support"}, edge.Support) {
		return false
	}
	if participantOutcomeCandidate(edge.Effect.Kind) && edge.Rule == nil {
		return false
	}
	if edge.Cause.Kind == "action" {
		if edge.Cause.Ref != event.Instance && edge.Cause.Ref != participantText(event.Action) {
			return false
		}
	} else if !grounded[edge.Cause.Ref] {
		return false
	}
	return participantOutcomeCandidate(edge.Effect.Kind) || grounded[edge.Effect.Ref]
}
func participantHistoryMapping(raw json.RawMessage) bool {
	trimmed := bytes.TrimSpace(raw)
	return len(trimmed) > 0 && trimmed[0] == '{'
}
