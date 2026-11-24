package module

import (
	"bytes"
	"testing"
)

func TestRegistryVerifiesPythonSignedArtifact(t *testing.T) {
	fixture := readModuleReference(t)

	registry := referenceRegistry(t, fixture)
	bundle, err := registry.Verify(t.Context(), "registry.example", fixture.Artifact.artifact())
	if err != nil {
		t.Fatal(err)
	}
	if bundle.RootFile() != fixture.Root || !bytes.Equal(bundle.Sources()[fixture.Root], fixture.Source) || bundle.Record().SignerID != "test-signer" {
		t.Fatal("Python-signed module did not retain verified source and signer facts")
	}
	if len(bundle.Record().ExportHash) != 64 {
		t.Fatal("lock export hash must retain the Python hex profile")
	}
	captured := bundle.Sources()
	clear(captured[fixture.Root])
	if !bytes.Equal(bundle.Sources()[fixture.Root], fixture.Source) {
		t.Fatal("caller mutation changed verified sources")
	}
	for _, field := range []string{"manifest", "config", "bundle"} {
		t.Run(field, func(t *testing.T) {
			changed := fixture.Artifact.artifact()
			switch field {
			case "manifest":
				changed.Manifest = append(bytes.Clone(changed.Manifest), 'x')
			case "config":
				changed.Config = append(bytes.Clone(changed.Config), 'x')
			case "bundle":
				changed.Bundle = append(bytes.Clone(changed.Bundle), 'x')
			}
			if result, err := registry.Verify(t.Context(), "registry.example", changed); result != nil || err == nil {
				t.Fatal("changed OCI bytes retained verified authority")
			}
		})
	}
	if result, err := registry.Verify(t.Context(), "untrusted.example", fixture.Artifact.artifact()); result != nil || err == nil {
		t.Fatal("a supplied module bypassed the registry allowlist")
	}
}
