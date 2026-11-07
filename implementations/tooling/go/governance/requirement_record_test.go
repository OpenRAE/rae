package governance

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const testRequirement = "---\nid: GOV-001\nstatus: ACTIVE\n---\n## Traceability\n- IMPLEMENTS → SPEC `contracts/schemas/contract-v1.json`\n"

func recordReader(t *testing.T, dir string) *requirementReader {
	t.Helper()
	r, err := openRepository(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = r.root.Close() })
	return &requirementReader{repo: r}
}

func TestRequirementRecordBoundaries1204(t *testing.T) {
	for _, tc := range []struct{ name, text, message string }{
		{"missing", "", requirementReadFailure},
		{"invalid-utf8", string([]byte{0xff}), requirementReadFailure},
		{"oversize", testRequirement + strings.Repeat("x", requirementLimit), "Requirement source is not its bounded canonical file."},
		{"deep-unused", strings.Replace(testRequirement, "status: ACTIVE", "status: ACTIVE\nunused: "+strings.Repeat("[", 65)+"null"+strings.Repeat("]", 65), 1), requirementReadFailure},
		{"duplicate-nested", strings.Replace(testRequirement, "status: ACTIVE", "status: ACTIVE\nunused: {key: 1, key: 2}", 1), requirementReadFailure},
		{"alias-unused", strings.Replace(testRequirement, "status: ACTIVE", "status: ACTIVE\nunused: &x [*x]", 1), requirementReadFailure},
	} {
		t.Run(tc.name, func(t *testing.T) {
			dir := t.TempDir()
			if tc.name != "missing" {
				testWrite(t, dir, "docs/requirements/GOV-001/requirement.md", []byte(tc.text))
			}
			_, err := recordReader(t, dir).load("GOV-001")
			if err == nil || err.Error() != tc.message {
				t.Fatalf("record error=%v, want %q", err, tc.message)
			}
		})
	}
}

func TestRequirementCanonicalLocation1237(t *testing.T) {
	for _, kind := range []string{"file", "parent", "dangling", "loop"} {
		t.Run(kind, func(t *testing.T) { checkRequirementCanonicalLocation(t, kind) })
	}
}

func checkRequirementCanonicalLocation(t *testing.T, kind string) {
	t.Helper()
	dir := t.TempDir()
	name := "docs/requirements/GOV-001/requirement.md"
	testWrite(t, dir, "record.md", []byte(testRequirement))
	if err := os.MkdirAll(filepath.Dir(filepath.Join(dir, name)), 0o700); err != nil {
		t.Fatal(err)
	}
	link, target := name, "../../../record.md"
	switch kind {
	case "parent":
		if err := os.Remove(filepath.Dir(filepath.Join(dir, name))); err != nil {
			t.Fatal(err)
		}
		link, target = "docs/requirements/GOV-001", "../../records"
		testWrite(t, dir, "records/requirement.md", []byte(testRequirement))
	case "dangling":
		target = "missing"
	case "loop":
		target = "requirement.md"
	}
	if err := os.Symlink(target, filepath.Join(dir, link)); err != nil {
		t.Fatal(err)
	}
	_, err := recordReader(t, dir).load("GOV-001")
	if err == nil || err.Error() != "Requirement source is not its bounded canonical file." {
		t.Fatalf("canonical authority error=%v", err)
	}
}

func TestRequirementUIDAndSnapshot(t *testing.T) {
	dir := t.TempDir()
	testWrite(t, dir, "docs/requirements/GOV-001/requirement.md", []byte(testRequirement))
	reader := recordReader(t, dir)
	for _, uid := range []string{"GOV-1", "gov-001", "../GOV-001", "GOV-001\n"} {
		_, err := reader.load(uid)
		if err == nil || err.Error() != "Requirement identity is not a canonical UID." {
			t.Errorf("UID %q error=%v", uid, err)
		}
	}
	first, err := reader.load("GOV-001")
	if err != nil {
		t.Fatal(err)
	}
	first.links[0].identifier = "mutated"
	testWrite(t, dir, "docs/requirements/GOV-001/requirement.md", []byte("replaced after the snapshot"))
	second, err := reader.load("GOV-001")
	if err != nil {
		t.Fatal(err)
	}
	if second.uid != "GOV-001" || second.status != "ACTIVE" || len(second.links) != 1 || second.links[0].identifier != "contracts/schemas/contract-v1.json" {
		t.Fatalf("snapshot changed: %+v", second)
	}
	if !canonicalUID("GOV-٠٠١") {
		t.Fatal("reference Unicode decimal UID was refused")
	}
}
