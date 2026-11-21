package stub

import (
	"bytes"
	"context"
	"encoding/json"
	"slices"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/clock"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
	"github.com/OpenRAE/rae/implementations/go/internal/base/timestamp"
)

type component struct {
	mutex   sync.Mutex
	domain  string
	clock   clock.Clock
	running bool
	startup []string
	order   []string
	results map[string]map[string]any
	history map[string][]map[string]any
}
type orchestrator struct{ *component }
type evaluator struct{ *component }

// NewOrchestrator constructs the portable orchestration double.
func NewOrchestrator() (Orchestrator, error) { //nolint:ireturn // The declared public API returns the portable role interface.
	return NewOrchestratorWithConfiguration(Configuration{})
}

// NewOrchestratorWithConfiguration supplies an explicit wall clock.
func NewOrchestratorWithConfiguration(c Configuration) (Orchestrator, error) { //nolint:ireturn // The declared public API returns the portable role interface.
	return &orchestrator{newComponent("orchestration", c.Clock)}, nil
}

// NewEvaluator constructs the portable evaluation double.
func NewEvaluator() (Evaluator, error) { //nolint:ireturn // The declared public API returns the portable role interface.
	return NewEvaluatorWithConfiguration(Configuration{})
}

// NewEvaluatorWithConfiguration supplies an explicit wall clock.
func NewEvaluatorWithConfiguration(c Configuration) (Evaluator, error) { //nolint:ireturn // The declared public API returns the portable role interface.
	return &evaluator{newComponent("evaluation", c.Clock)}, nil
}
func newComponent(domain string, wall clock.Clock) *component {
	return &component{domain: domain, clock: wall, startup: []string{}, results: map[string]map[string]any{}, history: map[string][]map[string]any{}}
}
func (o *orchestrator) Start(ctx context.Context, plan binding.OrchestrationPlanV1, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	return o.start(ctx, plan, "orchestration-plan-v1", snapshot)
}
func (e *evaluator) Start(ctx context.Context, plan binding.EvaluationPlanV1, snapshot binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	return e.start(ctx, plan, "evaluation-plan-v1", snapshot)
}

func (c *component) start(ctx context.Context, plan any, contract string, previous binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	if err := callReady(ctx); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	request, err := checkedPlan(plan, contract)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	snapshot, err := snapshotObject(previous)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	c.mutex.Lock()
	defer c.mutex.Unlock()
	now := timestamp.Format(clock.Read(c.clock))
	results := table(snapshot, c.domain+"_results")
	history := table(snapshot, c.domain+"_history")
	order := foldEntryOrder(c.orderedEntries(table(snapshot, "entries")), array(request["operations"]))
	changed, running := c.foldOperations(request, snapshot, now)

	output, err := snapshotResult(snapshot)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	retainedResults := map[string]map[string]any{}
	retainedHistory := map[string][]map[string]any{}
	if err := copyJSON(results, &retainedResults); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	if err := copyJSON(history, &retainedHistory); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	if err := callReady(ctx); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	c.running = running
	c.startup = stringList(request["startup_order"])
	c.order = order
	c.results = retainedResults
	c.history = retainedHistory
	return runtimecontract.ApplyResult{Success: true, Snapshot: output, ChangedAddresses: changed}, nil
}
func (c *component) Status(ctx context.Context) (map[string]any, error) {
	if err := callReady(ctx); err != nil {
		return nil, err
	}
	c.mutex.Lock()
	defer c.mutex.Unlock()
	return map[string]any{termRunning: c.running, "startup_order": slices.Clone(c.startup), "results": len(c.results)}, nil
}
func (c *component) Results(ctx context.Context) (map[string]map[string]any, error) {
	if err := callReady(ctx); err != nil {
		return nil, err
	}
	c.mutex.Lock()
	defer c.mutex.Unlock()
	result := map[string]map[string]any{}
	if err := copyJSON(c.results, &result); err != nil {
		return nil, err
	}
	return result, nil
}
func (c *component) History(ctx context.Context) (map[string][]map[string]any, error) {
	if err := callReady(ctx); err != nil {
		return nil, err
	}
	c.mutex.Lock()
	defer c.mutex.Unlock()
	result := map[string][]map[string]any{}
	if err := copyJSON(c.history, &result); err != nil {
		return nil, err
	}
	return result, nil
}
func (c *component) Stop(ctx context.Context, previous binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	if err := callReady(ctx); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	snapshot, err := snapshotObject(previous)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	c.mutex.Lock()
	defer c.mutex.Unlock()
	entries := table(snapshot, "entries")
	removed := c.orderedEntries(entries)
	for _, address := range removed {
		delete(entries, address)
	}

	snapshot[c.domain+"_results"] = map[string]any{}
	snapshot[c.domain+"_history"] = map[string]any{}
	output, err := snapshotResult(snapshot)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	if err := callReady(ctx); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	c.running = false
	c.startup = []string{}
	c.order = []string{}
	c.results = map[string]map[string]any{}
	c.history = map[string][]map[string]any{}
	return runtimecontract.ApplyResult{Success: true, Snapshot: output, ChangedAddresses: removed}, nil
}
func copyJSON(input, output any) error {
	raw, err := json.Marshal(input)
	if err != nil {
		return invalid()
	}
	// Input is retained native JSON data, admitted and bounded before publication.
	// UseNumber preserves score and other numeric carrier identity on readback.
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if decoder.Decode(output) != nil {
		return invalid()
	}
	return nil
}

