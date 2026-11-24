package corpus

import (
	"archive/zip"
	"bytes"
	"fmt"
	"io/fs"
	"strings"
	"testing"
	"testing/fstest"
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

func TestRejectsCorruptEncodedPieces(t *testing.T) {
	for _, content := range []string{"zz\n", "1\n", strings.Repeat("0", 262146)} {
		source := fstest.MapFS{"data/0000": {Data: []byte(content)}}
		if _, err := openPieces(source); err == nil {
			t.Fatal("accepted invalid encoded piece")
		}
	}
	source := fstest.MapFS{}
	for index := range 65 {
		source[fmt.Sprintf("data/%04d", index)] = &fstest.MapFile{Data: []byte("00\n")}
	}
	if _, err := openPieces(source); err == nil {
		t.Fatal("accepted too many pieces")
	}
}
