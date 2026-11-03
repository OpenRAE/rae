package corpus

import (
	"archive/zip"
	"bytes"
	"io/fs"
	"testing"
)

func TestPackagedCorpus(t *testing.T) {
	source, err := Open()
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"schema-publication-manifest.json", "schemas/profiles/raes-semantic-invariants-v1.json", "provenance/THIRD_PARTY_NOTICES.md", "profiles/backend/provisioning-only.json"} {
		data, err := fs.ReadFile(source, name)
		if err != nil || len(data) == 0 {
			t.Errorf("ReadFile(%s) length = %d, error = %v", name, len(data), err)
		}
	}
	if _, err := source.Open("../contracts/README.md"); err == nil {
		t.Error("Open(traversal) = nil, want refusal")
	}
}

func TestRejectsCorruptArchives(t *testing.T) {
	if _, err := openArchive([]byte("invalid archive")); err == nil {
		t.Error("openArchive(corrupt) = nil, want refusal")
	}
	for _, names := range [][]string{nil, {"../outside"}, {"same", "same"}} {
		var data bytes.Buffer
		archive := zip.NewWriter(&data)
		for _, name := range names {
			file, err := archive.Create(name)
			if err != nil {
				t.Fatal(err)
			}
			if _, err := file.Write([]byte("content")); err != nil {
				t.Fatal(err)
			}
		}
		if err := archive.Close(); err != nil {
			t.Fatal(err)
		}
		if _, err := openArchive(data.Bytes()); err == nil {
			t.Errorf("openArchive(%v) = nil, want refusal", names)
		}
	}
}
