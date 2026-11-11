package module

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func TestHTTPResponseBoundsAndCancellation(t *testing.T) {
	for _, row := range []struct {
		name, body, length string
		status             int
		valid              bool
	}{
		{"exact", "xx", "", 200, true}, {"too-large", "xxx", "", 200, false}, {"stream-too-large", "xxx", "chunked", 200, false},
		{"declared-too-large", "xx", "20", 200, false}, {"invalid-length", "xx", "bad", 200, false},
		{"negative-length", "xx", "-1", 200, false}, {"status", "xx", "", 403, false},
	} {
		t.Run(row.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				writeHTTPResponseForTest(t, w, row.length, row.body, row.status)
			}))
			defer server.Close()
			raw, err := fetch(t.Context(), server.Client(), server.URL, 2)
			if (err == nil) != row.valid || row.valid && string(raw) != row.body {
				t.Fatalf("response=%q, %v; valid=%v", raw, err, row.valid)
			}
		})
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if _, err := fetch(ctx, http.DefaultClient, "http://127.0.0.1:1", 2); !errors.Is(err, context.Canceled) {
		t.Fatalf("canceled transport=%v", err)
	}
}
func TestRegistryRedirectCannotChangeAuthority(t *testing.T) {
	var calls atomic.Int64
	other := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { calls.Add(1); _, _ = w.Write([]byte("x")) }))
	defer other.Close()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/local":
			http.Redirect(w, r, "/ok", http.StatusFound)
		case "/remote":
			http.Redirect(w, r, other.URL, http.StatusFound)
		default:
			_, _ = w.Write([]byte("x"))
		}
	}))
	defer server.Close()
	host := strings.TrimPrefix(server.URL, "http://")
	client, transport, err := registryClient("http", host)
	if err != nil {
		t.Fatal(err)
	}
	defer transport.CloseIdleConnections()
	if raw, fetchErr := fetch(t.Context(), client, server.URL+"/local", 10); fetchErr != nil || string(raw) != "x" {
		t.Fatalf("same-authority redirect=%q, %v", raw, fetchErr)
	}
	if _, err = fetch(t.Context(), client, server.URL+"/remote", 10); err == nil || calls.Load() != 0 {
		t.Fatal("redirect acquired a different registry authority")
	}
	if client.Timeout != 30*time.Second {
		t.Fatal("registry request timeout is unbounded")
	}
}

