package governance

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io/fs"
	"maps"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

type repositoryReference struct {
	Name           string            `json:"Name"`
	Files          map[string]string `json:"Files"`
	Findings       []Finding         `json:"Findings"`
	Error          string            `json:"Error,omitempty"`
	Text           string            `json:"Text,omitempty"`
	RequirementUID string            `json:"RequirementUID,omitempty"`
	Environment    map[string]string `json:"Environment,omitempty"`
	Paths          []string          `json:"Paths,omitempty"`
	ExitCode       *int              `json:"ExitCode,omitempty"`
	Tracked        *[]string         `json:"Tracked,omitempty"`
	VerdictOnly    bool              `json:"VerdictOnly,omitempty"`
}

type deltaRepositoryReference struct {
	Base  map[string]string `json:"Base"`
	Cases []struct {
		Name        string             `json:"Name"`
		Changes     map[string]*string `json:"Changes"`
		Findings    []Finding          `json:"Findings"`
		Tracked     *[]string          `json:"Tracked,omitempty"`
		VerdictOnly bool               `json:"VerdictOnly,omitempty"`
	} `json:"Cases"`
}

func runDeltaReference(t *testing.T, tool, name string) {
	t.Helper()
	reference := readReference[deltaRepositoryReference](t, name)
	// Reuse only the immutable contract owner; every case still opens its own
	// repository and runs the same request normalization and dispatcher.
	c := new(checker)
	for _, tc := range reference.Cases {
		t.Run(tc.Name, func(t *testing.T) {
			files := deltaFiles(reference.Base, tc.Changes)
			runRepositoryReferenceWith(t, tool, repositoryReference{Name: tc.Name, Files: files, Findings: tc.Findings, Tracked: tc.Tracked, VerdictOnly: tc.VerdictOnly}, c.evaluate)
		})
	}
}

func deltaFiles(base map[string]string, changes map[string]*string) map[string]string {
	files := maps.Clone(base)
	for name, text := range changes {
		if text == nil {
			delete(files, name)
		} else {
			files[name] = *text
		}
	}
	return files
}

func deltaFixture(t *testing.T, name, selected string) string {
	t.Helper()
	reference := readReference[deltaRepositoryReference](t, name)
	for _, tc := range reference.Cases {
		if tc.Name == selected {
			dir := t.TempDir()
			for name, text := range deltaFiles(reference.Base, tc.Changes) {
				testWrite(t, dir, name, []byte(text))
			}
			return dir
		}
	}
	t.Fatalf("reference case %q missing from %q", selected, name)
	return ""
}

func TestDeprecationReference(t *testing.T) {
	runDeltaReference(t, "deprecation-lifecycle", "deprecation-reference")
}

func TestIdentityReference(t *testing.T) {
	runDeltaReference(t, "identity-cutover", "identity-reference")
}

func TestVocabularyReference(t *testing.T) {
	for _, tool := range []string{"attack-tactic-vocabulary", "atlas-tactic-vocabulary", "nist-csf-defensive-vocabulary", "autonomous-behavior-vocabularies"} {
		t.Run(tool, func(t *testing.T) { runDeltaReference(t, tool, tool+"-reference") })
	}
}

//nolint:ireturn // T is the concrete type of a decoded reference fixture.
func readReference[T any](t *testing.T, name string) T {
	t.Helper()
	encoded := readReferenceHex(t, name)
	data, err := hex.DecodeString(encoded)
	if err != nil {
		t.Fatal(err)
	}
	var result T
	if err := json.Unmarshal(data, &result); err != nil {
		t.Fatal(err)
	}
	return result
}

