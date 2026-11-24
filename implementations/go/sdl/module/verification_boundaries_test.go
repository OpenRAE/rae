package module

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func rebindConfig(t *testing.T, original Artifact, change func(map[string]any)) Artifact {
	t.Helper()
	var config map[string]any
	if err := json.Unmarshal(original.Config, &config); err != nil {
		t.Fatal(err)
	}
	change(config)
	raw, err := json.Marshal(config)
	if err != nil {
		t.Fatal(err)
	}
	var manifest ociManifest
	if err = json.Unmarshal(original.Manifest, &manifest); err != nil {
		t.Fatal(err)
	}
	manifest.Config.Digest = digest.SHA256(raw)
	manifest.Config.Size = int64(len(raw))
	encoded, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	return Artifact{Manifest: encoded, Config: raw, Bundle: bytes.Clone(original.Bundle)}
}
func TestSignatureBindsPublishedCoordinates(t *testing.T) {
	fixture := readModuleReference(t)
	registry := referenceRegistry(t, fixture)
	for _, row := range []struct {
		name   string
		change func(map[string]any)
	}{
		{"different-root", func(c map[string]any) { c[termRootFile] = "other.yaml" }},
		{"empty-root", func(c map[string]any) { c[termRootFile] = "" }},
		{"escaping-root", func(c map[string]any) { c[termRootFile] = "../module.yaml" }},
		{"non-string-root", func(c map[string]any) { c[termRootFile] = 12 }},
		{"null-root", func(c map[string]any) { c[termRootFile] = nil }},
		{"identity", func(c map[string]any) { object(c["module"])["id"] = "other/module" }},
		{"version", func(c map[string]any) { object(c["module"])["version"] = "2.0.0" }},
		{"exports", func(c map[string]any) { object(c["module"])["exports"] = map[string]any{} }},
		{"unsigned", func(c map[string]any) { delete(c, "signatures") }},
		{"non-object-signature", func(c map[string]any) { c["signatures"] = []any{"bad"} }},
	} {
		t.Run(row.name, func(t *testing.T) {
			artifact := rebindConfig(t, fixture.Artifact.artifact(), row.change)
			if bundle, err := registry.Verify(t.Context(), "registry.example", artifact); err == nil || bundle != nil {
				t.Fatal("changed signed coordinates acquired module authority")
			}
		})
	}
}
func TestSignatureEncodingAndUnsignedPolicy(t *testing.T) {
	fixture := readModuleReference(t)
	fixture.PublicKey = " \t" + fixture.PublicKey + "====!"
	registry := referenceRegistry(t, fixture)
	artifact := rebindConfig(t, fixture.Artifact.artifact(), func(c map[string]any) {
		signatures, _ := c["signatures"].([]any)
		entry := object(signatures[0])
		entry["signature"] = "\t" + text(entry["signature"]) + "=====!"
	})
	if _, err := registry.Verify(t.Context(), "registry.example", artifact); err != nil {
		t.Fatalf("reference base64 encoding rejected: %v", err)
	}
	policy := DefaultPolicy()
	policy.Registries["registry.example"] = RegistryTrust{RequireSignatures: false}
	unsigned, err := NewRegistry(t.TempDir(), policy, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = unsigned.Close() })
	artifact = rebindConfig(t, fixture.Artifact.artifact(), func(c map[string]any) { c["signatures"] = true })
	if _, err = unsigned.Verify(t.Context(), "registry.example", artifact); err != nil {
		t.Fatalf("unsigned policy rejected unused signature metadata: %v", err)
	}
}

type observedTrust struct {
	calls   int
	facts   VerificationFacts
	refusal error
}

func (o *observedTrust) AdmitModule(ctx context.Context, facts VerificationFacts) error {
	o.calls++
	o.facts = facts
	if err := ctx.Err(); err != nil {
		return err
	}
	return o.refusal
}
func TestTrustCallbackOnlyNarrowsNativeAdmission(t *testing.T) {
	fixture := readModuleReference(t)
	policy := DefaultPolicy()
	policy.Registries["registry.example"] = RegistryTrust{RequireSignatures: true, TrustedSigners: map[string]string{"test-signer": fixture.PublicKey}}
	observer := &observedTrust{}
	registry, err := NewRegistry(t.TempDir(), policy, observer)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = registry.Close() })
	// Mutating the caller's policy cannot broaden or remove captured authority.
	delete(policy.Registries, "registry.example")
	if _, err = registry.Verify(t.Context(), "registry.example", fixture.Artifact.artifact()); err != nil {
		t.Fatal(err)
	}
	if observer.calls != 1 || !observer.facts.SignatureVerified || !observer.facts.ManifestVerified || !observer.facts.ContentVerified || !observer.facts.ExportsVerified {
		t.Fatal("callback did not receive verified facts")
	}
	changed := rebindConfig(t, fixture.Artifact.artifact(), func(c map[string]any) { c[termRootFile] = "other.yaml" })
	for _, row := range []struct {
		registry string
		artifact Artifact
	}{{"untrusted.example", fixture.Artifact.artifact()}, {"registry.example", changed}} {
		if result, verifyErr := registry.Verify(t.Context(), row.registry, row.artifact); verifyErr == nil || result != nil {
			t.Fatal("callback minted native verification authority")
		}
	}
	if observer.calls != 1 {
		t.Fatal("unverified input reached callback")
	}
	observer.refusal = errors.New("private policy reason")
	if _, err = registry.Verify(t.Context(), "registry.example", fixture.Artifact.artifact()); err == nil {
		t.Fatal("callback refusal ignored")
	}
	if category, _ := fault.CategoryOf(err); category != fault.Authorization || strings.Contains(err.Error(), "private policy reason") {
		t.Fatal("policy refusal lost its value-free category")
	}
}

func TestSignatureCandidateFailureKeepsValidAlternative(t *testing.T) {
	fixture := readModuleReference(t)
	registry := referenceRegistry(t, fixture)
	for _, candidate := range []any{
		map[string]any{"signer_id": "unknown", "signature": "invalid"},
		map[string]any{"signer_id": "test-signer", "signature": "invalid"},
		map[string]any{"signer_id": "test-signer", "signature": true},
		map[string]any{},
	} {
		artifact := rebindConfig(t, fixture.Artifact.artifact(), func(c map[string]any) {
			prior, _ := c["signatures"].([]any)
			c["signatures"] = append([]any{candidate}, prior...)
		})
		if _, err := registry.Verify(t.Context(), "registry.example", artifact); err != nil {
			t.Fatalf("invalid candidate hid the valid trusted signature: %v", err)
		}
	}
}
func TestOCIMetadataRefusesInvalidUTF8(t *testing.T) {
	fixture := readModuleReference(t)
	registry := referenceRegistry(t, fixture)
	for _, raw := range [][]byte{fixture.Artifact.Manifest, fixture.Artifact.Config} {
		encoded := bytes.TrimSpace(raw)
		changed := append(bytes.Clone(encoded[:len(encoded)-1]), []byte(",\"unused\":\"")...)
		changed = append(changed, 0xff)
		changed = append(changed, []byte("\"}")...)
		if _, _, err := registry.readManifest(changed); err == nil {
			t.Fatal("invalid UTF-8 manifest was normalized")
		}
		if _, err := registry.decodeModuleConfig(changed); err == nil {
			t.Fatal("invalid UTF-8 config was normalized")
		}
	}
}
