package stub

import (
	"context"
	"maps"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func (p *participant) ResetMany(ctx context.Context, requests []runtimecontract.EpisodeResetRequest, previous binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	if err := callReady(ctx); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	if len(requests) > value.Runtime().MaxMembers {
		return runtimecontract.ApplyResult{}, invalid()
	}
	snapshot, err := snapshotObject(previous)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	if len(requests) == 0 {
		return runtimecontract.ApplyResult{Success: true, Snapshot: previous, ChangedAddresses: []string{}}, nil
	}
	if !resetAddressesUnique(requests) {
		return participantRefusal(previous, "", "coordinated reset participant addresses must be unique"), nil
	}

	p.mutex.Lock()
	defer p.mutex.Unlock()
	counters := maps.Clone(p.counters)
	changed := make([]string, 0, len(requests))
	for _, request := range requests {
		success, message, stepErr := p.episodeChange(episodeCommand{action: termReset, address: request.ParticipantAddress, episode: request.EpisodeID, reason: request.Reason}, snapshot, counters)
		if stepErr != nil {
			return runtimecontract.ApplyResult{}, stepErr
		}
		if !success {
			return participantRefusal(previous, request.ParticipantAddress, message), nil
		}
		changed = append(changed, request.ParticipantAddress)
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
	return runtimecontract.ApplyResult{Success: true, Snapshot: output, ChangedAddresses: changed}, nil
}

func resetAddressesUnique(requests []runtimecontract.EpisodeResetRequest) bool {
	seen := map[string]bool{}
	for _, request := range requests {
		if seen[request.ParticipantAddress] {
			return false
		}
		seen[request.ParticipantAddress] = true
	}
	return true
}
