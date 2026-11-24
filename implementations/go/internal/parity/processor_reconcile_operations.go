package parity

import (
	"context"
	"encoding/json"
	"os"
	"slices"
	"strings"
	"sync"
	"testing/fstest"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

var processorTargetOwner = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Shared immutable packaged validator.

func processorTarget(data []byte) (binding.BackendManifestV2, bool) {
	var manifest binding.BackendManifestV2
	if len(data) > 1<<20 || !utf8.Valid(data) {
		return manifest, false
	}
	owner, err := processorTargetOwner()
	if err != nil {
		return manifest, false
	}
	if owner.CheckPortable("backend-manifest-v2", data, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 128}) != nil || json.Unmarshal(data, &manifest) != nil {
		return manifest, false
	}
	envelope, _ := manifest.RealizationEnvelope.Value()
	return manifest, len(envelope) == 0 || string(envelope) == "null"
}

//nolint:ireturn // Each generated instantiation returns its concrete transport type without a runtime interface.
func processorField[T any](field binding.Field[T]) T { result, _ := field.Value(); return result }
func processorSourceFiles(files map[string][]byte) fstest.MapFS {
	result := fstest.MapFS{}
	for name, content := range files {
		result[name] = &fstest.MapFile{Data: content}
	}
	return result
}
func processorReconcileRunner() Runner {
	defaultJSON, loadErr := os.ReadFile("../../../../contracts/fixtures/backend-manifest/backend-manifest-v2/valid/stub.json")
	return func(ctx context.Context, c Case) (json.RawMessage, error) {
		if loadErr != nil {
			return nil, loadErr
		}
		baseline, candidate, target, valid := processorReconcileInput(c, defaultJSON)
		if !valid {
			return formatEnvelope(2, nil)
		}
		return processorReconcileCase(ctx, c, baseline, candidate, target)
	}
}

func processorReconcileInput(c Case, defaultJSON []byte) (string, string, binding.BackendManifestV2, bool) {
	if len(c.Args) < 4 || c.Args[0] != "processor" || c.Args[1] != "reconcile" || strings.HasPrefix(c.Args[2], "-") || strings.HasPrefix(c.Args[3], "-") {
		return "", "", binding.BackendManifestV2{}, false
	}
	baseline, candidate := c.Args[2], c.Args[3]
	targetJSON, valid := processorReconcileOptions(c, defaultJSON)
	if !valid {
		return "", "", binding.BackendManifestV2{}, false
	}
	target, valid := processorTarget(targetJSON)
	if !valid {
		return "", "", binding.BackendManifestV2{}, false
	}
	if _, exists := c.Files[baseline]; !exists {
		return "", "", binding.BackendManifestV2{}, false
	}
	if _, exists := c.Files[candidate]; !exists {
		return "", "", binding.BackendManifestV2{}, false
	}
	return baseline, candidate, target, true
}

func processorReconcileOptions(c Case, defaultJSON []byte) ([]byte, bool) {
	targetJSON, hasFormat := defaultJSON, false
	for index := 4; index < len(c.Args); index++ {
		if index+1 >= len(c.Args) {
			return nil, false
		}
		switch c.Args[index] {
		case "--format":
			if c.Args[index+1] != termJSON {
				return nil, false
			}
			hasFormat = true
		case "--manifest":
			var present bool
			targetJSON, present = c.Files[c.Args[index+1]]
			if !present {
				return nil, false
			}
		default:
			return nil, false
		}
		index++
	}
	if !hasFormat {
		return nil, false
	}
	return targetJSON, true
}

