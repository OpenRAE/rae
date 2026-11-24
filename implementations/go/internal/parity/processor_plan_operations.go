package parity

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/planning"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// The existing contract fixture carries the recorder's default target
// capabilities. Backend identity is not part of a plan-inspection payload.
func processorPlanRunner() Runner {
	defaultJSON, loadErr := os.ReadFile("../../../../contracts/fixtures/backend-manifest/backend-manifest-v2/valid/stub.json")
	return func(ctx context.Context, c Case) (json.RawMessage, error) {
		if loadErr != nil {
			return nil, loadErr
		}
		name, manifest, valid := processorPlanInput(c, defaultJSON)
		if !valid {
			return formatEnvelope(2, nil)
		}
		return processorPlanCase(ctx, c, name, manifest)
	}
}

func processorPlanInput(c Case, defaultJSON []byte) (string, binding.BackendManifestV2, bool) {
	if len(c.Args) < 3 || c.Args[0] != "processor" || c.Args[1] != "plan" {
		return "", binding.BackendManifestV2{}, false
	}
	name, arguments, valid := operationArguments(c.Args[2:], false)
	if !valid {
		return "", binding.BackendManifestV2{}, false
	}
	manifestJSON, valid := processorPlanOptions(c, arguments, defaultJSON)
	if !valid {
		return "", binding.BackendManifestV2{}, false
	}
	manifest, valid := processorTarget(manifestJSON)
	if !valid {
		return "", binding.BackendManifestV2{}, false
	}
	if _, present := c.Files[name]; !present {
		return "", binding.BackendManifestV2{}, false
	}
	return name, manifest, true
}

func processorPlanOptions(c Case, arguments []operationOption, defaultJSON []byte) ([]byte, bool) {
	manifestJSON := defaultJSON
	hasFormat := false
	for _, argument := range arguments {
		switch argument.name {
		case "--format":
			if argument.value != termJSON {
				return nil, false
			}
			hasFormat = true
		case "--manifest":
			var present bool
			manifestJSON, present = c.Files[argument.value]
			if !present {
				return nil, false
			}
		default:
			return nil, false
		}
	}
	if !hasFormat {
		return nil, false
	}
	return manifestJSON, true
}

func processorPlanCase(ctx context.Context, c Case, name string, manifest binding.BackendManifestV2) (json.RawMessage, error) {
	files := processorSourceFiles(c.Files)
	scenario, err := sdl.ParseFileWithContext(ctx, files, name, sdl.DefaultParseOptions())
	if err != nil {
		return processorPlanRefusal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		return processorPlanRefusal(err)
	}
	result, err := planning.PlanWithManifest(compiled, manifest, planning.Options{})
	if err != nil {
		return processorPlanRefusal(err)
	}
	provisioning, err := processorValueFreeAccounts(result.Plan.Provisioning())
	if err != nil {
		return processorPlanRefusal(err)
	}
	payload := map[string]any{termScenarioName: compiled.Model().View().Name, "provisioning": provisioning, "orchestration": result.Plan.Orchestration(), "evaluation": result.Plan.Evaluation(), termDiagnostics: result.Diagnostics}
	raw, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	var output any
	if json.Unmarshal(raw, &output) != nil {
		return nil, errors.New("processor runner: invalid native projection")
	}
	output = processorDiagnosticProjection(output)
	code := 0
	if !result.Plan.Valid() {
		code = 1
	}
	return formatEnvelope(code, output)
}

func processorPlanRefusal(err error) (json.RawMessage, error) {
	category, known := fault.CategoryOf(err)
	if known && (category == fault.InvalidInput || category == fault.Operational) {
		return formatEnvelope(1, nil)
	}
	if errors.Is(err, os.ErrNotExist) {
		return formatEnvelope(1, nil)
	}
	return nil, err
}

// Only these report and phase records contain adapter-owned diagnostics.
// Operation payloads and profile values retain arbitrary authored field names.
func processorDiagnosticProjection(input any) any {
	record, ok := input.(map[string]any)
	if !ok {
		return input
	}
	processorRecordDiagnostics(record)
	for _, key := range []string{"provisioning", "orchestration", "evaluation", "baseline", "candidate"} {
		if child, known := record[key].(map[string]any); known {
			processorRecordDiagnostics(child)
		}
	}
	return input
}

func processorRecordDiagnostics(record map[string]any) {
	findings, ok := record[termDiagnostics].([]any)
	if !ok {
		return
	}
	projected := make([]any, len(findings))
	for i, item := range findings {
		finding, valid := item.(map[string]any)
		if !valid {
			projected[i] = item
			continue
		}
		projected[i] = map[string]any{
			"code":      processorDiagnosticMember(finding, "code"),
			termDomain:  processorDiagnosticMember(finding, termDomain),
			termAddress: processorDiagnosticMember(finding, termAddress),
			"severity":  processorDiagnosticMember(finding, "severity"),
		}
	}
	record[termDiagnostics] = projected
}

func processorDiagnosticMember(finding map[string]any, name string) any {
	if item, present := finding[name]; present {
		return item
	}
	for key, item := range finding {
		if strings.EqualFold(key, name) {
			return item
		}
	}
	return ""
}
