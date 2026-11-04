package admission

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"maps"
	"strconv"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestAssociatedSnapshotBindsVersionAndDigest(t *testing.T) {
	e := boundTestOwner(t)
	parent, err := e.low.Validate("sdl-authoring-input-v1", []byte(`{"name":"scenario","version":"1.0.0"}`), ingress.Limits{MaxBytes: 1024, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatal(err)
	}
	digest := "sha256:" + strings.Repeat("a", 64)
	for _, test := range []struct {
		version, ownerDigest string
		valid                bool
	}{
		{"1.0.0", digest, true},
		{"other", digest, false},
		{"1.0.0", "", false},
		{"1.0.0", "sha256:" + strings.Repeat("b", 64), false},
	} {
		manifest := map[string]any{"parent_ref": map[string]any{"ref_kind": kindScenarioSnapshot, "ref_id": "scenario", "ref_version": test.version, "ref_digest": digest}}
		if err := associatedParent(manifest, parent, test.ownerDigest); (err == nil) != test.valid {
			t.Errorf("snapshot version %q and owner digest %q: %v", test.version, test.ownerDigest, err)
		}
	}
}

type artifactBudgetProbe struct{ reads *int }

func (p artifactBudgetProbe) Read([]byte) (int, error) {
	*p.reads++
	return 0, errors.New("unavailable artifact")
}

func TestAssociatedBudgetsCheckBeforeReading(t *testing.T) {
	for _, test := range []struct {
		name  string
		count int
		size  int64
		extra bool
		read  bool
	}{
		{"exact-count", 1024, 0, false, true},
		{"excess-count", 1025, 0, false, false},
		{"empty-payload", 1, 0, false, true},
		{"negative-size", 1, -1, false, false},
		{"exact-payload-size", 1, 1073741824, false, true},
		{"excess-payload-size", 1, 1073741825, false, false},
		{"exact-total-size", 4, 1073741824, false, true},
		{"excess-total-size", 4, 1073741824, true, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			artifacts, readers := map[string]any{}, map[string]io.Reader{}
			reads := 0
			for index := range test.count {
				id := fmt.Sprintf("artifact-%d", index)
				artifacts[id] = map[string]any{"size_bytes": json.Number(strconv.FormatInt(test.size, 10)), "checksum": map[string]any{"algorithm": "sha256"}}
				readers[id] = artifactBudgetProbe{&reads}
			}
			if test.extra {
				artifacts["extra"] = map[string]any{"size_bytes": json.Number("1")}
				readers["extra"] = artifactBudgetProbe{&reads}
			}
			// A probe refuses the actual read. This checks admission of the declared
			// budget without allocating or hashing gigabytes of artificial content.
			if err := associatedBytes(artifacts, readers); err == nil {
				t.Error("admitted unavailable artifact bytes")
			}
			if (reads > 0) != test.read {
				t.Errorf("reader calls = %d, want read allowed %v", reads, test.read)
			}
		})
	}
}

func associatedBoundaryDescriptor() map[string]any {
	return map[string]any{"artifact_id": "first", "role": "other", "uri": "urn:example:payload", "media_type": "text/plain", "size_bytes": int64(0), "created_at": "2026-01-01T00:00:00Z", "source": "test", "sensitivity": "public", "checksum": map[string]any{"algorithm": "sha256", "value": strings.Repeat("a", 64)}}
}

func TestAssociatedDescriptorDefaultsDoNotCreateDistinctArtifacts(t *testing.T) {
	first := associatedBoundaryDescriptor()
	second := maps.Clone(first)
	second["artifact_id"] = "second"
	second["satisfies_refs"] = []any{}
	descriptors, locators := map[string]bool{}, map[string]string{}
	if err := associatedDescriptor(first, descriptors, locators); err != nil {
		t.Fatal(err)
	}
	if err := associatedDescriptor(second, descriptors, locators); err == nil {
		t.Error("defaulted reference list bypassed duplicate artifact detection")
	}
}

func TestAssociatedLocatorCannotClaimDifferentBytes(t *testing.T) {
	for _, uri := range []string{"urn:example:payload", "urn:example:other"} {
		first := associatedBoundaryDescriptor()
		second := maps.Clone(first)
		second["artifact_id"], second["size_bytes"], second["uri"] = "second", int64(1), uri
		descriptors, locators := map[string]bool{}, map[string]string{}
		if err := associatedDescriptor(first, descriptors, locators); err != nil {
			t.Fatal(err)
		}
		if err := associatedDescriptor(second, descriptors, locators); (err == nil) != (uri != "urn:example:payload") {
			t.Errorf("locator %q reused for different byte claims: %v", uri, err)
		}
	}
}
