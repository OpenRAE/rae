package admission

import (
	"io"
	"math"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// The reference associated_artifact_set_digest returned this value for the
// manifest below, which omits satisfies_refs and uses an upper-case checksum.
const associatedReferenceSetDigest = "sha256:3775b1d2a5b9794700f62aadfdb17f15756a4eb0266540047c789114b725acdd"

func associatedPublicManifest(setDigest string) []byte {
	return []byte(`{"schema_version":"associated-artifact-manifest/v1","manifest_id":"set","manifest_version":"1","canonicalization_profile":"associated-artifact-set/v1","scope":"scenario","parent_ref":{"ref_kind":"scenario","ref_id":"scenario"},"artifacts":{"file":{"artifact_id":"file","role":"other","media_type":"text/plain","uri":"urn:example:payload","checksum":{"algorithm":"sha256","value":"BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD"},"size_bytes":3,"created_at":"2026-01-01T00:00:00Z","source":"test","sensitivity":"public"}},"set_digest":"` + setDigest + `"}`)
}

func TestAssociatedManifestOperations(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 1048576, MaxDepth: 64}
	manifest, err := LoadAssociatedManifest(e, associatedPublicManifest(associatedReferenceSetDigest), limits)
	if err != nil {
		t.Fatal(err)
	}
	if parent, ok := manifest.ParentRef.Value(); !ok || !parent.RefVersion.Null() {
		t.Error("LoadAssociatedManifest did not apply the published null default")
	}
	got, err := AssociatedArtifactSetDigest(manifest)
	if err != nil || got != associatedReferenceSetDigest {
		t.Fatalf("AssociatedArtifactSetDigest() = %q, %v, want the reference digest", got, err)
	}
	parent, err := e.low.Validate("sdl-authoring-input-v1", []byte(`{"name":"scenario","version":"1.0.0"}`), limits, nil)
	if err != nil {
		t.Fatal(err)
	}
	context := associatedTestContext{parent: parent, payloads: map[string]io.Reader{"file": strings.NewReader("ignored")}}
	admitted, err := ValidateAssociatedManifest(e, manifest, context, map[string]io.Reader{"file": strings.NewReader("abc")}, DefaultAssociatedArtifactLimits())
	if err != nil || admitted.ContractID() != termAssociatedArtifactManifestV1 {
		t.Fatalf("ValidateAssociatedManifest() = %q, %v, want admission", admitted.ContractID(), err)
	}
	for _, tc := range []struct {
		name    string
		parent  AssociatedArtifactsContext
		payload string
		limits  AssociatedArtifactLimits
	}{
		{"substituted bytes", context, "abd", DefaultAssociatedArtifactLimits()},
		{"missing parent", nil, "abc", DefaultAssociatedArtifactLimits()},
		{"no artifacts allowed", context, "abc", AssociatedArtifactLimits{MaxArtifacts: 0, MaxTotalBytes: 3, MaxArtifactBytes: 3}},
		{"artifact bytes", context, "abc", AssociatedArtifactLimits{MaxArtifacts: 1, MaxTotalBytes: 3, MaxArtifactBytes: 2}},
		{"total bytes", context, "abc", AssociatedArtifactLimits{MaxArtifacts: 1, MaxTotalBytes: 2, MaxArtifactBytes: 3}},
		{"negative total", context, "abc", AssociatedArtifactLimits{MaxArtifacts: 1, MaxTotalBytes: -1, MaxArtifactBytes: 3}},
		{"negative artifact", context, "abc", AssociatedArtifactLimits{MaxArtifacts: 1, MaxTotalBytes: 3, MaxArtifactBytes: -1}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			readers := map[string]io.Reader{"file": strings.NewReader(tc.payload)}
			if got, err := ValidateAssociatedManifest(e, manifest, tc.parent, readers, tc.limits); err == nil || got.ContractID() != "" {
				t.Errorf("ValidateAssociatedManifest() = %q, %v, want refusal", got.ContractID(), err)
			}
		})
	}
	exact := AssociatedArtifactLimits{MaxArtifacts: 1, MaxTotalBytes: 3, MaxArtifactBytes: 3}
	if _, err := ValidateAssociatedManifest(e, manifest, context, map[string]io.Reader{"file": strings.NewReader("abc")}, exact); err != nil {
		t.Errorf("ValidateAssociatedManifest(inclusive limits) = %v", err)
	}
}

func TestAssociatedManifestLoadingRefusesInvalidInput(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 1048576, MaxDepth: 64}
	for name, data := range map[string][]byte{
		"schema":    []byte(`{"schema_version":"associated-artifact-manifest/v1"}`),
		"duplicate": []byte(`{"manifest_id":"a","manifest_id":"b"}`),
		"bytes":     associatedPublicManifest(associatedReferenceSetDigest)[:64],
	} {
		if _, err := LoadAssociatedManifest(e, data, limits); err == nil {
			t.Errorf("LoadAssociatedManifest(%s) = nil, want refusal", name)
		}
	}
	if _, err := LoadAssociatedManifest(e, associatedPublicManifest(associatedReferenceSetDigest), ingress.Limits{MaxBytes: 64, MaxDepth: 64}); err == nil {
		t.Error("LoadAssociatedManifest ignored the byte limit")
	}
	stale, err := LoadAssociatedManifest(e, associatedPublicManifest("sha256:"+strings.Repeat("a", 64)), limits)
	if err != nil {
		t.Fatal(err)
	}
	parent, err := e.low.Validate("sdl-authoring-input-v1", []byte(`{"name":"scenario","version":"1.0.0"}`), limits, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ValidateAssociatedManifest(e, stale, associatedTestContext{parent: parent}, map[string]io.Reader{"file": strings.NewReader("abc")}, DefaultAssociatedArtifactLimits()); err == nil {
		t.Error("ValidateAssociatedManifest accepted a stale set digest")
	}
}

func TestDefaultAssociatedArtifactLimits(t *testing.T) {
	want := AssociatedArtifactLimits{MaxArtifacts: 1024, MaxTotalBytes: min(4<<30, math.MaxInt), MaxArtifactBytes: min(1<<30, math.MaxInt)}
	if got := DefaultAssociatedArtifactLimits(); got != want {
		t.Errorf("DefaultAssociatedArtifactLimits() = %+v, want %+v", got, want)
	}
}
