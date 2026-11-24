package processor

import (
	"encoding/json"
	"fmt"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"
)

type participantTemporalTransition struct {
	Contract  string   `json:"temporal_contract_id"`
	From      string   `json:"from_state"`
	To        string   `json:"to_state"`
	Event     string   `json:"event_point"`
	Domain    string   `json:"time_domain"`
	Authority string   `json:"clock_authority"`
	Boundary  string   `json:"boundary_ref"`
	Evidence  []string `json:"evidence_refs"`
}
type participantTemporalState struct{ state, domain, authority string }
type participantTemporalDeclaration struct {
	ID, Domain, Authority              string
	EventPoints, BackendDisclosureRefs []string
	Reset, Replay                      *string
}

func participantTemporalStateKnown(state string) bool {
	return slices.Contains([]string{"eligible", "ineligible", "cadence_ready", termCadenceWaiting, termDwellActive, "dwell_satisfied", "deadline_open", "deadline_met", "deadline_missed", "timeout", termReset, termReplayBoundary}, state)
}
func participantTemporalDomainKnown(domain string) bool {
	return slices.Contains([]string{"episode_step", "scenario_time", "simulation_time", "backend_time", "wall_clock_time"}, domain)
}
func participantTemporalEventKnown(event string) bool {
	return slices.Contains([]string{"submit", "start", "end", "observed", "effective", "deadline", "window_open", "window_close", termReset, termReplay}, event)
}
func (transition participantTemporalTransition) valid() bool {
	return transition.Contract != "" && transition.Authority != "" && transition.Boundary != "" && len(transition.Evidence) > 0 && participantUniqueStrings(transition.Evidence) && participantTemporalStateKnown(transition.From) && participantTemporalStateKnown(transition.To) && participantTemporalDomainKnown(transition.Domain) && participantTemporalEventKnown(transition.Event)
}
func (transition participantTemporalTransition) violations(prior participantTemporalState, exists bool) []string {
	result := []string{}
	if exists && (transition.Domain != prior.domain || transition.Authority != prior.authority) {
		result = append(result, fmt.Sprintf("temporal contract %s changed time domain or clock authority from %s/%s to %s/%s", pyrepr.Quote(transition.Contract), prior.domain, pyrepr.Quote(prior.authority), transition.Domain, pyrepr.Quote(transition.Authority)))
	}
	boundary := transition.Event == termReset || transition.Event == termReplay || temporalBoundaryState(transition.To)
	if exists && transition.From != prior.state && !temporalBoundaryState(prior.state) && !boundary {
		result = append(result, fmt.Sprintf("temporal contract %s transition from_state %s does not match prior to_state %s", pyrepr.Quote(transition.Contract), pyrepr.Quote(transition.From), pyrepr.Quote(prior.state)))
	}
	if transition.From == termCadenceWaiting && slices.Contains([]string{"submit", "start", "observed", "effective"}, transition.Event) && !boundary {
		result = append(result, "cadence repeated event requires cadence_ready or reset/replay boundary before reuse")
	} else if transition.To == termCadenceWaiting && !temporalCadenceReady(transition.From) && !temporalCadenceReady(prior.state) && !boundary {
		result = append(result, "cadence_waiting requires prior cadence_ready or eligible state in the same segment")
	}
	if transition.To == "dwell_satisfied" && transition.From != termDwellActive && prior.state != termDwellActive {
		result = append(result, "dwell_satisfied requires prior dwell_active state in the same temporal segment")
	}
	if (transition.From == "deadline_missed" || transition.From == "timeout") && transition.Event != termReset && transition.Event != termReplay && !temporalBoundaryState(transition.To) {
		result = append(result, "terminal temporal state requires reset or replay boundary before reuse")
	}
	return result
}
func temporalBoundaryState(state string) bool {
	return state == termReset || state == termReplayBoundary
}
func temporalCadenceReady(state string) bool {
	return state == "cadence_ready" || state == "eligible" || temporalBoundaryState(state)
}

// ParticipantTemporalStateMachineViolations folds the abstract temporal history in source order.
func ParticipantTemporalStateMachineViolations(transitions admission.Fragment) ([]diagnostic.Diagnostic, error) {
	var raw []json.RawMessage
	if err := participantFragmentDecode(transitions, admission.RealizationValue, &raw); err != nil {
		return nil, err
	}
	if raw == nil {
		return nil, participantContractInput()
	}
	states := map[string]participantTemporalState{}
	result := []diagnostic.Diagnostic{}
	budget := newParticipantViolations()
	for index, item := range raw {
		if !budget.work.spend(1) {
			return nil, participantContractInput()
		}
		pointer := fmt.Sprintf("participant temporal state transition[%d]", index)
		var transition participantTemporalTransition
		if participantDecode(item, &transition) != nil || !transition.valid() {
			result = append(result, participantFinding("participant.temporal-state-violation", "", pointer, "participant temporal state transition is invalid"))
			continue
		}
		prior, exists := states[transition.Contract]
		for _, message := range transition.violations(prior, exists) {
			budget.add(message)
			result = append(result, participantFinding("participant.temporal-state-violation", transition.Contract, pointer, message))
		}
		if budget.err != nil {
			return nil, budget.err
		}
		if !exists {
			prior.domain = transition.Domain
			prior.authority = transition.Authority
		}
		prior.state = transition.To
		states[transition.Contract] = prior
	}
	return result, nil
}
