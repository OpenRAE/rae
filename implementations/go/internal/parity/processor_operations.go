package parity

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func processorManifestRunner() Runner {
	// Supply the frozen recording's release version to the native builder.
	// Version selection is an application input, not processor semantics.
	manifest, err := processor.Manifest("10.2.0", nil)
	return func(_ context.Context, _ Case) (json.RawMessage, error) {
		if err != nil {
			return nil, err
		}
		return formatEnvelope(0, manifest)
	}
}

func semanticCompileEnvelope(ctx context.Context, raw []byte, command semanticCommand, result map[string]any) (json.RawMessage, error) {
	options := sdl.DefaultParseOptions()
	options.MigrationPolicy = sdl.MigrationPolicy(command.policy)
	scenario, err := sdl.ParseWithContext(ctx, raw, options)
	if err != nil {
		return semanticRefusal(result, err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		category, known := fault.CategoryOf(err)
		if !known || category != fault.InvalidInput {
			return nil, err
		}
		code, domain := "sdl.compile", "sdl-compile"
		if carrier, ok := errors.AsType[interface {
			error
			Code() string
		}](err); ok && carrier.Code() == "sdl-instantiation-invalid" {
			code, domain = "sdl.instantiation", "sdl-instantiation"
		}
		result["status"] = "invalid"
		result[termDiagnostics] = []any{semanticDiagnostic(code, domain, "", "error")}
		return semanticEnvelope(1, result)
	}
	model := compiled.Model().View()
	counts := map[string]int{}
	for _, section := range []string{"networks", "node_deployments", "feature_bindings", "propositions", "assertions", "injects", "events", "scripts", "stories", "workflows", "objectives"} {
		counts[section] = 0
	}
	sections := map[string]string{"network": "networks", "node": "node_deployments", "feature-binding": "feature_bindings", "proposition": "propositions", "assertion": "assertions", "inject": "injects", "event": "events", "script": "scripts", "story": "stories", "workflow": "workflows", "objective": "objectives"}
	for _, resource := range model.Resources {
		if section := sections[resource.Kind]; section != "" {
			counts[section]++
		}
	}
	findings, _ := result[termDiagnostics].([]any)
	for _, finding := range model.Diagnostics {
		findings = append(findings, semanticDiagnostic(finding.Code, finding.Domain, finding.Address, finding.Severity))
	}
	result[termDiagnostics] = findings
	result["payload"] = map[string]any{"phase": "compiled-runtime-summary", "root_type": "object", termScenarioName: model.Name, "resource_counts": counts, "diagnostic_count": len(model.Diagnostics)}
	result["validation_strength"] = termSemantic
	result["processor_profile"] = "raes-compiler/default"
	return semanticEnvelope(0, result)
}
