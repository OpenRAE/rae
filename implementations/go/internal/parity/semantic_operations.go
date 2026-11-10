package parity

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/authoring"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type semanticCommand struct{ operation, name, contract, policy, transform string }

func semanticOperationRunner() Runner {
	parser, loadErr := authoring.New(source.DefaultLimits())
	return func(ctx context.Context, c Case) (json.RawMessage, error) {
		if loadErr != nil {
			return nil, loadErr
		}
		command, ok := semanticArguments(c.Args)
		if !ok {
			return formatEnvelope(2, nil)
		}
		result := semanticResult(command)
		if command.contract != termSdlYamlV1 {
			result["status"] = "unsupported"
			result["diagnostics"] = []any{semanticDiagnostic("cli.operation-unsupported", "cli", "", "error")}
			return semanticEnvelope(3, result)
		}
		raw, present := semanticCommandInput(c, command)
		if !present || int64(len(raw)) > source.DefaultLimits().MaxInputBytes {
			result["status"] = "operational"
			result["diagnostics"] = []any{semanticDiagnostic("cli.input", "cli", "", "error")}
			return semanticEnvelope(4, result)
		}
		document, advisories, err := admitSemanticCommand(ctx, parser, raw, command)
		if err != nil {
			return semanticRefusal(result, err)
		}
		result["diagnostics"] = advisories
		result["validation_strength"] = "semantic"
		payload, err := semanticPayload(ctx, parser, document, command, raw)
		if err != nil {
			result["status"] = "internal"
			result["validation_strength"] = nil
			result["diagnostics"] = []any{semanticDiagnostic("cli.internal", "cli", "", "error")}
			return semanticEnvelope(70, result)
		}
		result["payload"] = payload
		if command.operation == termTransform {
			result["transform_profile"] = command.transform
		}
		return semanticEnvelope(0, result)
	}
}
func semanticPayload(ctx context.Context, parser *authoring.Parser, document *authoring.Document, command semanticCommand, raw []byte) (map[string]any, error) {
	if command.operation == termResolve {
		bindings, err := document.ReferenceBindings()
		if err != nil {
			return nil, err
		}
		var fields map[string]any
		if err = json.Unmarshal(document.JSON(), &fields); err != nil {
			return nil, err
		}
		return map[string]any{termPhase: "resolved-references", termRootType: termObject, "scenario_name": fields["name"], "reference_binding_count": len(bindings), "reference_bindings": bindings}, nil
	}
	if command.operation == termTransform && command.transform == termCanonical {
		canonical, err := document.CanonicalBytes()
		if err != nil {
			return nil, err
		}
		identity, err := document.CanonicalDigest()
		return map[string]any{termPhase: "transformed", termRootType: termObject, "content": string(canonical), termDigest: semanticDigest(identity)}, err
	}
	formatted, err := parser.FormatContext(ctx, authoring.Request{Source: raw})
	if err != nil {
		return nil, err
	}
	payload := map[string]any{termPhase: "transformed", termRootType: termObject, "content": string(formatted.Content)}
	if command.operation == "normalize" {
		var fields map[string]any
		if err = json.Unmarshal(document.JSON(), &fields); err != nil {
			return nil, err
		}
		identity, err := document.CanonicalDigest()
		if err != nil {
			return nil, err
		}
		payload[termPhase], payload["scenario_name"], payload["field_count"], payload["semantic_validated"], payload[termDigest] = "normalized-authoring", fields["name"], len(fields), true, semanticDigest(identity)
	}
	return payload, nil
}
func semanticDigest(identity string) map[string]any {
	return map[string]any{"algorithm": "sha256", "profile": "raes-sdl-semantic/v2", "value": identity}
}
func semanticResult(command semanticCommand) map[string]any {
	result := map[string]any{"operation": command.operation, "status": "success", "contract_id": command.contract, "source_format": nil, "migration_policy": nil, "normalization_profile": nil, "validation_strength": nil, "processor_profile": nil, "transform_profile": nil, "provenance": map[string]any{"network": "disabled", "filesystem": "read-only"}, "payload": map[string]any{}, "diagnostics": []any{}}
	if command.contract == termSdlYamlV1 {
		result["source_format"] = termSdlYamlV1
		result["migration_policy"] = command.policy
		result["normalization_profile"] = "raes-sdl-semantic/v2"
	}
	return result
}
func semanticDiagnostic(code, domain, address, severity string) map[string]any {
	return map[string]any{"code": code, "domain": domain, "address": address, "severity": severity}
}
func semanticEnvelope(code int, result map[string]any) (json.RawMessage, error) {
	return formatEnvelope(code, result)
}
func semanticRefusal(result map[string]any, err error) (json.RawMessage, error) {
	result["status"] = "invalid"
	findings := []any{}
	if carrier, ok := errors.AsType[diagnostic.Error](err); ok && carrier.Code() == "sdl-semantic-invalid" {
		findings = append(findings, semanticDiagnostic("sdl.validation", "sdl-validation", "", "error"))
	} else {
		for _, finding := range source.Diagnostics(err) {
			findings = append(findings, semanticDiagnostic(finding.Code, "sdl-parse", finding.Pointer, finding.Severity))
			if len(findings) == 20 {
				break
			}
		}
		if len(findings) == 0 {
			findings = append(findings, semanticDiagnostic("sdl.parse", "sdl-parse", "", "error"))
		}
	}
	result["diagnostics"] = findings
	return semanticEnvelope(1, result)
}
func semanticArguments(args []string) (semanticCommand, bool) {
	command := semanticCommand{contract: termSdlYamlV1, policy: "reject", transform: termCanonical}
	if len(args) < 3 || args[0] != "semantic" {
		return command, false
	}
	command.operation = args[1]
	if command.operation != termResolve && command.operation != "normalize" && command.operation != termTransform {
		return command, false
	}
	name, arguments, ok := operationArguments(args[2:], true)
	if !ok {
		return command, false
	}
	command.name = name
	for _, argument := range arguments {
		if !command.option(argument.name, argument.value) {
			return command, false
		}
	}
	return command, true
}
func (c *semanticCommand) option(option, value string) bool {
	switch option {
	case "--contract":
		c.contract = value
	case "--migration-policy":
		if value != "accept" && value != "reject" {
			return false
		}
		c.policy = value
	case "--output":
		return value == "json"
	case "--transform":
		if c.operation != termTransform || value != termCanonical && value != "format" {
			return false
		}
		c.transform = value
	default:
		return false
	}
	return true
}
func admitSemanticCommand(ctx context.Context, parser *authoring.Parser, raw []byte, command semanticCommand) (*authoring.Document, []any, error) {
	request := authoring.Request{Source: raw}
	advisories := []any{}
	if command.policy == "accept" {
		formatted, err := parser.FormatContext(ctx, request)
		if err != nil {
			return nil, nil, err
		}
		request.Source = formatted.Content
		for _, finding := range formatted.Diagnostics {
			advisories = append(advisories, semanticDiagnostic(finding.Code, "sdl-parse", finding.Pointer, finding.Severity))
		}
	}
	document, err := parser.DecodeContext(ctx, request)
	if err != nil {
		return nil, nil, err
	}
	document, _, err = parser.Validate(document)
	return document, advisories, err
}

func semanticCommandInput(c Case, command semanticCommand) ([]byte, bool) {
	name := command.name
	if name == "-" {
		name = "stdin.bin"
	}
	raw, present := c.Files[name]
	return raw, present
}
