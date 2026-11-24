package module

import (
	"encoding/json"
	"os"
	"testing"
)

type artifactReference struct {
	Manifest []byte `json:"manifest"`
	Config   []byte `json:"config"`
	Bundle   []byte `json:"bundle"`
}

func (f artifactReference) artifact() Artifact {
	return Artifact(f)
}

type moduleReference struct {
	PublicKey string            `json:"public_key"`
	Root      string            `json:"root"`
	Source    []byte            `json:"source"`
	Sources   map[string][]byte `json:"sources"`
	Artifact  artifactReference `json:"artifact"`
}

func readModuleReference(t *testing.T) moduleReference {
	t.Helper()
	raw, err := os.ReadFile("testdata/python-signed.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture moduleReference
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	return fixture
}

func referenceRegistry(t *testing.T, fixture moduleReference) *Registry {
	t.Helper()
	policy := DefaultPolicy()
	policy.Registries["registry.example"] = RegistryTrust{RequireSignatures: true, TrustedSigners: map[string]string{"test-signer": fixture.PublicKey}}
	registry, err := NewRegistry(t.TempDir(), policy, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := registry.Close(); err != nil {
			t.Error(err)
		}
	})
	return registry
}
