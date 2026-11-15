package experiment

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"reflect"
	"slices"
	"sync"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/clock"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/trial"
)

type coordinator struct {
	options   Options
	id        string
	schedule  trial.BatchSchedule
	slots     []trialSlot
	slotsMu   sync.RWMutex
	gate      chan struct{}
	deadlines map[string]*attemptDeadline
}
type trialSlot struct {
	plan        binding.AdmittedTrialPlanV1
	view        map[string]any
	entry       trial.ScheduledEntry
	realization trial.Realization
	root        string
	commitment  string
}

func (*coordinator) experimentCoordinator() {}
func missing(v any) bool {
	if v == nil {
		return true
	}
	rv := reflect.ValueOf(v)
	return rv.Kind() == reflect.Pointer && rv.IsNil()
}
func invalidOptions() error { return fault.New(fault.InvalidInput, "experiment-options-invalid", nil) }

// New admits every realization before it claims the actor-bound experiment.
// All effects and recovery remain the responsibility of the installed shared host.
func New(ctx context.Context, options Options) (Coordinator, error) { //nolint:ireturn // The coordinator is sealed to this owner.
	if missing(options.Host) || missing(options.Journal) || missing(options.Calls) || options.AdmissionBudget <= 0 || options.ExecutionBudget <= 0 || options.StoreBudget <= 0 || !identityString(options.Identity.ActorID) || len(options.Identity.AuthorizationScope) == 0 || len(options.Identity.AuthorizationScope) > 64 {
		return nil, invalidOptions()
	}
	for _, scope := range options.Identity.AuthorizationScope {
		if !identityString(scope) {
			return nil, invalidOptions()
		}
	}
	options.Identity = normalizedIdentity(options.Identity)
	var err error
	options.Inputs, err = detachInputs(options.Inputs)
	if err != nil {
		return nil, err
	}
	schedule, err := trial.PlanBatchSchedule(options.Inputs.Plan)
	if err == nil && len(schedule.Entries) > 4096 {
		return nil, fault.New(fault.Conflict, "experiment-entry-capacity-exceeded", nil)
	}
	if err != nil {
		return nil, invalidOptions()
	}
	c := &coordinator{options: options, id: schedule.PlanID, schedule: schedule, gate: make(chan struct{}, 1), deadlines: map[string]*attemptDeadline{}}
	if err = c.authorize(ctx, options.Identity); err != nil {
		return nil, err
	}
	if err = c.requireReplacement(ctx); err != nil {
		return nil, err
	}
	slot, err := c.planSlots(ctx, options.Inputs.Plan, "")
	if err != nil {
		return nil, err
	}
	c.slots = slot
	commitments := make([]string, 0, len(slot))
	for _, s := range slot {
		commitments = append(commitments, s.commitment)
	}
	_, err = c.claim(ctx, experimentSchema, map[string]any{termExperimentID: c.id, termPlanDigest: schedule.PlanDigest, "realization_digests": commitments, "actor_id": options.Identity.ActorID, "authorization_scope": options.Identity.AuthorizationScope})
	if err != nil {
		return nil, err
	}
	return c, nil
}
func (c *coordinator) requireReplacement(ctx context.Context) error {
	view, err := transportView(c.options.Inputs.Plan)
	if err != nil {
		return err
	}
	if at(view, "replacement_policy") == nil {
		return nil
	}
	if c.options.Replacement == nil || missing(c.options.Archive) {
		return invalidOptions()
	}
	root, err := trial.Readmit(ctx, c.options.Inputs.Plan, *c.options.Replacement)
	if err != nil {
		return err
	}
	c.options.Inputs.Plan = root
	request := *c.options.Replacement
	c.options.Replacement = &request
	return nil
}
func detachInputs(input trial.RealizationInputs) (trial.RealizationInputs, error) {
	var err error
	input.Plan, err = copyDTO(input.Plan)
	if err != nil {
		return input, err
	}
	input.Task, err = copyDTO(input.Task)
	if err != nil {
		return input, err
	}
	input.CaptureSpecs, err = copyDTO(input.CaptureSpecs)
	if err != nil {
		return input, err
	}
	input.ApparatusManifests, err = detachManifests(input.ApparatusManifests)
	if err != nil {
		return input, err
	}
	participants := make(map[trial.ParticipantManifestKey]binding.ParticipantImplementationManifestV1, len(input.ParticipantManifests))
	for key, value := range input.ParticipantManifests {
		participants[key], err = copyDTO(value)
		if err != nil {
			return input, err
		}
	}
	input.ParticipantManifests = participants
	return input, nil
}