func (c *component) foldOperations(request, snapshot map[string]any, now string) ([]string, bool) {
	entries := table(snapshot, "entries")
	results := table(snapshot, c.domain+"_results")
	history := table(snapshot, c.domain+"_history")
	changed := []string{}
	running := len(array(request["startup_order"])) > 0
	for _, item := range array(request["operations"]) {
		operation, _ := item.(map[string]any)
		action := text(operation, "action")
		address := text(operation, "address")
		if action != termDelete {
			running = true
		}
		if action == termUnchanged {
			continue
		}
		if action == termDelete {
			delete(entries, address)
			delete(results, address)
			delete(history, address)
			changed = append(changed, address)
			continue
		}
		c.foldOperation(operation, entries, results, history, now)
		changed = append(changed, address)
	}
	return changed, running
}

func (c *component) foldOperation(operation, entries, results, history map[string]any, now string) {
	address, kind := text(operation, "address"), text(operation, "resource_type")
	status := "bound"
	if c.domain == "evaluation" {
		status = "evaluating"
		if kind == "proposition" || kind == "assertion" {
			status = "admitted"
		}
	} else if slices.Contains([]string{"event", "script", "story", "workflow"}, kind) {
		status = "queued"
	}
	entries[address] = operationEntry(operation, c.domain, status)
	if c.domain == "orchestration" && kind == "workflow" {
		results[address], history[address] = workflowState(operation, now)
	}
	if c.domain == "evaluation" && kind != "proposition" && kind != "assertion" {
		results[address], history[address] = evaluationState(operation, now)
	}
}

// A generated snapshot map has no insertion-order carrier. Retain the order
// established by this double; imported entries use canonical address order.
func (c *component) orderedEntries(entries map[string]any) []string {
	remaining := map[string]bool{}
	for address, item := range entries {
		entry, _ := item.(map[string]any)
		if text(entry, "domain") == c.domain {
			remaining[address] = true
		}
	}
	ordered := []string{}
	for _, address := range c.order {
		if remaining[address] {
			ordered = append(ordered, address)
			delete(remaining, address)
		}
	}
	imported := make([]string, 0, len(remaining))
	for address := range remaining {
		imported = append(imported, address)
	}
	slices.Sort(imported)
	return append(ordered, imported...)
}
func foldEntryOrder(order []string, operations []any) []string {
	for _, item := range operations {
		operation, _ := item.(map[string]any)
		address, action := text(operation, "address"), text(operation, "action")
		if action == termDelete {
			order = slices.DeleteFunc(order, func(item string) bool { return item == address })
			continue
		}
		if action != termUnchanged && !slices.Contains(order, address) {
			order = append(order, address)
		}
	}
	return order
}
