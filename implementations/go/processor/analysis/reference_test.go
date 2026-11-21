package analysis

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type analysisReference struct {
	SourceText      string                   `json:"source_text"`
	InputBytes      []byte                   `json:"input_bytes"`
	SourceID        string                   `json:"source_id"`
	SourceTest      string                   `json:"source_test"`
	Kind            string                   `json:"kind"`
	Input           json.RawMessage          `json:"input"`
	Profile         json.RawMessage          `json:"profile"`
	Catalog         json.RawMessage          `json:"catalog"`
	Expected        map[string]any           `json:"expected"`
	ErrorType       string                   `json:"error_type"`
	CandidateSource *string                  `json:"candidate_source"`
	SemanticResult  map[string]any           `json:"semantic_result"`
	Left            authoringReferenceOutput `json:"left"`
	Right           authoringReferenceOutput `json:"right"`
	LeftPath        string                   `json:"left_path"`
	RightPath       string                   `json:"right_path"`
}
type authoringReferenceOutput struct {
	InputSource  string  `json:"input_source"`
	OutputSource *string `json:"output_source"`
	Diagnostics  []struct {
		Carrier string         `json:"carrier"`
		Value   map[string]any `json:"value"`
	} `json:"diagnostics"`
	TransformationReport json.RawMessage `json:"transformation_report"`
}

