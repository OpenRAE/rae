package analysis

import (
	"context"
	"fmt"
)

func analyzeOpacityModel(ctx context.Context, request Request) (Result, error) {
	if len(request.Options) != 0 {
		return Result{}, invalidAnalysis()
	}
	input, err := admitOpacityDocument(request.Input, "participant-opacity-model-check-input-v1", 16<<20)
	if err != nil {
		return Result{}, err
	}
	profile, err := opacityProfileFor(input, request.Input)
	if err != nil {
		return Result{}, err
	}
	points, err := decodeShape[[]opacityPoint](input[termStates])
	if err != nil {
		return Result{}, err
	}
	if err = admitOpacityCatalog(input, request.Input); err != nil {
		return Result{}, err
	}
	if err = admitModelAssumptions(input, profile, points); err != nil {
		return Result{}, err
	}
	document, err := opacityModelDocument(input)
	if err != nil {
		return Result{}, err
	}
	findings := opacityModelUnsupported(input)
	if len(findings) > 0 {
		document[fieldOutcome] = outcomeUnsupported
		document[fieldDiagnostics] = diagnosticsDocument(findings)
		document[outcomeUnsupported] = map[string]any{fieldProfile: "raes-participant-opacity-model-check-unsupported/v1", fieldReasonCodes: diagnosticCodes(findings)}
		return opacityResult(termParticipantOpacityModelCheckEvidenceV1, document)
	}
	transitions, err := decodeShape[[]opacityTransition](input["transitions"])
	if err != nil {
		return Result{}, err
	}
	initial := []int{}
	for _, value := range array(input["initial_state_ordinals"]) {
		initial = append(initial, integer(value))
	}
	reached, err := reachableOpacity(ctx, points, transitions, initial)
	if err != nil {
		return Result{}, err
	}
	document["coverage"] = opacityCoverage(input, points, reached)
	evaluation, carrier := opacityEvaluationCarrier(input, reached)
	document[termDerivedCarrierDigest], err = hash(carrier)
	if err != nil {
		return Result{}, err
	}
	if err = opacityModelOutcome(document, evaluation, points, reached); err != nil {
		return Result{}, err
	}
	return opacityResult(termParticipantOpacityModelCheckEvidenceV1, document)
}

func opacityModelDocument(input map[string]any) (map[string]any, error) {
	config := modelOpacityConfiguration()
	document := map[string]any{fieldSchemaVersion: "participant-opacity-model-check-evidence/v1", fieldAnalysisProfile: "raes-participant-opacity-model-check/v1", "provenance_scope": "normalized-model-only", "checker_configuration": config, fieldDiagnostics: []any{}, termCounterexample: nil, outcomeUnsupported: nil}
	for _, field := range []string{"catalog_digest", termProfileID, termProfileRevision, fieldProfileDigest, fieldSource, "model_ref", "model_revision", "materializer_id", "materializer_version", "materializer_digest", termAssumptions, termClaim} {
		document[field] = input[field]
	}
	claim := object(input[termClaim])
	for _, field := range []string{termTaxonomyID, termTaxonomyRevision, termRelationID} {
		document[field] = claim[field]
	}
	for key, value := range map[string]any{fieldModelDigest: input, "assumptions_digest": input[termAssumptions], "checker_configuration_digest": config} {
		identity, err := hash(value)
		if err != nil {
			return nil, err
		}
		document[key] = identity
	}
	emptyDigest, err := hash([]any{})
	if err != nil {
		return nil, err
	}
	document[termDerivedCarrierDigest] = emptyDigest
	document["coverage"] = map[string]any{"declared": input[termDeclaredCounts], fieldExploredStates: 0, fieldExploredTransitions: 0, termReachableEvaluationPoints: 0, termReachableSecretPoints: 0, "strategy_coverage": []any{}, "explored_scheduler_environment_pairs": 0, "explored_order_variants": 0, "complete_fixed_point": false}

	return document, nil
}

func opacityModelOutcome(document map[string]any, evaluation, points []opacityPoint, reached opacityReachability) error {
	scan := opacityKernel(evaluation)
	switch {
	case scan.secret == 0:
		opacityReason(document, opacityModelKind, "raes-participant-opacity-model-check-unsupported/v1", termVacuousSecretDomain, termVacuousSecretDomain, "/states", "The reachable evaluation-point carrier contains no protected secret point.")
	case scan.counterexample != nil:
		ordinal := *scan.counterexample
		counterexample := map[string]any{"safe_ref": fmt.Sprintf("participant-opacity-model-check-counterexample:%06d", ordinal), "actual_state_ordinal": ordinal, "actual_path_transition_ordinals": opacityCounterexamplePath(ordinal, reached.parents), "strategy_ref": points[ordinal].Strategy, "examined_cell_size": scan.cellSize, fieldModelDigest: document[fieldModelDigest], fieldProfileDigest: document[fieldProfileDigest], termDerivedCarrierDigest: document[termDerivedCarrierDigest]}
		identity, err := hash(counterexample)
		if err != nil {
			return err
		}
		for _, field := range []string{fieldModelDigest, fieldProfileDigest, termDerivedCarrierDigest} {
			delete(counterexample, field)
		}
		counterexample["counterexample_digest"] = identity
		document[termCounterexample] = counterexample
		document[fieldOutcome] = "counterexample-found"
	default:
		document[fieldOutcome] = "holds-on-exact-complete-finite-model"
	}
	return nil
}

func opacityEvaluationCarrier(input map[string]any, reached opacityReachability) ([]opacityPoint, []any) {
	evaluation := []opacityPoint{}
	carrier := []any{}
	sourceRows := array(input[termStates])
	for _, point := range reached.points {
		if point.Evaluation {
			evaluation = append(evaluation, point)
			carrier = append(carrier, sourceRows[point.Ordinal])
		}
	}

	return evaluation, carrier
}