//nolint:ireturn // The type parameter retains each exact generated transport type.
func copyDTO[T any](v T) (T, error) {
	var copyValue T
	if checkRecordTree(v) != nil {
		return copyValue, invalidOptions()
	}
	raw, err := json.Marshal(v)
	if err != nil {
		return copyValue, invalidOptions()
	}
	if json.Unmarshal(raw, &copyValue) != nil {
		return copyValue, invalidOptions()
	}
	return copyValue, nil
}
func transportView(v any) (map[string]any, error) {
	if checkRecordTree(v) != nil {
		return nil, invalidOptions()
	}
	raw, err := json.Marshal(v)
	if err != nil {
		return nil, invalidOptions()
	}
	parsed, err := ingress.Parse(raw, runtimeIngress(), ingress.Object)
	return object(parsed), err
}
func (c *coordinator) planSlots(ctx context.Context, plan binding.AdmittedTrialPlanV1, root string) ([]trialSlot, error) {
	schedule, err := trial.PlanBatchSchedule(plan)
	if err != nil {
		return nil, err
	}
	view, err := transportView(plan)
	if err != nil {
		return nil, err
	}
	for _, cleanup := range object(view["cleanup_plans"]) {
		if attempts := integer(at(cleanup, "retry_policy", "max_attempts")); attempts < 1 || attempts > 1000 {
			return nil, fault.New(fault.Conflict, "experiment-attempt-capacity-exceeded", nil)
		}
	}
	slots := make([]trialSlot, 0, len(schedule.Entries))
	for _, entry := range schedule.Entries {
		slot, slotErr := c.planSlot(ctx, plan, view, entry, root)
		if slotErr != nil {
			return nil, slotErr
		}
		slots = append(slots, slot)
	}

	return slots, nil
}
func (s trialSlot) request(attempt map[string]any) Trial {
	return Trial{Plan: s.plan, PlanEntryID: s.entry.PlanEntryID, RunID: s.entry.RunID, ExecutionAttemptID: text(attempt, termExecutionAttemptID), Attempt: integer(attempt["attempt"]), StartedAt: text(attempt, termStartedAt), Deadline: text(attempt, "deadline"), Realization: s.realization}
}
func copyTrial(t Trial) Trial {
	plan, err := copyDTO(t.Plan)
	if err == nil {
		t.Plan = plan
	}
	configs, err := copyDTO(t.Realization.ParticipantConfigurations)
	if err == nil {
		t.Realization.ParticipantConfigurations = configs
	}
	t.Identity.AuthorizationScope = slices.Clone(t.Identity.AuthorizationScope)
	t.Realization.ProcessorPlanRefs = slices.Clone(t.Realization.ProcessorPlanRefs)
	t.Realization.ProvisioningPlan = t.Realization.ExecutionPlan.Provisioning()
	t.Realization.OrchestrationPlan = t.Realization.ExecutionPlan.Orchestration()
	t.Realization.EvaluationPlan = t.Realization.ExecutionPlan.Evaluation()
	return t
}

//nolint:ireturn // The type parameter retains each exact owner result type.
func foreignCall[T any](ctx context.Context, work func(context.Context) (T, error)) (result T, err error) {
	defer func() {
		if recover() != nil {
			slog.ErrorContext(ctx, "installed experiment owner failed", slog.String("failure_class", "panic"))
			err = fault.New(fault.Operational, "experiment-owner-failed", nil)
		}
	}()
	return work(ctx)
}