func referenceAdmission(id string, raw []byte, context any) (validation.Value, error) {
	owner, err := analysisOwner()
	if err != nil {
		return validation.Value{}, err
	}
	return owner.Validate(id, raw, ingress.Limits{MaxBytes: 16 << 20, MaxDepth: 128}, context)
}
func (input authoringReferenceOutput) native() AuthoringOutput {
	result := AuthoringOutput{InputSource: input.InputSource, OutputSource: input.OutputSource}
	for _, row := range input.Diagnostics {
		finding := diagnosticRecord(row.Value)
		if row.Carrier == "source" {
			finding = diagnostic.Diagnostic{Stage: text(row.Value["stage"]), Code: text(row.Value["code"]), Severity: text(row.Value["severity"]), Pointer: text(row.Value["pointer"]), Message: text(row.Value["message"])}
		}
		result.Diagnostics = append(result.Diagnostics, finding)
	}
	if len(input.TransformationReport) > 0 && string(input.TransformationReport) != "null" {
		// A rejected foreign carrier has no constructible native Value. The absent
		// report exercises the same closed provenance boundary at this API.
		result.TransformationReport, _ = referenceAdmission("artifact-transformation-report-v1", input.TransformationReport, nil)
	}
	return result
}
func (row analysisReference) request() (Request, error) {
	request := Request{Kind: row.Kind, Input: &JSONInput{Data: row.Input, SourceID: row.SourceID}}
	if row.InputBytes != nil {
		request.Input.Data = row.InputBytes
	}

	if len(row.Profile) > 0 {
		input, err := decodeObject(row.Input, 16<<20)
		if err != nil {
			return request, err
		}
		claim, err := canonical(input["claim"])
		if err != nil {
			return request, err
		}
		request.Input.Profile, err = referenceAdmission("behavioral-relation-profile-v1", row.Profile, opacityClaimContext{claim: claim})
		if err != nil {
			return request, err
		}
	}
	if len(row.Catalog) > 0 {
		var err error
		request.Input.Catalog, err = referenceAdmission("behavioral-relations-v1", row.Catalog, nil)
		if err != nil {
			return request, err
		}
	}
	if row.Kind == "authoring-adapter-comparison" {
		vector, err := referenceAdmission("authoring-adapter-vector-v1", row.Input, nil)
		if err != nil {
			return request, err
		}
		request.Authoring = &AuthoringInput{Vector: vector, Left: row.Left.native(), Right: row.Right.native(), LeftPath: row.LeftPath, RightPath: row.RightPath}
	}
	return row.bindReferenceSolver(request)
}
func TestAnalysisIndependentPythonReference(t *testing.T) {
	for _, kind := range []string{"participant-opacity", "participant-opacity-model-check", "candidate-synthesis", "authoring-adapter-comparison", "exploit-path", "satisfiability"} {
		t.Run(kind, func(t *testing.T) {
			if kind == "satisfiability" && os.Getenv("RAES_TEST_Z3") == "" {
				t.Skip("explicit admitted executable required")
			}
			raw := testGzip(t, readTestFile(t, "testdata/"+kind+".json.gz"))
			var fixture struct {
				Cases []analysisReference `json:"cases"`
			}
			decoder := json.NewDecoder(bytes.NewReader(raw))
			decoder.UseNumber()
			if err := decoder.Decode(&fixture); err != nil {
				t.Fatal(err)
			}
			for index, row := range fixture.Cases {
				t.Run(fmt.Sprintf("%s-%d", row.SourceTest, index), func(t *testing.T) { checkAnalysisReference(t, row) })
			}
		})
	}
}
func checkAnalysisReference(t *testing.T, row analysisReference) {
	t.Helper()
	request, err := row.request()
	var got Result
	if err == nil {
		got, err = AnalyzeContext(t.Context(), request)
	}
	if row.ErrorType != "" {
		expected := fault.InvalidInput
		if row.ErrorType == "ParticipantOpacityOperationalError" || row.ErrorType == "ExploitPathOperationalError" {
			expected = fault.Operational
		}
		if category, ok := fault.CategoryOf(err); !ok || category != expected {
			t.Fatalf("reference %s became %v", row.ErrorType, err)
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	rebindReferenceMetadata(t, row)
	if diff := cmp.Diff(row.Expected, got.Document); diff != "" {
		t.Fatal(diff)
	}
	if diff := cmp.Diff(row.CandidateSource, got.CandidateSource); diff != "" {
		t.Fatal(diff)
	}
	if row.SemanticResult != nil {
		if diff := cmp.Diff(row.SemanticResult, testObject(t, got.SemanticResult.JSON())); diff != "" {
			t.Fatal(diff)
		}
	}
}

func rebindReferenceSolverIdentity(t *testing.T, expected map[string]any) {
	t.Helper()
	config := object(expected["solver_configuration"])
	owner, err := analysisOwner()
	if err != nil {
		t.Fatal(err)
	}
	if err = owner.CheckModelFragment("scenario-satisfiability-evidence-v2", "#/$defs/SolverConfigurationModel", testJSON(t, config), ingress.Limits{MaxBytes: 4096, MaxDepth: 16}); err != nil {
		t.Fatal(err)
	}
	originalDigest, err := hash(config)
	if err != nil || expected["solver_configuration_digest"] != originalDigest || config["profile"] != "raes-z3-finite-domain/v1" {
		t.Fatal("reference solver identity is not bound")
	}
	config["profile"], config["package"], config["package_version"] = "raes-z3-finite-domain/v2", "raes-go-z3-smtlib", "1.0.0"
	expected["solver_configuration_digest"], err = hash(config)
	if err != nil {
		t.Fatal(err)
	}
}

func (row analysisReference) bindReferenceSolver(request Request) (Request, error) {
	if row.Kind == "satisfiability" {
		options := sdl.DefaultParseOptions()
		options.MigrationPolicy = sdl.AcceptMigration
		request.Source = &SourceInput{Source: sdl.SourceContext{Root: row.SourceID, RootBytes: []byte(row.SourceText)}, Options: options}
		var err error
		request.Solver, err = OpenSolver(os.Getenv("RAES_TEST_Z3"))
		if err != nil {
			return request, err
		}
	}
	return request, nil
}

// Historical fixtures retain their captured version. Only this verified release
// metadata follows the current package; every other reference field stays exact.
func referenceReleaseMetadata(expected map[string]any) error {
	config := object(expected["checker_configuration"])
	identity, err := hash(config)
	if err != nil || expected["checker_configuration_digest"] != identity || config["package"] != "raes" {
		return errors.New("reference checker configuration is not bound")
	}
	owner, err := analysisOwner()
	if err != nil {
		return err
	}
	raw, err := canonical(config)
	if err != nil {
		return err
	}
	if err = owner.CheckModelFragment("participant-opacity-model-check-evidence-v1", "#/$defs/ParticipantOpacityModelCheckConfigurationModel", raw, ingress.Limits{MaxBytes: 4096, MaxDepth: 16}); err != nil {
		return err
	}
	config["package_version"] = analysisPackageVersion
	expected["checker_configuration_digest"], err = hash(config)
	return err
}

func rebindReferenceMetadata(t *testing.T, row analysisReference) {
	t.Helper()
	if row.Kind == satisfiabilityKind {
		rebindReferenceSolverIdentity(t, row.Expected)
	}
	if row.Kind == opacityModelKind {
		if err := referenceReleaseMetadata(row.Expected); err != nil {
			t.Fatal(err)
		}
	}
}
