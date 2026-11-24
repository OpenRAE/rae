package analysis

import (
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestSatisfiabilityPublishedControlContext(t *testing.T) {
	executable := os.Getenv("RAES_TEST_Z3")
	if executable == "" {
		t.Skip("explicit admitted executable required")
	}
	solver, err := OpenSolver(executable)
	if err != nil {
		t.Fatal(err)
	}
	request := Request{Kind: "satisfiability", Solver: solver, Source: &SourceInput{Source: sdl.SourceContext{FS: os.DirFS("../../../.."), Root: "examples/scenarios/participant-control-context/context-kit.sdl.yaml"}, Options: sdl.DefaultParseOptions()}}
	checkSatisfiabilityStages(t, request)
}

func checkSatisfiabilityStages(t *testing.T, request Request) {
	t.Helper()
	solver := request.Solver
	source, err := readAnalysisSource(request.Source)
	if err != nil {
		t.Fatal(err)
	}
	scenario, err := sdl.ParseSourceWithContext(t.Context(), source, request.Source.Options)
	if err != nil {
		t.Fatalf("source: %v", err)
	}
	model, findings, err := translateScenario(scenario, "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
	if err != nil || len(findings) > 0 {
		t.Fatalf("translation: %v %v", err, findings)
	}
	solution, err := solver.solve(t.Context(), model)
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.InstantiateWithProfile(scenario, solution.assignment, satisfiabilityProfile)
	if err != nil {
		t.Fatalf("instantiation: %v", err)
	}
	if _, err = sdl.CanonicalBytes(instance); err != nil {
		t.Fatal(err)
	}
	raw, err := sdl.DocumentBytes(instance)
	if err != nil {
		t.Fatal(err)
	}
	phase, err := (witnessPhaseOwner{ctx: t.Context()}).CompileMaterialization(admission.MaterializationCompileRequest{ContractID: "instantiated-scenario-v1", Source: raw})
	if err != nil {
		t.Fatalf("phase: %v", err)
	}
	before, _ := decodeObject(raw, 8<<20)
	after, _ := decodeObject(phase.FullDocument, 8<<20)
	if diff := cmp.Diff(before, after); diff != "" {
		t.Fatal(diff)
	}
	if _, err = Analyze(request); err != nil {
		t.Fatalf("evidence: %v", err)
	}
}
func TestSatisfiabilityPrivateVariableGrammar(t *testing.T) {
	occurrences := []variableOccurrence{}
	variableOccurrences(map[string]any{"os": "${kit.__private.platform}"}, "", &occurrences)
	if len(occurrences) != 1 || occurrences[0].name != "kit.__private.platform" {
		t.Fatalf("private reference lost: %v", occurrences)
	}
	for _, input := range []string{"${__private}", "${kit.__private}", "${bad..x}"} {
		if variableToken.MatchString(input) {
			t.Fatalf("invalid reference accepted: %s", input)
		}
	}
}

func TestSatisfiabilityImportedAndArchitectureSources(t *testing.T) {
	executable := os.Getenv("RAES_TEST_Z3")
	if executable == "" {
		t.Skip("explicit admitted executable required")
	}
	solver, err := OpenSolver(executable)
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"participant-tools/twice-imported.sdl.yaml", "participant-control-context/twice-imported.sdl.yaml"} {
		t.Run(name, func(t *testing.T) {
			checkSatisfiabilityStages(t, Request{Kind: "satisfiability", Solver: solver, Source: &SourceInput{Source: sdl.SourceContext{FS: os.DirFS("../../../.."), Root: "examples/scenarios/" + name}, Options: sdl.DefaultParseOptions()}})
		})
	}
	for _, tc := range []struct{ field, token string }{{"architecture", "AMD64"}, {"architecture", "x-owner:private-architecture"}, {"os", "x-owner:private-os"}} {
		t.Run(tc.token, func(t *testing.T) {
			source := "name: private-os-domain\nvariables:\n  family: {type: string, default: " + tc.token + ", allowed_values: ['" + tc.token + "']}\nnodes:\n  host: {type: compute, " + tc.field + ": '${family}'}\n"
			checkSatisfiabilityStages(t, Request{Kind: "satisfiability", Solver: solver, Source: &SourceInput{Source: sdl.SourceContext{Root: "private.sdl.yaml", RootBytes: []byte(source)}, Options: sdl.DefaultParseOptions()}})
		})
	}
}
