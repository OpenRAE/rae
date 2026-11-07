package governance

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestProjectPositioningReference(t *testing.T) {
	runDeltaReference(t, "project-positioning", "positioning-reference")
}

func positioningFixture(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	base := readReference[deltaRepositoryReference](t, "positioning-reference").Base
	for name, text := range base {
		testWrite(t, dir, name, []byte(text))
	}
	return dir
}

func TestProjectPositioningFileBoundaries(t *testing.T) {
	for _, tc := range []struct {
		name string
		size int
		want string
	}{
		{"below", 511_999, ""},
		{"at", 512_000, ""},
		{"above", 512_001, "positioning surface exceeds the 512000-byte inspection limit"},
		{"invalid-utf8", 0, "positioning surface is not readable UTF-8 text"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			dir := positioningFixture(t)
			data := []byte(readReference[deltaRepositoryReference](t, "positioning-reference").Base["README.md"])
			if tc.size == 0 {
				data = append(data, 0xff)
			} else {
				data = append(data, []byte(strings.Repeat(" ", tc.size-len(data)))...)
			}
			testWrite(t, dir, "README.md", data)
			report, err := Check(t.Context(), Request{Tool: "project-positioning", Root: dir})
			if err != nil {
				t.Fatal(err)
			}
			checkPositioningSurface(t, report, tc.want)
		})
	}
}

func checkPositioningSurface(t *testing.T, report Report, message string) {
	t.Helper()
	if message == "" {
		if len(report.Findings) != 0 || report.ExitCode != 0 {
			t.Fatalf("valid surface findings=%v, exit=%d", report.Findings, report.ExitCode)
		}
		return
	}
	if report.ExitCode != 1 || len(report.Findings) == 0 {
		t.Fatal("invalid surface passed the check")
	}
	first := report.Findings[0]
	if first.RuleID != "project-positioning-surface" || first.Message != message || first.Path == nil || *first.Path != "README.md" {
		t.Fatalf("surface failure=%+v", first)
	}
}

func TestProjectPositioningContainedLinks(t *testing.T) {
	for _, contained := range []bool{false, true} {
		t.Run(map[bool]string{false: "outside", true: "inside"}[contained], func(t *testing.T) { checkPositioningLink(t, contained) })
	}
}

func checkPositioningLink(t *testing.T, contained bool) {
	t.Helper()
	dir := positioningFixture(t)
	targetRoot := dir
	if !contained {
		targetRoot = positioningFixture(t)
	}
	target := filepath.Join(targetRoot, "copy.md")
	data := []byte(readReference[deltaRepositoryReference](t, "positioning-reference").Base["README.md"])
	testWrite(t, targetRoot, "copy.md", data)
	if err := os.Remove(filepath.Join(dir, "README.md")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(target, filepath.Join(dir, "README.md")); err != nil {
		t.Fatal(err)
	}
	report, err := Check(t.Context(), Request{Tool: "project-positioning", Root: dir})
	if err != nil {
		t.Fatal(err)
	}
	message := "required positioning surface is missing"
	if contained {
		message = ""
	}
	checkPositioningSurface(t, report, message)
}

func TestProjectPositioningCurrentRepository(t *testing.T) {
	report, err := Check(t.Context(), Request{Tool: "project-positioning", Root: filepath.Join("..", "..", "..", "..")})
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Findings) != 0 || report.ExitCode != 0 {
		t.Fatalf("repository positioning findings=%v, exit=%d", report.Findings, report.ExitCode)
	}
}
