package stub

import (
	"context"
	"encoding/json"
	"maps"
	"math/big"

	"github.com/OpenRAE/rae/implementations/go/base/clock"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
	"github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"
	"github.com/OpenRAE/rae/implementations/go/internal/base/timestamp"
)

type participant struct {
	*component

	counters map[string]*big.Int
}
type episodeCommand struct {
	action, address string
	episode         *string
	reason, detail  string
}

// NewParticipantRuntime constructs the inert participant lifecycle double.
func NewParticipantRuntime() (ParticipantRuntime, error) { //nolint:ireturn // The declared public API returns the portable role interface.
	return NewParticipantRuntimeWithConfiguration(Configuration{})
}

// NewParticipantRuntimeWithConfiguration injects the participant wall clock.
func NewParticipantRuntimeWithConfiguration(c Configuration) (ParticipantRuntime, error) { //nolint:ireturn // The declared public API returns the portable role interface.
	return &participant{component: newComponent("participant_episode", c.Clock), counters: map[string]*big.Int{}}, nil
}
func (p *participant) Initialize(ctx context.Context, r runtimecontract.EpisodeInitializeRequest, s binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	return p.transition(ctx, episodeCommand{action: termInitialize, address: r.ParticipantAddress, episode: r.EpisodeID}, s)
}
func (p *participant) Reset(ctx context.Context, r runtimecontract.EpisodeResetRequest, s binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	return p.transition(ctx, episodeCommand{action: termReset, address: r.ParticipantAddress, episode: r.EpisodeID, reason: r.Reason}, s)
}
func (p *participant) Restart(ctx context.Context, r runtimecontract.EpisodeRestartRequest, s binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	return p.transition(ctx, episodeCommand{action: termRestart, address: r.ParticipantAddress, episode: r.EpisodeID, reason: r.Reason}, s)
}
func (p *participant) Terminate(ctx context.Context, r runtimecontract.EpisodeTerminateRequest, s binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	return p.transition(ctx, episodeCommand{action: termTerminate, address: r.ParticipantAddress, reason: r.TerminalReason, detail: r.Detail}, s)
}
func (p *participant) transition(ctx context.Context, command episodeCommand, previous binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	if err := callReady(ctx); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	snapshot, err := snapshotObject(previous)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	p.mutex.Lock()
	defer p.mutex.Unlock()
	counters := maps.Clone(p.counters)
	success, message, err := p.episodeChange(command, snapshot, counters)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	if !success {
		return participantRefusal(previous, command.address, message), nil
	}
	output, err := snapshotResult(snapshot)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	results := map[string]map[string]any{}
	history := map[string][]map[string]any{}
	if copyJSON(snapshot["participant_episode_results"], &results) != nil || copyJSON(snapshot["participant_episode_history"], &history) != nil {
		return runtimecontract.ApplyResult{}, invalid()
	}
	if err := callReady(ctx); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	p.counters = counters
	p.results = results
	p.history = history
	return runtimecontract.ApplyResult{Success: true, Snapshot: output, ChangedAddresses: []string{command.address}}, nil
}
func participantRefusal(snapshot binding.RuntimeSnapshotV1, address, message string) runtimecontract.ApplyResult {
	if address == "" {
		address = "runtime.participant-runtime"
	}
	return runtimecontract.ApplyResult{Success: false, Snapshot: snapshot, Diagnostics: []diagnostic.Diagnostic{{Code: "runtime.participant-runtime.rejected", Severity: termError, Domain: termRuntime, Address: address, Message: message}}}
}
func (p *participant) episodeChange(command episodeCommand, snapshot map[string]any, counters map[string]*big.Int) (bool, string, error) {
	address, action := command.address, command.action
	if address == "" {
		return false, "participant_address must be non-empty", nil
	}
	results := table(snapshot, "participant_episode_results")
	history := table(snapshot, "participant_episode_history")
	current := object(results, address)
	if message := episodePrecondition(action, address, current); message != "" {
		return false, message, nil
	}
	now := timestamp.Format(clock.Read(p.clock))
	var state map[string]any
	var events []any
	var err error
	if action == termTerminate {
		state, events, err = terminatedEpisode(command, current, now)
	} else {
		state, events, err = runningEpisode(command, current, counters, now)
	}
	if err != nil {
		return false, "", err
	}

	if !validEpisode(state) {
		return false, "", invalid()
	}
	results[address] = state
	if action == termInitialize {
		history[address] = events
	} else {
		history[address] = append(array(history[address]), events...)
	}
	return true, "", nil
}
func validEpisode(state map[string]any) bool {
	owner, err := schemas()
	if err != nil {
		return false
	}
	raw, err := json.Marshal(state)
	return err == nil && owner.CheckPortable("participant-episode-state-envelope-v1", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) == nil
}
func episodeEvent(kind string, state map[string]any, now string) map[string]any {
	return map[string]any{termEventType: kind, termTimestamp: now, termParticipantAddress: state[termParticipantAddress], termEpisodeID: state[termEpisodeID], "sequence_number": state["sequence_number"], termTerminalReason: nil, "control_action": nil, termDetails: map[string]any{}}
}
func (p *participant) Status(ctx context.Context) (map[string]any, error) {
	if err := callReady(ctx); err != nil {
		return nil, err
	}
	p.mutex.Lock()
	defer p.mutex.Unlock()
	running := 0
	for _, state := range p.results {
		if text(state, termStatus) == termRunning {
			running++
		}
	}
	return map[string]any{"participants": len(p.results), termRunning: running}, nil
}

