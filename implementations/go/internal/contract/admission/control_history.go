package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) controlOccurrence(i validation.Invocation) error {
	context, ok := i.Context.(ControlOccurrenceContext)
	if !ok {
		return contextRequired()
	}
	records, hasV2, err := e.controlHistoryDocuments(context.ControlOccurrences())
	if err != nil {
		return err
	}
	if !hasV2 {
		return e.controlOccurrenceV1(i)
	}
	historyContext, ok := i.Context.(ControlOccurrenceHistoryContext)
	if !ok {
		return contextRequired()
	}
	if err := e.controlCandidate(records, i.Instance); err != nil {
		return err
	}
	return e.controlHistory(records, historyContext)
}

func controlLineage(v any) string {
	if stringAt(v, "schema_name") != "participant-control-occurrence" {
		return ""
	}
	switch stringAt(v, termSchemaVersion) {
	case "1.0.0":
		return termParticipantControlOccurrenceV1
	case "2.0.0":
		return termParticipantControlOccurrenceV2
	default:
		return ""
	}
}

func (e *Validator) controlHistoryDocuments(raw [][]byte) ([]any, bool, error) {
	if len(raw) > 4096 {
		return nil, false, invalid()
	}
	remaining := 64 * 1048576
	records := make([]any, 0, len(raw))
	hasV2 := false
	for _, data := range raw {
		if len(data) > remaining {
			return nil, false, invalid()
		}
		remaining -= len(data)
		v, err := ingress.Parse(data, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
		if err != nil {
			return nil, false, invalid()
		}
		id := controlLineage(v)
		if id == "" {
			return nil, false, invalid()
		}
		if _, err = e.contextDocument(id, data); err != nil {
			return nil, false, err
		}
		normal, err := e.defaulted(id, v)
		if err != nil {
			return nil, false, err
		}
		records = append(records, normal)
		hasV2 = hasV2 || id == termParticipantControlOccurrenceV2
	}
	return records, hasV2, nil
}

func (e *Validator) controlCandidate(records []any, candidate any) error {
	id := controlLineage(candidate)
	if id == "" {
		return invalid()
	}
	value, err := e.defaulted(id, candidate)
	if err != nil {
		return err
	}
	for _, record := range records {
		if equal(record, value) {
			return nil
		}
	}
	return invalid()
}

func (e *Validator) controlHistory(records []any, context ControlOccurrenceHistoryContext) error {
	policies, err := e.controlPolicies(context.ControlOccurrencePolicies())
	if err != nil {
		return err
	}
	available := context.ControlAvailableTargets()
	if err = controlAvailableTargets(available); err != nil {
		return err
	}
	episodes, order, err := controlEpisodes(records)
	if err != nil {
		return err
	}
	completions := map[string]bool{}
	v1 := []any{}
	for _, key := range order {
		batch := episodes[key]
		if controlLineage(batch[0]) == termParticipantControlOccurrenceV1 {
			v1 = append(v1, batch...)
			continue
		}
		if err := controlFoldBatch(batch, policies, available, completions); err != nil {
			return err
		}
	}
	if len(v1) > 0 {
		return e.controlV1Subset(v1, context)
	}
	return nil
}

func controlAvailableTargets(targets []AvailableControlTarget) error {
	if len(targets) > 4096 {
		return invalid()
	}
	for _, target := range targets {
		if !controlTargetKind(target.Target.Kind) || !controlReference(target.Target.Reference) || !controlReference(target.Target.ParticipantAddress) || !controlReference(target.Target.EpisodeID) || !controlCount(target.AvailableAt) || !controlCount(target.Target.Revision) || numericEqual(target.Target.Revision, jsonZero) {
			return invalid()
		}
	}
	return nil
}

func (e *Validator) controlPolicies(raw [][]byte) ([]any, error) {
	if len(raw) > 4096 {
		return nil, invalid()
	}
	remaining := 64 * 1048576
	policies := make([]any, 0, len(raw))
	for _, data := range raw {
		if len(data) > remaining {
			return nil, invalid()
		}
		remaining -= len(data)
		policy, err := e.controlPolicy(data)
		if err != nil {
			return nil, err
		}
		policies = append(policies, policy)
	}
	return policies, nil
}

func controlEpisodes(records []any) (map[string][]any, []string, error) {
	episodes := map[string][]any{}
	order := []string{}
	positions := map[string]any{}
	events := map[string]bool{}
	for _, record := range records {
		participant, event := stringAt(record, fieldParticipantAddress), stringAt(record, "event_id")
		position := at(record, "occurrence", "occurrence_revision")
		previous := positions[participant]
		if previous == nil {
			previous = jsonZero
		}
		if events[event] || !numericSuccessor(position, previous) {
			return nil, nil, invalid()
		}
		events[event] = true
		positions[participant] = position
		key := join(participant, stringAt(record, fieldEpisodeID))
		if len(episodes[key]) == 0 {
			order = append(order, key)
		} else if controlLineage(episodes[key][0]) != controlLineage(record) {
			return nil, nil, invalid()
		}
		episodes[key] = append(episodes[key], record)
	}
	return episodes, order, nil
}

func controlResolvePolicy(record any, policies []any) (any, error) {
	var selected any
	for _, policy := range policies {
		if !matchingFields(record, policy, fieldParticipantAddress, fieldEpisodeID, "semantics") || !equal(at(record, termPolicy), at(policy, "pin")) {
			continue
		}
		if selected != nil && !equal(selected, policy) {
			return nil, invalid()
		}
		selected = policy
	}
	if selected == nil {
		return nil, invalid()
	}
	return selected, nil
}

type controlSubsetContext struct {
	ControlOccurrenceContext

	records [][]byte
}

func (c controlSubsetContext) ControlOccurrences() [][]byte { return c.records }

func (e *Validator) controlV1Subset(records []any, context ControlOccurrenceContext) error {
	raw := make([][]byte, len(records))
	for index, record := range records {
		encoded, err := json.Marshal(record)
		if err != nil {
			return err
		}
		raw[index] = encoded
	}
	return e.controlOccurrenceV1(validation.Invocation{Instance: records[0], Context: controlSubsetContext{context, raw}})
}

func controlFoldBatch(batch, policies []any, available []AvailableControlTarget, completions map[string]bool) error {
	policy, err := controlResolvePolicy(batch[0], policies)
	if err != nil {
		return err
	}
	fold := newControlEpisodeFold(policy, available)
	for _, record := range batch {
		if err := fold.apply(record); err != nil {
			return err
		}
	}
	for completion := range fold.completions {
		if completions[completion] {
			return invalid()
		}
		completions[completion] = true
	}
	return nil
}
