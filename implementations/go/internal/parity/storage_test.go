package parity

import (
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"io/fs"
	"strconv"
	"strings"
	"testing"
	"testing/fstest"
)

func compressed(content []byte) []byte {
	var buffer bytes.Buffer
	writer := gzip.NewWriter(&buffer)
	if _, err := writer.Write(content); err != nil {
		panic(err)
	}
	if err := writer.Close(); err != nil {
		panic(err)
	}
	return buffer.Bytes()
}

func blobFS(content []byte) (fstest.MapFS, string) {
	sum := sha256.Sum256(content)
	identity := hex.EncodeToString(sum[:])
	return fstest.MapFS{"inputs/" + identity: {Data: compressed(content)}}, identity
}

func TestBlobStorageReassemblesOpaquePieces(t *testing.T) {
	content := []byte("exact bytes\x00 without a final newline  ")
	fsys, identity := blobFS(content)
	encoded := fsys["inputs/"+identity].Data
	fsys["inputs/"+identity].Data = []byte(`{"parts": 2}`)
	for number, piece := range [][]byte{encoded[:7], encoded[7:]} {
		fsys["pieces/"+identity+"/"+strconv.Itoa(number)] = &fstest.MapFile{Data: append([]byte{0}, piece...)}
	}
	got, err := readBlob(fsys, identity)
	if err != nil || !bytes.Equal(got, content) {
		t.Fatalf("readBlob() = %q, %v; want %q, nil", got, err, content)
	}
	delete(fsys, "pieces/"+identity+"/1")
	if _, err := readBlob(fsys, identity); err == nil {
		t.Error("readBlob(missing piece) error = nil")
	}
}

func TestBlobStorageRejectsInvalidEncodings(t *testing.T) {
	for _, content := range [][]byte{
		[]byte(`{"parts": 0}`), []byte(`{"parts": 513}`), []byte(`{"parts": -1}`),
		[]byte(`{"parts": true}`), []byte(`{"parts": 1, "other": 1}`), []byte(`{"parts": 1} {}`),
		[]byte("not gzip"), {0x1f, 0x8b, 0}, bytes.Repeat([]byte{0}, pieceLimit+1),
	} {
		fsys, identity := blobFS([]byte(input))
		fsys["inputs/"+identity].Data = content
		fsys["pieces/"+identity+"/0"] = &fstest.MapFile{Data: []byte("missing marker")}
		if _, err := readBlob(fsys, identity); err == nil {
			t.Errorf("readBlob(%q) error = nil", content[:min(len(content), 40)])
		}
	}
	fsys, identity := blobFS([]byte(input))
	encoded := fsys["inputs/"+identity].Data
	fsys["inputs/"+identity].Data = encoded[:len(encoded)-1]
	if _, err := readBlob(fsys, identity); err == nil {
		t.Error("readBlob(truncated gzip) error = nil")
	}
	observed := &observedFS{FS: fsys}
	if _, err := readBlob(observed, "../escape"); err == nil || len(observed.opened) != 0 {
		t.Error("readBlob(invalid identity) must reject before opening any file")
	}
}

func TestReadLimitedPreservesTheBoundaryAndReadErrors(t *testing.T) {
	fsys := fstest.MapFS{"file": {Data: []byte("abcd")}}
	for _, limit := range []int64{4, 5} {
		got, err := readLimited(fsys, "file", limit)
		if err != nil || string(got) != "abcd" {
			t.Fatalf("readLimited(%d) = %q, %v", limit, got, err)
		}
	}
	if _, err := readLimited(fsys, "file", 3); err == nil {
		t.Error("readLimited(oversized file) error = nil")
	}
	if _, err := readLimited(fsys, "absent", 4); !strings.Contains(err.Error(), "absent") {
		t.Errorf("readLimited(absent) = %v", err)
	}
	if _, err := readLimited(fstest.MapFS{"dir": {Mode: fs.ModeDir}}, "dir", 4); err == nil {
		t.Error("readLimited(directory) error = nil")
	}
}

func TestLoadReadsReferencedDocumentsAndRejectsInvalidReferences(t *testing.T) {
	fsys := corpus([]byte(input))
	content := fsys[caseName].Data
	blobs, identity := blobFS(content)
	fsys["inputs/"+identity] = blobs["inputs/"+identity]
	fsys[caseName].Data = []byte(`{"document_ref": "` + identity + `"}`)
	cases, err := Load(fsys)
	if err != nil || len(cases) != 1 || string(cases[0].Files["input.yaml"]) != input {
		t.Fatalf("Load(referenced case) = %v, %v", cases, err)
	}
	for _, reference := range []string{`null`, `true`, `"../escape"`, `"` + strings.Repeat("0", 64) + `"`} {
		fsys[caseName].Data = []byte(`{"document_ref": ` + reference + `}`)
		if _, err := Load(fsys); err == nil {
			t.Errorf("Load(reference %s) error = nil", reference)
		}
	}
}