func episodePrecondition(action, address string, current map[string]any) string {
	quoted := pyrepr.Quote(address)
	if action == termInitialize && current != nil {
		return "participant " + quoted + " already has a live episode; use reset or restart"
	}
	if action == termInitialize {
		return ""
	}

	if current == nil {
		return "cannot " + action + " participant " + quoted + ": no live episode"
	}
	if !validEpisode(current) {
		return "current state is invalid"
	}
	terminal := text(current, termStatus) == termTerminated
	if action == termReset && terminal {
		return "cannot reset terminated participant " + quoted + "; use restart"
	}
	if action == termRestart && !terminal {
		return "cannot restart non-terminated participant " + quoted + "; use reset"
	}
	if action == termTerminate && terminal {
		return "participant " + quoted + " is already terminated"
	}
	return ""
}
func terminatedEpisode(command episodeCommand, current map[string]any, now string) (map[string]any, []any, error) {
	if command.reason == "" {
		command.reason = "interrupted"
	}
	switch command.reason {
	case "completed", "timed_out", "truncated", "interrupted":
	default:
		return nil, nil, invalid()
	}
	state := maps.Clone(current)
	state[termStatus] = termTerminated
	state[termTerminalReason] = command.reason
	state["terminated_at"] = now
	state[termUpdatedAt] = now
	event := episodeEvent("episode_"+command.reason, state, now)
	event[termTerminalReason] = command.reason
	event[termDetails] = map[string]any{termDetail: command.detail}
	events := []any{event}
	return state, events, nil
}
func runningEpisode(command episodeCommand, current map[string]any, counters map[string]*big.Int, now string) (map[string]any, []any, error) {
	address, action := command.address, command.action

	id := ""
	if command.episode != nil {
		id = *command.episode
	}
	if id == "" {
		next := new(big.Int).SetInt64(1)
		if old := counters[address]; old != nil {
			next.Add(old, next)
		}
		counters[address] = next
		id = address + "-episode-" + next.String()
	}
	sequence := new(big.Int)
	var predecessor any
	if current != nil {
		sequenceNumber, typed := current["sequence_number"].(json.Number)
		if !typed {
			return nil, nil, invalid()
		}
		sequenceText := string(sequenceNumber)
		number, ok := new(big.Int).SetString(sequenceText, 10)
		if !ok {
			return nil, nil, invalid()
		}
		sequence.Add(number, big.NewInt(1))
		predecessor = current[termEpisodeID]
	}
	state := map[string]any{termStateSchemaVersion: "participant-episode-state/v1", termParticipantAddress: address, termEpisodeID: id, "sequence_number": json.Number(sequence.String()), termStatus: termRunning, termTerminalReason: nil, "initialized_at": now, termUpdatedAt: now, "terminated_at": nil, "last_control_action": action, "previous_episode_id": predecessor}
	eventType := map[string]string{termInitialize: "episode_initialized", termReset: "episode_reset", termRestart: "episode_restarted"}[action]
	event := episodeEvent(eventType, state, now)
	event["control_action"] = action
	if current != nil {
		event[termDetails] = map[string]any{"previous_episode_id": predecessor, "reason": command.reason}
	}
	events := []any{event, episodeEvent("episode_running", state, now)}
	return state, events, nil
}
