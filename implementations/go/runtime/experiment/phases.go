package experiment

import (
	"context"
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

type verifiedObservation struct{ value Observation }

func phasePending(state string) bool {
	return state == termProgress || state == termPending || state == termIndeterminate
}
func (c *coordinator) phase(ctx context.Context, s trialSlot, t Trial, kind string, known map[string]map[string]any, method func(context.Context) (Phase, error)) (string, error) {
	phase, err := ownerCall(ctx, c, "control", c.options.ExecutionBudget, method)
	if err != nil {
		return "", err
	}
	if !slices.Contains([]string{termProgress, termPending, termIndeterminate, termSucceeded, termFailed, termCancelled}, phase.State) {
		return "", integrity()
	}
	if phase.Observation != nil {
		if kind == "" {
			return "", integrity()
		}
		if err = c.phaseObservation(ctx, s, t, kind, *phase.Observation, known); err != nil {
			return "", err
		}
	} else if phase.State == termSucceeded && kind != "" && known[kind] == nil {
		return "", integrity()
	}
	return phase.State, nil
}
func (c *coordinator) phaseObservation(ctx context.Context, s trialSlot, t Trial, kind string, o Observation, known map[string]map[string]any) error {
	if o.Kind != kind {
		return integrity()
	}
	if prior := known[kind]; prior != nil {
		payload, snapshot, err := observationPayload(o)
		if err != nil {
			return err
		}
		if !same(prior["observation"], payload) || text(prior, "snapshot_json") != snapshot {
			return integrity()
		}
		return nil
	}
	verified, err := c.validateObservation(ctx, s, t, kind, o)
	if err != nil {
		return err
	}
	return c.retainVerifiedObservation(ctx, t, verified, known)
}
func observationPayload(o Observation) (map[string]any, string, error) {
	payload, err := observationDocument(o)
	if err != nil {
		return nil, "", err
	}
	if admission.CheckTransport(o.Snapshot, runtimeIngress()) != nil {
		return nil, "", integrity()
	}
	snapshot, err := json.Marshal(o.Snapshot)
	if err != nil {
		return nil, "", integrity()
	}
	return payload, string(snapshot), nil
}
func (c *coordinator) retainVerifiedObservation(ctx context.Context, t Trial, verified verifiedObservation, known map[string]map[string]any) error {
	payload, snapshot, err := observationPayload(verified.value)
	if err != nil {
		return err
	}
	if prior := known[verified.value.Kind]; prior != nil {
		if !same(prior["observation"], payload) || text(prior, "snapshot_json") != snapshot {
			return integrity()
		}
		return nil
	}
	d, err := c.claim(ctx, observationSchema, map[string]any{termExecutionAttemptID: t.ExecutionAttemptID, "observation": payload, "observed_at": runtimeTimestamp(c.now()), "snapshot_json": snapshot})
	if err != nil {
		return err
	}
	known[verified.value.Kind] = decisionMap(d)
	return nil
}
