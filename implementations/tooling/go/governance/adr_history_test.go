package governance

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

const testADRText = "# ADR-001: Example\n\n## Status\n\naccepted\n\n## Date\n\n2026-04-05\n\n## Context\n\nThe decision body.\n"
const testADRAmendment = "\n## Amendments\n\n| Date | Commit/PR | Summary |\n|------|-----------|---------|\n| 2026-10-12 | abc1234 | rewrote the body |\n"
const testADROriginal = adrDirectory + "/adr-001-example.md"
const testADRRename = adrDirectory + "/adr-001-renamed-example.md"

func testWrite(t *testing.T, dir, name string, data []byte) {
	t.Helper()
	if !repositoryPath(name) {
		t.Fatal("unsafe fixture filename")
	}
	root, openErr := os.OpenRoot(dir)
	if openErr != nil {
		t.Fatal(openErr)
	}
	defer func() { _ = root.Close() }()
	if err := root.MkdirAll(filepath.Dir(name), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := root.WriteFile(name, data, 0o600); err != nil {
		t.Fatal(err)
	}
}

func testGit(t *testing.T, dir string, args ...string) []byte {
	t.Helper()
	cmd := exec.CommandContext(t.Context(), "git", args...) // #nosec G204 -- Test callers supply fixed Git operations and local fixture paths.
	cmd.Dir = dir
	data, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v: %s", args, err, data)
	}
	return data
}

func testGitRepository(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	testGit(t, dir, "init", "-q")
	testGit(t, dir, "config", "user.email", "test@example.invalid")
	testGit(t, dir, "config", "user.name", "Test")
	testGit(t, dir, "config", "commit.gpgsign", "false")
	return dir
}

func testADRWrite(t *testing.T, dir, name, text, recorded string) {
	t.Helper()
	testWrite(t, dir, name, []byte(text))
	if recorded == "" {
		recorded = name
	}
	refs := []map[string]string{}
	for _, ref := range amendmentRefs(text) {
		refs = append(refs, map[string]string{"ref": ref})
	}
	manifest := map[string]any{"hash_algorithm": "sha256", "adrs": []map[string]any{{"id": "ADR-001", "path": recorded, "pin": adrHash(text), "amendments": refs}}}
	data, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	testWrite(t, dir, adrManifest, data)
}

func testCommit(t *testing.T, dir string) {
	t.Helper()
	testGit(t, dir, "add", "-A")
	testGit(t, dir, "commit", "-q", "-m", "test fixture")
}

func TestADRHistory1567(t *testing.T) {
	for _, staged := range []bool{false, true} {
		for _, recorded := range []string{testADROriginal, adrDirectory + "/./adr-001-example.md", "./" + testADROriginal, "docs//decisions/adrs/adr-001-example.md", "docs/adr-link.md", "docs/decisions/adrs-link/adr-001-example.md", "docs/adrs-chain/adr-001-example.md"} {
			for _, change := range []string{"unrecorded", "unchanged", "amended"} {
				t.Run(fmt.Sprintf("staged=%t/%s/%s", staged, recorded, change), func(t *testing.T) {
					exerciseADRHistory(t, staged, recorded, change)
				})
			}
		}
	}
}

func TestADRUnresolvedRevision1567(t *testing.T) {
	dir := testGitRepository(t)
	testADRWrite(t, dir, testADROriginal, testADRText, "")
	testCommit(t, dir)
	for _, rev := range []string{"no-such-rev", strings.Repeat("0", 40), "--all", "HEAD^{tree}", "HEAD\n--all", "HEAD:path", "HEAD;whoami"} {
		t.Run(rev, func(t *testing.T) {
			report, err := Check(t.Context(), Request{Tool: "adr-immutability", Root: dir, BaseRevision: rev})
			if err != nil {
				t.Fatal(err)
			}
			if len(report.Findings) != 1 || report.Findings[0].RuleID != "adr-base-rev-unresolved" || report.Findings[0].Path != nil {
				t.Fatalf("unresolved revision findings=%v", report.Findings)
			}
		})
	}
}

func TestADRBaseWithoutManifest1567(t *testing.T) {
	for _, manifest := range []string{"", "adrs: [\n", "- not a mapping\n", "hash_algorithm: sha256\nadrs: {}\n", "adrs:\n- not-an-entry\n- {id: ADR-001}\n", "date: 2026-99-99\n", "value: !!bool unknown\n", "value: !!int ''\n"} {
		t.Run(manifest, func(t *testing.T) {
			dir := testGitRepository(t)
			testWrite(t, dir, testADROriginal, []byte(testADRText))
			if manifest != "" {
				testWrite(t, dir, adrManifest, []byte(manifest))
			}
			testCommit(t, dir)
			testADRWrite(t, dir, testADROriginal, testADRText+"changed\n", "")
			report, err := Check(t.Context(), Request{Tool: "adr-immutability", Root: dir, BaseRevision: "HEAD"})
			if err != nil {
				t.Fatal(err)
			}
			if len(report.Findings) != 1 || report.Findings[0].RuleID != "adr-amendment-unrecorded" {
				t.Fatalf("base fallback findings=%v", report.Findings)
			}
		})
	}
}

