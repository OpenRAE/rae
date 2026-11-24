package stub

import (
	"context"
	"encoding/json"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/clock"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
	"github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"
	"github.com/OpenRAE/rae/implementations/go/internal/base/timestamp"
)

func (p *participant) AdmitAction(ctx context.Context, request runtimecontract.ParticipantActionRequest, previous binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	if err := callReady(ctx); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	input, err := runtimecontract.ParticipantActionInputFor(request)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	snapshot, err := snapshotObject(previous)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	address := input.ParticipantAddress
	state := object(object(snapshot, "participant_episode_results"), address)
	failure, refused, checkErr := actionPrecondition(input, snapshot, previous)
	if checkErr != nil {
		return runtimecontract.ApplyResult{}, checkErr
	}
	if refused {
		return failure, nil
	}

	p.mutex.Lock()
	defer p.mutex.Unlock()
	now := timestamp.Format(clock.Read(p.clock))
	history := table(snapshot, "participant_behavior_history")
	history[address] = append(array(history[address]), participantActionEvents(input, text(state, termEpisodeID), now)...)
	output, err := snapshotResult(snapshot)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	if err := callReady(ctx); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	return runtimecontract.ApplyResult{Success: true, Snapshot: output, ChangedAddresses: []string{address}}, nil
}
func actionRefusal(snapshot binding.RuntimeSnapshotV1, address, code, message string) runtimecontract.ApplyResult {
	return runtimecontract.ApplyResult{Success: false, Snapshot: snapshot, Diagnostics: []diagnostic.Diagnostic{{Code: code, Severity: termError, Domain: "participant", Address: address, Message: message}}}
}
func generationRefusal(input runtimecontract.ParticipantActionInput, snapshot map[string]any) (string, error) {
	if input.ExecutionScopeRef == nil {
		return "", nil
	}
	state := object(object(snapshot, "participant_execution_services"), *input.ExecutionScopeRef)
	if state == nil {
		return "execution-service state is missing", nil
	}
	owner, err := schemas()
	if err != nil {
		return "", err
	}
	raw, err := json.Marshal(state)
	if err != nil || owner.CheckPortable("participant-execution-service-state-v1", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return "", invalid()
	}
	wanted := strconv.FormatInt(*input.ExecutionGeneration, 10)
	if state["generation"] != json.Number(wanted) || state["observed_generation"] != json.Number(wanted) {
		return "execution generation changed", nil
	}
	if text(state, "observed_lifecycle") != termRunning || state["accepting_new_work"] != true || text(state, "readiness") != termReady {
		return "execution service is not accepting work", nil
	}
	return "", nil
}
func participantActionEvents(input runtimecontract.ParticipantActionInput, episode, now string) []any {
	parts := []string{input.ParticipantAddress, input.ActionContractAddress, input.ObservationBoundaryAddress, input.ActionInstanceID}
	parts = append(parts, input.TargetAddresses...)
	scope, generation := "", ""
	if input.ExecutionScopeRef != nil {
		scope = *input.ExecutionScopeRef
		generation = strconv.FormatInt(*input.ExecutionGeneration, 10)
	}
	parts = append(parts, scope, generation)
	post := digest.SHA256([]byte(strings.Join(parts, "|")))
	if input.PostStateDigest != nil {
		post = *input.PostStateDigest
	}
	common := func(kind, phase string) map[string]any {
		result := map[string]any{termEventType: kind, termTimestamp: now, termParticipantAddress: input.ParticipantAddress, termEpisodeID: episode, "action_instance_id": input.ActionInstanceID, "action_contract_address": input.ActionContractAddress, "lifecycle_phase": phase, "phase_realization": "runtime_mediated"}
		if len(input.TemporalContexts) > 0 {
			contexts := make([]any, len(input.TemporalContexts))
			for i, context := range input.TemporalContexts {
				document, _ := context.Document().(map[string]any)
				contexts[i] = participantModelPayload("temporal", document)
			}
			result["temporal_contexts"] = contexts
		}
		return result
	}
	attempted := common("action_attempted", "selection_or_admission")
	selection, _ := input.ImplementationSelection.Document().(map[string]any)
	identity := object(selection, "implementation_identity")
	attempted["actor_provenance"] = "participant-implementation:" + text(identity, "name") + "@" + text(identity, "version")
	attempted["admission_disposition"] = "admitted"
	committed := common("state_transition_recorded", "state_update_commit")
	committed["state_transition_kind"] = input.StateTransitionKind
	committed["post_state_digest"] = post
	observed := common("observation_emitted", "observation_emission")
	observed["observation_boundary_address"] = input.ObservationBoundaryAddress
	observed["observation_status"] = "terminal"
	observed["post_state_digest"] = post
	if input.ActionResult != nil {
		document, _ := input.ActionResult.Document().(map[string]any)
		observed["action_result"] = participantModelPayload("action", document)
	}
	details := map[string]any{}
	if len(input.VisibleRefs) > 0 {
		details["visible_refs"] = input.VisibleRefs
	}
	if len(input.DisclosedRefs) > 0 {
		details["disclosed_refs"] = input.DisclosedRefs
	}
	if len(input.EvidenceRefs) > 0 {
		details[termEvidenceRefs] = input.EvidenceRefs
	}
	if len(details) > 0 {
		observed[termDetails] = details
	}
	return []any{attempted, committed, observed}
}

func actionPrecondition(input runtimecontract.ParticipantActionInput, snapshot map[string]any, previous binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, bool, error) {
	address := input.ParticipantAddress
	state := object(object(snapshot, "participant_episode_results"), address)
	if state == nil {
		return participantRefusal(previous, address, "cannot admit participant action for "+pyrepr.Quote(address)+": no live episode"), true, nil
	}
	if !validEpisode(state) {
		return participantRefusal(previous, address, "current state is invalid"), true, nil
	}
	if text(state, termStatus) == termTerminated {
		return participantRefusal(previous, address, "cannot admit participant action for terminated participant "+pyrepr.Quote(address)), true, nil
	}
	if reason, err := generationRefusal(input, snapshot); err != nil {
		return runtimecontract.ApplyResult{}, false, err
	} else if reason != "" {
		return actionRefusal(previous, address, "runtime.participant-execution-stale-work", "Participant action work was rejected because its generation-bound "+reason+"."), true, nil
	}
	var action map[string]any
	if input.ActionResult != nil {
		action, _ = input.ActionResult.Document().(map[string]any)
	}
	if action != nil && text(action, termEpisodeID) != text(state, termEpisodeID) {
		return participantRefusal(previous, address, "native action result episode_id must match the live participant episode"), true, nil
	}
	if input.RequiresTerminalOutcome {
		if action == nil {
			return actionRefusal(previous, address, "runtime.participant-autonomous-native-outcome-missing", "Autonomous native execution did not publish a typed action outcome."), true, nil
		}
		switch text(action, termStatus) {
		case "succeeded", "failed", "partial_success", "rejected", "withheld":
		default:
			return actionRefusal(previous, address, "runtime.participant-autonomous-native-outcome-nonterminal", "Autonomous native execution must publish a terminal typed action outcome."), true, nil
		}
	}
	return runtimecontract.ApplyResult{}, false, nil
}
