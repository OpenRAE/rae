package governance

import (
	"crypto/sha256"
	"fmt"
	"path/filepath"
	"strings"
	"testing"
)

func TestVocabularyRemoteLocalRefusal(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "missing-snapshot")
	for _, tool := range []string{attackVocabularyCheck, atlasVocabularyCheck, nistVocabularyCheck, autonomousVocabularyCheck} {
		t.Run(tool, func(t *testing.T) {
			report, err := Check(t.Context(), Request{Tool: tool, Root: "../../../..", VerifyRemote: true, LocalInput: missing, ActivityStreamsLocalInput: missing, FIPALocalInput: missing})
			if err != nil {
				t.Fatal(err)
			}
			if report.ExitCode != 1 || len(report.Findings) != 1 || !strings.Contains(report.Findings[0].Message, "local input failed locked identity validation") {
				t.Fatalf("explicit input did not refuse locally: %+v", report)
			}
		})
	}
}

func TestVocabularyRemoteComparisons(t *testing.T) {
	for _, tc := range readReference[[]extractionReference](t, "vocabulary-extraction-reference") {
		if tc.Name != "stix-valid" && tc.Name != "atlas-valid" && tc.Name != "nist-xml-utf8-bom" {
			continue
		}
		t.Run(tc.Name, func(t *testing.T) { checkVocabularyRemoteComparison(t, tc) })
	}
}
func checkVocabularyRemoteComparison(t *testing.T, tc extractionReference) {
	t.Helper()

	rows, err := extractionRows(tc)
	if err != nil {
		t.Fatal(err)
	}
	source := newMapping()
	source.set("tactics", rows)
	source.set("categories", rows)
	hashed := tc.Data
	if tc.Label == nistVocabulary {
		hashed, err = canonicalJSON(schemaTransport(rows), true)
		if err != nil {
			t.Fatal(err)
		}
	}
	source.set(sourceDigestField, "sha256:"+fmt.Sprintf("%x", sha256.Sum256(hashed)))
	profile := vocabularyProfile{label: tc.Label, path: "snapshot.json"}
	findings, err := compareVocabularyBytes(profile, source, tc.Data)
	if err != nil || len(findings) != 0 {
		t.Fatalf("matching snapshot=%v, %v", findings, err)
	}
	source.set(sourceDigestField, "sha256:changed")
	source.set("tactics", []any{})
	source.set("categories", []any{})
	findings, err = compareVocabularyBytes(profile, source, tc.Data)
	if err != nil || len(findings) != 2 {
		t.Fatalf("changed identity/rows=%v, %v", findings, err)
	}
}
