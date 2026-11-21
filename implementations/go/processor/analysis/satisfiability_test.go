package analysis

import (
	"context"
	"encoding/json"
	"os"
	"path"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestSatisfiabilityGoldenControlAndReplay(t *testing.T) {
	executable := os.Getenv("RAES_TEST_Z3")
	if executable == "" {
		t.Skip("explicit admitted executable required")
	}
	solver, err := OpenSolver(executable)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile("../../internal/parity/testdata/cases/cli/processor-satisfiability/841ddf9e2252dfa2f7b2742960b36fc11ba2b8e17ee4dea1bcfdf4027c5b9421.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture cliAnalysisFixture
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	name := fixture.Args[2]
	source, err := os.ReadFile("../../internal/parity/testdata/inputs/" + strings.TrimPrefix(fixture.Files[name], "sha256:"))
	if err != nil {
		t.Fatal(err)
	}
	source = testGzip(t, source)
	options := sdl.DefaultParseOptions()
	options.MigrationPolicy = sdl.AcceptMigration
	request := Request{Kind: "satisfiability", Source: &SourceInput{Source: sdl.SourceContext{Root: path.Base(name), RootBytes: source}, Options: options}, Solver: solver}
	got, err := Analyze(request)
	if err != nil {
		t.Fatal(err)
	}
	want := fixture.Result.Stdout
	config := object(want["solver_configuration"])
	config["profile"] = "raes-z3-finite-domain/v2"
	config["package"] = "raes-go-z3-smtlib"
	config["package_version"] = "1.0.0"
	encoded := testJSON(t, config)
	encoded, err = canonjson.JCS(encoded)
	if err != nil {
		t.Fatal(err)
	}
	want["solver_configuration_digest"] = digest.SHA256(encoded)
	encoded, err = json.Marshal(got.Document)
	if err != nil {
		t.Fatal(err)
	}
	var actual map[string]any
	if err = json.Unmarshal(encoded, &actual); err != nil {
		t.Fatal(err)
	}
	if !cmp.Equal(actual, want) {
		t.Fatalf("got %s\nwant %#v", encoded, want)
	}
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	admitted, err := owner.Validate("scenario-satisfiability-evidence-v2", encoded, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}, witnessPhaseOwner{ctx: context.Background()})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = ReplayContext(context.Background(), request, admitted); err != nil {
		t.Fatal(err)
	}
	request.Source.Source.RootBytes = append(request.Source.Source.RootBytes, '\n')
	_, err = ReplayContext(context.Background(), request, admitted)
	if category, _ := fault.CategoryOf(err); category != fault.EvidenceIntegrity {
		t.Fatalf("source mutation: %v", err)
	}
}

func TestSatisfiabilityUnsupportedRetainsBoundedDiagnostics(t *testing.T) {
	options := sdl.DefaultParseOptions()
	source := []byte("name: unsupported-control\nvariables:\n  cpu_count: {type: integer, allowed_values: [1, 2], required: true}\nnodes:\n  target:\n    type: compute\n    resources: {ram: 1 gib, cpu: '${cpu_count}'}\n")
	got, err := Analyze(Request{Kind: "satisfiability", Source: &SourceInput{Source: sdl.SourceContext{Root: "input.yaml", RootBytes: source}, Options: options}})
	if err != nil {
		t.Fatal(err)
	}
	if got.Document["outcome"] != "unsupported" || len(got.Diagnostics) != 1 || got.Diagnostics[0].Address != "/nodes/target/resources/cpu" {
		t.Fatalf("%+v", got)
	}
}
