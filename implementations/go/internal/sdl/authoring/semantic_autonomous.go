package authoring

import (
	"encoding/json"
	"fmt"
	"slices"
)

type semanticAutonomous struct {
	Budget      *semanticResourceBudget `json:"resource_budget"`
	Profile     string                  `json:"profile"`
	Clock       string                  `json:"clock_ref"`
	Progression string                  `json:"progression_policy_ref"`
	Constraints []string                `json:"temporal_constraint_refs"`
	Work        []string                `json:"work_window_refs"`
	Pause       []string                `json:"pause_window_refs"`
	Actions     []string                `json:"action_order"`
	Candidates  map[string]struct {
		Action string `json:"action_ref"`
	} `json:"action_candidates"`
	Boundary string `json:"observation_boundary_ref"`
	Timing   struct {
		Minimum json.RawMessage `json:"minimum_ticks"`
		Maximum json.RawMessage `json:"maximum_ticks"`
	} `json:"timing"`
	Authority struct {
		Mode       string   `json:"mode"`
		Objectives []string `json:"objective_refs"`
		Proofs     []string `json:"proof_producer_refs"`
		Scores     []string `json:"score_authority_refs"`
		Receipts   []string `json:"receipt_authority_refs"`
	} `json:"evaluation_authority"`
}

func (m *semanticModel) autonomousFacts(name string) (semanticAutonomous, error) {
	raw := fieldValue(fieldValue(m.transport.BehaviorSpecifications)[name].AutonomousExecution)
	var policy semanticAutonomous
	if err := json.Unmarshal(raw, &policy); err != nil {
		return semanticAutonomous{}, invalid()
	}
	if policy.Candidates != nil {
		policy.Actions = nil
		for _, key := range m.keys(behaviorSection, name, "autonomous_execution", "action_candidates") {
			policy.Actions = append(policy.Actions, policy.Candidates[key].Action)
		}
		policy.Candidates = nil
	}
	return policy, nil
}

type semanticAutonomousCheck struct {
	model        *semanticModel
	collector    *semanticCollector
	row          semanticBehavior
	policy       *semanticAutonomous
	participants []string
}

func (a semanticAutonomousCheck) reportf(format string, args ...any) {
	a.collector.report(semanticOwner{behaviorSection, a.row.name}, "Behavior specification '"+a.row.name+"' "+fmt.Sprintf(format, args...))
}
func (m *semanticModel) behaviorAutonomous(c *semanticCollector, row semanticBehavior) {
	if row.autonomous == nil {
		return
	}
	check := semanticAutonomousCheck{m, c, row, row.autonomous, m.selectParticipants(row.participants, row.roles)}
	check.declaration()
	check.references()
	check.time()
	check.evaluation()
}
func (a semanticAutonomousCheck) declaration() {
	if len(a.row.participants) == 0 {
		a.reportf("autonomous execution requires explicit participant_refs")
	}
	for _, required := range []string{"action_contracts", "autonomous_execution", "behavior_history", "observation_boundaries", "temporal_contracts"} {
		if !slices.Contains(a.row.features, required) {
			a.reportf("autonomous execution requires backend feature '%s'", required)
		}
	}
}
func (a semanticAutonomousCheck) references() {
	for _, ref := range a.policy.Actions {
		if variable(ref) {
			continue
		}
		if !slices.Contains(a.row.actions, ref) {
			a.reportf("autonomous action '%s' widens its action contracts", ref)
		}
		for _, name := range a.participants {
			if !slices.Contains(fieldValue(fieldValue(a.model.transport.Agents)[name].Actions), ref) {
				a.reportf("autonomous action '%s' is outside participant '%s' actions", ref, name)
			}
		}
	}
	a.boundary()
}
func (a semanticAutonomousCheck) boundary() {
	ref := a.policy.Boundary
	if variable(ref) {
		return
	}
	if !slices.Contains(a.row.boundaries, ref) {
		a.reportf("autonomous observation boundary '%s' widens its observation boundaries", ref)
	}
	for _, name := range a.participants {
		if !slices.Contains(fieldValue(fieldValue(a.model.transport.Agents)[name].ObservationBoundaries), ref) {
			a.reportf("autonomous observation boundary '%s' is outside participant '%s' observation boundaries", ref, name)
		}
	}
}
func (a semanticAutonomousCheck) evaluation() {
	switch a.policy.Authority.Mode {
	case noneTerm:
		a.nonEvaluated()
	case "declared":
		a.declaredAuthority()
	}
}
func (a semanticAutonomousCheck) nonEvaluated() {
	for _, name := range a.participants {
		if a.model.roles[name] != "green" {
			a.reportf("non-evaluated autonomous participant '%s' must have the green role", name)
		}
		for _, objective := range a.model.objectives {
			if objective.Participant == name {
				a.reportf("non-evaluated participant '%s' cannot be assigned an objective", name)
				break
			}
		}
	}
	if len(a.row.outcomes) != 0 || len(a.row.authority) != 0 {
		a.reportf("non-evaluated autonomous execution cannot carry outcome-interpretation or authority-scope refs")
	}
}
func (a semanticAutonomousCheck) declaredAuthority() {
	a.objectiveAuthority()
	for _, group := range []struct {
		field string
		refs  []string
	}{{"proof_producer_refs", a.policy.Authority.Proofs}, {"score_authority_refs", a.policy.Authority.Scores}, {"receipt_authority_refs", a.policy.Authority.Receipts}} {
		for _, ref := range group.refs {
			if !variable(ref) {
				a.reportf("evaluation-authority %s ref '%s' cannot resolve because RAES SDL declares no such authority namespace", group.field, ref)
			}
		}
	}
}
func (m *semanticModel) checkAutonomousOwners(c *semanticCollector) {
	owners := map[string]string{}
	for _, row := range m.behaviors {
		if row.autonomous == nil {
			continue
		}
		for _, name := range m.selectParticipants(row.participants, row.roles) {
			if prior, ok := owners[name]; ok {
				c.report(semanticOwner{behaviorSection, row.name}, fmt.Sprintf("Behavior specification '%s' autonomous participant '%s' is already controlled by behavior specification '%s'", row.name, name, prior))
			} else {
				owners[name] = row.name
			}
		}
	}
}

func (a semanticAutonomousCheck) objectiveAuthority() {
	for _, ref := range a.policy.Authority.Objectives {
		if variable(ref) {
			continue
		}
		name, known := a.model.sectionReference(ref, objectivesSection)
		if !known {
			a.reportf("evaluation-authority objective_ref '%s' is not declared in objectives", ref)
			continue
		}
		for _, objective := range a.model.objectives {
			if objective.name == name && !variable(objective.Participant) && !slices.Contains(a.participants, objective.Participant) {
				a.reportf("objective '%s' must be assigned to a selected participant", ref)
			}
		}
	}
}
