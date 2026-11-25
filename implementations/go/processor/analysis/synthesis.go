package analysis

import (
	"context"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func synthesisProfile() (map[string]any, error) {
	profiles, err := analysisProfiles()
	if err != nil {
		return nil, err
	}
	for _, p := range profiles.Documents() {
		if p.ContractID == "sdl-candidate-synthesis-profile-v1" {
			return admitOpacityDocument(&JSONInput{Data: p.JSON}, p.ContractID, 8<<20)
		}
	}
	return nil, invalidAnalysis()
}
func synthesisChoice(id, reason string, alternatives ...string) any {
	slices.Sort(alternatives)
	return map[string]any{termChoiceID: id + "-" + reason, termReason: reason, termAssertionIDs: []string{id}, "alternatives": slices.Compact(alternatives)}
}
func synthesisChoices(input map[string]any) []any {
	counts := map[string]int{}
	for _, row := range array(input[termDecisions]) {
		for _, id := range stringValues(object(row)[termAssertionIDs]) {
			counts[id]++
		}
	}
	choices := []any{}
	for _, row := range array(input["assertions"]) {
		assertion := object(row)
		id := text(assertion["assertion_id"])
		switch assertion[termKind] {
		case "concept":
			if counts[id] != 1 {
				choices = append(choices, synthesisChoice(id, termMissingNativeSemantics, "supply-one-explicit-native-construct-decision"))
			}
		case "relationship":
			choices = append(choices, synthesisChoice(id, termUnsupportedRelation, "select-a-governed-profile-with-an-exact-native-relation"))
		case "parameterization":
			choices = append(choices, synthesisChoice(id, "unresolved-parameterization", stringValues(assertion["candidate_values"])...))
		case "ordering":
			if assertion["direction"] == "unspecified" {
				choices = append(choices, synthesisChoice(id, "ambiguous-ordering", "left-before-right", "right-before-left"))
			} else {
				choices = append(choices, synthesisChoice(id, termMissingNativeSemantics, "select-a-governed-profile-with-an-exact-native-rule"))
			}
		default:
			choices = append(choices, synthesisChoice(id, termMissingNativeSemantics, "select-a-governed-profile-with-an-exact-native-rule"))
		}
	}
	slices.SortFunc(choices, func(a, b any) int {
		return strings.Compare(text(object(a)[termChoiceID]), text(object(b)[termChoiceID]))
	})
	return choices
}
func transformationCheck(id, outcome string, codes ...string) any {
	if codes == nil {
		codes = []string{}
	}
	return map[string]any{"check_id": id, fieldOutcome: outcome, "diagnostic_codes": codes}
}
func transformationDiagnostic(code, message, address string) any {
	return map[string]any{termDomain: "artifact-transformation", fieldCode: code, termMessage: message, fieldAddress: address, termSeverity: severityError}
}
func synthesisTraces(input map[string]any) []any {
	traces := []any{}
	for _, row := range array(input[termDecisions]) {
		decision := object(row)
		ids := stringValues(decision[termAssertionIDs])
		parts := []any{}
		add := func(kind string, id any) { parts = append(parts, map[string]any{termKind: kind, "ref_id": id}) }
		for _, id := range ids {
			add("imported-assertion", id)
		}
		for _, row := range array(input[termAssumptions]) {
			assumption := object(row)
			for _, id := range stringValues(assumption[termAssertionIDs]) {
				if slices.Contains(ids, id) {
					add("transformation-assumption", assumption["assumption_id"])
					break
				}
			}
		}
		add("inferred-structure", "concept-node-emission")
		kind := "governed-policy-decision"
		if decision["actor_kind"] == "author" {
			kind = "author-decision"
		}
		add(kind, decision["decision_id"])
		traces = append(traces, map[string]any{termTargetRef: decision[termTargetRef], "contributions": parts})
	}
	slices.SortFunc(traces, func(a, b any) int {
		return strings.Compare(text(object(a)[termTargetRef]), text(object(b)[termTargetRef]))
	})
	return traces
}
func synthesisReport(input map[string]any, inputDigest string) (map[string]any, error) {
	derivation, err := hash(map[string]any{termInputDigest: inputDigest, termOperationProfile: termConceptNodesV1, termPolicyDigest: input[termPolicyDigest], "transformation_profile_digest": object(input["transformation_profile"])["digest"]})
	if err != nil {
		return nil, err
	}
	return map[string]any{fieldSchemaVersion: "artifact-transformation-report/v1", termOperationProfile: termConceptNodesV1, "artifact_kind": "sdl-authoring", "source_profile": input[fieldSchemaVersion], "target_profile": authoringProfile, termCanonicalizationProfile: "raes-sdl-canonical/v1", "source_digest": inputDigest, termTargetDigest: nil, termPolicyDigest: input[termPolicyDigest], "derivation_digest": derivation, termPreconditions: []any{}, "postconditions": []any{}, "affected_identities": []any{}, "identity_map": []any{}, "losses": []any{}, fieldDiagnostics: []any{}}, nil
}
func refuseSynthesis(record, report map[string]any, choices []any, disposition, code string) {
	record["disposition"] = disposition
	record["unresolved_choices"] = choices
	report[termStatus] = "refused"
	report[termPreconditions] = []any{transformationCheck("candidate-resolved", "failed", code), transformationCheck("source-admitted", termPassed)}
	report["preservation"] = map[string]any{fieldProfile: "source-neutral-candidate-provenance/v1", fieldOutcome: notApplicable, "evidence_digests": []any{}, "limitations": []string{"A refused synthesis emits no SDL candidate."}}
	report[fieldDiagnostics] = []any{transformationDiagnostic(code, "Candidate synthesis requires an exact governed choice or supported transformation profile.", "")}
	losses := []any{}
	for _, row := range choices {
		choice := object(row)
		if choice[termReason] == termUnsupportedRelation {
			ids, _ := choice[termAssertionIDs].([]string)
			for _, id := range ids {
				losses = append(losses, map[string]any{termKind: "semantic-omission", "affected_identity": id, "diagnostic": transformationDiagnostic("candidate-synthesis.semantic-omission", "The source assertion cannot be represented without omitting unsupported semantics.", "/assertions/"+id)})
			}
		}
	}
	report["losses"] = losses
}
func analyzeSynthesis(ctx context.Context, request Request) (Result, error) {
	if len(request.Options) != 0 {
		return Result{}, invalidAnalysis()
	}
	input, err := admitOpacityDocument(request.Input, "sdl-candidate-synthesis-input-v1", 8<<20)
	if err != nil {
		return Result{}, err
	}
	profile, err := synthesisProfile()
	if err != nil {
		return Result{}, err
	}
	inputDigest, err := hash(input)
	if err != nil {
		return Result{}, err
	}
	report, err := synthesisReport(input, inputDigest)
	if err != nil {
		return Result{}, err
	}
	record := map[string]any{fieldSchemaVersion: "sdl-candidate-synthesis-record/v1", "record_id": text(input[termInputID]) + "-record", termInputID: input[termInputID], termInputDigest: inputDigest, "input": input, fieldProfile: profile, "construct_traces": []any{}, "unresolved_choices": []any{}, "candidate_exact_digest": nil, "candidate_canonical_digest": nil, "transformation_report": report}
	coordinate := object(input["transformation_profile"])
	if coordinate[termProfileID] != profile[termProfileID] || coordinate[termVersion] != profile["profile_version"] || coordinate["digest"] != profile[fieldProfileDigest] {
		record[fieldProfile] = nil
		choices := []any{synthesisChoice(text(object(array(input["assertions"])[0])["assertion_id"]), "transformation-profile-unavailable", termConceptNodesV1)}
		refuseSynthesis(record, report, choices, "non-reproducible", "candidate-synthesis.transformation-profile-unavailable")
		return admitOutput(termSdlCandidateSynthesisRecordV1, record, nil)
	}
	choices := synthesisChoices(input)
	if len(choices) > 0 {
		disposition := "requires-decision"
		for _, row := range choices {
			if object(row)[termReason] == termUnsupportedRelation {
				disposition = outcomeUnsupported
			}
		}
		refuseSynthesis(record, report, choices, disposition, "candidate-synthesis.unresolved-semantics")
		return admitOutput(termSdlCandidateSynthesisRecordV1, record, nil)
	}
	return synthesizeCandidate(ctx, input, record, report)
}
func synthesizeCandidate(ctx context.Context, input, record, report map[string]any) (Result, error) {
	nodes := map[string]any{}
	identities := []any{}
	for _, row := range array(input[termDecisions]) {
		decision := object(row)
		ref := text(decision[termTargetRef])
		nodes[strings.TrimPrefix(ref, "nodes.")] = map[string]any{termType: decision["node_type"]}
		identities = append(identities, ref)
	}
	target := object(input["target"])
	raw, err := canonical(map[string]any{"name": target["scenario_id"], termVersion: target["scenario_version"], "nodes": nodes})
	if err != nil {
		return Result{}, err
	}
	scenario, err := sdl.ParseWithContext(ctx, raw, sdl.DefaultParseOptions())
	if err != nil {
		return Result{}, err
	}
	rendered, err := sdl.RenderSource(ctx, scenario)
	if err != nil {
		return Result{}, err
	}
	scenario, err = sdl.ParseWithContext(ctx, rendered, sdl.DefaultParseOptions())
	if err != nil {
		return Result{}, err
	}
	semantic, err := sdl.CanonicalDigest(scenario)
	if err != nil {
		return Result{}, err
	}
	exact := digest.SHA256(rendered)
	record["disposition"] = outcomeSuccess
	record["construct_traces"] = synthesisTraces(input)
	record["candidate_exact_digest"] = exact
	record["candidate_canonical_digest"] = semantic
	report[termStatus] = outcomeSuccess
	report[termTargetDigest] = semantic
	report[termCanonicalizationProfile] = sdlSemanticProfile
	report["affected_identities"] = identities
	pre := []any{}
	for _, id := range []string{"assertions-current", "decisions-complete", "source-admitted", "transformation-profile-supported"} {
		pre = append(pre, transformationCheck(id, termPassed))
	}
	report[termPreconditions] = pre
	report["postconditions"] = []any{transformationCheck("candidate-reparsed", termPassed), transformationCheck("candidate-semantic-valid", termPassed)}
	evidence := []string{text(record[termInputDigest]), semantic, exact}
	slices.Sort(evidence)
	report["preservation"] = map[string]any{fieldProfile: "source-neutral-candidate-provenance/v1", fieldOutcome: "verified", "evidence_digests": slices.Compact(evidence), "limitations": []string{"Synthesis admission does not establish source equivalence, instantiation, compilation, or execution."}}
	result, err := admitOutput(termSdlCandidateSynthesisRecordV1, record, nil)
	if err != nil {
		return Result{}, err
	}
	content := string(rendered)
	result.CandidateSource = &content
	result.Candidate = scenario
	return result, nil
}
