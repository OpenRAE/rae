package module

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"io"
	"testing"
)

func archiveForTest(t *testing.T, headers []*tar.Header) []byte {
	t.Helper()
	var output bytes.Buffer
	zip := gzip.NewWriter(&output)
	writer := tar.NewWriter(zip)
	for _, header := range headers {
		if err := writer.WriteHeader(header); err != nil {
			t.Fatal(err)
		}
		if header.Size > 0 {
			if _, err := writer.Write(bytes.Repeat([]byte{'x'}, int(header.Size))); err != nil {
				t.Fatal(err)
			}
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	if err := zip.Close(); err != nil {
		t.Fatal(err)
	}
	return output.Bytes()
}

func TestArchiveInspectionBoundsAndPaths(t *testing.T) {
	for _, test := range []struct {
		name    string
		headers []*tar.Header
		mutate  func(*resourceLimits)
	}{
		{name: "traversal", headers: []*tar.Header{{Name: "../escape", Mode: 0600}}},
		{name: "absolute", headers: []*tar.Header{{Name: "/escape", Mode: 0600}}},
		{name: "drive", headers: []*tar.Header{{Name: "C:/escape", Mode: 0600}}},
		{name: "backslash", headers: []*tar.Header{{Name: "a\\b", Mode: 0600}}},
		{name: "noncanonical", headers: []*tar.Header{{Name: "a//b", Mode: 0600}}},
		{name: "symlink", headers: []*tar.Header{{Name: "link", Typeflag: tar.TypeSymlink, Linkname: "/tmp"}}},
		{name: "fifo", headers: []*tar.Header{{Name: "fifo", Typeflag: tar.TypeFifo}}},
		{name: "block-device", headers: []*tar.Header{{Name: "device", Typeflag: tar.TypeBlock}}},
		{name: "character-device", headers: []*tar.Header{{Name: "device", Typeflag: tar.TypeChar}}},
		{name: "hardlink", headers: []*tar.Header{{Name: "link", Typeflag: tar.TypeLink, Linkname: "root"}}},
		{name: "metadata", headers: []*tar.Header{{Name: cacheManifestName, Mode: 0600}}},
		{name: "duplicate", headers: []*tar.Header{{Name: "root", Mode: 0600}, {Name: "root", Mode: 0600}}},
		{name: "parent-file", headers: []*tar.Header{{Name: "a/b", Mode: 0600}, {Name: "a", Mode: 0600}}},
		{name: "root-file", headers: []*tar.Header{{Name: ".", Mode: 0600}}},
		{name: "member-count", headers: []*tar.Header{{Name: "a"}, {Name: "b"}}, mutate: func(l *resourceLimits) { l.members = 1 }},
		{name: "member-size", headers: []*tar.Header{{Name: "a", Size: 2}}, mutate: func(l *resourceLimits) { l.memberBytes = 1 }},
		{name: "total-size", headers: []*tar.Header{{Name: "a", Size: 2}, {Name: "b", Size: 2}}, mutate: func(l *resourceLimits) { l.totalBytes = 3 }},
		{name: "depth", headers: []*tar.Header{{Name: "a/b"}}, mutate: func(l *resourceLimits) { l.depth = 1 }},
		{name: "tar-stream", headers: []*tar.Header{{Name: "a"}}, mutate: func(l *resourceLimits) { l.tarBytes = 100 }},
		{name: "gzip-ratio", headers: []*tar.Header{{Name: "a", Size: 1024}}, mutate: func(l *resourceLimits) { l.expansionRatio = 1 }},
	} {
		t.Run(test.name, func(t *testing.T) {
			limits := defaultResourceLimits()
			if test.mutate != nil {
				test.mutate(&limits)
			}
			raw := archiveForTest(t, test.headers)
			if _, err := inspectArchive(raw, "sha256:test", "root", limits); err == nil {
				t.Fatal("unsafe archive accepted")
			}
		})
	}
	valid := archiveForTest(t, []*tar.Header{{Name: "a/file", Size: 3, Mode: 04777}, {Name: "empty", Mode: 0600}, {Name: "a/", Typeflag: tar.TypeDir}})
	inventory, err := inspectArchive(valid, "sha256:test", "a/file", defaultResourceLimits())
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(inventory.files["a/file"], []byte("xxx")) || len(inventory.entries) != 4 {
		t.Fatal("inventory lost file bytes or implicit directories")
	}
	for _, entry := range inventory.entries {
		if entry.Path == "a/file" && entry.Mode != 0755 {
			t.Fatal("archive mode was not filtered")
		}
	}
	valid[len(valid)-5] ^= 1
	if _, err = inspectArchive(valid, "sha256:test", "a/file", defaultResourceLimits()); err == nil {
		t.Fatal("gzip trailer corruption accepted")
	}
}

func TestArchiveExactLimitsAndGzipPadding(t *testing.T) {
	raw := archiveForTest(t, []*tar.Header{{Name: "a/b", Size: 3, Mode: 0600}})
	original, err := inspectArchive(raw, "sha256:test", "a/b", defaultResourceLimits())
	if err != nil {
		t.Fatal(err)
	}
	compressed := bytes.NewReader(raw)
	zip, err := gzip.NewReader(compressed)
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := io.ReadAll(zip)
	if err != nil {
		t.Fatal(err)
	}
	if err = zip.Close(); err != nil {
		t.Fatal(err)
	}
	for _, row := range []struct {
		name  string
		limit int64
		set   func(*resourceLimits, int64)
	}{
		{"compressed", int64(len(raw)), func(l *resourceLimits, n int64) { l.bundleBytes = n }},
		{"decoded", int64(len(decoded)), func(l *resourceLimits, n int64) { l.tarBytes = n }},
		{"metadata", int64(len(original.metadata)), func(l *resourceLimits, n int64) { l.metadataBytes = n }},
		{"member", 3, func(l *resourceLimits, n int64) { l.memberBytes = n }},
		{"total", 3, func(l *resourceLimits, n int64) { l.totalBytes = n }},
		{"implicit-entries", 2, func(l *resourceLimits, n int64) { l.members = int(n) }},
		{"path-depth", 2, func(l *resourceLimits, n int64) { l.depth = int(n) }},
	} {
		t.Run(row.name, func(t *testing.T) {
			limits := defaultResourceLimits()
			row.set(&limits, row.limit)
			if _, boundaryErr := inspectArchive(raw, "sha256:test", "a/b", limits); boundaryErr != nil {
				t.Fatalf("exact boundary rejected: %v", boundaryErr)
			}
			row.set(&limits, row.limit-1)
			if _, boundaryErr := inspectArchive(raw, "sha256:test", "a/b", limits); boundaryErr == nil {
				t.Fatal("over-limit inventory admitted")
			}
		})
	}
}

func TestArchiveGzipSequenceValidation(t *testing.T) {
	raw := archiveForTest(t, []*tar.Header{{Name: "a/b", Size: 3, Mode: 0600}})
	var err error
	padded := append(bytes.Clone(raw), make([]byte, 20)...)
	if _, err = inspectArchive(padded, "sha256:test", "a/b", defaultResourceLimits()); err != nil {
		t.Fatalf("reference gzip padding rejected: %v", err)
	}
	concatenated := append(bytes.Clone(padded), raw...)
	if _, err = inspectArchive(concatenated, "sha256:test", "a/b", defaultResourceLimits()); err != nil {
		t.Fatalf("reference gzip member sequence rejected: %v", err)
	}
	for _, trailing := range [][]byte{[]byte("invalid trailing stream"), raw[:len(raw)-2]} {
		damaged := append(bytes.Clone(padded), trailing...)
		if _, err = inspectArchive(damaged, "sha256:test", "a/b", defaultResourceLimits()); err == nil {
			t.Fatal("invalid trailing gzip member was ignored")
		}
	}
}
