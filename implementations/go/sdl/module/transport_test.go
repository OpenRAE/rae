package module

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func TestRegistryFetchesOnlyAuthorizedBoundedArtifacts(t *testing.T) {
	fixture := readModuleReference(t)
	var requests atomic.Int64
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		requests.Add(1)
		switch request.URL.Path {
		case "/v2/example/shared/tags/list":
			_, _ = w.Write([]byte(`{"tags":["0.1.0","1.0.0","invalid"]}`))
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

	policy := DefaultPolicy()
	policy.Registries[host] = RegistryTrust{RequireSignatures: true, TrustedSigners: map[string]string{"test-signer": fixture.PublicKey}}
	registry, err := NewRegistry(t.TempDir(), policy, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = registry.Close() })
	bundle, err := registry.Resolve(t.Context(), "oci:"+host+"/example/shared", ">=1.0,<2", digest.SHA256(fixture.Artifact.Bundle))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasSuffix(bundle.Record().ResolvedSource, "@"+digest.SHA256(fixture.Artifact.Manifest)) || requests.Load() != 4 {
		t.Fatal("resolution did not bind distinct OCI facts")
	}
	before := requests.Load()
	for _, source := range []string{"oci:untrusted.example/a", "oci:" + host + "/../a", "oci:" + host + "/a?x=y"} {
		if _, err = registry.Resolve(t.Context(), source, "*", ""); err == nil {
			t.Fatal("unauthorized or malformed source accepted")
		}
	}
	if requests.Load() != before {
		t.Fatal("invalid source fetched before admission")
	}
	registry.limits.metadataBytes = 10
	if _, err = registry.Resolve(t.Context(), "oci:"+host+"/example/shared", "*", ""); err == nil {
		t.Fatal("oversized metadata accepted")
	}
}
