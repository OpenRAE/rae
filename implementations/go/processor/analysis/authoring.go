package analysis

import (
	"context"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/profile"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/processor/comparison"
)

func authoringProfiles(vector map[string]any) (profile.ComparisonProfile, error) {
	profiles, err := analysisProfiles()
	if err != nil {
		return profile.ComparisonProfile{}, err
	}
	semantic, err := profiles.ComparisonProfile("reference-v2")
	if err != nil {
		return semantic, err
	}
	for _, candidate := range profiles.Documents() {
		if candidate.ContractID == "authoring-adapter-profile-v1" {
			governed, err := admitOpacityDocument(&JSONInput{Data: candidate.JSON}, candidate.ContractID, 16384)
			if err != nil {
				return semantic, err
			}
			identity, err := hash(governed)
			if err != nil {
				return semantic, err
			}
			if identity != vector[fieldProfileDigest] || governed["semantic_profile_digest"] != semantic.Digest {
				return semantic, invalidAnalysis()
			}
			return semantic, nil
		}
	}
	return semantic, invalidAnalysis()
}
func authoringSemantic(governed profile.ComparisonProfile, left, right comparison.Artifact) (validation.Value, error) {
	before, err := comparison.Coordinate(left, "2", nil)
	if err != nil {
		return validation.Value{}, err
	}
	after, err := comparison.Coordinate(right, "2", nil)
	if err != nil {
		return validation.Value{}, err
	}
	scope, err := comparison.BuildImpactScope([]comparison.Artifact{left}, []comparison.Artifact{right}, []string{text(object(after.Document())["canonical_identity"])}, "complete", "comparison-scope", "2")
	if err != nil {
		return validation.Value{}, err
	}
	raw, err := canonical(map[string]any{fieldSchemaVersion: "semantic-comparison-request/v1", "comparison_profile": governed.ProfileID, "comparison_profile_digest": governed.Digest, "analyzer_profile": governed.AnalyzerProfile, "before": before.Document(), "after": after.Document(), "impact_scope": scope.Document()})
	if err != nil {
		return validation.Value{}, err
	}
	owner, err := analysisOwner()
	if err != nil {
		return validation.Value{}, err
	}
	request, err := owner.Validate("semantic-comparison-request-v1", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}, nil)
	if err != nil {
		return validation.Value{}, err
	}
	return comparison.Analyze(governed, request, left, right, comparison.Options{BeforeScope: []comparison.Artifact{left}, AfterScope: []comparison.Artifact{right}})
}
func authoringSemanticRelation(result validation.Value) (string, error) {
	document, err := decodeObject(result.JSON(), 8<<20)
	if err != nil {
		return "", err
	}
	for _, reason := range array(document[fieldReasonCodes]) {
		if reason != "representation-evidence-missing" {
			return relationIncomparable, nil
		}
	}
	different := false
	for _, row := range array(document["changes"]) {
		change := object(row)
		if change[termSemanticRelation] == "unknown" || change[termSemanticRelation] == relationIncomparable {
			return relationIncomparable, nil
		}
		if change["identity_relation"] != "same" || change[termSemanticRelation] == "changed" {
			different = true
		}
	}
	if different {
		return relationDifferent, nil
	}
	return "equivalent", nil
}
func authoringRelation(left, right any) string {
	if left == nil && right == nil {
		return notApplicable
	}
	if left == right {
		return "equivalent"
	}
	return relationDifferent
}
func authoringEqual(left, right any) bool {
	a, err := hash(left)
	if err != nil {
		return false
	}
	b, err := hash(right)
	return err == nil && a == b
}
func analyzeAuthoring(ctx context.Context, request Request) (Result, error) {
	input := request.Authoring
	if input == nil || len(request.Options) != 0 || input.Vector.ContractID() != "authoring-adapter-vector-v1" {
		return Result{}, invalidAnalysis()
	}
	vector, err := admitOpacityDocument(&JSONInput{Data: input.Vector.JSON()}, "authoring-adapter-vector-v1", 128<<10)
	if err != nil {
		return Result{}, err
	}
	governed, err := authoringProfiles(vector)
	if err != nil {
		return Result{}, err
	}
	reasons := []string{}
	left, leftArtifact, err := observeAuthoringPath(ctx, vector, input.Left, termLeft, &reasons)
	if err != nil {
		return Result{}, err
	}
	right, rightArtifact, err := observeAuthoringPath(ctx, vector, input.Right, termRight, &reasons)
	if err != nil {
		return Result{}, err
	}
	leftExpected := left != nil && authoringEqual(left, vector["expected"])
	rightExpected := right != nil && authoringEqual(right, vector["expected"])
	if !leftExpected {
		reasons = append(reasons, "left-unexpected")
	}
	if !rightExpected {
		reasons = append(reasons, "right-unexpected")
	}
	identity, err := hash(vector)
	if err != nil {
		return Result{}, err
	}
	leftPath, rightPath := input.LeftPath, input.RightPath
	if leftPath == "" {
		leftPath = termLeft
	}
	if rightPath == "" {
		rightPath = termRight
	}
	document := map[string]any{fieldSchemaVersion: "authoring-adapter-comparison/v1", "case_id": vector["case_id"], "vector_digest": identity, "left_path": leftPath, "right_path": rightPath, termLeft: left, termRight: right, "left_matches_expected": leftExpected, "right_matches_expected": rightExpected, termArtifactRelation: relationIncomparable, termDiagnosticRelation: relationIncomparable, termProvenanceRelation: relationIncomparable, termSemanticRelation: relationIncomparable, "semantic_result_digest": nil}
	semantic, err := authoringRelations(document, governed, left, right, leftArtifact, rightArtifact, &reasons)
	if err != nil {
		return Result{}, err
	}
	slices.Sort(reasons)
	document[fieldReasonCodes] = slices.Compact(reasons)
	result, err := admitOutput("authoring-adapter-comparison-v1", document, nil)
	result.SemanticResult = semantic
	return result, err
}

