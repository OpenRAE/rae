package governance

import (
	"bytes"
	"encoding/json"
	"errors"
	"maps"
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"github.com/google/go-cmp/cmp"
)

type liveReferenceCase struct {
	repositoryReference

	Changes       map[string]*string             `json:"Changes"`
	JSONEdits     map[string][]referenceJSONEdit `json:"JSONEdits"`
	Directories   []string                       `json:"Directories"`
	Changed       []string                       `json:"Changed"`
	CheckSet      string                         `json:"CheckSet"`
	ErrorType     string                         `json:"ErrorType"`
	NativeRefusal string                         `json:"NativeRefusal"`
	ProseFree     bool                           `json:"ProseFree"`
	Messages      []string                       `json:"Messages"`
}
type liveReferenceCatalog struct {
	Base  map[string]string   `json:"Base"`
	Cases []liveReferenceCase `json:"Cases"`
}
type liveReferenceResult struct {
	Findings []Finding `json:"findings"`
	Text     string    `json:"text"`
	Error    string    `json:"error"`
}

// CI runs both implementations on the same freshly seeded repository. The
// larger recorded suites also run without Python in the native test lane.
func TestLiveReferenceParity(t *testing.T) {
	if os.Getenv("GOVERNANCE_REFERENCE_PYTHON") == "" {
		t.Skip("hosted comparison requires the explicit frozen reference interpreter")
	}
	for _, family := range []struct{ tool, fixture string }{
		{"adr-immutability", "adr-reference"}, {"agent-guidance", "guidance-reference"},
		{"assurance-policy", "assurance-reference"}, {"authority-boundary", "authority-reference"},
		{"concept-authority-governance", "concept-reference"}, {"contract-requirement-tracing", "tracing-reference"},
		{"deprecation-lifecycle", "deprecation-reference"}, {"identity-cutover", "identity-reference"},
		{"project-positioning", "positioning-reference"}, {"schema-coverage", "coverage-reference"},
		{"schema-publication", "publication-reference"}, {"public-docs", "public-docs-reference"},
		{"repo-policy", "repo-reference"}, {"requirement-governance", "requirement-reference"},
		{"requirement-context", "scope-reference"},
		{attackVocabularyCheck, attackVocabularyCheck + "-reference"}, {atlasVocabularyCheck, atlasVocabularyCheck + "-reference"},
		{nistVocabularyCheck, nistVocabularyCheck + "-reference"}, {autonomousVocabularyCheck, autonomousVocabularyCheck + "-reference"},
	} {
		t.Run(family.tool, func(t *testing.T) { liveReferenceFamily(t, family.tool, family.fixture) })
	}
	t.Run("pr-title", liveTitleReference)
	t.Run("pr-body", liveBodyReference)
	t.Run("public-docs-reads", liveReadsReference)
	t.Run("json-artifacts", liveArtifactsReference)
	t.Run("repo-policy-rego-denial", func(t *testing.T) {
		catalog := loadLiveReference(t, "repo-reference")
		for _, tc := range catalog.Cases {
			if tc.Name == "conftest-canonical" {
				liveRepositoryReference(t, "repo-policy", catalog.Base, tc)
				return
			}
		}
		t.Fatal("missing actual Rego denial case")
	})
}

func liveReferenceFamily(t *testing.T, tool, fixture string) {
	t.Helper()
	catalog := loadLiveReference(t, fixture)
	selected := 0
	negative := false
	clean := false
	for _, tc := range catalog.Cases {
		if !tc.liveEligible() {
			continue
		}
		failure := len(tc.Findings) > 0 || len(tc.Messages) > 0
		if liveResultSelected(failure, negative, clean) {
			continue
		}
		t.Run(tc.Name, func(t *testing.T) { liveRepositoryReference(t, tool, catalog.Base, tc) })
		negative = negative || failure
		clean = clean || !failure
		selected++
		if selected == 2 {
			break
		}
	}
	if tool == "requirement-context" {
		return
	}
	if selected < 2 || !negative {
		t.Fatalf("%s has only %d comparison cases", fixture, selected)
	}
}

func liveResultSelected(failure, negative, clean bool) bool {
	if failure {
		return negative
	}
	return clean
}

func (tc liveReferenceCase) liveEligible() bool {
	return !tc.VerdictOnly && !tc.ProseFree && tc.Error == "" && tc.ErrorType == "" && tc.NativeRefusal == ""
}