//nolint:ireturn // Preserve the exact result type returned by each bounded owner call.
func ownerCall[T any](ctx context.Context, c *coordinator, lane string, budget time.Duration, work func(context.Context) (T, error)) (T, error) {
	var zero T
	if err := ctx.Err(); err != nil {
		return zero, err
	}
	result, err := foreignCall(ctx, func(callContext context.Context) (any, error) {
		return c.options.Calls.Call(callContext, lane, budget, func(workContext context.Context) (any, error) {
			result, workErr := foreignCall(workContext, work)
			if workErr != nil {
				return result, normalizeOwnerError(workContext, workErr)
			}
			return result, nil
		})
	})
	if err != nil {
		if ctx.Err() != nil {
			return zero, ctx.Err()
		}
		return zero, normalizeOwnerError(ctx, err)
	}
	typed, ok := result.(T)
	if !ok {
		return zero, fault.New(fault.Operational, "experiment-owner-result-invalid", nil)
	}
	return typed, nil
}
func normalizeOwnerError(ctx context.Context, err error) error {
	if ctx.Err() != nil {
		return ctx.Err()
	}
	if owned := safeOwnerFault(err); owned != nil {
		return owned
	}
	slog.ErrorContext(ctx, "installed experiment owner failed", slog.String("failure_class", "foreign"))
	return fault.New(fault.Operational, "experiment-owner-failed", nil)
}

// Error inspection can invoke methods supplied by the installed owner.
func safeOwnerFault(err error) (result error) {
	defer func() {
		if recover() != nil {
			result = nil
		}
	}()
	owned, ok := errors.AsType[*fault.Error](err)
	if !ok || owned == nil {
		return nil
	}
	result = fault.New(owned.Category(), owned.Code(), nil)
	if errors.Is(result, fault.ErrDefinition) {
		return nil
	}
	return result
}
func (c *coordinator) authorize(ctx context.Context, id Identity) error {
	id = normalizedIdentity(id)
	if id.ActorID != c.options.Identity.ActorID || !slices.Equal(id.AuthorizationScope, c.options.Identity.AuthorizationScope) {
		return fault.New(fault.Authorization, "experiment-actor-mismatch", nil)
	}
	id.AuthorizationScope = slices.Clone(id.AuthorizationScope)
	_, err := ownerCall(ctx, c, "control", c.options.AdmissionBudget, func(work context.Context) (struct{}, error) {
		return struct{}{}, c.options.Host.Authorize(work, id, c.id)
	})
	return err
}
func (c *coordinator) acquire(ctx context.Context) (func(), error) {
	timer := time.NewTimer(c.options.AdmissionBudget)
	defer timer.Stop()
	select {
	case c.gate <- struct{}{}:
		return func() { <-c.gate }, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-timer.C:
		return nil, fault.New(fault.Conflict, "experiment-progress-busy", nil)
	}
}
func (c *coordinator) load(ctx context.Context) ([]Decision, error) {
	records, err := ownerCall(ctx, c, "store", c.options.StoreBudget, c.options.Journal.Load)
	if err != nil {
		return nil, err
	}
	result := make([]Decision, 0, len(records))
	seen := map[string]Decision{}
	for _, record := range records {
		if missing(record) {
			return nil, integrity()
		}
		d, decodeErr := DecodeDecision(record.JSON())
		if decodeErr != nil || d.ID() != record.ID() || d.SchemaVersion() != record.SchemaVersion() {
			return nil, integrity()
		}
		if prior, ok := seen[d.ID()]; ok {
			if !same(decisionMap(prior), decisionMap(d)) {
				return nil, integrity()
			}
			continue
		}
		seen[d.ID()] = d
		result = append(result, d)
	}
	return result, nil
}
func (c *coordinator) claim(ctx context.Context, schema string, m map[string]any) (Decision, error) { //nolint:ireturn // Journal claims use the sealed decision handle.
	d, err := makeDecision(schema, m)
	if err != nil {
		return nil, err
	}
	claimed, err := ownerCall(ctx, c, "store", c.options.StoreBudget, func(work context.Context) (bool, error) { return c.options.Journal.Claim(work, d) })
	if err != nil {
		return nil, err
	}
	if !claimed {
		records, loadErr := c.load(ctx)
		if loadErr != nil {
			return nil, loadErr
		}
		for _, prior := range records {
			if prior.ID() == d.ID() {
				if !same(decisionMap(prior), decisionMap(d)) {
					return nil, fault.New(fault.Conflict, "experiment-decision-conflict", nil)
				}
				return prior, nil
			}
		}
		return nil, integrity()
	}
	return d, nil
}
func (c *coordinator) progress(state string, t Trial) Progress {
	entry, attempt := t.PlanEntryID, t.ExecutionAttemptID
	return Progress{ExperimentID: c.id, State: state, PlanEntryID: &entry, ExecutionAttemptID: &attempt}
}
func (c *coordinator) now() time.Time { return clock.Read(c.options.Clock) }