func readReferenceHex(t *testing.T, name string) string {
	t.Helper()
	encoded, err := os.ReadFile("testdata/" + name + ".hex") // #nosec G304 -- Fixed test fixture name, never candidate input.
	if err == nil {
		return strings.TrimSpace(string(encoded))
	}
	if !errors.Is(err, fs.ErrNotExist) {
		t.Fatal(err)
	}
	parts, err := filepath.Glob("testdata/" + name + "/*.hex")
	if err != nil || len(parts) == 0 {
		t.Fatalf("reference fixture %s: %v", name, err)
	}
	var joined strings.Builder
	for _, part := range parts {
		data, readErr := os.ReadFile(part) // #nosec G304 -- Parts of the fixed trusted test fixture.
		if readErr != nil {
			t.Fatal(readErr)
		}
		joined.WriteString(strings.TrimSpace(string(data)))
	}
	return joined.String()
}

func seedRepositoryReference(t *testing.T, tc repositoryReference) string {
	t.Helper()
	dir := t.TempDir()
	if tc.Tracked != nil {
		dir = testGitRepository(t)
	}
	for name, value := range tc.Environment {
		t.Setenv(name, value)
	}
	for name, text := range tc.Files {
		testWrite(t, dir, name, []byte(text))
	}
	if tc.Tracked != nil && len(*tc.Tracked) > 0 {
		testGit(t, dir, append([]string{"add", "--"}, *tc.Tracked...)...)
	}
	return dir
}

func runRepositoryReference(t *testing.T, tool string, tc repositoryReference) {
	t.Helper()
	runRepositoryReferenceWith(t, tool, tc, Check)
}

func runRepositoryReferenceWith(t *testing.T, tool string, tc repositoryReference, check func(context.Context, Request) (Report, error)) {
	t.Helper()
	dir := seedRepositoryReference(t, tc)
	report, err := check(t.Context(), Request{Tool: tool, Root: dir, RequirementUID: tc.RequirementUID, Paths: tc.Paths})
	if tc.Error != "" {
		if err == nil || err.Error() != tc.Error {
			t.Fatalf("reference error=%v, want %q", err, tc.Error)
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(tc.Findings, report.Findings); !tc.VerdictOnly && diff != "" {
		t.Errorf("reference findings (-want +got):\n%s", diff)
	}
	if tc.VerdictOnly && len(report.Findings) == 0 {
		t.Fatal("reference model refusal has no native finding")
	}
	if tc.Text != "" && report.Text != tc.Text {
		t.Errorf("report text=%q, want %q", report.Text, tc.Text)
	}
	wantExit := 0
	if len(tc.Findings) > 0 {
		wantExit = 1
	}
	if tc.ExitCode != nil {
		wantExit = *tc.ExitCode
	}
	if report.ExitCode != wantExit {
		t.Errorf("exit=%d, want %d", report.ExitCode, wantExit)
	}
}

func TestAgentGuidanceReference(t *testing.T) {
	for _, tc := range readReference[[]repositoryReference](t, "guidance-reference") {
		t.Run(tc.Name, func(t *testing.T) { runRepositoryReference(t, "agent-guidance", tc) })
	}
}

func TestContractTracingReference(t *testing.T) {
	for _, tc := range readReference[[]repositoryReference](t, "tracing-reference") {
		t.Run(tc.Name, func(t *testing.T) { runRepositoryReference(t, "contract-requirement-tracing", tc) })
	}
}

func TestPolicyWaiverReference(t *testing.T) {
	for _, tc := range readReference[[]repositoryReference](t, "waiver-reference") {
		t.Run(tc.Name, func(t *testing.T) { runRepositoryReference(t, "contract-requirement-tracing", tc) })
	}
}

func TestRequirementScopeReference(t *testing.T) {
	for _, tc := range readReference[[]repositoryReference](t, "scope-reference") {
		t.Run(tc.Name, func(t *testing.T) { runRepositoryReference(t, "requirement-context", tc) })
	}
}

func TestRequirementGovernanceReference(t *testing.T) {
	for _, tc := range readReference[[]repositoryReference](t, "requirement-reference") {
		t.Run(tc.Name, func(t *testing.T) { runRepositoryReference(t, "requirement-governance", tc) })
	}
}
