package analysis

import (
	"context"
	"fmt"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func diagnosticRecord(value map[string]any) diagnostic.Diagnostic {
	return diagnostic.Diagnostic{Code: text(value[fieldCode]), Domain: text(value[termDomain]), Address: text(value[fieldAddress]), Severity: text(value[termSeverity]), Message: text(value[termMessage])}
}
func admitOpacityDocument(input *JSONInput, contract string, limit int) (map[string]any, error) {
	if input == nil {
		return nil, invalidAnalysis()
	}
	owner, err := analysisOwner()
	if err != nil {
		return nil, err
	}
	limits := ingress.Limits{MaxBytes: limit, MaxDepth: 64}
	admitted, err := owner.Validate(contract, input.Data, limits, nil)
	if err != nil {
		return nil, err
	}
	transport, err := transportOwner()
	if err != nil {
		return nil, err
	}
	value, err := transport.Defaulted(contract, admitted.JSON(), limits)
	if err != nil {
		return nil, err
	}
	return object(value), nil
}
func analyzeOpacity(_ context.Context, request Request) (Result, error) {
	if len(request.Options) != 0 {
		return Result{}, invalidAnalysis()
	}
	input, err := admitOpacityDocument(request.Input, "participant-opacity-analysis-input-v1", 8<<20)
	if err != nil {
		return Result{}, err
	}
	profile, err := opacityProfileFor(input, request.Input)
	if err != nil {
		return Result{}, err
	}
	rows := normalizeOpacityRows(array(input[termPoints]))
	input[termPoints] = rows
	points, err := decodeShape[[]opacityPoint](rows)
	if err != nil {
		return Result{}, err
	}
	if err = opacityDomains(input, profile, points, false); err != nil {
		return Result{}, err
	}
	modelDigest, err := hash(input)
	if err != nil {
		return Result{}, err
	}
	config := boundedOpacityConfiguration()
	configDigest, err := hash(config)
	if err != nil {
		return Result{}, err
	}
	claim := object(input[termClaim])
	document := map[string]any{
		fieldSchemaVersion: "participant-opacity-analysis-evidence/v1", fieldAnalysisProfile: "raes-participant-opacity-bounded-test/v1", "provenance_scope": "normalized-input-only", termTaxonomyID: claim[termTaxonomyID], termTaxonomyRevision: claim[termTaxonomyRevision], termRelationID: claim[termRelationID], termProfileID: input[termProfileID], termProfileRevision: input[termProfileRevision], fieldProfileDigest: input[fieldProfileDigest], "normalized_model_ref": input["normalized_model_ref"], fieldNormalizedDigest: modelDigest, "checker_configuration": config, "checker_configuration_digest": configDigest, termClaim: claim, "checked_points": 0, "checked_secret_points": 0, termCounterexample: nil, outcomeUnsupported: nil, fieldDiagnostics: []any{},
	}
	reason := func(outcome, code, address, message string) {
		opacityReason(document, termParticipantOpacity, "raes-participant-opacity-unsupported/v1", outcome, code, address, message)
	}
	switch {
	case input["complete_enumeration"] != true:
		reason(outcomeUnsupported, "incomplete-enumeration", "/complete_enumeration", "The declared finite carrier is not complete.")
	case len(points) > 4096:
		reason(outcomeUnsupported, termAnalysisBoundExceeded, "/points", "The declared finite carrier exceeds the deterministic checker bound.")
	default:
		if err = scanBoundedOpacity(document, points, reason); err != nil {
			return Result{}, err
		}
	}
	return opacityResult("participant-opacity-analysis-evidence-v1", document)
}

func scanBoundedOpacity(document map[string]any, points []opacityPoint, reason func(string, string, string, string)) error {
	reachable := make([]opacityPoint, 0, len(points))
	for _, point := range points {
		if point.Reachable {
			reachable = append(reachable, point)
		}
	}
	scan := opacityKernel(reachable)
	document["checked_points"] = scan.checked
	document["checked_secret_points"] = scan.secret
	switch {
	case scan.secret == 0:
		reason(termVacuousSecretDomain, termVacuousSecretDomain, "/points", "The reachable carrier contains no protected secret point.")
	case scan.counterexample != nil:
		counterexample := map[string]any{"safe_ref": fmt.Sprintf("participant-opacity-counterexample:%06d", *scan.counterexample), "actual_point_ordinal": *scan.counterexample, "examined_cell_size": scan.cellSize, fieldNormalizedDigest: text(document[fieldNormalizedDigest])}
		identity, err := hash(counterexample)
		if err != nil {
			return err
		}
		delete(counterexample, fieldNormalizedDigest)
		counterexample["counterexample_digest"] = identity
		document[fieldOutcome] = "counterexample-found"
		document[termCounterexample] = counterexample
	default:
		document[fieldOutcome] = "no-counterexample-within-declared-finite-bounds"
	}
	return nil
}