func processorReconcileCase(ctx context.Context, c Case, baseline, candidate string, target binding.BackendManifestV2) (json.RawMessage, error) {
	files := processorSourceFiles(c.Files)
	source, err := sdl.ParseFileWithContext(ctx, files, baseline, sdl.DefaultParseOptions())
	if err != nil {
		return processorPlanRefusal(err)
	}
	first, err := processor.Compile(source, nil)
	if err != nil {
		return processorPlanRefusal(err)
	}
	planned, err := planning.PlanWithManifest(first, target, planning.Options{})
	if err != nil {
		return processorPlanRefusal(err)
	}
	baselinePayload := map[string]any{termScenarioName: first.Model().View().Name, termDiagnostics: planned.Diagnostics, "snapshot": nil}
	output := map[string]any{"status": "baseline_rejected", "snapshot_kind": "planned-state-projection", "baseline": baselinePayload, "candidate": nil, "actions": nil, "operations": nil}
	if !planned.Plan.Valid() {
		return processorReportEnvelope(1, output)
	}
	snapshot, err := planning.AssumedSnapshot(planned.Plan)
	if err != nil {
		return processorPlanRefusal(err)
	}
	baselinePayload["snapshot"], err = processorSnapshotSummary(snapshot)
	if err != nil {
		return nil, err
	}
	source, err = sdl.ParseFileWithContext(ctx, files, candidate, sdl.DefaultParseOptions())
	if err != nil {
		return processorPlanRefusal(err)
	}
	second, err := processor.Compile(source, nil)
	if err != nil {
		return processorPlanRefusal(err)
	}
	proposed, err := planning.PlanWithManifest(second, target, planning.Options{Snapshot: &snapshot})
	if err != nil {
		return processorPlanRefusal(err)
	}
	output["status"] = "reconciled"
	code := 0
	if !proposed.Plan.Valid() {
		output["status"] = "candidate_rejected"
		code = 1
	}
	output["candidate"] = map[string]any{termScenarioName: second.Model().View().Name, termDiagnostics: proposed.Diagnostics}
	output["actions"], output["operations"] = processorReconcileOperations(proposed)

	return processorReportEnvelope(code, output)
}
func processorReportEnvelope(code int, output any) (json.RawMessage, error) {
	raw, err := json.Marshal(output)
	if err != nil {
		return nil, err
	}
	var document any
	if err := json.Unmarshal(raw, &document); err != nil {
		return nil, err
	}
	return formatEnvelope(code, processorDiagnosticProjection(document))
}
func processorSnapshotSummary(snapshot binding.RuntimeSnapshotV1) (any, error) {
	type summary struct {
		Address  string                           `json:"address"`
		Domain   string                           `json:"domain"`
		Kind     string                           `json:"resource_type"`
		Ordering []string                         `json:"ordering_dependencies"`
		Refresh  []string                         `json:"refresh_dependencies"`
		Bindings []binding.DomainProfileBindingV1 `json:"profile_bindings"`
	}
	type summaryRow struct {
		Address    string   `json:"address"`
		Domain     string   `json:"domain"`
		Kind       string   `json:"resource_type"`
		Ordering   []string `json:"ordering_dependencies"`
		Refresh    []string `json:"refresh_dependencies"`
		BindingIDs []string `json:"profile_binding_ids"`
	}
	entries := []summaryRow{}
	for _, raw := range processorField(snapshot.Entries) {
		var entry summary
		if err := json.Unmarshal(raw, &entry); err != nil {
			return nil, err
		}
		ids := []string{}
		for _, binding := range entry.Bindings {
			ids = append(ids, processorField(binding.BindingId))
		}
		slices.Sort(ids)
		entries = append(entries, summaryRow{Address: entry.Address, Domain: entry.Domain, Kind: entry.Kind, Ordering: entry.Ordering, Refresh: entry.Refresh, BindingIDs: ids})
	}
	slices.SortFunc(entries, func(a, b summaryRow) int {
		return strings.Compare(a.Address, b.Address)
	})
	return map[string]any{"entry_count": len(entries), "entries": entries}, nil
}

func processorReconcileOperations(proposed planning.Result) (map[string]int, []any) {
	counts := map[string]int{"create": 0, "update": 0, "delete": 0, "unchanged": 0}
	operations := []any{}
	appendOperation := func(domain, address, kind, action string) {
		counts[action]++
		operations = append(operations, map[string]any{termDomain: domain, termAddress: address, "resource_type": kind, "action": action})
	}
	for _, operation := range processorField(proposed.Plan.Provisioning().Operations) {
		appendOperation("provisioning", processorField(operation.Address), processorField(operation.ResourceType), processorField(operation.Action))
	}
	for _, operation := range processorField(proposed.Plan.Orchestration().Operations) {
		appendOperation("orchestration", processorField(operation.Address), processorField(operation.ResourceType), processorField(operation.Action))
	}
	for _, operation := range processorField(proposed.Plan.Evaluation().Operations) {
		appendOperation("evaluation", processorField(operation.Address), processorField(operation.ResourceType), processorField(operation.Action))
	}

	return counts, operations
}
