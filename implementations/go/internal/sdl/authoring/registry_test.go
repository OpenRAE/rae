package authoring

import (
	"encoding/json"
	"io/fs"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
	"github.com/OpenRAE/rae/implementations/go/sdl/module"
)

func TestCompositionUsesVerifiedRegistrySources(t *testing.T) {
	for _, fixture := range []string{"python-signed.json", "python-signed-graph.json"} {
		t.Run(fixture, func(t *testing.T) { checkVerifiedRegistrySources(t, fixture) })
	}
}
func checkVerifiedRegistrySources(t *testing.T, fixtureName string) {
	t.Helper()
	var fixture struct {
		PublicKey string `json:"public_key"`
		Artifact  struct {
			Manifest []byte `json:"manifest"`
			Config   []byte `json:"config"`
			Bundle   []byte `json:"bundle"`
		} `json:"artifact"`
		Sources map[string][]byte `json:"sources"`
	}
	raw, err := fs.ReadFile(os.DirFS("../../../sdl/module/testdata"), fixtureName)
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/v2/example/shared/tags/list":
			_, _ = w.Write([]byte(`{"tags":["1.0.0"]}`))
		case "/v2/example/shared/manifests/1.0.0":
			_, _ = w.Write(fixture.Artifact.Manifest)
		case "/v2/example/shared/blobs/" + digest.SHA256(fixture.Artifact.Config):
			_, _ = w.Write(fixture.Artifact.Config)
		case "/v2/example/shared/blobs/" + digest.SHA256(fixture.Artifact.Bundle):
			_, _ = w.Write(fixture.Artifact.Bundle)
		default:
			http.NotFound(w, request)
		}
	}))
	defer server.Close()
	host := strings.TrimPrefix(server.URL, "http://")
	policy := module.DefaultPolicy()
	policy.Registries[host] = module.RegistryTrust{RequireSignatures: true, TrustedSigners: map[string]string{"test-signer": fixture.PublicKey}}
	registry, err := module.NewRegistry(t.TempDir(), policy, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = registry.Close() })
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	input := []byte("name: root\nimports: [{source: 'oci:" + host + "/example/shared', namespace: lib}]\n")
	document, err := parser.Decode(Request{Source: input, Name: "main.yaml", FS: fstest.MapFS{}, Registry: registry})
	if err != nil {
		t.Fatal(err)
	}
	family, err := parser.AdmitFamily(document)
	if err != nil {
		t.Fatal(err)
	}
	var expanded map[string]any
	if err = json.Unmarshal(family.JSON(), &expanded); err != nil {
		t.Fatal(err)
	}
	if object(expanded[nodesSection])["lib.host"] == nil {
		t.Fatalf("verified source was not composed: %s", family.JSON())
	}
	assertRegistryProvenance(t, expanded, fixture.Artifact.Manifest, len(fixture.Sources))
	if _, err = parser.Decode(Request{Source: input, Name: "main.yaml", FS: fstest.MapFS{}}); err == nil {
		t.Fatal("remote import acquired ambient network authority")
	}
	if _, err = parser.Decode(Request{Source: input, Name: "main.yaml", Sources: map[string][]byte{"main.yaml": input}, Registry: registry}); err == nil {
		t.Fatal("supplied-source mode acquired registry authority")
	}
}

func assertRegistryProvenance(t *testing.T, expanded map[string]any, manifest []byte, sources int) {
	t.Helper()
	imports := array(object(expanded["expansion_provenance"])["imports"])
	remote := 0
	for _, raw := range imports {
		if object(raw)["manifest_digest"] == digest.SHA256(manifest) && object(raw)["signer_id"] == "test-signer" {
			remote++
		}
	}
	if len(imports) != max(1, sources) || remote != 1 {
		t.Fatal("verified module facts were not retained")
	}
}