func liveArtifactsReference(t *testing.T) {
	for _, value := range []string{`{"schema_version":"sample/v1","value":"accepted"}`, `{"schema_version":"sample/v1","value":17}`} {
		root := t.TempDir()
		testWrite(t, root, "contracts/schemas/profiles/sample-v1.json", []byte(`{"type":"object","properties":{"schema_version":{"type":"string"},"value":{"type":"string"}},"required":["value"]}`))
		name := "contracts/profiles/semantic/sample.json"
		testWrite(t, root, name, []byte(value))
		compareLiveReference(t, Request{Tool: jsonArtifactCheck, Root: root, Paths: []string{name}}, nil)
	}
}
func loadLiveReference(t *testing.T, fixture string) liveReferenceCatalog {
	t.Helper()
	raw := readReference[json.RawMessage](t, fixture)
	var catalog liveReferenceCatalog
	if len(raw) > 0 && raw[0] == '[' {
		if err := json.Unmarshal(raw, &catalog.Cases); err != nil {
			t.Fatal(err)
		}
	} else if err := json.Unmarshal(raw, &catalog); err != nil {
		t.Fatal(err)
	}
	return catalog
}
func liveRepositoryReference(t *testing.T, tool string, base map[string]string, tc liveReferenceCase) {
	t.Helper()
	if base != nil {
		changes := referenceJSONEdits(t, base, tc.JSONEdits)
		maps.Copy(changes, tc.Changes)
		tc.Files = deltaFiles(base, changes)
	}
	root := seedRepositoryReference(t, tc.repositoryReference)
	if _, exists := tc.Files[exceptionPath]; !exists {
		testWrite(t, root, exceptionPath, []byte("exceptions: []\n"))
	}
	for _, name := range tc.Directories {
		testWrite(t, root, name+"/.keep", nil)
	}
	paths := tc.Paths
	if paths == nil {
		paths = tc.Changed
	}
	request := Request{Tool: tool, Root: root, Paths: paths, CheckSet: tc.CheckSet, RequirementUID: tc.RequirementUID}
	if tool == "repo-policy" && request.CheckSet == "" {
		request.CheckSet = "file-local"
	}
	compareLiveReference(t, request, tc.Environment)
}

func compareLiveReference(t *testing.T, request Request, environment map[string]string) {
	t.Helper()
	payload, err := json.Marshal(map[string]any{"Request": map[string]any{"Tool": request.Tool, "Root": request.Root, "Paths": request.Paths, "CheckSet": request.CheckSet, "RequirementUID": request.RequirementUID, "Title": request.Title, "Body": request.Body, "IssuesFile": request.IssuesFile, "Documentation": request.Documentation}, "Environment": environment})
	if err != nil {
		t.Fatal(err)
	}
	interpreter := os.Getenv("GOVERNANCE_REFERENCE_PYTHON")
	if !filepath.IsAbs(interpreter) {
		t.Fatal("reference interpreter must be an absolute frozen environment path")
	}
	cmd := exec.CommandContext(t.Context(), interpreter, "testdata/reference_driver.py") // #nosec G204 G702 -- Explicit CI-owned frozen interpreter and fixed trusted source driver; repository fixtures are data on stdin.
	cmd.Stdin = bytes.NewReader(payload)
	output, err := cmd.Output()
	if err != nil {
		if exited, ok := errors.AsType[*exec.ExitError](err); ok {
			t.Fatalf("reference driver: %v: %s", err, exited.Stderr)
		}
		t.Fatal(err)
	}
	var reference liveReferenceResult
	if err := json.Unmarshal(output, &reference); err != nil {
		t.Fatalf("reference result: %v: %s", err, output)
	}
	report, nativeErr := Check(t.Context(), request)
	if reference.Error != "" {
		t.Fatalf("reference comparison could not evaluate its selected case: %s", reference.Error)
	}
	if nativeErr != nil {
		t.Fatal(nativeErr)
	}
	if diff := cmp.Diff(reference.Findings, report.Findings); diff != "" {
		t.Fatalf("live findings (-Python +Go):\n%s", diff)
	}
	if reference.Text != report.Text {
		t.Fatalf("live text=%q want %q", report.Text, reference.Text)
	}
	want := 0
	if len(reference.Findings) > 0 {
		want = 1
	}
	if report.ExitCode != want {
		t.Fatalf("native exit=%d want %d", report.ExitCode, want)
	}
}

func liveReadsReference(t *testing.T) {
	for _, index := range []int{2, 3, 7} {
		tc := readReference[[]documentReadReference](t, "docs-reads-reference")[index]
		t.Run(tc.Name, func(t *testing.T) {
			root := t.TempDir()
			docs := &Documentation{SourceRoot: "docs/public", ModuleRoots: tc.ModuleRoots, ImportedModules: tc.ImportedModules, Reads: []DocumentRead{}}
			for _, file := range tc.Files {
				docs.Reads = append(docs.Reads, DocumentRead{Page: "index", File: file})
			}
			compareLiveReference(t, Request{Tool: "public-docs-reads", Root: root, Documentation: docs}, nil)
		})
	}
}

func liveTitleReference(t *testing.T) {
	for _, title := range []string{"feat: add policy checks", "missing conventional title"} {
		compareLiveReference(t, Request{Tool: "pr-title", Root: t.TempDir(), Title: title}, nil)
	}
}
func liveBodyReference(t *testing.T) {
	cases := readReference[[]struct{ Name, Body, Issues string }](t, "pr-body-reference")
	for _, tc := range cases[:2] {
		t.Run(tc.Name, func(t *testing.T) {
			root := t.TempDir()
			testWrite(t, root, "issues.json", []byte(tc.Issues))
			compareLiveReference(t, Request{Tool: "pr-body", Root: root, Body: tc.Body, IssuesFile: filepath.Join(root, "issues.json"), Repository: "OpenRAE/rae"}, nil)
		})
	}
}