func moduleHTTPFixture(t *testing.T, fixture moduleReference) (string, *atomic.Int64) {
	t.Helper()
	tags := &atomic.Int64{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/v2/example/shared/tags/list":
			tags.Add(1)
			_, _ = w.Write([]byte(`{"tags":["1.0.0","2.0.0"]}`))
		case "/v2/example/shared/manifests/1.0.0", "/v2/example/shared/manifests/2.0.0", "/v2/example/shared/manifests/" + digest.SHA256(fixture.Artifact.Manifest):
			_, _ = w.Write(fixture.Artifact.Manifest)
		case "/v2/example/shared/blobs/" + digest.SHA256(fixture.Artifact.Config):
			_, _ = w.Write(fixture.Artifact.Config)
		case "/v2/example/shared/blobs/" + digest.SHA256(fixture.Artifact.Bundle):
			_, _ = w.Write(fixture.Artifact.Bundle)
		default:
			http.NotFound(w, r)
		}
	}))
	t.Cleanup(server.Close)
	return strings.TrimPrefix(server.URL, "http://"), tags
}
func httpFixtureRegistry(t *testing.T, fixture moduleReference, host string, observer TrustPolicy) *Registry {
	t.Helper()
	policy := DefaultPolicy()
	policy.Registries[host] = RegistryTrust{RequireSignatures: true, TrustedSigners: map[string]string{"test-signer": fixture.PublicKey}}
	registry, err := NewRegistry(t.TempDir(), policy, observer)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = registry.Close() })
	return registry
}
func TestLockedResolutionUsesExactManifestAndRequestFacts(t *testing.T) {
	fixture := readModuleReference(t)
	host, tags := moduleHTTPFixture(t, fixture)
	observer := &observedTrust{}
	registry := httpFixtureRegistry(t, fixture, host, observer)
	admitted, err := registry.Verify(t.Context(), host, fixture.Artifact.artifact())
	if err != nil {
		t.Fatal(err)
	}
	record := admitted.Record()
	record.Source = "oci:" + host + "/example/shared"
	record.RequestedVersion = "1.0.0"
	resolved, err := registry.ResolveLocked(t.Context(), record)
	if err != nil {
		t.Fatal(err)
	}
	if tags.Load() != 0 || resolved.Record().ManifestDigest != record.ManifestDigest {
		t.Fatal("locked resolution followed tags")
	}
	facts := observer.facts.Record
	if facts.Source != record.Source || facts.RequestedVersion != record.RequestedVersion || facts.ResolvedSource != host+"/example/shared@"+record.ManifestDigest {
		t.Fatalf("callback lost request facts: %+v", facts)
	}
}
func TestRejectedResolutionDoesNotPublishCache(t *testing.T) {
	fixture := readModuleReference(t)
	host, _ := moduleHTTPFixture(t, fixture)
	for _, kind := range []string{"version", "pin", "locked-identity", "locked-exports"} {
		t.Run(kind, func(t *testing.T) {
			observer := &observedTrust{}
			registry := httpFixtureRegistry(t, fixture, host, observer)
			source := "oci:" + host + "/example/shared"
			record := LockRecord{Source: source, RequestedVersion: "1.0.0", ManifestDigest: digest.SHA256(fixture.Artifact.Manifest), ContentDigest: digest.SHA256(fixture.Artifact.Bundle), ModuleID: "example/shared", ExportHash: strings.TrimPrefix(digest.SHA256([]byte(`{"nodes":["host"]}`)), "sha256:")}
			var err error
			switch kind {
			case "version":
				_, err = registry.Resolve(t.Context(), source, "2.0.0", "")
			case "pin":
				_, err = registry.Resolve(t.Context(), source, "1.0.0", "sha256:"+strings.Repeat("0", 64))
			case "locked-identity":
				record.ModuleID = "wrong"
				_, err = registry.ResolveLocked(t.Context(), record)
			case "locked-exports":
				record.ExportHash = "wrong"
				_, err = registry.ResolveLocked(t.Context(), record)
			}
			if err == nil {
				t.Fatal("mismatched requested module admitted")
			}
			entries, readErr := os.ReadDir(registry.directory)
			if readErr != nil || len(entries) != 0 || observer.calls != 0 {
				t.Fatal("rejected request reached cache publication or admission callback")
			}
		})
	}
}

func writeRawLengthResponse(t *testing.T, w http.ResponseWriter, length, body string) {
	t.Helper()
	hijacker, ok := w.(http.Hijacker)
	if !ok {
		t.Error("test server cannot write an exact wire response")
		return
	}
	connection, buffer, err := hijacker.Hijack()
	if err != nil {
		t.Error(err)
		return
	}
	defer func() { _ = connection.Close() }()
	if _, err = buffer.WriteString("HTTP/1.1 200 OK\r\nContent-Length: " + length + "\r\nConnection: close\r\n\r\n" + body); err != nil {
		t.Error(err)
		return
	}
	if err = buffer.Flush(); err != nil {
		t.Error(err)
	}
}

func writeHTTPResponseForTest(t *testing.T, w http.ResponseWriter, length, body string, status int) {
	t.Helper()
	if length == "bad" || length == "-1" {
		writeRawLengthResponse(t, w, length, body)
		return
	}
	if length == "chunked" {
		w.Header().Set("Transfer-Encoding", "chunked")
	} else if length != "" {
		w.Header().Set("Content-Length", length) //nolint:gosec // The exclusive branches select one framing header for each test response.
	}
	w.WriteHeader(status)
	_, _ = w.Write([]byte(body))
}
