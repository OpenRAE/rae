package sdlrules

import (
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

const (
	actionsSection     = "action_contracts"
	behaviorSection    = "behavior_specifications"
	boundariesSection  = "observation_boundaries"
	constraintsSection = "temporal_constraints"
)

type temporalModel struct {
	policyBySpec map[string]temporalPolicy
	input        binding.SdlAuthoringInputV1
	order        map[string][]string
	actions      []temporalAction
	policies     []temporalPolicy
	coordinates  map[string]temporalInterval
	findings     []Finding
}
type temporalAction struct {
	name       string
	contracts  []temporalContract
	conditions []temporalCondition
}
type temporalCondition struct {
	id                string
	support, evidence []string
}
type temporalContract struct {
	id, kind, domain string
	binding          temporalBinding
}
type temporalBinding struct {
	Clock      string `json:"clock_ref"`
	Constraint string `json:"constraint_ref"`
	Condition  string `json:"condition_precondition_id"`
	Boundary   string `json:"observation_boundary_ref"`
}
type temporalPolicy struct {
	Clock      string   `json:"clock_ref"`
	Boundary   string   `json:"observation_boundary_ref"`
	Actions    []string `json:"action_order"`
	Candidates map[string]struct {
		Action string `json:"action_ref"`
	} `json:"action_candidates"`
}
type temporalCoordinate struct {
	Tick      json.Number `json:"tick"`
	Microstep json.Number `json:"microstep"`
}
type temporalInterval struct{ start, end *temporalCoordinate }

func temporalProjectionInvalid() error {
	return fault.New(fault.InvalidInput, "sdl-temporal-projection-invalid", nil)
}
func decodeTemporal(data []byte, order map[string][]string) (*temporalModel, error) {
	m := &temporalModel{order: order, coordinates: map[string]temporalInterval{}, policyBySpec: map[string]temporalPolicy{}}
	if json.Unmarshal(data, &m.input) != nil {
		return nil, temporalProjectionInvalid()
	}
	for _, load := range []func() error{m.actionFacts, m.policyFacts, m.coordinateFacts} {
		if err := load(); err != nil {
			return nil, err
		}
	}
	return m, nil
}
func (m *temporalModel) actionFacts() error {
	values := fieldValue(m.input.ActionContracts)
	for _, name := range orderedKeys(values, m.order, actionsSection) {
		raw := values[name]
		action := temporalAction{name: name}
		for _, value := range fieldValue(raw.TemporalContracts) {
			source := fieldValue(value.SharedTimeBinding)
			if len(source) == 0 || string(source) == jsonNull {
				continue
			}
			row := temporalContract{id: fieldValue(value.TemporalId), kind: string(fieldValue(value.TemporalKind)), domain: string(fieldValue(value.TimeDomain))}
			if json.Unmarshal(source, &row.binding) != nil {
				return temporalProjectionInvalid()
			}
			action.contracts = append(action.contracts, row)
		}
		for _, value := range fieldValue(raw.Preconditions) {
			action.conditions = append(action.conditions, temporalCondition{fieldValue(value.PreconditionId), fieldValue(value.SupportRefs), fieldValue(value.EvidenceRefs)})
		}
		m.actions = append(m.actions, action)
	}
	return nil
}
func (m *temporalModel) policyFacts() error {
	values := fieldValue(m.input.BehaviorSpecifications)
	for _, name := range orderedKeys(values, m.order, behaviorSection) {
		raw := fieldValue(values[name].AutonomousExecution)
		if len(raw) == 0 || string(raw) == jsonNull {
			continue
		}
		var policy temporalPolicy
		if json.Unmarshal(raw, &policy) != nil {
			return temporalProjectionInvalid()
		}
		if policy.Candidates != nil {
			policy.Actions = nil
			for _, key := range orderedKeys(policy.Candidates, m.order, behaviorSection, name, "autonomous_execution", "action_candidates") {
				policy.Actions = append(policy.Actions, policy.Candidates[key].Action)
			}
			policy.Candidates = nil
		}
		m.policies = append(m.policies, policy)
		m.policyBySpec[name] = policy
	}
	return nil
}
func (m *temporalModel) coordinateFacts() error {
	for name, row := range fieldValue(m.input.TemporalConstraints) {
		start, err := decodeTemporalCoordinate(fieldValue(row.Start))
		if err != nil {
			return err
		}
		end, err := decodeTemporalCoordinate(fieldValue(row.End))
		if err != nil {
			return err
		}
		m.coordinates[name] = temporalInterval{start, end}
	}
	return nil
}
func decodeTemporalCoordinate(raw json.RawMessage) (*temporalCoordinate, error) {
	// Null is a valid absent endpoint. The pointer decoder retains that distinction.
	var coordinate *temporalCoordinate
	if len(raw) == 0 {
		raw = json.RawMessage(jsonNull)
	}
	if json.Unmarshal(raw, &coordinate) != nil {
		return nil, temporalProjectionInvalid()
	}
	if coordinate != nil {
		if coordinate.Tick == "" {
			coordinate.Tick = "0"
		}
		if coordinate.Microstep == "" {
			coordinate.Microstep = "0"
		}
	}
	return coordinate, nil
}
func sectionReference[T any](ref, section string, values map[string]T) (string, bool) {
	if _, ok := values[ref]; ok {
		return ref, true
	}
	name, qualified := strings.CutPrefix(ref, section+".")
	_, ok := values[name]
	return name, qualified && ok
}
func referencesName[T any](refs []string, name, section string, values map[string]T) bool {
	for _, ref := range refs {
		if resolved, ok := sectionReference(ref, section, values); ok && resolved == name {
			return true
		}
	}
	return false
}
