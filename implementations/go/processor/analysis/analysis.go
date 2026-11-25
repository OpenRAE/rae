package analysis

import (
	"bytes"
	"context"
	"encoding/json"
	"slices"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/processor/comparison"
)

var analysisOwner = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Immutable packaged admission owner.
func invalidAnalysis() error                       { return fault.New(fault.InvalidInput, "analysis-input", nil) }
func canonical(value any) ([]byte, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return nil, invalidAnalysis()
	}
	return canonjson.JCS(raw)
}
func hash(value any) (string, error) {
	raw, err := canonical(value)
	if err != nil {
		return "", err
	}
	return digest.SHA256(raw), nil
}
func object(value any) map[string]any { v, _ := value.(map[string]any); return v }
func array(value any) []any           { v, _ := value.([]any); return v }
func text(value any) string           { v, _ := value.(string); return v }
func decodeObject(raw []byte, limit int) (map[string]any, error) {
	v, err := ingress.Parse(raw, ingress.Limits{MaxBytes: limit, MaxDepth: 128}, ingress.Object)
	if err != nil {
		return nil, err
	}
	return object(v), nil
}
func admitOutput(id string, document, context any) (Result, error) {
	raw, err := canonical(document)
	if err != nil {
		return Result{}, err
	}
	owner, err := analysisOwner()
	if err != nil {
		return Result{}, err
	}
	_, err = owner.Validate(id, raw, ingress.Limits{MaxBytes: 16 << 20, MaxDepth: 128}, context)
	if err != nil {
		return Result{}, err
	}
	value, err := decodeObject(raw, 16<<20)
	return Result{Document: value}, err
}
func diagnosticsDocument(findings []diagnostic.Diagnostic) []any {
	result := make([]any, 0, len(findings))
	for _, finding := range findings {
		result = append(result, map[string]any{fieldCode: finding.Code, termDomain: finding.Domain, fieldAddress: finding.Address, termMessage: finding.Message, termSeverity: finding.Severity})
	}
	return result
}

// Analyze performs one bounded processor analysis.
func Analyze(request Request) (Result, error) { return AnalyzeContext(context.Background(), request) }

// AnalyzeContext performs one analysis under explicit caller cancellation.
func AnalyzeContext(ctx context.Context, request Request) (Result, error) {
	if ctx == nil {
		return Result{}, invalidAnalysis()
	}
	if ctx.Err() != nil {
		return Result{}, fault.New(fault.Operational, termAnalysisCancelled, nil)
	}
	var result Result
	var err error
	switch request.Kind {
	case "authoring-adapter-comparison":
		result, err = analyzeAuthoring(ctx, request)
	case "candidate-synthesis":
		result, err = analyzeSynthesis(ctx, request)
	case opacityModelKind:
		result, err = analyzeOpacityModel(ctx, request)
	case termParticipantOpacity:
		result, err = analyzeOpacity(ctx, request)
	case exploitKind:
		result, err = analyzeExploit(ctx, request)
	case satisfiabilityKind:
		result, err = analyzeSatisfiability(ctx, request)
	case "semantic-comparison":
		if request.Comparison == nil {
			return Result{}, invalidAnalysis()
		}
		input := request.Comparison
		result.SemanticResult, err = comparison.Analyze(input.Profile, input.Request, input.Before, input.After, input.Options)
		if err == nil {
			result.Document, err = decodeObject(result.SemanticResult.JSON(), 16<<20)
		}
	default:
		return Result{}, invalidAnalysis()
	}
	if ctx.Err() != nil {
		return Result{}, fault.New(fault.Operational, termAnalysisCancelled, nil)
	}
	return result, err
}

// ReplayContext re-admits stored evidence and compares every reproduced field.
func ReplayContext(ctx context.Context, request Request, evidence validation.Value) (Result, error) {
	contracts := map[string]string{
		satisfiabilityKind:             "scenario-satisfiability-evidence-v2",
		exploitKind:                    "exploit-path-analysis-evidence-v1",
		termParticipantOpacity:         "participant-opacity-analysis-evidence-v1",
		opacityModelKind:               termParticipantOpacityModelCheckEvidenceV1,
		"candidate-synthesis":          termSdlCandidateSynthesisRecordV1,
		"authoring-adapter-comparison": "authoring-adapter-comparison-v1",
		"semantic-comparison":          "semantic-comparison-result-v1",
	}
	if ctx == nil || contracts[request.Kind] == "" || evidence.ContractID() != contracts[request.Kind] {
		return Result{}, invalidAnalysis()
	}
	if ctx.Err() != nil {
		return Result{}, fault.New(fault.Operational, termAnalysisCancelled, nil)
	}
	owner, err := analysisOwner()
	if err != nil {
		return Result{}, err
	}
	var admissionContext any
	if request.Kind == satisfiabilityKind {
		admissionContext = witnessPhaseOwner{ctx: ctx}
	}
	if _, err = owner.Validate(evidence.ContractID(), evidence.JSON(), ingress.Limits{MaxBytes: 16 << 20, MaxDepth: 128}, admissionContext); err != nil {
		return Result{}, fault.New(fault.EvidenceIntegrity, termAnalysisReplay, nil)
	}
	request, err = bindReplaySource(request, evidence.JSON())
	if err != nil {
		return Result{}, err
	}
	result, err := AnalyzeContext(ctx, request)
	if err != nil {
		return Result{}, err
	}
	actual, err := canonical(result.Document)
	if err != nil {
		return Result{}, err
	}
	expected, err := canonjson.JCS(evidence.JSON())
	if err != nil || !bytes.Equal(actual, expected) {
		return Result{}, fault.New(fault.EvidenceIntegrity, termAnalysisReplay, nil)
	}
	return result, nil
}

func diagnosticCodes(findings []diagnostic.Diagnostic) []string {
	codes := make([]string, 0, len(findings))
	for _, finding := range findings {
		codes = append(codes, finding.Code)
	}
	slices.Sort(codes)
	return slices.Compact(codes)
}

//nolint:ireturn // Each use decodes a concrete private wire type.
func decodeShape[T any](value any) (T, error) {
	var result T
	raw, err := canonical(value)
	if err != nil {
		return result, err
	}
	err = json.Unmarshal(raw, &result)
	return result, err
}

func bindReplaySource(request Request, evidence []byte) (Request, error) {
	var raw []byte
	switch request.Kind {
	case satisfiabilityKind:
		source, err := readAnalysisSource(request.Source)
		if err != nil {
			return request, err
		}
		raw = source.RootBytes
		input := *request.Source
		input.Source = source
		request.Source = &input
	case exploitKind:
		if request.Input == nil {
			return request, invalidAnalysis()
		}
		raw = request.Input.Data
	default:
		return request, nil
	}
	document, err := decodeObject(evidence, 16<<20)
	if err != nil {
		return request, err
	}
	if object(document[fieldSource])["byte_digest"] != digest.SHA256(raw) {
		return request, fault.New(fault.EvidenceIntegrity, termAnalysisReplay, nil)
	}
	return request, nil
}
