package governance

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

func TestIdentityRejectedPrefixes(t *testing.T) {
	prefix := strings.Repeat("xa"+"ces-", 100_000)
	text := prefix + "_a" + "ces"
	for _, escaped := range []bool{false, true} {
		matches := identityMatches(text, escaped)
		if len(matches) != 1 || matches[0][0] != len(prefix)+1 || matches[0][1] != len(text) {
			t.Fatalf("rejected prefix changed match boundaries: %v", matches)
		}
	}
}

func BenchmarkIdentityRejectedPrefixes(b *testing.B) {
	for _, count := range []int{1_024, 16_384, 262_144} {
		b.Run(strconv.Itoa(count), func(b *testing.B) {
			text := strings.Repeat("xa"+"ces-", count)
			b.SetBytes(int64(len(text)))
			b.ResetTimer()
			for b.Loop() {
				if len(identityMatches(text, true)) != 0 {
					b.Fatal("invalid prefix accepted")
				}
			}
		})
	}
}

func identityFixture(t *testing.T) string {
	t.Helper()
	dir := deltaFixture(t, "identity-reference", "valid")
	testGit(t, dir, "init", "-q")
	testGit(t, dir, "add", "-A")
	return dir
}

func TestIdentityManifestBoundaries(t *testing.T) {
	base := readReference[deltaRepositoryReference](t, "identity-reference").Base[identityManifest]
	for _, tc := range []struct {
		name    string
		data    []byte
		invalid bool
	}{
		{"below", []byte(base + strings.Repeat(" ", identityManifestLimit-1-len(base))), false},
		{"at", []byte(base + strings.Repeat(" ", identityManifestLimit-len(base))), false},
		{"above", []byte(base + strings.Repeat(" ", identityManifestLimit+1-len(base))), true},
		{"invalid-utf8", append([]byte(base), 0xff), true},
		{"duplicate-nested", []byte(strings.TrimSpace(base[:len(base)-2]) + `,"extra":{"x":1,"x":2}}`), true},
		{"large-integer", []byte(strings.TrimSpace(base[:len(base)-2]) + `,"extra":` + strings.Repeat("1", 4301) + `}`), true},
		{"depth", []byte(`{"extra":` + strings.Repeat("[", governanceJSONDepth+1) + `0` + strings.Repeat("]", governanceJSONDepth+1) + `}`), true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			dir := identityFixture(t)
			testWrite(t, dir, identityManifest, tc.data)
			report, err := Check(t.Context(), Request{Tool: "identity-cutover", Root: dir})
			if err != nil {
				t.Fatal(err)
			}
			if tc.invalid {
				if report.ExitCode != 1 || len(report.Findings) != 1 || report.Findings[0].RuleID != "identity-cutover-manifest" {
					t.Fatalf("invalid manifest accepted: %+v", report)
				}
			} else if report.ExitCode != 0 || len(report.Findings) != 0 {
				t.Fatalf("valid manifest rejected: %+v", report)
			}
		})
	}
}

func TestIdentityTrackedFiles(t *testing.T) {
	for _, kind := range []string{"binary", "missing", "outside", "inside", "unicode-name", "newline-name"} {
		t.Run(kind, func(t *testing.T) { checkIdentityTrackedFile(t, kind) })
	}
}

func checkIdentityTrackedFile(t *testing.T, kind string) {
	t.Helper()
	dir := identityFixture(t)
	name := "live.txt"
	rule := "identity-cutover-live-token"
	switch kind {
	case "unicode-name":
		name = "visible-λ.txt"
	case "newline-name":
		name = "visible\nname.txt"
	}
	testWrite(t, dir, name, []byte{0xff, '\n', 'a', 'c', 'e', 's'})
	testGit(t, dir, "add", "--", name)
	switch kind {
	case "outside", "inside":
		targetRoot := dir
		if kind == "outside" {
			targetRoot = t.TempDir()
			rule = "identity-cutover-tracked-tree"
		}
		testWrite(t, targetRoot, "target.txt", []byte{'a', 'c', 'e', 's'})
		if err := os.Remove(filepath.Join(dir, name)); err != nil {
			t.Fatal(err)
		}
		if err := os.Symlink(filepath.Join(targetRoot, "target.txt"), filepath.Join(dir, name)); err != nil {
			t.Fatal(err)
		}
	case "missing":
		if err := os.Remove(filepath.Join(dir, name)); err != nil {
			t.Fatal(err)
		}
		rule = "identity-cutover-tracked-tree"
	}
	report, err := Check(t.Context(), Request{Tool: "identity-cutover", Root: dir})
	if err != nil {
		t.Fatal(err)
	}
	if report.ExitCode != 1 || len(report.Findings) != 1 || report.Findings[0].RuleID != rule || report.Findings[0].Path == nil || *report.Findings[0].Path != name {
		t.Fatalf("tracked %s findings=%+v", kind, report.Findings)
	}
}

func TestIdentityGitUnavailable(t *testing.T) {
	dir := deltaFixture(t, "identity-reference", "valid")
	report, err := Check(t.Context(), Request{Tool: "identity-cutover", Root: dir})
	if err != nil {
		t.Fatal(err)
	}
	if report.ExitCode != 1 || len(report.Findings) != 1 || report.Findings[0].RuleID != "identity-cutover-tracked-tree" {
		t.Fatalf("missing Git tree accepted: %+v", report)
	}
}

func TestIdentityCurrentRepository(t *testing.T) {
	report, err := Check(t.Context(), Request{Tool: "identity-cutover", Root: filepath.Join("..", "..", "..", "..")})
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Findings) != 0 || report.ExitCode != 0 {
		t.Fatalf("repository identity findings=%+v, exit=%d", report.Findings, report.ExitCode)
	}
}