// Both opaque artifacts come from their native owner.
//
//nolint:ireturn // comparison.Artifact is the sealed owner interface.
func observeAuthoringPath(ctx context.Context, vector map[string]any, output AuthoringOutput, side string, reasons *[]string) (map[string]any, comparison.Artifact, error) {
	if output.InputSource != vector[termInputSource] {
		*reasons = append(*reasons, side+"-input-mismatch")
		return nil, nil, nil
	}
	observed, artifact, err := observeAuthoring(ctx, vector, output)
	if err == nil {
		return observed, artifact, nil
	}
	if !authoringInvalidOutput(err) {
		return nil, nil, err
	}
	*reasons = append(*reasons, side+"-invalid")
	return nil, nil, nil
}
func authoringInvalidOutput(err error) bool {
	category, ok := fault.CategoryOf(err)
	return ok && (category == fault.InvalidInput || category == fault.EvidenceIntegrity)
}
func authoringRelations(document map[string]any, governed profile.ComparisonProfile, left, right map[string]any, leftArtifact, rightArtifact comparison.Artifact, reasons *[]string) (validation.Value, error) {
	if left == nil || right == nil {
		return validation.Value{}, nil
	}
	document[termArtifactRelation] = authoringRelation(left[termCanonicalArtifactDigest], right[termCanonicalArtifactDigest])
	document[termDiagnosticRelation] = authoringRelation(left[termDiagnosticsDigest], right[termDiagnosticsDigest])
	document[termProvenanceRelation] = authoringRelation(left[termTransformationDigest], right[termTransformationDigest])
	document[termSemanticRelation] = notApplicable
	if left[fieldOutcome] != right[fieldOutcome] {
		*reasons = append(*reasons, "outcomes-differ")
	}
	var semantic validation.Value
	var err error
	if leftArtifact != nil && rightArtifact != nil {
		semantic, err = authoringSemanticEvidence(document, governed, leftArtifact, rightArtifact)
		if err != nil {
			return validation.Value{}, err
		}
	}
	for _, axis := range [][2]string{{termArtifactRelation, "artifacts-differ"}, {termDiagnosticRelation, "diagnostics-differ"}, {termProvenanceRelation, "provenance-differs"}, {termSemanticRelation, "semantics-differ"}} {
		if document[axis[0]] == relationDifferent {
			*reasons = append(*reasons, axis[1])
		}
	}
	if document[termSemanticRelation] == relationIncomparable {
		*reasons = append(*reasons, "semantic-context-incomplete")
	}
	return semantic, nil
}
func authoringSemanticEvidence(document map[string]any, governed profile.ComparisonProfile, left, right comparison.Artifact) (validation.Value, error) {
	semantic, err := authoringSemantic(governed, left, right)
	if err != nil {
		return validation.Value{}, err
	}
	document[termSemanticRelation], err = authoringSemanticRelation(semantic)
	if err != nil {
		return validation.Value{}, err
	}
	semanticDocument, err := decodeObject(semantic.JSON(), 8<<20)
	if err != nil {
		return validation.Value{}, err
	}
	document["semantic_result_digest"], err = hash(semanticDocument)
	return semantic, err
}
