package governance

import (
	"encoding/json"
	"path/filepath"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func requirementPatternDocument(t *testing.T, patterns ...string) []byte {
	t.Helper()
	data, err := json.Marshal(map[string]any{
		"project": "fixture", "requirement_source": "repository",
		"phases":       []any{map[string]any{"id": "phase", "patterns": patterns}},
		"ownership":    map[string]any{},
		"traceability": map[string]any{"required_code_roots": []string{}, "required_test_roots": []string{}},
	})
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestRequirementPatternsStandardLibrary(t *testing.T) {
	for _, tc := range []struct {
		pattern, uid string
		matches      bool
	}{
		{`^DSL-`, "DSL-001", true},
		{`^SEM-`, "SEM-235", true},
		{`^ACT-`, "ACT-613", true},
		{`^DSL-`, "ACT-DSL-001", false},
		{`GOV`, "GOV-001", true},
		{`GOV`, "prefix-GOV-001", false},
		{`^GOV-[0-9]{3}$`, "GOV-001", true},
		{`^GOV-[0-9]{3}$`, "GOV-0011", false},
		{`(?i)^gov-`, "GOV-001", true},
		{`^\p{L}+-$`, "GOV-", true},
		{`\QGOV`, "GOV-001", true},
		{`\QGOV`, "prefix-GOV-001", false},
		{``, "GOV-001", true},
	} {
		t.Run(tc.pattern+"/"+tc.uid, func(t *testing.T) {
			value, err := yamlValue(requirementPatternDocument(t, tc.pattern), true)
			if err != nil {
				t.Fatal(err)
			}
			policy, err := parseRequirementPolicy(value)
			if err != nil {
				t.Fatal(err)
			}
			phase, err := matchRequirementPhase(t.Context(), policy, tc.uid)
			if err != nil {
				t.Fatal(err)
			}
			if (phase != nil) != tc.matches {
				t.Fatalf("matched=%t, want %t", phase != nil, tc.matches)
			}
		})
	}
}

func TestRequirementPatternConfigurationFailure(t *testing.T) {
	for _, pattern := range []string{`(`, `GOV)|SEM(?:`, `(?=GOV)GOV-`, `(?<=GOV)-`, `(GOV)\1`, `\N{LATIN CAPITAL LETTER G}OV-`} {
		t.Run(pattern, func(t *testing.T) {
			dir := t.TempDir()
			testWrite(t, dir, requirementPolicyPath, requirementPatternDocument(t, pattern))
			branch := ""
			_, err := Check(t.Context(), Request{
				Tool: "requirement-governance", Root: dir, Branch: &branch,
				RequirementUID: "GOV-001", Paths: []string{"implementations/example/a.py"},
			})
			if err == nil {
				t.Fatal("unsupported configuration reached requirement evaluation")
			}
			if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
				t.Fatalf("configuration error category=%v, known=%t", category, ok)
			}
		})
	}
}

func TestRequirementCurrentPolicyPatterns(t *testing.T) {
	r, err := openRepository(filepath.Join("..", "..", "..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = r.root.Close() })
	policy, err := loadRequirementPolicy(r)
	if err != nil {
		t.Fatal(err)
	}
	for uid, want := range map[string]string{"DSL-001": "sdl-language", "SEM-235": "modular-control-semantics", "SEM-999": "semantics-expansion", "ACT-613": "participant-model"} {
		phase, err := matchRequirementPhase(t.Context(), policy, uid)
		if err != nil {
			t.Fatal(err)
		}
		if phase == nil || phase.id != want {
			t.Errorf("phase for %s=%v, want %s", uid, phase, want)
		}
	}
}
