package module

import (
	"encoding/json"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func TestOCILockAcceptsDeclaredParameters(t *testing.T) {
	fixture := parameterizedLockReference(t)
	host, _ := moduleHTTPFixture(t, fixture)
	registry := httpFixtureRegistry(t, fixture, host, nil)
	rule := registry.policy.Registries[host]
	rule.RequireSignatures = false
	registry.policy.Registries[host] = rule
	files := fstest.MapFS{"main.yaml": {Data: []byte("name: root\nimports: [{source: 'oci:" + host + "/example/shared', namespace: lib, version: '1.0.0', parameters: {declared: value}}]\n")}}
	lock, err := registry.ResolveLock(t.Context(), files, "main.yaml")
	if err != nil || len(lock.Imports) != 1 {
		t.Fatalf("declared OCI parameter was refused: %v", err)
	}
}

func parameterizedLockReference(t *testing.T) moduleReference {
	t.Helper()
	fixture := readModuleReference(t)
	fixture.Source = []byte("name: shared\nmodule: {id: example/shared, version: 1.0.0, exports: {nodes: [host]}, parameters: [declared]}\nvariables: {declared: {type: string, default: value}}\nnodes: {host: {type: compute}}\n")
	bundle, err := buildBundle(map[string][]byte{fixture.Root: fixture.Source}, defaultResourceLimits())
	if err != nil {
		t.Fatal(err)
	}
	var manifest ociManifest
	if err = json.Unmarshal(fixture.Artifact.Manifest, &manifest); err != nil {
		t.Fatal(err)
	}
	manifest.Layers[0].Digest, manifest.Layers[0].Size = digest.SHA256(bundle), int64(len(bundle))
	raw, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	artifact := rebindConfig(t, Artifact{Manifest: raw, Config: fixture.Artifact.Config, Bundle: bundle}, func(c map[string]any) {
		object(c["module"])["parameters"] = []string{"declared"}
		c["signatures"] = []any{}
	})
	fixture.Artifact = artifactReference(artifact)
	return fixture
}

func TestOCILockRejectsUndeclaredParameters(t *testing.T) {
	fixture := readModuleReference(t)
	host, _ := moduleHTTPFixture(t, fixture)
	registry := httpFixtureRegistry(t, fixture, host, nil)
	for _, parameters := range []string{"{}", "{undeclared: value}"} {
		files := fstest.MapFS{"main.yaml": {Data: []byte("name: root\nimports: [{source: 'oci:" + host + "/example/shared', namespace: lib, version: '1.0.0', parameters: " + parameters + "}]\n")}}
		lock, err := registry.ResolveLock(t.Context(), files, "main.yaml")
		if parameters == "{}" {
			if err != nil || len(lock.Imports) != 1 {
				t.Fatalf("valid OCI import failed: %v", err)
			}
		} else if err == nil || len(lock.Imports) != 0 {
			t.Fatal("OCI lock accepted undeclared parameters")
		}
	}
}

func TestLockDecoderAndLocalResolution(t *testing.T) {
	for _, raw := range []string{`{"imports":[],"imports":[]}`, `{"schema_version":"other"}`, `{"extra":1}`, `{"imports":[{}]}`} {
		if _, err := DecodeLockfile([]byte(raw)); err == nil {
			t.Fatal("invalid lock accepted")
		}
	}
	files := fstest.MapFS{"main.yaml": {Data: []byte("name: root\nimports: [{path: child.yaml, namespace: child}]\n")}, "child.yaml": {Data: []byte("name: child\nmodule: {id: example/child, version: 1.0.0, exports: {}}\n")}}
	lock, err := ResolveLock(t.Context(), files, "main.yaml", DefaultPolicy())
	if err != nil {
		t.Fatal(err)
	}
	if len(lock.Imports) != 1 || lock.Imports[0].Source != "local:child.yaml" || lock.Imports[0].ModuleID != "example/child" || lock.Imports[0].RequestedVersion != "*" || len(lock.Imports[0].ExportHash) != 64 {
		t.Fatal("local lock facts differ")
	}
	policy := DefaultPolicy()
	policy.AllowUnsignedLocalSources = false
	if _, err = ResolveLock(t.Context(), files, "main.yaml", policy); err == nil {
		t.Fatal("local trust refusal ignored")
	}
}