func TestADRHistoricalBlobBytes1567(t *testing.T) {
	dir := testGitRepository(t)
	for name, data := range map[string][]byte{"empty": {}, "newline": []byte("text\r\nwith a final newline\n"), "invalid-utf8": {'x', 0xff, '\n'}} {
		testWrite(t, dir, name, data)
	}
	for name, target := range map[string]string{"outside": "/outside.md", "traversal": "../../../outside.md", "dangling": "missing.md", "loop": "loop"} {
		if err := os.Symlink(target, filepath.Join(dir, name)); err != nil {
			t.Fatal(err)
		}
	}
	testCommit(t, dir)
	r, err := openRepository(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = r.root.Close() })
	for name, want := range map[string][]byte{"empty": {}, "newline": []byte("text\r\nwith a final newline\n"), "invalid-utf8": {'x', 0xff, '\n'}} {
		got, err := gitBlob(context.Background(), r, "HEAD:"+name, true)
		if err != nil || got == nil || string(got) != string(want) {
			t.Errorf("blob(%s)=%x,%v; want %x", name, got, err, want)
		}
	}
	for _, name := range []string{"outside", "traversal", "dangling", "loop", "missing"} {
		got, err := gitBlob(context.Background(), r, "HEAD:"+name, true)
		if err != nil || got != nil {
			t.Errorf("blob(%s)=%x,%v; want no blob", name, got, err)
		}
	}
}

func TestADRRejectDistinctHardlink(t *testing.T) {
	dir := t.TempDir()
	testADRWrite(t, dir, testADROriginal, testADRText, "same-inode.md")
	if err := os.Link(filepath.Join(dir, testADROriginal), filepath.Join(dir, "same-inode.md")); err != nil {
		t.Fatal(err)
	}
	report, err := Check(t.Context(), Request{Tool: "adr-immutability", Root: dir})
	if err != nil {
		t.Fatal(err)
	}
	want := []Finding{finding("adr-manifest-malformed", "ADR-001: manifest path does not resolve to the ADR file on disk", "same-inode.md")}
	if diff := cmp.Diff(want, report.Findings); diff != "" {
		t.Errorf("path identity (-want +got):\n%s", diff)
	}
}

func TestADRCurrentAlias1567(t *testing.T) {
	dir := testGitRepository(t)
	testADRWrite(t, dir, "real.md", testADRText, "")
	if err := os.MkdirAll(filepath.Join(dir, adrDirectory), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("../../../real.md", filepath.Join(dir, testADROriginal)); err != nil {
		t.Fatal(err)
	}
	testCommit(t, dir)
	for _, staged := range []bool{false, true} {
		report, err := Check(t.Context(), Request{Tool: "adr-immutability", Root: dir, BaseRevision: "HEAD", Staged: staged})
		if err != nil {
			t.Fatal(err)
		}
		if len(report.Findings) != 0 {
			t.Errorf("staged=%t: unchanged alias findings=%v", staged, report.Findings)
		}
	}
}

func exerciseADRHistory(t *testing.T, staged bool, recorded, change string) {
	t.Helper()
	dir := testGitRepository(t)
	testADRWrite(t, dir, testADROriginal, testADRText, recorded)
	links := map[string]string{"docs/adr-link.md": "decisions/adrs/adr-001-example.md", "docs/decisions/adrs-link": "adrs", "docs/adrs-chain": "decisions/adrs-link"}
	for name, target := range links {
		if err := os.Symlink(target, filepath.Join(dir, name)); err != nil {
			t.Fatal(err)
		}
	}
	testCommit(t, dir)
	testGit(t, dir, "mv", testADROriginal, testADRRename)
	text := testADRText
	if change != "unchanged" {
		text = strings.ReplaceAll(text, "The decision body.", "A materially rewritten decision body.")
	}
	if change == "amended" {
		text += testADRAmendment
	}
	testADRWrite(t, dir, testADRRename, text, "")
	for name := range links {
		if err := os.Remove(filepath.Join(dir, name)); err != nil {
			t.Fatal(err)
		}
	}
	if staged {
		testGit(t, dir, "add", "-A")
	}
	report, err := Check(t.Context(), Request{Tool: "adr-immutability", Root: dir, BaseRevision: "HEAD", Staged: staged})
	if err != nil {
		t.Fatal(err)
	}
	want := []Finding{}
	if change == "unrecorded" {
		want = append(want, finding("adr-amendment-unrecorded", "ADR-001: accepted ADR content changed without a new ## Amendments record; add an amendment (and update its pin) or supersede it with a new ADR", testADRRename))
	}
	if diff := cmp.Diff(want, report.Findings); diff != "" {
		t.Errorf("history findings (-want +got):\n%s", diff)
	}
}
