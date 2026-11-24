package module_test

import (
	"bytes"
	"crypto/ed25519"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/authoring"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
	"github.com/OpenRAE/rae/implementations/go/sdl/module"
)

func TestPublicationIsDeterministicSignedAndRecoverable(t *testing.T) {
	parser, err := authoring.New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	seed := bytes.Repeat([]byte{42}, ed25519.SeedSize)
	key := ed25519.NewKeyFromSeed(seed)
	encoded, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	private := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: encoded})
	policy := module.DefaultPolicy()
	policy.Registries["example.test"] = module.RegistryTrust{RequireSignatures: true, TrustedSigners: map[string]string{"local-test": base64.StdEncoding.EncodeToString(key[ed25519.SeedSize:])}}
	registry, err := module.NewRegistry(t.TempDir(), policy, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = registry.Close() })
	files := fstest.MapFS{"module.yaml": {Data: []byte("name: shared\nmodule: {id: example/shared, version: 1.0.0, exports: {nodes: [host]}}\nnodes: {host: {type: compute}}\n")}}
	output := filepath.Join(t.TempDir(), "layout")
	first, err := registry.Publish(t.Context(), files, "module.yaml", output, "local-test", private, parser)
	if err != nil {
		t.Fatal(err)
	}
	expectedSlot := filepath.Join(output, "example_shared-1.0.0.oci")
	if filepath.Dir(filepath.Dir(first.LayoutDir)) != expectedSlot || filepath.Base(filepath.Dir(first.LayoutDir)) != "versions" {
		t.Fatal("publication changed the established layout slot")
	}
	second, err := registry.Publish(t.Context(), files, "module.yaml", output, "local-test", private, parser)
	if err != nil {
		t.Fatal(err)
	}
	if first != second {
		t.Fatal("unchanged publication was not reused deterministically")
	}
	read := publicationReader(t, first.LayoutDir)
	manifest := read(first.ManifestDigest)
	var content struct {
		Config struct {
			Digest string `json:"digest"`
		} `json:"config"`
	}
	if err = json.Unmarshal(manifest, &content); err != nil {
		t.Fatal(err)
	}
	artifact := module.Artifact{Manifest: manifest, Config: read(content.Config.Digest), Bundle: read(first.ContentDigest)}
	if _, err = registry.Verify(t.Context(), "example.test", artifact); err != nil {
		t.Fatal(err)
	}
	if err = os.Remove(filepath.Join(expectedSlot, ".raes-current")); err != nil {
		t.Fatal(err)
	}
	recovered, err := registry.Publish(t.Context(), files, "module.yaml", output, "local-test", private, parser)
	if err != nil || recovered != first {
		t.Fatal("valid publication orphan was not recovered", err)
	}
	files["module.yaml"].Data = []byte("name: root\nmodule: {id: example/root, version: 1.0.0}\nimports: [{path: missing.yaml, namespace: bad}]\n")
	if _, err = registry.Publish(t.Context(), files, "module.yaml", output, "local-test", private, parser); err == nil {
		t.Fatal("publisher bypassed composition validation")
	}
}

func publicationReader(t *testing.T, directory string) func(string) []byte {
	t.Helper()
	return func(hash string) []byte {
		t.Helper()
		raw, err := fs.ReadFile(os.DirFS(directory), "blobs/sha256/"+strings.TrimPrefix(hash, "sha256:"))
		if err != nil {
			t.Fatal(err)
		}
		return raw
	}
}
