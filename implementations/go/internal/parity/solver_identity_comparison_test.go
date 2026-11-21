package parity

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func solverComparisonFixture(t *testing.T, native bool, mutate func(map[string]any)) json.RawMessage {
	t.Helper()
	raw, err := os.ReadFile("../../../../contracts/fixtures/satisfiability/scenario-satisfiability-evidence-v1/valid/unsupported-target.json")
	if err != nil {
		t.Fatal(err)
	}
	var evidence map[string]any
	if err = json.Unmarshal(raw, &evidence); err != nil {
		t.Fatal(err)
	}
	config := solverTestObject(t, evidence["solver_configuration"])
	if native {
		config["profile"], config["package"], config["package_version"] = "raes-z3-finite-domain/v2", "raes-go-z3-smtlib", "1.0.0"
	}
	encoded, err := json.Marshal(config)
	if err != nil {
		t.Fatal(err)
	}
	canonical, err := canonjson.JCS(encoded)
	if err != nil {
		t.Fatal(err)
	}
	evidence["solver_configuration_digest"] = digest.SHA256(canonical)
	if mutate != nil {
		mutate(evidence)
	}
	encoded, err = json.Marshal(map[string]any{"exit_code": 0, "stdout": evidence})
	if err != nil {
		t.Fatal(err)
	}
	return encoded
}

func TestSolverIdentityExceptionKeepsEveryOtherCoordinate(t *testing.T) {
	c := Case{Surface: "cli", Command: "processor satisfiability"}
	want := solverComparisonFixture(t, false, nil)
	got := solverComparisonFixture(t, true, nil)
	if diff, err := compareCaseResults(c, want, got); err != nil || diff != "" {
		t.Fatalf("admitted identity pair differed: %s %v", diff, err)
	}
	for name, mutate := range map[string]func(map[string]any){
		"stale digest":  func(e map[string]any) { e["solver_configuration_digest"] = "sha256:invalid" },
		"wrong package": func(e map[string]any) { solverTestObject(t, e["solver_configuration"])["package"] = "z3-solver" },
		"wrong engine":  func(e map[string]any) { solverTestObject(t, e["solver_configuration"])["engine_version"] = "4.15.0" },
		"changed seed":  func(e map[string]any) { solverTestObject(t, e["solver_configuration"])["random_seed"] = 1 },
		"wrong side": func(e map[string]any) {
			solverTestObject(t, e["solver_configuration"])["profile"] = "raes-z3-finite-domain/v1"
		},
		"extra identity": func(e map[string]any) { solverTestObject(t, e["solver_configuration"])["other"] = true },
		"changed model":  func(e map[string]any) { e["normalized_model_digest"] = "sha256:changed" },
		"changed source": func(e map[string]any) { solverTestObject(t, e["source"])["source_id"] = "other.yaml" },
		"changed diagnostic": func(e map[string]any) {
			solverTestObject(t, solverTestArray(t, e["diagnostics"])[0])["message"] = "changed"
		},
	} {
		t.Run(name, func(t *testing.T) {
			diff, err := compareCaseResults(c, want, solverComparisonFixture(t, true, mutate))
			if err == nil && diff == "" {
				t.Fatal("identity exception hid a forbidden change")
			}
		})
	}
}

func solverTestObject(t *testing.T, value any) map[string]any {
	t.Helper()
	result, ok := value.(map[string]any)
	if !ok {
		t.Fatal("expected fixture object")
	}
	return result
}
func solverTestArray(t *testing.T, value any) []any {
	t.Helper()
	result, ok := value.([]any)
	if !ok {
		t.Fatal("expected fixture array")
	}
	return result
}
