package analysis

import (
	"context"
	"errors"
	"slices"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor/comparison"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

//nolint:ireturn // sdl.Scenario is the sealed native owner handle.
func authoringSource(ctx context.Context, source string) (sdl.Scenario, error) {
	if !utf8.ValidString(source) {
		return nil, invalidAnalysis()
	}
	options := sdl.DefaultParseOptions()
	options.Limits = sdl.Limits{MaxInputBytes: 65536, MaxScalarBytes: 65536, MaxDepth: 32, MaxNodes: 4096, MaxAliases: 32, MaxExpandedNodes: 8192, MaxImports: 1, MaxComposedNodes: 8192, MaxComposedBytes: 65536, MaxCompositionDepth: 1, MaxNamespaceDepth: 1}
	scenario, err := sdl.ParseWithContext(ctx, []byte(source), options)
	if err != nil {
		return nil, err
	}
	document := scenario.Document()
	if len(array(document[termImports])) != 0 {
		return nil, invalidAnalysis()
	}
	findings, err := sdl.Validate(scenario)
	if err != nil {
		return nil, err
	}
	if len(findings) != 0 {
		return nil, invalidAnalysis()
	}
	return scenario, nil
}
func authoringDiagnosticDigest(findings []diagnostic.Diagnostic) (string, error) {
	if len(findings) > 64 {
		return "", invalidAnalysis()
	}
	keys := make([][]string, 0, len(findings))
	for _, finding := range findings {
		key, err := authoringDiagnosticKey(finding)
		if err != nil {
			return "", err
		}
		keys = append(keys, key)
	}
	slices.SortFunc(keys, func(a, b []string) int {
		for i := range a {
			if c := strings.Compare(a[i], b[i]); c != 0 {
				return c
			}
		}
		return 0
	})
	return hash(map[string]any{fieldProfile: "authoring-diagnostic-semantics/v1", "keys": keys})
}
func authoringTransformation(ctx context.Context, vector map[string]any, output AuthoringOutput, artifact sdl.Scenario, artifactDigest any) (any, error) {
	operation := object(vector["operation"])[fieldProfile]
	if output.TransformationReport.ContractID() == "" {
		if operation == "validate-sdl/v1" {
			return nil, nil //nolint:nilnil // Validation has no transformation provenance.
		}
		if err := authoringPreOperationRefusal(ctx, vector, artifact); err != nil {
			return nil, err
		}
		return nil, nil //nolint:nilnil // Structured source rejection prevented transformation.
	}
	if output.TransformationReport.ContractID() != "artifact-transformation-report-v1" || operation == "validate-sdl/v1" {
		return nil, invalidAnalysis()
	}
	report, err := admitOpacityDocument(&JSONInput{Data: output.TransformationReport.JSON()}, "artifact-transformation-report-v1", 16<<20)
	if err != nil {
		return nil, err
	}
	normalized, err := canonical(report)
	if err != nil || len(normalized) > 65536 {
		return nil, invalidAnalysis()
	}
	source, err := authoringSource(ctx, text(vector[termInputSource]))
	if err != nil {
		return nil, err
	}
	sourceDigest, err := sdl.CanonicalDigest(source)
	if err != nil {
		return nil, err
	}
	if report[termOperationProfile] != operation || report["source_digest"] != sourceDigest || report[termTargetDigest] != artifactDigest || report["source_profile"] != authoringProfile || report["target_profile"] != authoringProfile || report[termCanonicalizationProfile] != sdlSemanticProfile || (report[termStatus] == outcomeSuccess) != (artifact != nil) {
		return nil, invalidAnalysis()
	}
	return hash(report)
}

//nolint:ireturn // comparison.Artifact is the sealed native owner handle.
func observeAuthoring(ctx context.Context, vector map[string]any, output AuthoringOutput) (map[string]any, comparison.Artifact, error) {
	var scenario sdl.Scenario
	var artifact comparison.Artifact
	var coordinate, artifactDigest any
	outcome := "refused"
	if output.OutputSource != nil {
		var err error
		scenario, artifact, coordinate, artifactDigest, err = authoringArtifact(ctx, *output.OutputSource)
		if err != nil {
			return nil, nil, err
		}
		outcome = outcomeSuccess
	} else if len(output.Diagnostics) == 0 {
		return nil, nil, invalidAnalysis()
	}
	diagnosticDigest, err := authoringDiagnosticDigest(output.Diagnostics)
	if err != nil {
		return nil, nil, err
	}
	transformation, err := authoringTransformation(ctx, vector, output, scenario, artifactDigest)
	if err != nil {
		return nil, nil, err
	}
	return map[string]any{fieldOutcome: outcome, "artifact_coordinate": coordinate, termCanonicalArtifactDigest: artifactDigest, termDiagnosticsDigest: diagnosticDigest, termTransformationDigest: transformation}, artifact, nil
}

func authoringDiagnosticKey(finding diagnostic.Diagnostic) ([]string, error) {
	domain, address := finding.Domain, finding.Address
	if finding.Stage != "" {
		domain, address = finding.Stage, finding.Pointer
	}
	key := []string{domain, finding.Code, finding.Severity, address}
	for _, value := range key {
		if !utf8.ValidString(value) || len(value) > 4096 {
			return nil, invalidAnalysis()
		}
	}
	if domain == "" || finding.Code == "" || !slices.Contains([]string{severityError, "warning", "info"}, finding.Severity) || !utf8.ValidString(finding.Message) || len(finding.Message) > 512 {
		return nil, invalidAnalysis()
	}

	return key, nil
}

func authoringPreOperationRefusal(ctx context.Context, vector map[string]any, artifact sdl.Scenario) error {
	if artifact != nil {
		return invalidAnalysis()
	}
	_, err := authoringSource(ctx, text(vector[termInputSource]))
	var structured diagnostic.Error
	if errors.As(err, &structured) && len(structured.Diagnostics()) > 0 {
		return nil
	}
	if err != nil && !authoringInvalidOutput(err) {
		return err
	}
	return invalidAnalysis()
}

//nolint:ireturn // Both handles come from sealed native owners.
func authoringArtifact(ctx context.Context, source string) (sdl.Scenario, comparison.Artifact, any, any, error) {
	var err error
	scenario, err := authoringSource(ctx, source)
	if err != nil {
		return nil, nil, nil, nil, err
	}
	artifactDigest, err := sdl.CanonicalDigest(scenario)
	if err != nil {
		return nil, nil, nil, nil, err
	}
	artifact, err := comparison.FromScenario(scenario)
	if err != nil {
		return nil, nil, nil, nil, err
	}
	fragment, err := comparison.Coordinate(artifact, "2", nil)
	if err != nil {
		return nil, nil, nil, nil, err
	}
	return scenario, artifact, fragment.Document(), artifactDigest, nil
}
