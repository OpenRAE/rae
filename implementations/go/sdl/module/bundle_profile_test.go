package module

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"io"
	"testing"
)

func TestPublishedBundleMatchesPythonByteProfile(t *testing.T) {
	fixture := readModuleReference(t)

	actual, err := buildBundle(map[string][]byte{fixture.Root: fixture.Source}, defaultResourceLimits())
	if err != nil {
		t.Fatal(err)
	}
	decode := func(data []byte) []byte {
		t.Helper()
		reader, err := gzip.NewReader(bytes.NewReader(data))
		if err != nil {
			t.Fatal(err)
		}
		defer func() { _ = reader.Close() }()
		value, err := io.ReadAll(reader)
		if err != nil {
			t.Fatal(err)
		}
		return value
	}
	got, want := decode(actual), decode(fixture.Artifact.Bundle)
	if !bytes.Equal(got, want) {
		for index := range min(len(got), len(want)) {
			if got[index] != want[index] {
				t.Fatalf("tar byte profile differs at %d: %d / %d", index, got[index], want[index])
			}
		}
		t.Fatalf("tar lengths differ: %d / %d", len(got), len(want))
	}
	if !bytes.Equal(actual, fixture.Artifact.Bundle) {
		t.Fatalf("compressed byte profile differs: %d / %d bytes", len(actual), len(fixture.Artifact.Bundle))
	}
}

func TestPublisherPathAndWindowByteProfiles(t *testing.T) {
	raw, err := readCompressedFixture("testdata/python-bundles.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []struct {
			Name   string            `json:"name"`
			Files  map[string][]byte `json:"files"`
			Bundle []byte            `json:"bundle"`
		} `json:"cases"`
	}
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	for _, row := range fixture.Cases {
		t.Run(row.Name, func(t *testing.T) {
			bundle, err := buildBundle(row.Files, defaultResourceLimits())
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(bundle, row.Bundle) {
				t.Fatalf("publisher byte profile differs: %d / %d", len(bundle), len(row.Bundle))
			}
		})
	}
}
