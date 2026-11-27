package authoring

import (
	"slices"
	"strings"
)

// Realized coordinates of the ADR-013 episode state and history contracts, and
// the ADR-095 decision epoch. A policy record that carries one of them asserts
// execution instead of declaring intent.
var realizedEpisodeStateFields = []string{ //nolint:gochecknoglobals // Fixed reference vocabulary.
	"control_action", "decision_epoch", "details", "episode_id", "event_type", "initialized_at",
	"last_control_action", "participant_address", "previous_episode_id", "sequence_number",
	"state_schema_version", "status", "terminal_reason", "terminated_at", "timestamp", "updated_at",
}

// Episode intent models, and the terminal reason that a condition map already fixes.
var episodeIntentModels = map[string]string{ //nolint:gochecknoglobals // Fixed reference vocabulary.
	"ParticipantEpisodeInitialization":       "",
	"ParticipantEpisodeInteractionStructure": "",
	"ParticipantEpisodeCompletionCondition":  "",
	"ParticipantEpisodeTimeoutCondition":     "",
	"ParticipantEpisodeTruncationCondition":  "truncated",
	"ParticipantEpisodeResetPolicy":          "",
	"ParticipantEpisodePolicy":               "",
}

// episodeIntentInput refuses the whole record before field validation when it
// carries realized episode state, as the reference model's before-validator does.
func episodeIntentInput(pointer string, schema, value map[string]any) error {
	implied, intent := episodeIntentModels[strings.TrimPrefix(pointer, "#/$defs/")]
	if !intent {
		return nil
	}
	if _, present := value["terminal_reason"]; implied != "" && present {
		return invalid()
	}
	declared := object(schema["properties"])
	for name := range value {
		if _, field := declared[name]; !field && slices.Contains(realizedEpisodeStateFields, name) {
			return invalid()
		}
	}
	return nil
}

// episodePolicyModel refuses a condition id that is both terminal and
// truncating, and a truncation that reuses the assertions of a completion. One
// evidenced set of assertions cannot end an episode as both completed and truncated.
func episodePolicyModel(value map[string]any) error {
	terminal, truncation := object(value["terminal_conditions"]), object(value["truncation_conditions"])
	completions := map[string]bool{}
	for id, condition := range terminal {
		if _, shared := truncation[id]; shared {
			return invalid()
		}
		if text(object(condition)["terminal_reason"]) == "completed" {
			completions[assertionSet(object(condition)["assertion_refs"])] = true
		}
	}
	for _, condition := range truncation {
		if completions[assertionSet(object(condition)["assertion_refs"])] {
			return invalid()
		}
	}
	return nil
}

// assertionSet returns an order- and duplicate-free identity of a reference list.
func assertionSet(refs any) string {
	values := make([]string, 0, len(array(refs)))
	for _, ref := range array(refs) {
		values = append(values, text(ref))
	}
	slices.Sort(values)
	return strings.Join(slices.Compact(values), "\x00")
}