type attemptDeadline struct {
	timer   *time.Timer
	expired bool
}

func detachManifests(supplied map[trial.ApparatusManifestKey]admission.ApparatusManifest) (map[trial.ApparatusManifestKey]admission.ApparatusManifest, error) {
	manifests := make(map[trial.ApparatusManifestKey]admission.ApparatusManifest, len(supplied))
	for key, value := range supplied {
		copyManifest := admission.ApparatusManifest{}
		if value.Processor != nil {
			copyValue, copyErr := copyDTO(*value.Processor)
			if copyErr != nil {
				return nil, copyErr
			}
			copyManifest.Processor = &copyValue
		}
		if value.Backend != nil {
			copyValue, copyErr := copyDTO(*value.Backend)
			if copyErr != nil {
				return nil, copyErr
			}
			copyManifest.Backend = &copyValue
		}
		manifests[key] = copyManifest
	}

	return manifests, nil
}
func normalizedIdentity(id Identity) Identity {
	id.AuthorizationScope = slices.Clone(id.AuthorizationScope)
	slices.Sort(id.AuthorizationScope)
	id.AuthorizationScope = slices.Compact(id.AuthorizationScope)
	return id
}

func (c *coordinator) slotSnapshot() []trialSlot {
	c.slotsMu.RLock()
	defer c.slotsMu.RUnlock()
	return slices.Clone(c.slots)
}
func (c *coordinator) appendSlots(slots []trialSlot) error {
	c.slotsMu.Lock()
	defer c.slotsMu.Unlock()
	known := map[string]trialSlot{}
	for _, slot := range c.slots {
		known[slot.entry.PlanEntryID] = slot
	}
	next := slices.Clone(c.slots)
	for _, slot := range slots {
		prior, exists := known[slot.entry.PlanEntryID]
		if exists {
			if !same(prior.view, slot.view) {
				return integrity()
			}
			continue
		}
		known[slot.entry.PlanEntryID] = slot
		next = append(next, slot)
	}
	c.slots = next
	return nil
}

func (c *coordinator) planSlot(ctx context.Context, plan binding.AdmittedTrialPlanV1, view map[string]any, entry trial.ScheduledEntry, root string) (trialSlot, error) {
	input := c.options.Inputs
	input.Plan = plan
	realized, realizeErr := trial.RealizeEntry(input, entry.PlanEntryID, trial.RealizationOptions{})
	if realizeErr != nil {
		return trialSlot{}, realizeErr
	}
	slot := trialSlot{plan: plan, view: view, entry: entry, realization: realized, root: root}
	if root == "" {
		slot.root = entry.PlanEntryID
	}
	request := slot.request(nil)
	request.Identity = c.options.Identity
	request.ExecutionAttemptID = attemptID(c.id, entry.PlanEntryID, 1)
	request.Attempt = 1
	if requestErr := checkTrialRequest(request); requestErr != nil {
		return trialSlot{}, requestErr
	}
	commitment, admitErr := ownerCall(ctx, c, "control", c.options.AdmissionBudget, func(work context.Context) (string, error) { return c.options.Host.Admit(work, copyTrial(request)) })
	if admitErr != nil {
		return trialSlot{}, admitErr
	}
	if !sha(commitment) {
		return trialSlot{}, integrity()
	}
	slot.commitment = commitment
	return slot, nil
}
